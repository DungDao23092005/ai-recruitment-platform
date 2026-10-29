"""Background worker that releases abandoned quota reservations.

A process crash or an unhandled provider failure can leave a usage row in the
``RESERVED`` state. Those rows keep the subscription counter incremented even
though the AI operation never completed. This worker periodically marks stale
reservations as failed and releases their counters.

Only one process may reconcile at a time. A SQL Server session-scoped
application lock makes this safe with multiple Uvicorn workers: the losers skip
the pass instead of racing the same reservation.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.database.session import async_session_factory
from app.services.quota_enforcement_service import QuotaEnforcementService

logger = logging.getLogger(__name__)

LOCK_RESOURCE = f"quota_reconciliation:{settings.DATABASE_NAME}"

GET_APP_LOCK_SQL = text(
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

RELEASE_APP_LOCK_SQL = text(
    """
    DECLARE @result int;
    EXEC @result = sp_releaseapplock
        @Resource = :resource,
        @LockOwner = 'Session';
    SELECT @result AS result;
    """
)


class QuotaReconciliationWorker:
    def __init__(
        self,
        *,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        interval_seconds: float | None = None,
        max_age_minutes: int | None = None,
        batch_size: int | None = None,
    ) -> None:
        self._session_factory = session_factory or async_session_factory
        self.interval_seconds = float(
            interval_seconds
            if interval_seconds is not None
            else settings.QUOTA_RECONCILIATION_INTERVAL_SECONDS
        )
        self.max_age_minutes = max(
            1,
            int(
                max_age_minutes
                if max_age_minutes is not None
                else settings.QUOTA_RESERVATION_STALE_MINUTES
            ),
        )
        self.batch_size = max(
            1,
            int(
                batch_size
                if batch_size is not None
                else settings.QUOTA_RECONCILIATION_BATCH_SIZE
            ),
        )
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None

        self._started_at: datetime | None = None
        self._last_heartbeat_at: datetime | None = None
        self._last_run_at: datetime | None = None
        self._last_success_at: datetime | None = None
        self._last_outcome = "not_started"
        self._consecutive_failures = 0
        self._last_error_type: str | None = None
        self._last_reconciled = 0

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._started_at = datetime.now(timezone.utc)
        self._task = asyncio.create_task(
            self._run(), name="quota-reconciliation-worker"
        )
        logger.info(
            "Quota reconciliation worker started (interval=%.1fs stale=%dm "
            "batch=%d)",
            self.interval_seconds,
            self.max_age_minutes,
            self.batch_size,
        )

    async def stop(self) -> None:
        self._stop_event.set()
        task = self._task
        self._task = None
        if task is None:
            return
        try:
            await asyncio.wait_for(
                task, timeout=max(self.interval_seconds, 5.0) + 5.0
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            task.cancel()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Quota reconciliation worker stopped with error: %s", exc
            )
        logger.info("Quota reconciliation worker stopped")

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception(
                    "Quota reconciliation pass failed: %s", exc
                )
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.interval_seconds
                )
            except asyncio.TimeoutError:
                pass

    async def run_once(self) -> dict[str, int | bool]:
        try:
            result = await self._run_pass()
        except asyncio.CancelledError:
            self._record_outcome("cancelled")
            raise
        except Exception as exc:
            self._record_outcome("failure", exc)
            raise
        self._record_outcome(
            "skipped" if result["skipped"] else "success",
            reconciled=int(result["reconciled"]),
        )
        return result

    async def _run_pass(self) -> dict[str, int | bool]:
        # The lock session must stay checked out for the whole pass. An
        # AsyncSession may return its connection to the pool on commit, and a
        # session-scoped applock would then follow that pooled connection into
        # another request. Keeping an open transaction pins this connection,
        # while the work session commits independently.
        async with self._session_factory() as lock_session:
            if not await self._acquire_lock(lock_session):
                logger.debug(
                    "Quota reconciliation skipped: another worker holds the lock"
                )
                return {"skipped": True, "reconciled": 0}
            try:
                async with self._session_factory() as session:
                    try:
                        reconciled = await QuotaEnforcementService(
                            session
                        ).reconcile_stale_reservations(
                            max_age_minutes=self.max_age_minutes,
                            limit=self.batch_size,
                        )
                        await session.commit()
                    except asyncio.CancelledError:
                        await self._safe_rollback(session)
                        raise
                    except Exception:
                        await self._safe_rollback(session)
                        raise
                return {"skipped": False, "reconciled": reconciled}
            finally:
                await self._release_lock(lock_session)
                await self._safe_rollback(lock_session)

    def _record_outcome(
        self,
        outcome: str,
        exc: Exception | None = None,
        *,
        reconciled: int = 0,
    ) -> None:
        moment = datetime.now(timezone.utc)
        self._last_run_at = moment
        self._last_heartbeat_at = moment
        self._last_outcome = outcome
        self._last_reconciled = reconciled
        if outcome == "failure":
            self._consecutive_failures += 1
            self._last_error_type = type(exc).__name__ if exc else "Exception"
        elif outcome in {"success", "skipped"}:
            self._consecutive_failures = 0
            self._last_error_type = None
            if outcome == "success":
                self._last_success_at = moment

    def health_snapshot(self) -> dict[str, Any]:
        return {
            "enabled": bool(settings.QUOTA_RECONCILIATION_ENABLED),
            "running": self._task is not None and not self._task.done(),
            "started_at": _isoformat(self._started_at),
            "last_heartbeat_at": _isoformat(self._last_heartbeat_at),
            "last_run_at": _isoformat(self._last_run_at),
            "last_success_at": _isoformat(self._last_success_at),
            "last_outcome": self._last_outcome,
            "consecutive_failures": self._consecutive_failures,
            "last_error_type": self._last_error_type,
            "last_reconciled": self._last_reconciled,
            "heartbeat_timeout_seconds": max(
                float(self.interval_seconds) * 3, 300.0
            ),
        }

    async def _acquire_lock(self, session: AsyncSession) -> bool:
        try:
            result = await session.scalar(
                GET_APP_LOCK_SQL, {"resource": LOCK_RESOURCE}
            )
        except Exception:
            await self._safe_rollback(session)
            raise
        # Deliberately no commit here: it keeps the transaction (and thus the
        # physical connection that owns the session-scoped applock) pinned
        # until the pass finishes.
        return result is not None and int(result) >= 0

    async def _release_lock(self, session: AsyncSession) -> None:
        try:
            result = await session.scalar(
                RELEASE_APP_LOCK_SQL, {"resource": LOCK_RESOURCE}
            )
            if result is None or int(result) < 0:
                logger.error(
                    "Quota reconciliation lock release returned %s", result
                )
                await self._discard_lock_connection(session)
                return
            await session.commit()
        except Exception as exc:  # noqa: BLE001 - must not crash shutdown
            logger.error(
                "Quota reconciliation lock release failed type=%s",
                type(exc).__name__,
            )
            await self._discard_lock_connection(session)

    @staticmethod
    async def _discard_lock_connection(session: AsyncSession) -> None:
        try:
            connection = await session.connection()
            await connection.invalidate()
        except Exception:
            pass

    @staticmethod
    async def _safe_rollback(session: AsyncSession) -> None:
        try:
            await session.rollback()
        except Exception:
            pass


_default_worker: Optional[QuotaReconciliationWorker] = None


def get_default_worker() -> QuotaReconciliationWorker:
    global _default_worker
    if _default_worker is None:
        _default_worker = QuotaReconciliationWorker()
    return _default_worker


def reset_default_worker() -> None:
    global _default_worker
    _default_worker = None


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


async def start_default_worker() -> None:
    if not settings.QUOTA_RECONCILIATION_ENABLED:
        logger.info(
            "Quota reconciliation worker disabled "
            "(QUOTA_RECONCILIATION_ENABLED=false)"
        )
        return
    await get_default_worker().start()


async def stop_default_worker() -> None:
    global _default_worker
    if _default_worker is not None:
        await _default_worker.stop()
