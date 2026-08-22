from __future__ import annotations

import uuid

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AIError,
    ConflictException,
    EntityNotFoundException,
    InvalidTransitionException,
)
from app.domain.enums import ApplicationStatus
from app.domain.models import Application as DomainApplication
from app.domain.models.base import DomainException
from app.models import Application, Job, Resume, User
from app.repositories import (
    ApplicationRepository,
    JobRepository,
    ResumeRepository,
)
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.ai_matching_service import AIMatchingService
from app.services.job_service import JobService
from app.services.notification_service import NotificationService
from app.services.user_service import UserService

RECRUITER_MANAGED_STATUSES = frozenset(
    {
        ApplicationStatus.UNDER_REVIEW,
        ApplicationStatus.SHORTLISTED,
        ApplicationStatus.INTERVIEWING,
        ApplicationStatus.ACCEPTED,
        ApplicationStatus.REJECTED,
    }
)


class ApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.applications = ApplicationRepository(session, Application)
        self.jobs = JobRepository(session, Job)

    async def apply_job(
        self,
        candidate_id: uuid.UUID,
        job_id: uuid.UUID,
    ) -> Application:
        job = await self.jobs.get_by_id(job_id)
        if job is None:
            raise EntityNotFoundException(f"Job {job_id} not found")

        existing = await self.applications.get_by_candidate_and_job(
            candidate_id,
            job_id,
        )
        if existing is not None:
            raise ConflictException(
                f"Candidate {candidate_id} already applied to job {job_id}"
            )

        application = Application(
            candidate_id=candidate_id,
            job_id=job_id,
        )
        self.session.add(application)
        try:
            # Notify recruiter(s) about new application BEFORE commit
            notification_service = NotificationService(self.session)
            if job.company and job.company.recruiters:
                for recruiter in job.company.recruiters:
                    if recruiter.user_id:
                        await notification_service.create_notification(
                            user_id=recruiter.user_id,
                            title="Đơn ứng tuyển mới",
                            content=f"Ứng viên đã nộp đơn cho vị trí {job.title}",
                            notification_type="new_application",
                            entity_type="application",
                            entity_id=application.id,
                        )

            await self.session.commit()
            await self.session.refresh(
                application, attribute_names=["candidate"]
            )

        except Exception:
            await self.session.rollback()
            raise
        return application

    async def update_application_status(
        self,
        current_user: User,
        application_id: uuid.UUID,
        new_status: ApplicationStatus,
    ) -> Application:
        application = await self.applications.get_by_id(application_id)
        if application is None:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            )

        try:
            await JobService(self.session).get_recruiter_job_by_id(
                current_user,
                application.job_id,
            )
        except EntityNotFoundException:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            ) from None

        if new_status not in RECRUITER_MANAGED_STATUSES:
            raise InvalidTransitionException(
                f"Invalid Application status transition: "
                f"status {new_status.value!r} is not recruiter-managed."
            )

        old_status = application.status
        domain = DomainApplication(
            candidate_id=application.candidate_id,
            job_id=application.job_id,
            status=application.status,
        )
        try:
            domain.transition_to(new_status)
        except DomainException as exc:
            raise InvalidTransitionException(str(exc)) from exc

        application.status = domain.status
        try:
            # Notify candidate about status change BEFORE commit
            notification_service = NotificationService(self.session)
            await notification_service.create_notification(
                user_id=application.candidate_id,
                title="Cập nhật trạng thái đơn ứng tuyển",
                content=f"Đơn ứng tuyển của bạn cho vị trí {application.job.title if application.job else 'N/A'} đã thay đổi từ {old_status.value} sang {new_status.value}",
                notification_type="application_status_changed",
                entity_type="application",
                entity_id=application.id,
            )

            await self.session.commit()
            await self.session.refresh(
                application, attribute_names=["candidate"]
            )

        except Exception:
            await self.session.rollback()
            raise
        return application

    async def withdraw_application(
        self,
        current_user: User,
        application_id: uuid.UUID,
    ) -> Application:
        """Candidate-owned withdrawal of their own application.

        Ownership is resolved from the DB (current_user -> candidate_profile
        -> application.candidate_id). Missing/foreign/nonexistent applications
        all surface as 404 so existence is never leaked across tenants.
        """
        user = await UserService(self.session).get_user_with_profile(
            current_user.id
        )
        if user is None or user.candidate_profile is None:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            )

        application = await self.applications.get_by_id(application_id)
        if application is None:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            )
        if application.candidate_id != user.candidate_profile.id:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            )

        domain = DomainApplication(
            candidate_id=application.candidate_id,
            job_id=application.job_id,
            status=application.status,
        )
        try:
            domain.transition_to(ApplicationStatus.WITHDRAWN)
        except DomainException as exc:
            raise InvalidTransitionException(str(exc)) from exc

        application.status = domain.status
        try:
            # Notify recruiter(s) about application withdrawal BEFORE commit
            notification_service = NotificationService(self.session)
            if application.job and application.job.company and application.job.company.recruiters:
                for recruiter in application.job.company.recruiters:
                    if recruiter.user_id:
                        await notification_service.create_notification(
                            user_id=recruiter.user_id,
                            title="Ứng viên rút đơn",
                            content=f"Ứng viên đã rút đơn ứng tuyển cho vị trí {application.job.title}",
                            notification_type="application_withdrawn",
                            entity_type="application",
                            entity_id=application.id,
                        )

            await self.session.commit()
            await self.session.refresh(
                application, attribute_names=["candidate"]
            )

        except Exception:
            await self.session.rollback()
            raise
        return application

    async def list_applications_by_job(
        self,
        job_id: uuid.UUID,
    ) -> list[Application]:
        return await self.applications.list_by_job(job_id)

    async def get_application_detail(
        self,
        current_user: User,
        application_id: uuid.UUID,
    ) -> tuple[Application, Resume | None]:
        """Resolve an application for a recruiter/admin with ownership enforced.

        Admin may access any application; a recruiter may only access
        applications on their own company's jobs. Missing, soft-deleted, or
        unowned applications all surface as 404 so existence is never leaked.
        Returns the application together with the candidate's primary resume
        (``None`` when the candidate has no resume), so the digital CV can be
        rendered from ``Resume.parsed_data``.
        """
        application = await self.applications.get_by_id_with_candidate(
            application_id
        )
        if application is None:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            )

        try:
            await JobService(self.session).get_recruiter_job_by_id(
                current_user,
                application.job_id,
            )
        except EntityNotFoundException:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            ) from None

        resume = await ResumeRepository(self.session, Resume).get_primary_by_candidate(
            application.candidate_id
        )
        return application, resume

    async def get_application_match(
        self,
        current_user: User,
        application_id: uuid.UUID,
        matching_service: AIMatchingService,
    ) -> MatchResultSchema:
        """Compute the deterministic AI match score for an application.

        Recruiter/admin only, with ownership enforced exactly like
        ``get_application_detail`` (foreign/missing applications surface as
        404). The candidate resume and job are resolved server-side from the
        application; vectors come from the vector repository and fall back to
        on-demand embedding when a point is missing. Scoring is delegated to
        the existing ``MatchingEngine`` (no duplicated logic here). Missing
        or unparseable resume data degrades gracefully instead of crashing.
        """
        application = await self.applications.get_by_id_with_candidate(
            application_id
        )
        if application is None:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            )

        try:
            job = await JobService(self.session).get_recruiter_job_by_id(
                current_user,
                application.job_id,
            )
        except EntityNotFoundException:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            ) from None

        resume = await ResumeRepository(self.session, Resume).get_primary_by_candidate(
            application.candidate_id
        )

        parsed_resume = None
        resume_vector = None
        if resume is not None and resume.parsed_data:
            try:
                parsed_resume = ParsedResumeSchema.model_validate(
                    resume.parsed_data
                )
            except ValidationError:
                parsed_resume = None
            if parsed_resume is not None:
                resume_vector = await self._resolve_vector(
                    matching_service, "resumes", application.candidate_id
                )
                if resume_vector is None:
                    resume_vector = (
                        matching_service.embedding_service.embed_resume(
                            parsed_resume
                        )
                    )

        parsed_job = ParsedJobSchema(
            title=job.title,
            summary=job.description,
            required_skills=[skill.name for skill in job.skills],
        )
        job_vector = await self._resolve_vector(
            matching_service, "jobs", application.job_id
        )
        if job_vector is None:
            job_vector = matching_service.embedding_service.embed_job(
                parsed_job
            )

        return matching_service.matching_engine.match_resume_to_job(
            resume=parsed_resume,
            job=parsed_job,
            resume_vector=resume_vector,
            job_vector=job_vector,
        )

    @staticmethod
    async def _resolve_vector(
        matching_service: AIMatchingService,
        collection_name: str,
        point_id: uuid.UUID,
    ) -> list[float] | None:
        """Return the stored vector for a point or ``None`` when missing.

        Qdrant connectivity failures raise ``AIError`` (surfaced by the API
        layer as a controlled error); only a missing point is treated as
        ``None`` so the caller can embed on demand.
        """
        retrieved = await matching_service.vector_repository.retrieve_vector(
            collection_name=collection_name,
            point_id=point_id,
        )
        if retrieved is None:
            return None
        return retrieved["vector"]

    async def list_my_applications(
        self,
        current_user: User,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Application]:
        """Return the authenticated candidate's applications, newest first.

        Ownership is always resolved from the DB (current_user ->
        candidate_profile.id). A user without a candidate profile has no
        applications, so it is treated as an empty history.
        """
        user = await UserService(self.session).get_user_with_profile(
            current_user.id
        )
        if user is None or user.candidate_profile is None:
            return []
        return await self.applications.list_by_candidate_paginated(
            user.candidate_profile.id,
            skip=skip,
            limit=limit,
        )