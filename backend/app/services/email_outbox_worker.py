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
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.database.base_class import utc_now
from app.database.session import async_session_factory
from app.domain.enums import OutboxStatus
from app.services.email_outbox_realtime import (
    ACTION_CLAIMED,
    ACTION_FAILED,
    ACTION_LEASE_RECOVERED,
    ACTION_RETRY_SCHEDULED,
    ACTION_SENT,
    schedule_email_outbox_event,
)
from app.services.email_outbox_service import (
    EmailOutboxService,
    claim_due_messages,
    compute_backoff_seconds,
    mark_failed_attempt,
    mark_sent,
    recover_stale_leases,
    resolve_claim_lock_hints,
)
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60
CLEANUP_CONTENTION_COOLDOWN_SECONDS = 10 * 60
CLEANUP_FAILURE_RETRY_SECONDS = 60 * 60
CLEANUP_LOCK_RESOURCE = f"email_outbox_cleanup:{settings.DATABASE_NAME}"

GET_CLEANUP_LOCK_SQL = text(
    """
    DECLARE @result int;
    EXEC @result = sp_getapplock
        @Resource = :resource,
        @LockMode = 'Exclusive',
        @LockOwner = 'Session',
        @LockTimeout = 0;
    SELECT @result AS result;
    """
)

RELEASE_CLEANUP_LOCK_SQL = text(
    """
    DECLARE @result int;
    EXEC @result = sp_releaseapplock
        @Resource = :resource,
        @LockOwner = 'Session';
    SELECT @result AS result;
    """
)


