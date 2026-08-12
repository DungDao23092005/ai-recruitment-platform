from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException
from app.core.security import get_password_hash, verify_password
from app.models import User
from app.repositories import UserRepository
from app.schemas.user import UserCreate


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session, User)

    async def register_user(self, data: UserCreate) -> User:
        existing = await self.users.get_by_email(data.email)
        if existing is not None:
            raise ConflictException(
                f"User with email {data.email!r} already exists"
            )

        user = User(
            email=data.email,
            password_hash=get_password_hash(data.password),
            role=data.role,
        )
        self.session.add(user)
        try:
            await self.session.commit()
            await self.session.refresh(user)
        except Exception:
            await self.session.rollback()
            raise
        return user

    async def authenticate_user(
        self,
        email: str,
        password: str,
    ) -> User | None:
        user = await self.users.get_by_email(email)
        if user is None:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user