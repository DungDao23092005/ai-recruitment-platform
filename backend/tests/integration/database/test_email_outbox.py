"""Integration tests for the durable transactional outbox (SQL Server).

These exercise the real database and the real worker, with ``EmailService``
spied so no provider is ever contacted. They cover atomic enqueue, commit-only
visibility, delivery, backoff/terminal failure, lease recovery, concurrent
claims, idempotency and retention.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select, text

from app.database.base_class import utc_now
from app.database.session import async_session_factory
from app.domain.enums import OutboxStatus
from app.models import EmailOutbox
from app.services.email_outbox_service import (
    EmailOutboxService,
    claim_due_messages,
    enqueue_email,
    recover_stale_leases,
    reset_claim_hint_cache,
    resolve_claim_lock_hints,
)
from app.services.email_outbox_worker import EmailOutboxWorker, reset_default_worker
from app.services.email_service import EmailService

pytestmark = pytest.mark.integration


@pytest.fixture
def email_spy():
    spy = AsyncMock()
    with patch.object(EmailService, "send_email", new=spy):
        yield spy


@pytest.fixture(autouse=True)
def _isolate_worker_state():
    reset_claim_hint_cache()
    reset_default_worker()
    yield
    reset_default_worker()


def _worker(**kwargs) -> EmailOutboxWorker:
    kwargs.setdefault("batch_size", 20)
    kwargs.setdefault("lease_seconds", 300)
    return EmailOutboxWorker(session_factory=async_session_factory, **kwargs)


async def _enqueue(session, **overrides) -> EmailOutbox | None:
    values = {
        "event_type": "test_event",
        "to_email": f"{uuid.uuid4().hex[:8]}@example.com",
        "subject": "Chủ đề",
        "html_body": "<p>Xin chào</p>",
        "text_body": "Xin chào",
    }
    values.update(overrides)
    return await enqueue_email(session, **values)


async def _get(session, message_id) -> EmailOutbox | None:
    return await session.get(EmailOutbox, message_id)


async def _count(session, status: OutboxStatus | None = None) -> int:
    query = select(func.count()).select_from(EmailOutbox)
    if status is not None:
        query = query.where(EmailOutbox.status == status.value)
    return int((await session.execute(query)).scalar_one())


class TestEnqueueAtomicity:
    def test_commit_persists_pending_message(self, run_async, email_spy):
        async def _test():
            async with async_session_factory() as session:
                await _enqueue(session)
                await session.commit()

            async with async_session_factory() as session:
                assert await _count(session, OutboxStatus.PENDING) == 1

            # Enqueue alone must never contact the provider.
            email_spy.assert_not_awaited()

        run_async(_test())

    def test_rollback_discards_message(self, run_async, email_spy):
        async def _test():
            async with async_session_factory() as session:
                await _enqueue(session)
                await session.rollback()

            async with async_session_factory() as session:
                assert await _count(session) == 0

            await _worker().process_due_messages()
            email_spy.assert_not_awaited()

        run_async(_test())

    def test_uncommitted_message_is_invisible_to_worker(self, run_async, email_spy):
        async def _test():
            async with async_session_factory() as session:
                await _enqueue(session)
                # Deliberately not committed yet.
                await _worker().process_due_messages()
                email_spy.assert_not_awaited()

                await session.commit()

            await _worker().process_due_messages()
            email_spy.assert_awaited_once()

        run_async(_test())


class TestDeliveryOutcomes:
    def test_success_marks_sent_with_timestamp(self, run_async, email_spy):
        async def _test():
            async with async_session_factory() as session:
                row = await _enqueue(session)
                await session.commit()
                message_id = row.id

            sent = await _worker().process_due_messages()
            assert sent == 1

            async with async_session_factory() as session:
                row = await _get(session, message_id)
                assert row.status == OutboxStatus.SENT.value
                assert row.sent_at is not None
                assert row.attempts == 1
                assert row.processing_started_at is None
                assert row.last_error is None

            email_spy.assert_awaited_once()
            to_email, subject, html, text_body = email_spy.await_args.args
            assert subject == "Chủ đề"
            assert "Xin chào" in html
            assert "Xin chào" in text_body

        run_async(_test())

    def test_failure_schedules_backoff_retry(self, run_async, email_spy):
        email_spy.side_effect = RuntimeError("smtp exploded")

        async def _test():
            async with async_session_factory() as session:
                row = await _enqueue(session)
                await session.commit()
                message_id = row.id

            await _worker().process_due_messages()

            async with async_session_factory() as session:
                row = await _get(session, message_id)
                assert row.status == OutboxStatus.PENDING.value
                assert row.attempts == 1
                assert row.next_attempt_at > utc_now()
                assert "smtp exploded" in (row.last_error or "")

            # Not due yet: a second pass without waiting claims nothing.
            email_spy.reset_mock()
            sent = await _worker().process_due_messages()
            assert sent == 0
            email_spy.assert_not_awaited()

        run_async(_test())

    def test_exhausted_attempts_become_terminal_failure(self, run_async, email_spy):
        email_spy.side_effect = RuntimeError("permanent failure")

        async def _test():
            async with async_session_factory() as session:
                row = await _enqueue(session, max_attempts=1)
                await session.commit()
                message_id = row.id

            await _worker().process_due_messages()

            async with async_session_factory() as session:
                row = await _get(session, message_id)
                assert row.status == OutboxStatus.FAILED.value
                assert row.attempts == 1
                assert "permanent failure" in (row.last_error or "")

        run_async(_test())

    def test_error_isolation_between_messages(self, run_async, email_spy):
        async def _send(to_email, subject, html, text_body):
            if "bad" in to_email:
                raise RuntimeError("poison")
            return None

        email_spy.side_effect = _send

        async def _test():
            async with async_session_factory() as session:
                bad = await _enqueue(session, to_email="bad@example.com")
                good = await _enqueue(session, to_email="good@example.com")
                await session.commit()
                bad_id, good_id = bad.id, good.id

            await _worker().process_due_messages()

            async with async_session_factory() as session:
                assert (
                    await _get(session, good_id)
                ).status == OutboxStatus.SENT.value
                assert (
                    await _get(session, bad_id)
                ).status == OutboxStatus.PENDING.value

        run_async(_test())


class TestLeaseAndConcurrency:
    def test_stale_lease_is_recovered_then_delivered(
        self, run_async, email_spy
    ):
        async def _test():
            async with async_session_factory() as session:
                row = await _enqueue(session)
                await session.commit()
                message_id = row.id
                await session.execute(
                    text(
                        "UPDATE email_outbox SET status='processing', "
                        "processing_started_at=:old, attempts=1 WHERE id=:id"
                    ),
                    {"old": utc_now() - timedelta(seconds=600), "id": message_id},
                )
                await session.commit()

            await _worker(lease_seconds=60).process_due_messages()

            async with async_session_factory() as session:
                row = await _get(session, message_id)
                assert row.status == OutboxStatus.SENT.value
                assert row.attempts == 2

            email_spy.assert_awaited_once()

        run_async(_test())

    def test_fresh_lease_is_not_recovered(self, run_async):
        async def _test():
            async with async_session_factory() as session:
                row = await _enqueue(session)
                await session.commit()
                message_id = row.id
                await session.execute(
                    text(
                        "UPDATE email_outbox SET status='processing', "
                        "processing_started_at=:now WHERE id=:id"
                    ),
                    {"now": utc_now(), "id": message_id},
                )
                await session.commit()

            async with async_session_factory() as session:
                recovered = await recover_stale_leases(session, lease_seconds=300)
                await session.commit()
            assert recovered == 0

            async with async_session_factory() as session:
                assert (
                    await _get(session, message_id)
                ).status == OutboxStatus.PROCESSING.value

        run_async(_test())

    def test_concurrent_claimers_are_disjoint(self, run_async):
        async def _test():
            async with async_session_factory() as session:
                for _ in range(6):
                    await _enqueue(session)
                await session.commit()

            async def claim() -> set[str]:
                async with async_session_factory() as session:
                    hints = await resolve_claim_lock_hints(session)
                    claimed = await claim_due_messages(
                        session, batch_size=6, lock_hints=hints
                    )
                    await session.commit()
                    return {str(item["id"]) for item in claimed}

            first, second = await asyncio.gather(claim(), claim())
            assert first.isdisjoint(second)
            assert len(first) + len(second) == 6

        run_async(_test())


class TestIdempotencyAndRetention:
    def test_duplicate_key_enqueues_once(self, run_async):
        async def _test():
            async with async_session_factory() as session:
                first = await _enqueue(session, idempotency_key="dup-key")
                await session.commit()
                assert first is not None

            async with async_session_factory() as session:
                duplicate = await _enqueue(session, idempotency_key="dup-key")
                await session.commit()
                assert duplicate is None

            async with async_session_factory() as session:
                assert await _count(session) == 1

        run_async(_test())

    def test_purge_removes_only_old_sent_messages(self, run_async):
        async def _test():
            now = utc_now()
            async with async_session_factory() as session:
                session.add_all(
                    [
                        EmailOutbox(
                            event_type="t",
                            to_email="old-sent@example.com",
                            subject="s",
                            html_body="h",
                            text_body="t",
                            status=OutboxStatus.SENT.value,
                            attempts=1,
                            max_attempts=3,
                            next_attempt_at=now - timedelta(days=10),
                            sent_at=now - timedelta(days=10),
                        ),
                        EmailOutbox(
                            event_type="t",
                            to_email="fresh-sent@example.com",
                            subject="s",
                            html_body="h",
                            text_body="t",
                            status=OutboxStatus.SENT.value,
                            attempts=1,
                            max_attempts=3,
                            next_attempt_at=now,
                            sent_at=now,
                        ),
                        EmailOutbox(
                            event_type="t",
                            to_email="pending@example.com",
                            subject="s",
                            html_body="h",
                            text_body="t",
                            status=OutboxStatus.PENDING.value,
                            attempts=0,
                            max_attempts=3,
                            next_attempt_at=now - timedelta(days=10),
                        ),
                        EmailOutbox(
                            event_type="t",
                            to_email="failed@example.com",
                            subject="s",
                            html_body="h",
                            text_body="t",
                            status=OutboxStatus.FAILED.value,
                            attempts=3,
                            max_attempts=3,
                            next_attempt_at=now - timedelta(days=10),
                            last_error="boom",
                        ),
                    ]
                )
                await session.commit()

            async with async_session_factory() as session:
                deleted = await EmailOutboxService(session).purge_sent(
                    older_than_days=1, now=now
                )
            assert deleted == 1

            async with async_session_factory() as session:
                remaining = {
                    row.to_email
                    for row in (
                        await session.execute(select(EmailOutbox))
                    ).scalars()
                }
            assert remaining == {
                "fresh-sent@example.com",
                "pending@example.com",
                "failed@example.com",
            }

        run_async(_test())

    def test_bodies_are_bounded_on_enqueue(self, run_async):
        async def _test():
            async with async_session_factory() as session:
                row = await _enqueue(
                    session,
                    subject="x" * 900,
                    to_email=("y" * 400) + "@example.com",
                    idempotency_key="k" * 400,
                )
                await session.commit()
                message_id = row.id

            async with async_session_factory() as session:
                row = await _get(session, message_id)
                assert len(row.subject) == 500
                assert len(row.to_email) == 320
                assert len(row.idempotency_key) == 255

        run_async(_test())
