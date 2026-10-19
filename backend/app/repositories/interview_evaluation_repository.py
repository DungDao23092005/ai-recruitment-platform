from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InterviewEvaluation
from app.repositories.base import BaseRepository


class InterviewEvaluationRepository(BaseRepository[InterviewEvaluation]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, InterviewEvaluation)

    async def list_by_application(
        self, application_id: Any
    ) -> list[InterviewEvaluation]:
        stmt = (
            select(InterviewEvaluation)
            .where(
                InterviewEvaluation.application_id == application_id,
                InterviewEvaluation.is_deleted == False,  # noqa: E712
            )
            .order_by(
                InterviewEvaluation.created_at.asc(),
                InterviewEvaluation.id.asc(),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_interview(
        self, interview_id: Any
    ) -> list[InterviewEvaluation]:
        stmt = (
            select(InterviewEvaluation)
            .where(
                InterviewEvaluation.interview_id == interview_id,
                InterviewEvaluation.is_deleted == False,  # noqa: E712
            )
            .order_by(
                InterviewEvaluation.created_at.asc(),
                InterviewEvaluation.id.asc(),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_interview_and_evaluator(
        self,
        interview_id: Any,
        evaluator_id: Any,
    ) -> InterviewEvaluation | None:
        """Resolve the single active evaluation an evaluator wrote for an interview."""
        stmt = select(InterviewEvaluation).where(
            InterviewEvaluation.interview_id == interview_id,
            InterviewEvaluation.evaluator_id == evaluator_id,
            InterviewEvaluation.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_and_application(
        self,
        evaluation_id: Any,
        application_id: Any,
    ) -> InterviewEvaluation | None:
        """Retrieve an evaluation scoped to its application (no ID-only bypass)."""
        stmt = select(InterviewEvaluation).where(
            InterviewEvaluation.id == evaluation_id,
            InterviewEvaluation.application_id == application_id,
            InterviewEvaluation.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
