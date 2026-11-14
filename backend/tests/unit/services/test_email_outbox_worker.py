"""Unit tests for the outbox worker lifecycle, backoff policy and events."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services import email_outbox_worker as worker_module
from app.services.email_outbox_realtime import (
    ACTION_CLAIMED,
    ACTION_FAILED,
    ACTION_LEASE_RECOVERED,
    ACTION_RETRY_SCHEDULED,
    ACTION_SENT,
)
from app.services.email_outbox_service import compute_backoff_seconds
from app.services.email_outbox_worker import EmailOutboxWorker


class TestBackoff:
    def test_is_exponential(self):
        assert compute_backoff_seconds(1) == 2.0
        assert compute_backoff_seconds(2) == 4.0
        assert compute_backoff_seconds(3) == 8.0

    def test_is_capped(self):
        # base 2s doubling is capped at the configured ceiling (300s default).
        assert compute_backoff_seconds(20) == 300.0


class TestWorkerLifecycle:
    def test_start_is_idempotent_and_stop_terminates(self):
        async def _run():
            worker = EmailOutboxWorker(poll_interval=0.01)
            worker.process_due_messages = AsyncMock(return_value=0)

            await worker.start()
            first_task = worker._task
            await worker.start()
            assert worker._task is first_task

            await asyncio.sleep(0.03)
            await worker.stop()
            assert worker._task is None
            assert worker.process_due_messages.await_count >= 1

        asyncio.run(_run())

    def test_dispatch_now_never_raises(self):
        async def _run():
            worker = EmailOutboxWorker()
            worker.process_due_messages = AsyncMock(side_effect=RuntimeError("boom"))
            # Must swallow the error so a committed business request is unaffected.
            await worker.dispatch_now()

        asyncio.run(_run())


class _FakeSessionContext:
    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc_info) -> bool:
        return False


def _worker_with_fake_session(session) -> EmailOutboxWorker:
    return EmailOutboxWorker(session_factory=lambda: _FakeSessionContext(session))


class TestWorkerRealtimeEvents:
    """Every durable transition publishes exactly one admin event."""

    async def test_claim_schedules_processing_event_per_message(self):
        message = {"id": uuid.uuid4(), "attempts": 1, "max_attempts": 3}
        worker = _worker_with_fake_session(AsyncMock())

        with patch.object(
            worker_module, "resolve_claim_lock_hints", new=AsyncMock(return_value="HINTS")
        ), patch.object(
            worker_module, "claim_due_messages", new=AsyncMock(return_value=[message])
        ), patch.object(worker_module, "schedule_email_outbox_event") as schedule:
            claimed = await worker._claim_batch()

        assert claimed == [message]
        schedule.assert_called_once()
        kwargs = schedule.call_args.kwargs
        assert kwargs["status"] == "processing"
        assert kwargs["action"] == ACTION_CLAIMED
        assert kwargs["message_id"] == message["id"]

    async def test_sent_schedules_sent_event(self):
        message_id = uuid.uuid4()
        worker = _worker_with_fake_session(AsyncMock())

        with patch.object(
            worker_module, "mark_sent", new=AsyncMock()
        ), patch.object(worker_module, "schedule_email_outbox_event") as schedule:
            await worker._record_sent(message_id)

        schedule.assert_called_once()
        kwargs = schedule.call_args.kwargs
        assert kwargs["status"] == "sent"
        assert kwargs["action"] == ACTION_SENT
        assert kwargs["message_id"] == message_id
        assert kwargs["sent_at"] is not None

    async def test_retryable_failure_schedules_retry_event(self):
        message = {"id": uuid.uuid4(), "attempts": 1, "max_attempts": 3}
        worker = _worker_with_fake_session(AsyncMock())

        with patch.object(
            worker_module,
            "mark_failed_attempt",
            new=AsyncMock(return_value="pending"),
        ), patch.object(worker_module, "schedule_email_outbox_event") as schedule:
            await worker._record_failure(message, RuntimeError("boom"))

        schedule.assert_called_once()
        kwargs = schedule.call_args.kwargs
        assert kwargs["status"] == "pending"
        assert kwargs["action"] == ACTION_RETRY_SCHEDULED
        assert kwargs["has_error"] is True

    async def test_exhausted_failure_schedules_terminal_event(self):
        message = {"id": uuid.uuid4(), "attempts": 3, "max_attempts": 3}
        worker = _worker_with_fake_session(AsyncMock())

        with patch.object(
            worker_module,
            "mark_failed_attempt",
            new=AsyncMock(return_value="failed"),
        ), patch.object(worker_module, "schedule_email_outbox_event") as schedule:
            await worker._record_failure(message, RuntimeError("boom"))

        schedule.assert_called_once()
        kwargs = schedule.call_args.kwargs
        assert kwargs["status"] == "failed"
        assert kwargs["action"] == ACTION_FAILED
        assert kwargs["has_error"] is True

    async def test_lease_recovery_emits_single_aggregate_event(self):
        worker = _worker_with_fake_session(AsyncMock())

        with patch.object(
            worker_module, "recover_stale_leases", new=AsyncMock(return_value=2)
        ), patch.object(worker_module, "schedule_email_outbox_event") as schedule:
            await worker._recover_leases()

        schedule.assert_called_once()
        kwargs = schedule.call_args.kwargs
        assert kwargs["message_id"] is None
        assert kwargs["status"] == "pending"
        assert kwargs["action"] == ACTION_LEASE_RECOVERED

    async def test_lease_recovery_with_no_rows_emits_nothing(self):
        worker = _worker_with_fake_session(AsyncMock())

        with patch.object(
            worker_module, "recover_stale_leases", new=AsyncMock(return_value=0)
        ), patch.object(worker_module, "schedule_email_outbox_event") as schedule:
            await worker._recover_leases()

        schedule.assert_not_called()


class TestDispatchTaskOwnership:
    """Post-commit dispatch tasks are tracked and drained deterministically."""

    def test_schedule_dispatch_tracks_and_clears_task(self):
        async def _run():
            worker = EmailOutboxWorker()
            worker.dispatch_now = AsyncMock()

            task = worker.schedule_dispatch()

            assert task is not None
            assert task in worker._dispatch_tasks
            await task
            assert task not in worker._dispatch_tasks
            worker.dispatch_now.assert_awaited_once()

        asyncio.run(_run())

    def test_schedule_dispatch_runs_when_poll_loop_disabled(self, monkeypatch):
        async def _run():
            worker = EmailOutboxWorker()
            worker.dispatch_now = AsyncMock()
            monkeypatch.setattr(
                worker_module.settings, "EMAIL_OUTBOX_ENABLED", False
            )

            task = worker.schedule_dispatch()

            assert task is not None
            await task
            worker.dispatch_now.assert_awaited_once()

        asyncio.run(_run())

    def test_drain_waits_for_owned_tasks(self):
        async def _run():
            worker = EmailOutboxWorker()
            started = asyncio.Event()
            finish = asyncio.Event()

            async def _dispatch():
                started.set()
                await finish.wait()

            worker.dispatch_now = _dispatch
            task = worker.schedule_dispatch()
            assert task is not None
            await started.wait()

            drainer = asyncio.create_task(
                worker.drain_dispatch_tasks(timeout=1.0)
            )
            await asyncio.sleep(0.01)
            assert not drainer.done()

            finish.set()
            await asyncio.wait_for(drainer, timeout=1.0)
            assert task.done()

        asyncio.run(_run())

    def test_drain_does_not_touch_unowned_loop_tasks(self):
        async def _run():
            worker = EmailOutboxWorker()
            unowned = asyncio.create_task(asyncio.sleep(10))
            try:
                await worker.drain_dispatch_tasks(timeout=0.01)
                assert not unowned.done()
            finally:
                unowned.cancel()
                await asyncio.gather(unowned, return_exceptions=True)

        asyncio.run(_run())

    def test_drain_cancels_stalled_task_and_raises_actionable_error(self):
        async def _run():
            worker = EmailOutboxWorker()

            async def _stalled():
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    # Ignore the first cancellation long enough to exercise the
                    # bounded grace period and the teardown failure path.
                    await asyncio.sleep(0.2)
                    raise

            worker.dispatch_now = _stalled
            task = worker.schedule_dispatch()
            assert task is not None
            try:
                with pytest.raises(RuntimeError, match="did not stop"):
                    await worker.drain_dispatch_tasks(
                        timeout=0.01, cancel_grace=0.01
                    )
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        asyncio.run(_run())

    def test_reset_keeps_pending_dispatch_drainable(self):
        async def _run():
            worker_module.reset_default_worker()
            worker = worker_module.get_default_worker()
            finish = asyncio.Event()

            async def _dispatch():
                await finish.wait()

            worker.dispatch_now = _dispatch
            task = worker.schedule_dispatch()
            assert task is not None

            worker_module.reset_default_worker()

            drainer = asyncio.create_task(
                worker_module.drain_default_worker_dispatch_tasks(timeout=1.0)
            )
            await asyncio.sleep(0.01)
            assert not drainer.done()

            finish.set()
            await asyncio.wait_for(drainer, timeout=1.0)
            assert task.done()

        asyncio.run(_run())
