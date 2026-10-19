"""Unit tests for the outbox worker lifecycle and backoff policy."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

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
