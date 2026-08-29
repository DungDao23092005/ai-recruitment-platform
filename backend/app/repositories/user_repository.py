from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.domain.enums import UserRole
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

    async def get_by_email_including_inactive(self, email: str) -> User | None:
        """Get user by email including inactive (locked) users, but excluding soft-deleted."""
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

    async def get_admin_user(self, user_id: Any) -> User | None:
        """Fetch a user for admin views, including soft-deleted users."""
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_admin_users(
        self,
        skip: int,
        limit: int,
        search: str | None = None,
        role: UserRole | None = None,
    ) -> tuple[list[User], int]:
        """List users for the admin console.

        Soft-deleted users are excluded (they are permanently deleted accounts).
        Locked accounts (is_active=False) remain visible to administrators.
        Supports an optional case-insensitive email search and a role filter.
        """
        filters = [
            User.is_deleted == False,  # noqa: E712
        ]
        if search:
            filters.append(User.email.ilike(f"%{search.strip()}%"))
        if role is not None:
            filters.append(User.role == role)

        count_stmt = select(func.count()).select_from(User)
        # Use created_at desc, then id desc for stable pagination
        list_stmt = select(User).order_by(User.created_at.desc(), User.id.desc())

        if filters:
            count_stmt = count_stmt.where(*filters)
            list_stmt = list_stmt.where(*filters)

        total = (await self.session.execute(count_stmt)).scalar_one()
        list_stmt = list_stmt.offset(skip).limit(limit)
        rows = (await self.session.execute(list_stmt)).scalars().all()
        return list(rows), total
