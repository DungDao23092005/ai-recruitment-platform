from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    EntityNotFoundException,
    InvalidTransitionException,
)
from app.domain.enums import ApplicationStatus, InterviewStatus, InterviewType
from app.domain.models import Application as DomainApplication
from app.domain.models.base import DomainException
from app.models import Application, Interview, Job, User
from app.repositories import ApplicationRepository, InterviewRepository
from app.schemas.interview import InterviewCreate, InterviewRead, InterviewUpdate
from app.services.job_service import JobService


class InterviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.interviews = InterviewRepository(session, Interview)
        self.applications = ApplicationRepository(session, Application)

    async def schedule_interview(
        self,
        current_user: User,
        application_id: uuid.UUID,
        data: InterviewCreate,
    ) -> InterviewRead:
        """Schedule a new interview for an application.

        Recruiter/admin only. Ownership is enforced via JobService.
        Validates scheduled_at is not in the past.
        Transitions application to INTERVIEWING if not already in that state.
        """
        # Validate scheduled_at is not in the past
        if data.scheduled_at < datetime.now(timezone.utc):
            raise InvalidTransitionException(
                "Interview cannot be scheduled in the past"
            )

        application = await self.applications.get_by_id(application_id)
        if application is None:
            raise EntityNotFoundException(f"Application {application_id} not found")

        # Verify ownership
        try:
            await JobService(self.session).get_recruiter_job_by_id(
                current_user,
                application.job_id,
            )
        except EntityNotFoundException:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            ) from None

        # Create interview
        interview = Interview(
            application_id=application_id,
            scheduled_at=data.scheduled_at,
            duration_minutes=data.duration_minutes,
            interview_type=InterviewType(data.interview_type),
            meeting_url=str(data.meeting_url) if data.meeting_url else None,
            location=data.location,
            notes=data.notes,
            status=InterviewStatus.SCHEDULED,
        )
        self.session.add(interview)

        # Transition application to INTERVIEWING if not already
        if application.status != ApplicationStatus.INTERVIEWING:
            domain = DomainApplication(
                candidate_id=application.candidate_id,
                job_id=application.job_id,
                status=application.status,
            )
            try:
                if domain.status == ApplicationStatus.APPLIED:
                    domain.transition_to(ApplicationStatus.UNDER_REVIEW)
                if domain.status == ApplicationStatus.UNDER_REVIEW:
                    domain.transition_to(ApplicationStatus.SHORTLISTED)
                
                domain.transition_to(ApplicationStatus.INTERVIEWING)
            except DomainException as exc:
                raise InvalidTransitionException(str(exc)) from exc
            application.status = domain.status

        try:
            await self.session.commit()
            await self.session.refresh(interview)
        except Exception:
            await self.session.rollback()
            raise

        return InterviewRead.model_validate(interview)

    async def update_interview(
        self,
        current_user: User,
        interview_id: uuid.UUID,
        data: InterviewUpdate,
    ) -> InterviewRead:
        """Update an existing interview.

        Recruiter/admin only. Ownership enforced via application -> job.
        Reschedule keeps status as SCHEDULED.
        """
        interview = await self.interviews.get_by_id_with_application(interview_id)
        if interview is None:
            raise EntityNotFoundException(f"Interview {interview_id} not found")

        # Verify ownership through application -> job
        application = await self.applications.get_by_id(interview.application_id)
        if application is None:
            raise EntityNotFoundException(
                f"Application {interview.application_id} not found"
            )

        try:
            await JobService(self.session).get_recruiter_job_by_id(
                current_user,
                application.job_id,
            )
        except EntityNotFoundException:
            raise EntityNotFoundException(
                f"Interview {interview_id} not found"
            ) from None

        # Validate scheduled_at if being updated
        if data.scheduled_at is not None and data.scheduled_at < datetime.now(
            timezone.utc
        ):
            raise InvalidTransitionException(
                "Interview cannot be scheduled in the past"
            )

        # Update fields
        if data.scheduled_at is not None:
            interview.scheduled_at = data.scheduled_at
        if data.duration_minutes is not None:
            interview.duration_minutes = data.duration_minutes
        if data.interview_type is not None:
            interview.interview_type = InterviewType(data.interview_type)
        if data.meeting_url is not None:
            interview.meeting_url = str(data.meeting_url)
        if data.location is not None:
            interview.location = data.location
        if data.notes is not None:
            interview.notes = data.notes
        if data.status is not None:
            interview.status = InterviewStatus(data.status)

        try:
            await self.session.commit()
            await self.session.refresh(interview)
        except Exception:
            await self.session.rollback()
            raise

        return InterviewRead.model_validate(interview)

    async def cancel_interview(
        self,
        current_user: User,
        interview_id: uuid.UUID,
    ) -> InterviewRead:
        """Cancel an interview.

        Recruiter/admin only. Sets status to CANCELLED and soft-deletes.
        """
        interview = await self.interviews.get_by_id_with_application(interview_id)
        if interview is None:
            raise EntityNotFoundException(f"Interview {interview_id} not found")

        # Verify ownership through application -> job
        application = await self.applications.get_by_id(interview.application_id)
        if application is None:
            raise EntityNotFoundException(
                f"Application {interview.application_id} not found"
            )

        try:
            await JobService(self.session).get_recruiter_job_by_id(
                current_user,
                application.job_id,
            )
        except EntityNotFoundException:
            raise EntityNotFoundException(
                f"Interview {interview_id} not found"
            ) from None

        # Set status to CANCELLED and soft delete
        interview.status = InterviewStatus.CANCELLED
        await self.interviews.soft_delete(interview)

        try:
            await self.session.commit()
            await self.session.refresh(interview)
        except Exception:
            await self.session.rollback()
            raise

        return InterviewRead.model_validate(interview)

    async def list_interviews(
        self,
        current_user: User,
        application_id: uuid.UUID,
    ) -> list[InterviewRead]:
        """List all interviews for an application.

        Recruiter/admin only. Ownership enforced.
        """
        application = await self.applications.get_by_id(application_id)
        if application is None:
            raise EntityNotFoundException(f"Application {application_id} not found")

        try:
            await JobService(self.session).get_recruiter_job_by_id(
                current_user,
                application.job_id,
            )
        except EntityNotFoundException:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            ) from None

        interviews = await self.interviews.list_by_application(application_id)
        return [InterviewRead.model_validate(i) for i in interviews]

    async def get_interview(
        self,
        current_user: User,
        interview_id: uuid.UUID,
    ) -> InterviewRead:
        """Get a single interview by ID.

        Recruiter/admin only. Ownership enforced.
        """
        interview = await self.interviews.get_by_id_with_application(interview_id)
        if interview is None:
            raise EntityNotFoundException(f"Interview {interview_id} not found")

        # Verify ownership through application -> job
        application = await self.applications.get_by_id(interview.application_id)
        if application is None:
            raise EntityNotFoundException(
                f"Application {interview.application_id} not found"
            )

        try:
            await JobService(self.session).get_recruiter_job_by_id(
                current_user,
                application.job_id,
            )
        except EntityNotFoundException:
            raise EntityNotFoundException(
                f"Interview {interview_id} not found"
            ) from None

        return InterviewRead.model_validate(interview)