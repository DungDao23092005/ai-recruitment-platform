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
from app.models import Application, Job
from app.repositories import ApplicationRepository, JobRepository


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
            await self.session.refresh(application)
        except Exception:
            await self.session.rollback()
            raise
        return application

    async def update_application_status(
        self,
        application_id: uuid.UUID,
        new_status: ApplicationStatus,
    ) -> Application:
        application = await self.applications.get_by_id(application_id)
        if application is None:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
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
            await self.session.refresh(application)
        except Exception:
            await self.session.rollback()
            raise
        return application