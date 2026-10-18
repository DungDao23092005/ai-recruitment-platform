from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

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


class TestAdminServiceAccountLifecycleEmails:
    """Lock/delete operations schedule at most one primitive-only email."""

    def make_session(self) -> MagicMock:
        session = MagicMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.rollback = AsyncMock()
        return session

    def make_user(
        self,
        role: UserRole = UserRole.CANDIDATE,
        is_active: bool = True,
        is_deleted: bool = False,
    ) -> User:
        user = User(
            id=uuid.uuid4(),
            email=f"{uuid.uuid4()}@example.com",
            password_hash="hashed",
            role=role,
            is_active=is_active,
        )
        user.is_deleted = is_deleted
        return user

    def make_service(self, session) -> AdminService:
        service = AdminService(session)
        service.users = AsyncMock(spec=type(service.users))
        return service

    def test_active_lock_schedules_email_to_owner(self):
        session = self.make_session()
        service = self.make_service(session)
        user = self.make_user(is_active=True)
        service.users.get_admin_user.return_value = user
        admin_id = uuid.uuid4()
        original_email = user.email

        with patch(
            "app.services.admin_service.schedule_account_locked_email"
        ) as scheduler:
            result = asyncio.run(
                AdminService.deactivate_user(service, user.id, "Lý do khóa", admin_id)
            )

        scheduler.assert_called_once()
        _, kwargs = scheduler.call_args
        assert kwargs["to_email"] == original_email
        assert kwargs["reason"] == "Lý do khóa"
        assert isinstance(kwargs["locked_at"], datetime)
        # Primitives only - no ORM instance leaks into the deferred task.
        assert not hasattr(kwargs["to_email"], "is_active")
        assert result.is_active is False
        session.commit.assert_awaited_once()

    def test_repeated_lock_updates_audit_but_sends_no_email(self):
        session = self.make_session()
        service = self.make_service(session)
        user = self.make_user(is_active=False)
        service.users.get_admin_user.return_value = user

        with patch(
            "app.services.admin_service.schedule_account_locked_email"
        ) as scheduler:
            result = asyncio.run(
                AdminService.deactivate_user(
                    service, user.id, "Second reason", uuid.uuid4()
                )
            )

        scheduler.assert_not_called()
        # Existing behaviour preserved: audit fields still overwritten.
        assert user.lock_reason == "Second reason"
        assert result.is_active is False
        session.commit.assert_awaited_once()

    def test_lock_on_soft_deleted_user_sends_no_email(self):
        session = self.make_session()
        service = self.make_service(session)
        user = self.make_user(is_active=True, is_deleted=True)
        service.users.get_admin_user.return_value = user

        with patch(
            "app.services.admin_service.schedule_account_locked_email"
        ) as scheduler:
            asyncio.run(
                AdminService.deactivate_user(service, user.id, "Lý do", uuid.uuid4())
            )

        scheduler.assert_not_called()

    def test_missing_user_lock_raises_and_schedules_nothing(self):
        session = self.make_session()
        service = self.make_service(session)
        service.users.get_admin_user.return_value = None

        with patch(
            "app.services.admin_service.schedule_account_locked_email"
        ) as scheduler:
            with pytest.raises(EntityNotFoundException):
                asyncio.run(
                    AdminService.deactivate_user(
                        service, uuid.uuid4(), "Lý do", uuid.uuid4()
                    )
                )

        scheduler.assert_not_called()
        session.commit.assert_not_awaited()

    def test_delete_schedules_email_to_original_address_before_anonymization(self):
        session = self.make_session()
        service = self.make_service(session)
        user = self.make_user()
        original_email = user.email
        service.users.get_admin_user.return_value = user

        with patch(
            "app.services.admin_service.schedule_account_deleted_email"
        ) as scheduler:
            result = asyncio.run(AdminService.delete_user(service, user.id))

        scheduler.assert_called_once()
        _, kwargs = scheduler.call_args
        assert kwargs["to_email"] == original_email
        assert not kwargs["to_email"].endswith("@anonymized.local")
        assert isinstance(kwargs["deleted_at"], datetime)
        # The database row is still anonymized after the operation.
        assert result.email == f"deleted_{user.id}@anonymized.local"
        service.users.soft_delete.assert_awaited_once_with(user)
        session.commit.assert_awaited_once()

    def test_repeated_delete_sends_no_email(self):
        session = self.make_session()
        service = self.make_service(session)
        user = self.make_user(is_deleted=True)
        user.email = f"deleted_{user.id}@anonymized.local"
        service.users.get_admin_user.return_value = user

        with patch(
            "app.services.admin_service.schedule_account_deleted_email"
        ) as scheduler:
            asyncio.run(AdminService.delete_user(service, user.id))

        scheduler.assert_not_called()

    def test_missing_user_delete_raises_and_schedules_nothing(self):
        session = self.make_session()
        service = self.make_service(session)
        service.users.get_admin_user.return_value = None

        with patch(
            "app.services.admin_service.schedule_account_deleted_email"
        ) as scheduler:
            with pytest.raises(EntityNotFoundException):
                asyncio.run(AdminService.delete_user(service, uuid.uuid4()))

        scheduler.assert_not_called()
        session.commit.assert_not_awaited()


