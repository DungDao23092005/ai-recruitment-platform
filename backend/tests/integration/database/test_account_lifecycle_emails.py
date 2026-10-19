"""Real SQL Server integration tests for account lock/deletion emails.

Verifies which flows send an email, to whom, that the original (pre-anonymized)
address is used, that repeated operations do not resend, and that nothing is
sent when the surrounding transaction is rolled back. ``EmailService.send_email``
is spied so no provider call ever leaves the test.

Delivery is asynchronous: a post-commit signal only *schedules* a worker pass, so
these tests synchronise on the persisted outbox ``SENT`` marker (written after the
provider call returns) instead of a fixed ``asyncio.sleep``. The negative
("no second email") cases additionally run one deterministic worker drain so a
regression that wrongly enqueues a row fails loudly rather than racing the
background dispatch.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.database.session import async_session_factory  # noqa: E402
from app.domain.enums import OutboxStatus, UserRole  # noqa: E402
from app.models import CandidateProfile, EmailOutbox, Resume, User  # noqa: E402
from app.services.account_email_service import (  # noqa: E402
    EVENT_ACCOUNT_DELETED,
    EVENT_ACCOUNT_LOCKED,
    SUBJECT_ACCOUNT_DELETED,
    SUBJECT_ACCOUNT_LOCKED,
    schedule_account_locked_email,
)
from app.services.admin_service import AdminService  # noqa: E402
from app.services.email_outbox_service import reset_claim_hint_cache  # noqa: E402
from app.services.email_outbox_worker import (  # noqa: E402
    EmailOutboxWorker,
    reset_default_worker,
)
from app.services.email_service import EmailService  # noqa: E402


pytestmark = pytest.mark.integration

# Bounded, observable wait budget. Generous enough for a worker roundtrip under
# concurrent test load, small enough to fail fast when delivery never happens.
OUTBOX_WAIT_TIMEOUT_SECONDS = 5.0
OUTBOX_WAIT_INTERVAL_SECONDS = 0.02


@pytest.fixture
def email_spy():
    spy = AsyncMock()
    with patch.object(EmailService, "send_email", new=spy):
        yield spy


@pytest.fixture(autouse=True)
def _isolate_worker_state():
    """Keep the process-wide worker/hint cache from leaking between tests."""
    reset_claim_hint_cache()
    reset_default_worker()
    yield
    reset_default_worker()


async def _get_outbox_row(
    to_email: str, event_type: str | None = None
) -> EmailOutbox | None:
    async with async_session_factory() as session:
        stmt = select(EmailOutbox).where(EmailOutbox.to_email == to_email)
        if event_type is not None:
            stmt = stmt.where(EmailOutbox.event_type == event_type)
        return (await session.execute(stmt)).scalars().first()


async def _count_outbox_rows(to_email: str) -> int:
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(EmailOutbox).where(EmailOutbox.to_email == to_email)
            )
        ).scalars().all()
        return len(rows)


async def _wait_for_outbox_sent(
    *,
    to_email: str,
    event_type: str | None = None,
    timeout: float = OUTBOX_WAIT_TIMEOUT_SECONDS,
) -> EmailOutbox:
    """Block until the durable outbox row for ``to_email`` reaches ``SENT``.

    ``SENT`` is only recorded *after* the provider call returns, so observing it
    proves the expected email was actually delivered. This replaces the previous
    fixed ``asyncio.sleep(0.05)``, which could not guarantee that the scheduled
    worker pass had run under concurrent load.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    last_status: str | None = None
    while True:
        row = await _get_outbox_row(to_email, event_type)
        if row is not None and row.status == OutboxStatus.SENT.value:
            return row
        last_status = None if row is None else row.status
        if loop.time() >= deadline:
            raise AssertionError(
                f"Timed out after {timeout:.1f}s waiting for the outbox email to "
                f"{to_email!r} to reach SENT (last status={last_status!r})"
            )
        await asyncio.sleep(OUTBOX_WAIT_INTERVAL_SECONDS)


