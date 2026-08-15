from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.domain.enums import JobStatus
from app.models import Job
from app.repositories.base import BaseRepository


class JobRepository(BaseRepository[Job]):
    async def list_active_jobs(self, skip: int = 0, limit: int = 10) -> list[Job]:
        stmt = (
            select(Job)
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
            .where(Job.is_deleted == False)  # noqa: E712
            .order_by(Job.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

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
