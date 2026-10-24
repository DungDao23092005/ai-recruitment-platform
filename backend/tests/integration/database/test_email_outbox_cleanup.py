"""Live SQL Server coverage for the outbox cleanup application lock.

The cleanup lock is session-scoped, so it is only safe if the same physical
SQL Server connection acquires and releases it. These tests use the real worker
methods and verify ``@@SPID`` and ``APPLOCK_MODE`` rather than mock call order.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, text

from app.database.base_class import utc_now
from app.database.session import async_session_factory
from app.domain.enums import OutboxStatus
from app.models import EmailOutbox
from app.services.email_outbox_service import EmailOutboxService
from app.services.email_outbox_worker import (
    CLEANUP_LOCK_RESOURCE,
    EmailOutboxWorker,
)

pytestmark = pytest.mark.integration


async def _spid(session) -> int:
    return int(await session.scalar(text("SELECT @@SPID")))


async def _lock_mode(session) -> str:
    return str(
        await session.scalar(
            text("SELECT APPLOCK_MODE('public', :resource, 'Session')"),
            {"resource": CLEANUP_LOCK_RESOURCE},
        )
    )


async def _release_or_discard(worker: EmailOutboxWorker, session) -> bool:
    try:
        released = await worker._release_cleanup_lock(session)
    except Exception:
        released = False
    if not released:
        await worker._discard_lock_connection(session)
    return released


def test_cleanup_lock_is_released_on_the_same_physical_session(run_async):
    async def _test():
        now = utc_now()
        old_email = f"cleanup-old-{uuid.uuid4().hex}@example.com"
        fresh_email = f"cleanup-fresh-{uuid.uuid4().hex}@example.com"
        pending_email = f"cleanup-pending-{uuid.uuid4().hex}@example.com"
        failed_email = f"cleanup-failed-{uuid.uuid4().hex}@example.com"

        async with async_session_factory() as seed_session:
            seed_session.add_all(
                [
                    EmailOutbox(
                        event_type="cleanup_lock_test",
                        to_email=old_email,
                        subject="old sent",
                        html_body="<p>old</p>",
                        text_body="old",
                        status=OutboxStatus.SENT.value,
                        attempts=1,
                        max_attempts=3,
                        next_attempt_at=now - timedelta(days=31),
                        sent_at=now - timedelta(days=31),
                    ),
                    EmailOutbox(
                        event_type="cleanup_lock_test",
                        to_email=fresh_email,
                        subject="fresh sent",
                        html_body="<p>fresh</p>",
                        text_body="fresh",
                        status=OutboxStatus.SENT.value,
                        attempts=1,
                        max_attempts=3,
                        next_attempt_at=now,
                        sent_at=now - timedelta(days=1),
                    ),
                    EmailOutbox(
                        event_type="cleanup_lock_test",
                        to_email=pending_email,
                        subject="pending",
                        html_body="<p>pending</p>",
                        text_body="pending",
                        status=OutboxStatus.PENDING.value,
                        attempts=0,
                        max_attempts=3,
                        next_attempt_at=now - timedelta(days=31),
                    ),
                    EmailOutbox(
                        event_type="cleanup_lock_test",
                        to_email=failed_email,
                        subject="failed",
                        html_body="<p>failed</p>",
                        text_body="failed",
                        status=OutboxStatus.FAILED.value,
                        attempts=3,
                        max_attempts=3,
                        next_attempt_at=now - timedelta(days=31),
                        last_error="boom",
                    ),
                ]
            )
            await seed_session.commit()

        worker = EmailOutboxWorker(session_factory=async_session_factory)
        released = False
        async with async_session_factory() as lock_session:
            assert await worker._acquire_cleanup_lock(lock_session) is True
            try:
                lock_spid = await _spid(lock_session)
                assert await _lock_mode(lock_session) == "Exclusive"

                # The lock must block another physical session while held.
                async with async_session_factory() as contender:
                    contender_acquired = await worker._acquire_cleanup_lock(
                        contender
                    )
                    try:
                        assert contender_acquired is False
                    finally:
                        if contender_acquired:
                            await _release_or_discard(worker, contender)
                        else:
                            await contender.rollback()

                # Cleanup runs on a separate work session and commits its own
                # transaction; the lock session must remain checked out.
                async with async_session_factory() as work_session:
                    work_spid = await _spid(work_session)
                    assert work_spid != lock_spid
                    deleted = await EmailOutboxService(
                        work_session
                    ).purge_sent(older_than_days=30, now=now)
                assert deleted == 1

                # The committed cleanup is visible, and the original lock
                # session still has the same SPID and owns the lock.
                async with async_session_factory() as observer:
                    remaining = set(
                        (
                            await observer.execute(
                                select(EmailOutbox.to_email)
                            )
                        ).scalars()
                    )
                assert remaining == {
                    fresh_email,
                    pending_email,
                    failed_email,
                }
                assert await _spid(lock_session) == lock_spid
                assert await _lock_mode(lock_session) == "Exclusive"

                released = await worker._release_cleanup_lock(lock_session)
                assert released is True
            finally:
                if not released:
                    await _release_or_discard(worker, lock_session)

        # A different session can acquire the same resource after release.
        async with async_session_factory() as contender:
            acquired = await worker._acquire_cleanup_lock(contender)
            assert acquired is True
            try:
                assert await _lock_mode(contender) == "Exclusive"
            finally:
                assert await _release_or_discard(worker, contender) is True

    run_async(_test())