class CleanupLockReleaseError(RuntimeError):
    """Raised when a cleanup lock may still be held by the connection."""


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
        cleanup_interval_seconds: Optional[float] = None,
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
        self._cleanup_lock = asyncio.Lock()

        self._started_at: datetime | None = None
        self._last_heartbeat_at: datetime | None = None
        self._last_run_at: datetime | None = None
        self._last_success_at: datetime | None = None
        self._last_outcome = "not_started"
        self._consecutive_failures = 0
        self._last_error_type: str | None = None
        self._delivered_total = 0
        self._delivery_failures_total = 0

        self.cleanup_interval_seconds = float(
            cleanup_interval_seconds
            if cleanup_interval_seconds is not None
            else CLEANUP_INTERVAL_SECONDS
        )
        self._next_cleanup_at = utc_now() + timedelta(
            seconds=self.cleanup_interval_seconds
        )
        self._cleanup_last_attempt_at: datetime | None = None
        self._cleanup_last_success_at: datetime | None = None
        self._cleanup_last_outcome = "not_started"
        self._cleanup_consecutive_failures = 0
        self._cleanup_last_error_type: str | None = None
        self._cleanup_deleted_total = 0
        self._cleanup_release_failures = 0

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
        self._started_at = utc_now()
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
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover - defensive
                logger.exception("Email outbox pass failed")
            try:
                await self._maybe_run_cleanup()
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover - defensive
                logger.exception("Email outbox cleanup pass failed")
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
        try:
            async with self._lock:
                await self._recover_leases()
                claimed = await self._claim_batch()
                for message in claimed:
                    await self._deliver(message)
                    self._last_heartbeat_at = utc_now()
                count = len(claimed)
        except asyncio.CancelledError:
            self._record_run_outcome("cancelled")
            raise
        except Exception as exc:
            self._record_run_outcome("failure", exc)
            raise
        self._record_run_outcome("success")
        return count

    def _record_run_outcome(
        self, outcome: str, exc: Exception | None = None
    ) -> None:
        moment = utc_now()
        self._last_run_at = moment
        self._last_heartbeat_at = moment
        self._last_outcome = outcome
        if outcome == "failure":
            self._consecutive_failures += 1
            self._last_error_type = type(exc).__name__ if exc else "Exception"
        elif outcome in {"success", "skipped"}:
            self._consecutive_failures = 0
            self._last_error_type = None
            if outcome == "success":
                self._last_success_at = moment

    def health_snapshot(self) -> dict[str, Any]:
        """Return allowlisted operational state with no exception text."""
        return {
            "enabled": bool(settings.EMAIL_OUTBOX_ENABLED),
            "running": self._task is not None and not self._task.done(),
            "started_at": _isoformat(self._started_at),
            "last_heartbeat_at": _isoformat(self._last_heartbeat_at),
            "last_run_at": _isoformat(self._last_run_at),
            "last_success_at": _isoformat(self._last_success_at),
            "last_outcome": self._last_outcome,
            "consecutive_failures": self._consecutive_failures,
            "last_error_type": self._last_error_type,
            "delivered_total": self._delivered_total,
            "delivery_failures_total": self._delivery_failures_total,
            "heartbeat_timeout_seconds": max(float(self.poll_interval) * 3, 300.0),
            "cleanup": {
                "last_attempt_at": _isoformat(self._cleanup_last_attempt_at),
                "last_success_at": _isoformat(self._cleanup_last_success_at),
                "last_outcome": self._cleanup_last_outcome,
                "consecutive_failures": self._cleanup_consecutive_failures,
                "last_error_type": self._cleanup_last_error_type,
                "deleted_total": self._cleanup_deleted_total,
                "release_failures": self._cleanup_release_failures,
                "next_attempt_at": _isoformat(self._next_cleanup_at),
            },
        }

    async def _recover_leases(self) -> None:
        async with self._session_factory() as session:
            try:
                recovered = await recover_stale_leases(
                    session, lease_seconds=self.lease_seconds
                )
                if recovered:
                    # One aggregate signal for the whole sweep: stale rows carry
                    # no usable identity here and per-row noise is unwanted.
                    schedule_email_outbox_event(
                        session,
                        message_id=None,
                        status=OutboxStatus.PENDING.value,
                        action=ACTION_LEASE_RECOVERED,
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
                # Bounded by ``batch_size``: one PROCESSING event per claimed row.
                for message in messages:
                    schedule_email_outbox_event(
                        session,
                        message_id=message["id"],
                        status=OutboxStatus.PROCESSING.value,
                        action=ACTION_CLAIMED,
                        attempts=int(message["attempts"]),
                        max_attempts=int(message["max_attempts"]),
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
            self._delivery_failures_total += 1
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
        self._delivered_total += 1
        await self._record_sent(message_id)

    async def _record_sent(self, message_id: Any) -> None:
        try:
            async with self._session_factory() as session:
                moment = utc_now()
                await mark_sent(session, message_id=message_id, now=moment)
                schedule_email_outbox_event(
                    session,
                    message_id=message_id,
                    status=OutboxStatus.SENT.value,
                    action=ACTION_SENT,
                    sent_at=moment,
                )
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
                schedule_email_outbox_event(
                    session,
                    message_id=message["id"],
                    status=status,
                    action=(
                        ACTION_RETRY_SCHEDULED
                        if status == OutboxStatus.PENDING.value
                        else ACTION_FAILED
                    ),
                    attempts=attempts,
                    max_attempts=max_attempts,
                    next_attempt_at=next_attempt_at,
                    # A failure occurred, but the provider error text is never
                    # included - only a boolean flag crosses the wire.
                    has_error=True,
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

    # --------------------------------------------------------------- cleanup

    async def cleanup_now(
        self, now: datetime | None = None
    ) -> dict[str, Any]:
        """Attempt an outbox cleanup immediately (used by tests and ops)."""
        async with self._cleanup_lock:
            return await self._run_cleanup(now or utc_now())

    async def _maybe_run_cleanup(self) -> None:
        moment = utc_now()
        if (
            self._next_cleanup_at is not None
            and moment < self._next_cleanup_at
        ):
            return
        await self.cleanup_now(moment)

    async def _run_cleanup(self, moment: datetime) -> dict[str, Any]:
        self._cleanup_last_attempt_at = moment
        try:
            result = await self._cleanup_once(moment)
        except asyncio.CancelledError:
            self._cleanup_last_outcome = "cancelled"
            self._next_cleanup_at = moment + timedelta(
                seconds=CLEANUP_FAILURE_RETRY_SECONDS
            )
            raise
        except Exception as exc:
            self._cleanup_consecutive_failures += 1
            self._cleanup_last_outcome = "failure"
            self._cleanup_last_error_type = (
                "LockReleaseError"
                if isinstance(exc, CleanupLockReleaseError)
                else type(exc).__name__
            )
            self._next_cleanup_at = moment + timedelta(
                seconds=CLEANUP_FAILURE_RETRY_SECONDS
            )
            logger.warning(
                "Email outbox cleanup failed type=%s", type(exc).__name__
            )
            return {"outcome": "failure", "deleted": 0}

        if not result["acquired"]:
            self._cleanup_last_outcome = "skipped"
            self._next_cleanup_at = moment + timedelta(
                seconds=CLEANUP_CONTENTION_COOLDOWN_SECONDS
            )
            return {"outcome": "skipped", "deleted": 0}

        self._cleanup_last_outcome = "success"
        self._cleanup_last_success_at = moment
        self._cleanup_consecutive_failures = 0
        self._cleanup_last_error_type = None
        self._cleanup_deleted_total += int(result["deleted"])
        self._next_cleanup_at = moment + timedelta(
            seconds=self.cleanup_interval_seconds
        )
        if result["deleted"]:
            logger.info(
                "Email outbox cleanup removed %d sent message(s)",
                result["deleted"],
            )
        return {"outcome": "success", "deleted": int(result["deleted"])}

    async def _cleanup_once(self, moment: datetime) -> dict[str, Any]:
        async with self._session_factory() as lock_session:
            acquired = await self._acquire_cleanup_lock(lock_session)
            if not acquired:
                await _safe_rollback(lock_session)
                return {"acquired": False, "deleted": 0}

            released = False
            release_attempted = False
            try:
                async with self._session_factory() as work_session:
                    deleted = await EmailOutboxService(
                        work_session
                    ).purge_sent(now=moment)

                release_attempted = True
                released = await self._release_cleanup_lock(lock_session)
                if not released:
                    raise CleanupLockReleaseError(
                        "Email outbox cleanup lock release failed"
                    )
                return {"acquired": True, "deleted": int(deleted)}
            except asyncio.CancelledError:
                if not release_attempted:
                    released = await self._release_cleanup_lock(lock_session)
                raise
            except Exception:
                if not release_attempted:
                    released = await self._release_cleanup_lock(lock_session)
                raise
            finally:
                if not released:
                    await self._discard_lock_connection(lock_session)

    async def _acquire_cleanup_lock(self, session: AsyncSession) -> bool:
        try:
            result = await session.scalar(
                GET_CLEANUP_LOCK_SQL, {"resource": CLEANUP_LOCK_RESOURCE}
            )
        except Exception:
            await _safe_rollback(session)
            raise
        return result is not None and int(result) >= 0

    async def _release_cleanup_lock(self, session: AsyncSession) -> bool:
        task = asyncio.create_task(
            self._release_cleanup_lock_once(session),
            name="email-outbox-cleanup-release",
        )
        task.add_done_callback(_consume_task_result)
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Let the shielded release finish before propagating cancellation,
            # so the caller never returns a connection that may still own the
            # lock. Re-raise rather than swallowing task cancellation.
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                pass
            raise

    async def _release_cleanup_lock_once(
        self, session: AsyncSession
    ) -> bool:
        try:
            result = await session.scalar(
                RELEASE_CLEANUP_LOCK_SQL,
                {"resource": CLEANUP_LOCK_RESOURCE},
            )
            if result is None or int(result) < 0:
                self._cleanup_release_failures += 1
                self._cleanup_last_error_type = "LockReleaseError"
                logger.error(
                    "Email outbox cleanup lock release returned %s", result
                )
                return False
            await session.commit()
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._cleanup_release_failures += 1
            self._cleanup_last_error_type = type(exc).__name__
            logger.error(
                "Email outbox cleanup lock release failed type=%s",
                type(exc).__name__,
            )
            return False

    async def _discard_lock_connection(
        self, session: AsyncSession
    ) -> None:
        async def invalidate() -> None:
            connection = await session.connection()
            await connection.invalidate()

        task = asyncio.create_task(
            invalidate(), name="email-outbox-cleanup-discard"
        )
        task.add_done_callback(_consume_task_result)
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                pass
            raise
        except Exception as exc:
            self._cleanup_release_failures += 1
            self._cleanup_last_error_type = type(exc).__name__
            logger.error(
                "Could not discard email outbox cleanup connection type=%s",
                type(exc).__name__,
            )


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


async def _safe_rollback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except Exception:
        pass


def _consume_task_result(task: asyncio.Task[Any]) -> None:
    try:
        task.exception()
    except BaseException:
        pass


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


def default_worker_health() -> dict[str, Any]:
    """Return safe telemetry for the current process worker, if created."""
    worker = _default_worker
    if worker is None:
        return {
            "enabled": bool(settings.EMAIL_OUTBOX_ENABLED),
            "running": False,
            "started_at": None,
            "last_heartbeat_at": None,
            "last_run_at": None,
            "last_success_at": None,
            "last_outcome": "not_started",
            "consecutive_failures": 0,
            "last_error_type": None,
            "delivered_total": 0,
            "delivery_failures_total": 0,
            "heartbeat_timeout_seconds": max(
                float(settings.EMAIL_OUTBOX_POLL_INTERVAL_SECONDS) * 3,
                300.0,
            ),
            "cleanup": {
                "last_attempt_at": None,
                "last_success_at": None,
                "last_outcome": "not_started",
                "consecutive_failures": 0,
                "last_error_type": None,
                "deleted_total": 0,
                "release_failures": 0,
                "next_attempt_at": None,
            },
        }
    return worker.health_snapshot()


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
