import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ConflictException
from app.domain.enums import UserRole
from app.models import User
from app.repositories import UserRepository
from app.schemas.user import UserCreate
from app.services.auth_service import AuthService


def make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    return session


def make_user() -> User:
    return User(
        id=uuid.uuid4(),
        email=f"{uuid.uuid4()}@example.com",
        password_hash="hashed",
        role=UserRole.CANDIDATE,
    )


def make_service(session) -> AuthService:
    service = AuthService(session)
    service.users = AsyncMock(spec=UserRepository)
    return service


class TestRegisterUser:
    def test_creates_user(self):
        session = make_session()
        service = make_service(session)
        service.users.get_by_email.return_value = None
        data = UserCreate(
            email="dev@example.com",
            password="password123",
            role=UserRole.RECRUITER,
        )

        user = asyncio.run(service.register_user(data))

        assert user is not None
        assert user.email == "dev@example.com"
        assert user.role == UserRole.RECRUITER
        assert user.password_hash != data.password
        assert user.password_hash.startswith("$")
        session.add.assert_called_once_with(user)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(user)

    def test_duplicate_email_raises_conflict(self):
        session = make_session()
        service = make_service(session)
        service.users.get_by_email.return_value = make_user()
        data = UserCreate(email="dev@example.com", password="password123")

        with pytest.raises(ConflictException):
            asyncio.run(service.register_user(data))

        session.commit.assert_not_awaited()
        session.rollback.assert_not_awaited()

    def test_commit_failure_rolls_back(self):
        session = make_session()
        service = make_service(session)
        service.users.get_by_email.return_value = None
        session.commit.side_effect = RuntimeError("db down")
        data = UserCreate(email="dev@example.com", password="password123")

        with pytest.raises(RuntimeError):
            asyncio.run(service.register_user(data))

        session.rollback.assert_awaited_once()


class TestAuthenticateUser:
    def test_valid_credentials_returns_user(self):
        from app.core.security import get_password_hash

        session = make_session()
        service = make_service(session)
        user = make_user()
        user.password_hash = get_password_hash("password123")
        service.users.get_by_email.return_value = user

        result = asyncio.run(
            service.authenticate_user(email=user.email, password="password123")
        )

        assert result is user

    def test_unknown_email_returns_none(self):
        session = make_session()
        service = make_service(session)
        service.users.get_by_email.return_value = None

        result = asyncio.run(
            service.authenticate_user(
                email="missing@example.com",
                password="password123",
            )
        )

        assert result is None

    def test_wrong_password_returns_none(self):
        from app.core.security import get_password_hash

        session = make_session()
        service = make_service(session)
        user = make_user()
        user.password_hash = get_password_hash("password123")
        service.users.get_by_email.return_value = user

        result = asyncio.run(
            service.authenticate_user(email=user.email, password="wrong-password")
        )

        assert result is None