async def _drain_outbox() -> int:
    """Run one worker pass with a private worker to flush any pending rows.

    Used by the negative cases: if a redundant row were wrongly enqueued, this
    makes its delivery deterministic so the count assertion fails reliably
    instead of depending on the timing of the background dispatch.
    """
    worker = EmailOutboxWorker(session_factory=async_session_factory)
    return await worker.process_due_messages()


async def _seed_user(
    session,
    *,
    role: UserRole = UserRole.CANDIDATE,
    tag: str = "acct",
    is_active: bool = True,
) -> User:
    user = User(
        email=f"{tag}-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="hashed",
        role=role,
        is_active=is_active,
    )
    session.add(user)
    await session.flush()
    return user


def test_lock_emails_owner_once_and_updates_state(run_async, email_spy):
    async def _run():
        async with async_session_factory() as setup:
            user = await _seed_user(setup)
            admin = await _seed_user(setup, role=UserRole.ADMIN, tag="admin")
            await setup.commit()
            user_id, user_email = user.id, user.email
            admin_id, admin_email = admin.id, admin.email

        async with async_session_factory() as session:
            await AdminService(session).deactivate_user(
                user_id, reason="Violation of terms", admin_id=admin_id
            )

        await _wait_for_outbox_sent(
            to_email=user_email, event_type=EVENT_ACCOUNT_LOCKED
        )

        assert email_spy.await_count == 1
        to_email, subject, html, text = email_spy.await_args.args
        assert to_email == user_email
        assert to_email != admin_email
        assert subject == SUBJECT_ACCOUNT_LOCKED
        for body in (html, text):
            assert "Violation of terms" in body
            # Vietnamese template copy renders correctly.
            assert "không thể đăng nhập" in body
        assert re.search(r"\d{2}:\d{2} \d{2}/\d{2}/\d{4}", text)

        async with async_session_factory() as verify:
            row = await verify.get(User, user_id)
            assert row.is_active is False
            assert row.lock_reason == "Violation of terms"
            assert row.locked_at is not None
            assert row.locked_by == admin_id

    run_async(_run())


def test_repeated_lock_sends_no_second_email(run_async, email_spy):
    async def _run():
        async with async_session_factory() as setup:
            user = await _seed_user(setup)
            admin = await _seed_user(setup, role=UserRole.ADMIN, tag="admin")
            await setup.commit()
            user_id, user_email = user.id, user.email
            admin_id = admin.id

        async with async_session_factory() as session:
            await AdminService(session).deactivate_user(
                user_id, reason="First reason", admin_id=admin_id
            )
        await _wait_for_outbox_sent(
            to_email=user_email, event_type=EVENT_ACCOUNT_LOCKED
        )
        assert email_spy.await_count == 1

        async with async_session_factory() as session:
            await AdminService(session).deactivate_user(
                user_id, reason="Second reason", admin_id=admin_id
            )

        # Deterministically flush anything the second operation might have
        # enqueued, then assert no second notification was produced. The audit
        # reason is still updated.
        await _drain_outbox()
        assert email_spy.await_count == 1
        assert await _count_outbox_rows(user_email) == 1
        async with async_session_factory() as verify:
            row = await verify.get(User, user_id)
            assert row.lock_reason == "Second reason"

    run_async(_run())


