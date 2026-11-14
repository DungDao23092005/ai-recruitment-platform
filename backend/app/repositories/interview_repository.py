from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Application, Interview, Job
from app.repositories.base import BaseRepository


class InterviewRepository(BaseRepository[Interview]):
    async def get_by_id_with_application(self, interview_id: Any) -> Interview | None:
        stmt = select(Interview).where(
            Interview.id == interview_id,
            Interview.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_application(self, application_id: Any) -> list[Interview]:
        stmt = (
            select(Interview)
            .where(
                Interview.application_id == application_id,
                Interview.is_deleted == False,  # noqa: E712
            )
            .order_by(Interview.scheduled_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_candidate_id(self, candidate_id: Any) -> list[Interview]:
        stmt = (
            select(Interview)
            .join(Interview.application)
            .options(
                selectinload(Interview.application)
                .selectinload(Application.job)
                .selectinload(Job.company)
            )
            .where(
                Application.candidate_id == candidate_id,
                Application.is_deleted == False,  # noqa: E712
                Interview.is_deleted == False,  # noqa: E712
            )
            .order_by(Interview.scheduled_at.asc(), Interview.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())