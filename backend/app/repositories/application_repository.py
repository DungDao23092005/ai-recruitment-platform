from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models import Application, Job
from app.repositories.base import BaseRepository


class ApplicationRepository(BaseRepository[Application]):
    async def get_by_candidate_and_job(
        self,
        candidate_id: Any,
        job_id: Any,
    ) -> Application | None:
        stmt = select(Application).where(
            Application.candidate_id == candidate_id,
            Application.job_id == job_id,
            Application.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_candidate(self, candidate_id: Any) -> list[Application]:
        stmt = select(Application).where(
            Application.candidate_id == candidate_id,
            Application.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_candidate_paginated(
        self,
        candidate_id: Any,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Application]:
        stmt = (
            select(Application)
            .options(selectinload(Application.job).selectinload(Job.company))
            .where(
                Application.candidate_id == candidate_id,
                Application.is_deleted == False,  # noqa: E712
            )
            .order_by(Application.created_at.desc(), Application.id.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_job(self, job_id: Any) -> list[Application]:
        stmt = (
            select(Application)
            .options(selectinload(Application.candidate))
            .where(
                Application.job_id == job_id,
                Application.is_deleted == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_with_candidate(self, application_id: Any) -> Application | None:
        stmt = (
            select(Application)
            .options(
                selectinload(Application.candidate),
                selectinload(Application.job).selectinload(Job.company),
                selectinload(Application.job).selectinload(Job.skills),
            )
            .where(
                Application.id == application_id,
                Application.is_deleted == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_application_counts_by_status(
        self, company_id: Any
    ) -> list[dict[str, Any]]:
        stmt = (
            select(Application.status, func.count(Application.id))
            .join(Job, Application.job_id == Job.id)
            .where(
                Job.company_id == company_id,
                Job.is_deleted == False,  # noqa: E712
                Application.is_deleted == False,  # noqa: E712
            )
            .group_by(Application.status)
        )
        result = await self.session.execute(stmt)
        return [{"status": row[0].value, "count": row[1]} for row in result.all()]
