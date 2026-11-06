from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InterviewEvaluation
from app.models.interview_evaluation import (
    EVALUATION_STATUS_DRAFT,
    EVALUATION_STATUS_SUBMITTED,
)
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

    async def get_by_id_active(
        self,
        evaluation_id: Any,
    ) -> InterviewEvaluation | None:
        stmt = select(InterviewEvaluation).where(
            InterviewEvaluation.id == evaluation_id,
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

    async def try_submit(
        self,
        evaluation_id: Any,
        evaluator_id: Any,
        submitted_at: datetime,
    ) -> bool:
        """Atomically transition one draft to submitted.

        The conditional ``status = 'draft'`` predicate is the concurrency guard:
        exactly one concurrent submit can update the row. The losing request
        observes ``rowcount == 0`` and must treat the scorecard as already
        submitted.
        """
        stmt = (
            update(InterviewEvaluation)
            .where(
                InterviewEvaluation.id == evaluation_id,
                InterviewEvaluation.evaluator_id == evaluator_id,
                InterviewEvaluation.status == EVALUATION_STATUS_DRAFT,
                InterviewEvaluation.is_deleted == False,  # noqa: E712
            )
            .values(
                status=EVALUATION_STATUS_SUBMITTED,
                submitted_at=submitted_at,
                updated_at=submitted_at,
            )
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        return result.rowcount == 1
