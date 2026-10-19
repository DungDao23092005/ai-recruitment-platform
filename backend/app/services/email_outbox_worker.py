"""Background worker that delivers queued transactional-outbox emails.

The worker polls the ``email_outbox`` table, claims due messages atomically,
calls the configured email provider *outside* any database transaction, and
records the terminal outcome. It retries transient failures with backoff,
recovers leases abandoned by a crashed worker, and isolates per-message errors
so one poisoned message cannot stall the queue.

Every pass uses its own short-lived session: no request-scoped session is ever
reused, and no SQL transaction is held open across a provider call.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.database.base_class import utc_now
from app.database.session import async_session_factory
from app.services.email_outbox_service import (
    claim_due_messages,
    compute_backoff_seconds,
    mark_failed_attempt,
    mark_sent,
    recover_stale_leases,
    resolve_claim_lock_hints,
)
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


class EmailOutboxWorker:
    """Polls and delivers outbox messages with at-least-once semantics."""

    def __init__(
        self,
        *,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        email_service: Optional[EmailService] = None,
        poll_interval: Optional[float] = None,
        batch_size: Optional[int] = None,
        lease_seconds: Optional[int] = None,
    ) -> None:
        self._session_factory = session_factory or async_session_factory
        self._email_service = email_service
        self.poll_interval = (
            poll_interval
            if poll_interval is not None
            else settings.EMAIL_OUTBOX_POLL_INTERVAL_SECONDS
        )
        self.batch_size = (
            batch_size if batch_size is not None else settings.EMAIL_OUTBOX_BATCH_SIZE
        )
        self.lease_seconds = (
            lease_seconds
            if lease_seconds is not None
            else settings.EMAIL_OUTBOX_LEASE_SECONDS
        )
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None
        self._lock = asyncio.Lock()

    @property
    def email_service(self) -> EmailService:
        if self._email_service is None:
            self._email_service = EmailService()
        return self._email_service

    # --------------------------------------------------------------- lifecycle

    async def start(self) -> None:
        """Start the background poll loop (idempotent)."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="email-outbox-worker")
        logger.info(
            "Email outbox worker started (interval=%.1fs batch=%d lease=%ds)",
            self.poll_interval,
            self.batch_size,
            self.lease_seconds,
        )

    async def stop(self) -> None:
        """Signal shutdown and wait for the current pass to finish."""
        self._stop_event.set()
        task = self._task
        self._task = None
        if task is None:
            return
        try:
            await asyncio.wait_for(task, timeout=max(self.poll_interval, 5.0) + 5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            task.cancel()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Email outbox worker stopped with error: %s", exc)
        logger.info("Email outbox worker stopped")

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.process_due_messages()
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Email outbox pass failed: %s", exc)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.poll_interval
                )
            except asyncio.TimeoutError:
                pass

    async def dispatch_now(self) -> None:
        """Deliver any due message immediately (post-commit latency hint).

        Called after a business transaction commits so the notification is
        delivered without waiting for the next poll. The durable row is still
        the source of truth: if this pass fails for any reason, the poll loop
        delivers the message later. Errors are logged, never raised, so a
        caller's request handling is unaffected.
        """
        try:
            await self.process_due_messages()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Immediate email outbox dispatch failed: %s", exc)

    # ------------------------------------------------------------------ passes

    async def process_due_messages(self) -> int:
        """Recover leases, claim a batch, and deliver it. Returns sent count."""
        async with self._lock:
            await self._recover_leases()
            claimed = await self._claim_batch()
            for message in claimed:
                await self._deliver(message)
            return len(claimed)

    async def _recover_leases(self) -> None:
        async with self._session_factory() as session:
            try:
                recovered = await recover_stale_leases(
                    session, lease_seconds=self.lease_seconds
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        if recovered:
            logger.warning(
                "Recovered %d stale email outbox lease(s)", recovered
            )

    async def _claim_batch(self) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            hints = await resolve_claim_lock_hints(session)
            try:
                messages = await claim_due_messages(
                    session, batch_size=self.batch_size, lock_hints=hints
                )
                # Commit the claim BEFORE any provider call so a concurrent
                # worker can never see these rows as pending again.
                await session.commit()
                return messages
            except Exception:
                await session.rollback()
                raise

    async def _deliver(self, message: dict[str, Any]) -> None:
        message_id = message["id"]
        try:
            await self.email_service.send_email(
                message["to_email"],
                message["subject"],
                message["html_body"],
                message["text_body"],
            )
        except Exception as exc:
            logger.warning(
                "Email outbox message %s delivery failed (attempt %s/%s): %s",
                message_id,
                message["attempts"],
                message["max_attempts"],
                exc,
                extra={"outbox_message_id": str(message_id)},
            )
            await self._record_failure(message, exc)
            return
        await self._record_sent(message_id)

    async def _record_sent(self, message_id: Any) -> None:
        try:
            async with self._session_factory() as session:
                await mark_sent(session, message_id=message_id)
                await session.commit()
            logger.info(
                "Email outbox message %s delivered",
                message_id,
                extra={"outbox_message_id": str(message_id)},
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "Failed to record SENT for email outbox message %s: %s",
                message_id,
                exc,
                extra={"outbox_message_id": str(message_id)},
            )

    async def _record_failure(self, message: dict[str, Any], exc: Exception) -> None:
        attempts = int(message["attempts"])
        max_attempts = int(message["max_attempts"])
        next_attempt_at = None
        if attempts < max_attempts:
            next_attempt_at = utc_now() + timedelta(
                seconds=compute_backoff_seconds(attempts)
            )
        try:
            async with self._session_factory() as session:
                status = await mark_failed_attempt(
                    session,
                    message_id=message["id"],
                    attempts=attempts,
                    max_attempts=max_attempts,
                    error=str(exc),
                    next_attempt_at=next_attempt_at,
                )
                await session.commit()
            logger.info(
                "Email outbox message %s -> %s after attempt %d/%d",
                message["id"],
                status,
                attempts,
                max_attempts,
                extra={"outbox_message_id": str(message["id"])},
            )
        except Exception as record_exc:  # pragma: no cover - defensive
            logger.error(
                "Failed to record failure for email outbox message %s: %s",
                message["id"],
                record_exc,
                extra={"outbox_message_id": str(message["id"])},
            )


# --------------------------------------------------------------------- default

_default_worker: Optional[EmailOutboxWorker] = None


def get_default_worker() -> EmailOutboxWorker:
    """Return the process-wide worker shared by the poll loop and the signals."""
    global _default_worker
    if _default_worker is None:
        _default_worker = EmailOutboxWorker()
    return _default_worker


def reset_default_worker() -> None:
    """Drop the process-wide worker (used by tests)."""
    global _default_worker
    _default_worker = None


async def start_default_worker() -> None:
    """Start the shared worker when the outbox feature is enabled."""
    if not settings.EMAIL_OUTBOX_ENABLED:
        logger.info("Email outbox worker disabled (EMAIL_OUTBOX_ENABLED=false)")
        return
    await get_default_worker().start()


async def stop_default_worker() -> None:
    """Stop the shared worker if it was created."""
    global _default_worker
    if _default_worker is not None:
        await _default_worker.stop()


def signal_dispatch_after_commit(session: AsyncSession) -> None:
    """Wake the worker once ``session`` commits.

    This is purely a latency optimisation: it never touches the provider
    itself, it only asks the worker to drain committed rows immediately instead
    of waiting for the next poll. If the signal is lost (process crash, no
    running loop) the durable row is still delivered by the poll loop, so no
    notification is ever dropped. Registration is defensive because a session
    that cannot host event listeners (for example a mock) must never make the
    caller fail.
    """

    def _run_after_commit(sync_session) -> None:  # noqa: ARG001
        try:
            asyncio.create_task(get_default_worker().dispatch_now())
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Could not signal email outbox dispatch: %s", exc)

    try:
        event.listen(
            session.sync_session, "after_commit", _run_after_commit, once=True
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Could not register email outbox dispatch hook: %s", exc)
