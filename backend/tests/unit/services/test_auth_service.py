import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ConflictException, ForbiddenException
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
        service.users.get_by_email_including_inactive.return_value = None
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
        service.users.get_by_email_including_inactive.return_value = make_user()
        data = UserCreate(email="dev@example.com", password="password123")

        with pytest.raises(ConflictException):
            asyncio.run(service.register_user(data))

        session.commit.assert_not_awaited()
        session.rollback.assert_not_awaited()

    def test_commit_failure_rolls_back(self):
        session = make_session()
        service = make_service(session)
        service.users.get_by_email_including_inactive.return_value = None
        session.commit.side_effect = RuntimeError("db down")
        data = UserCreate(email="dev@example.com", password="password123")

        with pytest.raises(RuntimeError):
            asyncio.run(service.register_user(data))

        session.rollback.assert_awaited_once()

    def test_admin_role_rejected(self):
        session = make_session()
        service = make_service(session)
        service.users.get_by_email_including_inactive.return_value = None
        data = UserCreate(
            email="attacker@example.com",
            password="password123",
            role=UserRole.ADMIN,
        )

        with pytest.raises(ForbiddenException) as exc_info:
            asyncio.run(service.register_user(data))

        assert "Admin role cannot be assigned" in str(exc_info.value)
        session.commit.assert_not_awaited()
        session.rollback.assert_not_awaited()


class TestAuthenticateUser:
    def test_valid_credentials_returns_user(self):
        from app.core.security import get_password_hash

        session = make_session()
        service = make_service(session)
        user = make_user()
        user.is_active = True
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
        user.is_active = True
        user.password_hash = get_password_hash("password123")
        service.users.get_by_email.return_value = user

        result = asyncio.run(
            service.authenticate_user(email=user.email, password="wrong-password")
        )

        assert result is None


class TestAuthenticateUserLockedAccount:
    def test_locked_user_correct_password_returns_locked_exception(self):
        from app.core.security import get_password_hash
        from app.core.exceptions import LockedAccountException

        session = make_session()
        service = make_service(session)
        user = make_user()
        user.is_active = False
        user.lock_reason = "Test lock reason"
        user.password_hash = get_password_hash("password123")
        service.users.get_by_email.return_value = user

        with pytest.raises(LockedAccountException) as exc_info:
            asyncio.run(
                service.authenticate_user(email=user.email, password="password123")
            )

        assert exc_info.value.reason == "Test lock reason"

    def test_locked_user_wrong_password_returns_none(self):
        from app.core.security import get_password_hash

        session = make_session()
        service = make_service(session)
        user = make_user()
        user.is_active = False
        user.password_hash = get_password_hash("password123")
        service.users.get_by_email.return_value = user

        result = asyncio.run(
            service.authenticate_user(email=user.email, password="wrong-password")
        )

        assert result is None

    def test_active_user_can_login(self):
        from app.core.security import get_password_hash

        session = make_session()
        service = make_service(session)
        user = make_user()
        user.is_active = True
        user.password_hash = get_password_hash("password123")
        service.users.get_by_email.return_value = user

        result = asyncio.run(
            service.authenticate_user(email=user.email, password="password123")
        )

        assert result is user


class TestRegisterUserEmailUniqueness:
    def test_locked_user_email_remains_unique(self):
        session = make_session()
        service = make_service(session)

        # Existing user is locked (inactive)
        locked_user = make_user()
        locked_user.is_active = False
        service.users.get_by_email_including_inactive.return_value = locked_user

        data = UserCreate(email=locked_user.email, password="newpassword123")

        with pytest.raises(ConflictException) as exc_info:
            asyncio.run(service.register_user(data))

        assert "đã được sử dụng" in str(exc_info.value)
        session.commit.assert_not_awaited()

    def test_soft_deleted_user_email_can_be_reused(self):
        """Registration should succeed if email belongs to a soft-deleted user.

        The get_by_email_including_inactive still filters is_deleted=False,
        so soft-deleted users are not considered for uniqueness.
        """
        session = make_session()
        service = make_service(session)

        # Soft-deleted user is NOT returned by get_by_email_including_inactive
        service.users.get_by_email_including_inactive.return_value = None

        data = UserCreate(email="deleted@example.com", password="password123")

        user = asyncio.run(service.register_user(data))

        assert user is not None
        assert user.email == "deleted@example.com"
        session.commit.assert_awaited_once()

    def test_duplicate_email_raises_conflict_still_works(self):
        """Existing active user email should still raise conflict."""
        session = make_session()
        service = make_service(session)
        active_user = make_user()
        active_user.is_active = True
        service.users.get_by_email_including_inactive.return_value = active_user

        data = UserCreate(email=active_user.email, password="password123")

        with pytest.raises(ConflictException):
            asyncio.run(service.register_user(data))

        session.commit.assert_not_awaited()