def test_delete_emails_original_address_then_anonymizes(run_async, email_spy):
    async def _run():
        async with async_session_factory() as setup:
            user = await _seed_user(setup)
            admin = await _seed_user(setup, role=UserRole.ADMIN, tag="admin")
            await setup.commit()
            user_id, original_email = user.id, user.email
            admin_email = admin.email

        async with async_session_factory() as session:
            await AdminService(session).delete_user(user_id)

        await _wait_for_outbox_sent(
            to_email=original_email, event_type=EVENT_ACCOUNT_DELETED
        )

        assert email_spy.await_count == 1
        to_email, subject, html, text = email_spy.await_args.args
        # Sent to the original address, never the anonymized placeholder.
        assert to_email == original_email
        assert to_email != admin_email
        assert not to_email.endswith("@anonymized.local")
        assert subject == SUBJECT_ACCOUNT_DELETED
        for body in (html, text):
            assert "đã được xóa" in body
            assert "không thể khôi phục" in body
        assert re.search(r"\d{2}:\d{2} \d{2}/\d{2}/\d{4}", text)

        async with async_session_factory() as verify:
            row = await verify.get(User, user_id)
            assert row.is_deleted is True
            assert row.email == f"deleted_{user_id}@anonymized.local"

    run_async(_run())


def test_repeated_delete_sends_no_email(run_async, email_spy):
    async def _run():
        async with async_session_factory() as setup:
            user = await _seed_user(setup)
            await setup.commit()
            user_id, original_email = user.id, user.email

        async with async_session_factory() as session:
            await AdminService(session).delete_user(user_id)
        await _wait_for_outbox_sent(
            to_email=original_email, event_type=EVENT_ACCOUNT_DELETED
        )
        assert email_spy.await_count == 1

        async with async_session_factory() as session:
            await AdminService(session).delete_user(user_id)

        await _drain_outbox()
        assert email_spy.await_count == 1
        assert await _count_outbox_rows(original_email) == 1

    run_async(_run())


def test_delete_candidate_cleans_vector_and_still_emails(run_async, email_spy):
    async def _run():
        async with async_session_factory() as setup:
            user = await _seed_user(setup)
            profile = CandidateProfile(user_id=user.id, full_name="Ứng viên")
            setup.add(profile)
            await setup.flush()
            setup.add(
                Resume(
                    candidate_id=profile.id,
                    title="CV chính",
                    file_path="resumes/cv.pdf",
                    is_primary=True,
                )
            )
            await setup.commit()
            user_id, original_email, profile_id = user.id, user.email, profile.id

        with patch("app.services.admin_service.AIMatchingService") as matching_cls:
            matching_cls.return_value.delete_resume_vector = AsyncMock()
            async with async_session_factory() as session:
                await AdminService(session).delete_user(user_id)

            matching_cls.return_value.delete_resume_vector.assert_awaited_once_with(
                profile_id
            )

        await _wait_for_outbox_sent(
            to_email=original_email, event_type=EVENT_ACCOUNT_DELETED
        )

        assert email_spy.await_count == 1
        assert email_spy.await_args.args[0] == original_email

    run_async(_run())


def test_email_is_sent_only_after_commit_not_rollback(run_async, email_spy):
    async def _run():
        async with async_session_factory() as setup:
            user = await _seed_user(setup)
            await setup.commit()
            user_id, user_email = user.id, user.email

        # Rollback must never trigger the email.
        async with async_session_factory() as session:
            row = await session.get(User, user_id)
            await schedule_account_locked_email(
                session,
                to_email=row.email,
                reason="Rolled back",
                locked_at=datetime.now(timezone.utc),
            )
            await session.rollback()
        # No row was committed, so a deterministic drain can prove nothing was
        # sent even if a stale dispatch task were still pending.
        await _drain_outbox()
        email_spy.assert_not_awaited()

        # A real commit does trigger it, exactly once.
        async with async_session_factory() as session:
            row = await session.get(User, user_id)
            await schedule_account_locked_email(
                session,
                to_email=row.email,
                reason="Committed",
                locked_at=datetime.now(timezone.utc),
            )
            await session.commit()

        await _wait_for_outbox_sent(
            to_email=user_email, event_type=EVENT_ACCOUNT_LOCKED
        )

        assert email_spy.await_count == 1
        assert email_spy.await_args.args[0] == user_email

    run_async(_run())
