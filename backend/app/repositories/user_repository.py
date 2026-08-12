from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(
            User.email == email,
            User.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_profile(self, user_id: Any) -> User | None:
        stmt = (
            select(User)
            .options(
                joinedload(User.candidate_profile),
                joinedload(User.recruiter_profile),
            )
            .where(
                User.id == user_id,
                User.is_deleted == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
