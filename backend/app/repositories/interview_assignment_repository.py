from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InterviewAssignment
from app.repositories.base import BaseRepository


class InterviewAssignmentRepository(BaseRepository[InterviewAssignment]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, InterviewAssignment)


    async def get_active_for_interview_user(
        self,
        interview_id: Any,
        user_id: Any,
    ) -> InterviewAssignment | None:
        stmt = select(InterviewAssignment).where(
            InterviewAssignment.interview_id == interview_id,
            InterviewAssignment.user_id == user_id,
            InterviewAssignment.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def has_inactive_without_active_for_interview_user(
        self,
        interview_id: Any,
        user_id: Any,
    ) -> bool:
        active = await self.get_active_for_interview_user(
            interview_id, user_id
        )
        if active is not None:
            return False
        stmt = (
            select(InterviewAssignment.id)
            .where(
                InterviewAssignment.interview_id == interview_id,
                InterviewAssignment.user_id == user_id,
                InterviewAssignment.is_deleted == True,  # noqa: E712
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_active_by_id_for_interview(
        self,
        assignment_id: Any,
        interview_id: Any,
    ) -> InterviewAssignment | None:
        stmt = select(InterviewAssignment).where(
            InterviewAssignment.id == assignment_id,
            InterviewAssignment.interview_id == interview_id,
            InterviewAssignment.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active_by_interview(
        self,
        interview_id: Any,
    ) -> list[InterviewAssignment]:
        stmt = (
            select(InterviewAssignment)
            .where(
                InterviewAssignment.interview_id == interview_id,
                InterviewAssignment.is_deleted == False,  # noqa: E712
            )
            .order_by(
                InterviewAssignment.created_at.asc(),
                InterviewAssignment.id.asc(),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_by_user(
        self,
        user_id: Any,
    ) -> list[InterviewAssignment]:
        stmt = (
            select(InterviewAssignment)
            .where(
                InterviewAssignment.user_id == user_id,
                InterviewAssignment.is_deleted == False,  # noqa: E712
            )
            .order_by(
                InterviewAssignment.created_at.asc(),
                InterviewAssignment.id.asc(),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
