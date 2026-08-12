from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.models import Application
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

    async def list_by_job(self, job_id: Any) -> list[Application]:
        stmt = select(Application).where(
            Application.job_id == job_id,
            Application.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
