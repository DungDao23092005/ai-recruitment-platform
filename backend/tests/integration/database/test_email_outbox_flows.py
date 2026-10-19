"""Flow-level assertions that business flows write the durable outbox row.

These complement ``test_account_lifecycle_emails`` /
``test_subscription_lifecycle_emails`` (which assert delivery) by inspecting the
persisted row itself: recipient, event type and idempotency key.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from app.database.session import async_session_factory
from app.domain.enums import UserRole
from app.models import EmailOutbox, User
from app.services.account_email_service import (
    EVENT_ACCOUNT_DELETED,
    EVENT_ACCOUNT_LOCKED,
    SUBJECT_ACCOUNT_LOCKED,
)
from app.services.admin_service import AdminService
from app.services.auth_service import AuthService

pytestmark = pytest.mark.integration


async def _seed_user(session, *, role: UserRole = UserRole.CANDIDATE) -> User:
    user = User(
        email=f"flow-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="hashed",
        role=role,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def _outbox_rows(session) -> list[EmailOutbox]:
    return list((await session.execute(select(EmailOutbox))).scalars().all())


class TestAccountFlowEnqueuesOutboxRow:
    def test_lock_enqueues_single_row_with_vietnamese_reason(self, run_async):
        async def _test():
            async with async_session_factory() as session:
                user = await _seed_user(session)
                admin = await _seed_user(session, role=UserRole.ADMIN)
                await session.commit()
                user_id, user_email, admin_id = user.id, user.email, admin.id

            async with async_session_factory() as session:
                await AdminService(session).deactivate_user(
                    user_id, reason="Vi phạm điều khoản sử dụng", admin_id=admin_id
                )
                await asyncio.sleep(0.05)

            # A repeated lock must not enqueue a second row.
            async with async_session_factory() as session:
                await AdminService(session).deactivate_user(
                    user_id, reason="Lần hai", admin_id=admin_id
                )
                await asyncio.sleep(0.05)

            async with async_session_factory() as session:
                rows = await _outbox_rows(session)
            assert len(rows) == 1
            row = rows[0]
            assert row.event_type == EVENT_ACCOUNT_LOCKED
            assert row.to_email == user_email
            assert row.subject == SUBJECT_ACCOUNT_LOCKED
            assert "Vi phạm điều khoản sử dụng" in row.html_body
            # The row carries a stable per-transition idempotency key.
            assert row.idempotency_key.startswith(f"account_locked:{user_id}:")

        run_async(_test())

    def test_delete_row_targets_original_address(self, run_async):
        async def _test():
            async with async_session_factory() as session:
                user = await _seed_user(session)
                await session.commit()
                user_id, original_email = user.id, user.email

            async with async_session_factory() as session:
                await AdminService(session).delete_user(user_id)
                await asyncio.sleep(0.05)

            async with async_session_factory() as session:
                rows = await _outbox_rows(session)
            assert len(rows) == 1
            row = rows[0]
            assert row.event_type == EVENT_ACCOUNT_DELETED
            assert row.to_email == original_email
            assert not row.to_email.endswith("@anonymized.local")
            assert row.idempotency_key == f"account_deleted:{user_id}"

        run_async(_test())


class TestPasswordResetOtpIsNotOutboxed:
    def test_forgot_password_does_not_write_outbox(self, run_async):
        async def _test():
            async with async_session_factory() as session:
                user = await _seed_user(session)
                await session.commit()
                email = user.email

            async with async_session_factory() as session:
                await AuthService(session).forgot_password(email)

            async with async_session_factory() as session:
                total = int(
                    (
                        await session.execute(
                            select(func.count()).select_from(EmailOutbox)
                        )
                    ).scalar_one()
                )
            # OTP values are transient and must never be persisted in the outbox.
            assert total == 0

        run_async(_test())
