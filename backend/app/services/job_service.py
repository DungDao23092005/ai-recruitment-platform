from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException, InvalidTransitionException
from app.domain.enums import JobStatus
from app.models import Company, Job
from app.repositories import CompanyRepository, JobRepository
from app.schemas.job import JobCreate
from app.services.user_service import UserService


class JobService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.jobs = JobRepository(session, Job)
        self.companies = CompanyRepository(session, Company)

    async def create_job(self, data: JobCreate) -> Job:
        company = await self.companies.get_by_id(data.company_id)
        if company is None:
            raise EntityNotFoundException(f"Company {data.company_id} not found")

        job = Job(
            company_id=data.company_id,
            title=data.title,
            description=data.description,
            status=data.status,
            job_type=data.job_type,
            workplace_type=data.workplace_type,
            location=data.location or "",
        )
        self.session.add(job)
        try:
            await self.session.commit()
            await self.session.refresh(job)
        except Exception:
            await self.session.rollback()
            raise
        return job

    async def publish_job(self, job_id: uuid.UUID) -> Job:
        job = await self.jobs.get_by_id(job_id)
        if job is None:
            raise EntityNotFoundException(f"Job {job_id} not found")
        if job.status != JobStatus.DRAFT:
            raise InvalidTransitionException(
                f"Cannot publish job in status {job.status.value!r}; "
                "expected 'draft'"
            )
        job.status = JobStatus.PUBLISHED
        await self._commit_and_refresh(job)
        return job

    async def close_job(self, job_id: uuid.UUID) -> Job:
        job = await self.jobs.get_by_id(job_id)
        if job is None:
            raise EntityNotFoundException(f"Job {job_id} not found")
        if job.status != JobStatus.PUBLISHED:
            raise InvalidTransitionException(
                f"Cannot close job in status {job.status.value!r}; "
                "expected 'published'"
            )
        job.status = JobStatus.CLOSED
        await self._commit_and_refresh(job)
        return job

    async def list_jobs(
        self,
        skip: int = 0,
        limit: int = 10,
    ) -> list[Job]:
        return await self.jobs.list_active_jobs(skip=skip, limit=limit)

    async def list_recruiter_jobs(
        self,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 10,
    ) -> list[Job]:
        user = await UserService(self.session).get_user_with_profile(user_id)
        profile = user.recruiter_profile if user is not None else None
        if profile is None or profile.company_id is None:
            return []
        return await self.jobs.list_jobs_by_company(
            profile.company_id,
            skip=skip,
            limit=limit,
        )

    async def list_all_jobs(
        self,
        skip: int = 0,
        limit: int = 10,
    ) -> list[Job]:
        return await self.jobs.list_all_jobs(skip=skip, limit=limit)

    async def _commit_and_refresh(self, entity) -> None:
        try:
            await self.session.commit()
            await self.session.refresh(entity)
        except Exception:
            await self.session.rollback()
            raise