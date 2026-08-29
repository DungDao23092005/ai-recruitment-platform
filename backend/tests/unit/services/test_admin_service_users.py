from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import EntityNotFoundException
from app.domain.enums import UserRole
from app.models import User
from app.services.admin_service import AdminService


class TestAdminServiceUsers:
    def make_session(self) -> MagicMock:
        session = MagicMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.rollback = AsyncMock()
        return session

    def make_user(self, role: UserRole = UserRole.CANDIDATE) -> User:
        return User(
            id=uuid.uuid4(),
            email=f"{uuid.uuid4()}@example.com",
            password_hash="hashed",
            role=role,
            is_active=True,
        )

    def make_service(self, session) -> AdminService:
        service = AdminService(session)
        service.users = AsyncMock(spec=type(service.users))
        return service

    def test_list_users_delegates_to_repository(self):
        session = self.make_session()
        service = self.make_service(session)
        users = [self.make_user()]
        service.users.list_admin_users.return_value = (users, 7)

        items, total = asyncio.run(
            AdminService.list_users(
                service, skip=0, limit=10, search="acme", role=UserRole.RECRUITER
            )
        )

        service.users.list_admin_users.assert_awaited_once_with(
            skip=0, limit=10, search="acme", role=UserRole.RECRUITER
        )
        assert items == users
        assert total == 7

    def test_get_user_returns_existing(self):
        session = self.make_session()
        service = self.make_service(session)
        user = self.make_user()
        service.users.get_admin_user.return_value = user

        result = asyncio.run(AdminService.get_user(service, user.id))

        assert result is user

    def test_get_user_missing_raises_not_found(self):
        session = self.make_session()
        service = self.make_service(session)
        service.users.get_admin_user.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(AdminService.get_user(service, uuid.uuid4()))


class TestAdminServiceUsersLegacy:
    """Legacy tests for deactivate behavior - updated for is_active."""

    def make_session(self) -> MagicMock:
        session = MagicMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.rollback = AsyncMock()
        return session

    def make_user(self, role: UserRole = UserRole.CANDIDATE) -> User:
        return User(
            id=uuid.uuid4(),
            email=f"{uuid.uuid4()}@example.com",
            password_hash="hashed",
            role=role,
            is_active=True,
        )

    def make_service(self, session) -> AdminService:
        service = AdminService(session)
        service.users = AsyncMock(spec=type(service.users))
        return service

    def test_deactivate_user_sets_is_active_false(self):
        """Deactivate should set is_active=False, not soft_delete."""
        session = self.make_session()
        service = self.make_service(session)
        user = self.make_user()
        service.users.get_admin_user.return_value = user
        admin_id = uuid.uuid4()
        reason = "Test reason"

        result = asyncio.run(AdminService.deactivate_user(service, user.id, reason, admin_id))

        service.users.get_admin_user.assert_awaited_once_with(user.id)
        assert result is user
        assert result.is_active is False
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(user)

    def test_deactivate_missing_raises_not_found(self):
        session = self.make_session()
        service = self.make_service(session)
        service.users.get_admin_user.return_value = None
        admin_id = uuid.uuid4()

        with pytest.raises(EntityNotFoundException):
            asyncio.run(AdminService.deactivate_user(service, uuid.uuid4(), "reason", admin_id))

        session.commit.assert_not_awaited()


class TestAdminServiceActivateDeactivate:
    """Tests for admin lock/unlock using is_active instead of soft_delete."""

    def make_session(self) -> MagicMock:
        session = MagicMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.rollback = AsyncMock()
        return session

    def make_user(self, role: UserRole = UserRole.CANDIDATE, is_active: bool = True) -> User:
        return User(
            id=uuid.uuid4(),
            email=f"{uuid.uuid4()}@example.com",
            password_hash="hashed",
            role=role,
            is_active=is_active,
        )

    def make_service(self, session) -> AdminService:
        service = AdminService(session)
        service.users = AsyncMock(spec=type(service.users))
        return service

    def test_deactivate_user_sets_is_active_false(self):
        """Deactivate should set is_active=False, not soft_delete."""
        session = self.make_session()
        service = self.make_service(session)
        user = self.make_user(is_active=True)
        service.users.get_admin_user.return_value = user
        admin_id = uuid.uuid4()
        reason = "Test reason"

        result = asyncio.run(AdminService.deactivate_user(service, user.id, reason, admin_id))

        service.users.get_admin_user.assert_awaited_once_with(user.id)
        assert result is user
        assert result.is_active is False
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(user)

    def test_activate_user_sets_is_active_true(self):
        """Activate should set is_active=True."""
        session = self.make_session()
        service = self.make_service(session)
        user = self.make_user(is_active=False)
        service.users.get_admin_user.return_value = user

        result = asyncio.run(AdminService.activate_user(service, user.id))

        service.users.get_admin_user.assert_awaited_once_with(user.id)
        assert result is user
        assert result.is_active is True
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(user)

    def test_activate_missing_raises_not_found(self):
        session = self.make_session()
        service = self.make_service(session)
        service.users.get_admin_user.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(AdminService.activate_user(service, uuid.uuid4()))

        session.commit.assert_not_awaited()

    def test_deactivate_preserves_user_data(self):
        """Deactivate should not delete user data, only set is_active=False."""
        session = self.make_session()
        service = self.make_service(session)
        user = self.make_user(is_active=True, role=UserRole.RECRUITER)
        user_id = user.id
        user_email = user.email
        service.users.get_admin_user.return_value = user
        admin_id = uuid.uuid4()
        reason = "Test reason"

        result = asyncio.run(AdminService.deactivate_user(service, user_id, reason, admin_id))

        assert result.id == user_id
        assert result.email == user_email
        assert result.role == UserRole.RECRUITER
        assert result.is_active is False
        # Soft delete should NOT be called
        service.users.soft_delete.assert_not_awaited()
