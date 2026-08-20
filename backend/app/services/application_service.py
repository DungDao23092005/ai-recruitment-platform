from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
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
from app.services.job_service import JobService
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