class TestAdminServiceAccountLockEvent:
    """A genuine lock schedules exactly one post-commit forced-logout signal."""

    def make_session(self) -> MagicMock:
        session = MagicMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.rollback = AsyncMock()
        return session

    def make_user(
        self,
        role: UserRole = UserRole.CANDIDATE,
        is_active: bool = True,
        is_deleted: bool = False,
    ) -> User:
        user = User(
            id=uuid.uuid4(),
            email=f"{uuid.uuid4()}@example.com",
            password_hash="hashed",
            role=role,
            is_active=is_active,
        )
        user.is_deleted = is_deleted
        return user

    def make_service(self, session) -> AdminService:
        service = AdminService(session)
        service.users = AsyncMock(spec=type(service.users))
        return service

    def test_active_lock_schedules_forced_logout_event(self):
        session = self.make_session()
        service = self.make_service(session)
        user = self.make_user(is_active=True)
        service.users.get_admin_user.return_value = user
        admin_id = uuid.uuid4()

        with patch(
            "app.services.admin_service.schedule_account_locked_event"
        ) as scheduler:
            result = asyncio.run(
                AdminService.deactivate_user(service, user.id, "Lý do khóa", admin_id)
            )

        scheduler.assert_called_once()
        _, kwargs = scheduler.call_args
        assert kwargs["user_id"] == user.id
        assert kwargs["reason"] == "Lý do khóa"
        assert isinstance(kwargs["locked_at"], datetime)
        assert result.is_active is False
        session.commit.assert_awaited_once()

    def test_repeated_lock_schedules_no_event(self):
        session = self.make_session()
        service = self.make_service(session)
        user = self.make_user(is_active=False)
        service.users.get_admin_user.return_value = user

        with patch(
            "app.services.admin_service.schedule_account_locked_event"
        ) as scheduler:
            asyncio.run(
                AdminService.deactivate_user(
                    service, user.id, "Second reason", uuid.uuid4()
                )
            )

        scheduler.assert_not_called()

    def test_lock_on_soft_deleted_user_schedules_no_event(self):
        session = self.make_session()
        service = self.make_service(session)
        user = self.make_user(is_active=True, is_deleted=True)
        service.users.get_admin_user.return_value = user

        with patch(
            "app.services.admin_service.schedule_account_locked_event"
        ) as scheduler:
            asyncio.run(
                AdminService.deactivate_user(service, user.id, "Lý do", uuid.uuid4())
            )

        scheduler.assert_not_called()

    def test_missing_user_lock_schedules_no_event(self):
        session = self.make_session()
        service = self.make_service(session)
        service.users.get_admin_user.return_value = None

        with patch(
            "app.services.admin_service.schedule_account_locked_event"
        ) as scheduler:
            with pytest.raises(EntityNotFoundException):
                asyncio.run(
                    AdminService.deactivate_user(
                        service, uuid.uuid4(), "Lý do", uuid.uuid4()
                    )
                )

        scheduler.assert_not_called()
        session.commit.assert_not_awaited()
