from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.domain.enums import JobStatus
from app.models import Company, Job
from app.repositories.base import BaseRepository


class JobRepository(BaseRepository[Job]):
    async def list_active_jobs(self, skip: int = 0, limit: int = 10) -> list[Job]:
        stmt = (
            select(Job)
            .options(joinedload(Job.company))
            .where(
                Job.status == JobStatus.PUBLISHED,
                Job.is_deleted == False,  # noqa: E712
            )
            .order_by(Job.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_jobs_by_company(
        self,
        company_id: Any,
        skip: int = 0,
        limit: int = 10,
    ) -> list[Job]:
        stmt = (
            select(Job)
            .options(joinedload(Job.company))
            .where(
                Job.company_id == company_id,
                Job.is_deleted == False,  # noqa: E712
            )
            .order_by(Job.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_jobs(self, skip: int = 0, limit: int = 10) -> list[Job]:
        stmt = (
            select(Job)
            .options(joinedload(Job.company))
            .where(Job.is_deleted == False)  # noqa: E712
            .order_by(Job.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_job_with_company(self, job_id: Any) -> Job | None:
        stmt = (
            select(Job)
            .options(joinedload(Job.company))
            .where(
                Job.id == job_id,
                Job.is_deleted == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().first()

    async def get_job_with_skills(self, job_id: Any) -> Job | None:
        stmt = (
            select(Job)
            .options(joinedload(Job.skills))
            .where(
                Job.id == job_id,
                Job.is_deleted == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().first()

    async def get_job_with_company_and_skills(self, job_id: Any) -> Job | None:
        stmt = (
            select(Job)
            .options(joinedload(Job.company), joinedload(Job.skills))
            .where(
                Job.id == job_id,
                Job.is_deleted == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().first()

    async def get_job_with_company_and_recruiters(self, job_id: Any) -> Job | None:
        stmt = (
            select(Job)
            .options(joinedload(Job.company).joinedload(Company.recruiters))
            .where(
                Job.id == job_id,
                Job.is_deleted == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().first()

    async def get_job_counts_by_status(self, company_id: Any) -> list[dict[str, Any]]:
        stmt = (
            select(Job.status, func.count(Job.id))
            .where(
                Job.company_id == company_id,
                Job.is_deleted == False,  # noqa: E712
            )
            .group_by(Job.status)
        )
        result = await self.session.execute(stmt)
        return [{"status": row[0].value, "count": row[1]} for row in result.all()]
