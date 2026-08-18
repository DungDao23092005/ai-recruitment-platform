from __future__ import annotations

from typing import Any

from sqlalchemy import select
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
