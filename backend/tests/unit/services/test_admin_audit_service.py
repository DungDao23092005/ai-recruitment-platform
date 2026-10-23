from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import EntityNotFoundException
from app.domain.enums import AdminAuditAction, UserRole
from app.models import AdminAuditLog, User
from app.schemas.admin_audit import AdminAuditLogListParams
from app.services.admin_service import AdminService


class TestAdminServiceAudit:
    def make_session(self) -> MagicMock:
        session = MagicMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.rollback = AsyncMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        return session

    def make_user(
        self,
        role: UserRole = UserRole.CANDIDATE,
        *,
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

    def make_service(self, session: MagicMock) -> AdminService:
        service = AdminService(session)
        service.users = AsyncMock(spec=type(service.users))
        service.audit_logs = AsyncMock(spec=type(service.audit_logs))
        return service

    def _added_audit(self, session: MagicMock) -> AdminAuditLog:
        session.add.assert_called_once()
        audit = session.add.call_args.args[0]
        assert isinstance(audit, AdminAuditLog)
        return audit

    def test_list_audit_logs_delegates_all_filters(self):
        session = self.make_session()
        service = self.make_service(session)
        audit = AdminAuditLog(
            id=uuid.uuid4(),
            admin_id=uuid.uuid4(),
            target_user_id=uuid.uuid4(),
            action=AdminAuditAction.USER_LOCK,
            created_at=None,
        )
        service.audit_logs.list_page.return_value = ([audit], 1)
        params = AdminAuditLogListParams(
            skip=20,
            limit=10,
            action=AdminAuditAction.USER_LOCK,
            admin_id=uuid.uuid4(),
            target_user_id=uuid.uuid4(),
            created_from="2026-01-01T00:00:00Z",
            created_to="2026-01-31T23:59:59Z",
            search="  example.com  ",
        )

        items, total = asyncio.run(AdminService.list_audit_logs(service, params))

        assert items == [audit]
        assert total == 1
        service.audit_logs.list_page.assert_awaited_once_with(
            skip=20,
            limit=10,
            action=AdminAuditAction.USER_LOCK,
            admin_id=params.admin_id,
            target_user_id=params.target_user_id,
            created_from=params.created_from,
            created_to=params.created_to,
            search="example.com",
        )

    def test_deactivate_writes_audit_in_the_same_transaction(self):
        session = self.make_session()
        service = self.make_service(session)
        user = self.make_user(role=UserRole.RECRUITER)
        service.users.get_admin_user.return_value = user
        admin_id = uuid.uuid4()

        with patch(
            "app.services.admin_service.schedule_account_locked_email",
            new_callable=AsyncMock,
        ), patch(
            "app.services.admin_service.schedule_account_locked_event"
        ):
            result = asyncio.run(
                AdminService.deactivate_user(
                    service, user.id, "  Vi phạm điều khoản  ", admin_id
                )
            )

        assert result.is_active is False
        audit = self._added_audit(session)
        assert audit.admin_id == admin_id
        assert audit.target_user_id == user.id
        assert audit.action == AdminAuditAction.USER_LOCK
        assert audit.reason == "Vi phạm điều khoản"
        assert audit.details == {
            "was_active": True,
            "target_role": "recruiter",
        }
        session.commit.assert_awaited_once()

    def test_repeated_lock_still_records_each_attempt(self):
        session = self.make_session()
        service = self.make_service(session)
        user = self.make_user(is_active=False)
        service.users.get_admin_user.return_value = user

        with patch(
            "app.services.admin_service.schedule_account_locked_email",
            new_callable=AsyncMock,
        ), patch(
            "app.services.admin_service.schedule_account_locked_event"
        ):
            asyncio.run(
                AdminService.deactivate_user(
                    service, user.id, "Second reason", uuid.uuid4()
                )
            )

        audit = self._added_audit(session)
        assert audit.action == AdminAuditAction.USER_LOCK
        assert audit.reason == "Second reason"
        assert audit.details == {
            "was_active": False,
            "target_role": "candidate",
        }

    def test_activate_writes_unlock_audit(self):
        session = self.make_session()
        service = self.make_service(session)
        user = self.make_user(is_active=False)
        service.users.get_admin_user.return_value = user
        admin_id = uuid.uuid4()

        result = asyncio.run(
            AdminService.activate_user(service, user.id, admin_id=admin_id)
        )

        assert result.is_active is True
        audit = self._added_audit(session)
        assert audit.admin_id == admin_id
        assert audit.target_user_id == user.id
        assert audit.action == AdminAuditAction.USER_UNLOCK
        assert audit.reason is None
        assert audit.details == {
            "was_active": False,
            "target_role": "candidate",
        }
        session.commit.assert_awaited_once()

    def test_delete_writes_audit_without_original_email(self):
        session = self.make_session()
        service = self.make_service(session)
        user = self.make_user(role=UserRole.RECRUITER)
        original_email = user.email
        service.users.get_admin_user.return_value = user
        admin_id = uuid.uuid4()

        with patch(
            "app.services.admin_service.schedule_account_deleted_email",
            new_callable=AsyncMock,
        ):
            result = asyncio.run(
                AdminService.delete_user(service, user.id, admin_id=admin_id)
            )

        assert result.email == f"deleted_{user.id}@anonymized.local"
        audit = self._added_audit(session)
        assert audit.admin_id == admin_id
        assert audit.target_user_id == user.id
        assert audit.action == AdminAuditAction.USER_DELETE
        assert audit.reason is None
        assert audit.details == {
            "was_active": True,
            "was_already_deleted": False,
            "target_role": "recruiter",
        }
        assert original_email not in str(audit.details)
        session.commit.assert_awaited_once()

    def test_nonexistent_target_creates_no_audit_or_commit(self):
        session = self.make_session()
        service = self.make_service(session)
        service.users.get_admin_user.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(
                AdminService.deactivate_user(
                    service, uuid.uuid4(), "Reason", uuid.uuid4()
                )
            )

        session.add.assert_not_called()
        session.commit.assert_not_awaited()

    def test_activate_nonexistent_target_creates_no_audit_or_commit(self):
        session = self.make_session()
        service = self.make_service(session)
        service.users.get_admin_user.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(
                AdminService.activate_user(
                    service, uuid.uuid4(), admin_id=uuid.uuid4()
                )
            )

        session.add.assert_not_called()
        session.commit.assert_not_awaited()

    def test_delete_nonexistent_target_creates_no_audit_or_commit(self):
        session = self.make_session()
        service = self.make_service(session)
        service.users.get_admin_user.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(
                AdminService.delete_user(
                    service, uuid.uuid4(), admin_id=uuid.uuid4()
                )
            )

        session.add.assert_not_called()
        session.commit.assert_not_awaited()

    def test_commit_failure_does_not_swallow_error(self):
        session = self.make_session()
        session.commit.side_effect = RuntimeError("commit failed")
        service = self.make_service(session)
        user = self.make_user()
        service.users.get_admin_user.return_value = user

        with patch(
            "app.services.admin_service.schedule_account_locked_email",
            new_callable=AsyncMock,
        ), patch(
            "app.services.admin_service.schedule_account_locked_event"
        ):
            with pytest.raises(RuntimeError, match="commit failed"):
                asyncio.run(
                    AdminService.deactivate_user(
                        service, user.id, "Reason", uuid.uuid4()
                    )
                )

        self._added_audit(session)
        session.commit.assert_awaited_once()
