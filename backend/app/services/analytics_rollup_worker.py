"""Durable daily job-view aggregation and retention.

The worker recomputes the last ``ANALYTICS_ROLLUP_LOOKBACK_DAYS`` completed
Vietnam-local days on every pass. Recomputing absolute counts is idempotent and
repairs days missed while the process was down (backfill).

Only one process may roll up at a time. Instead of assuming ``MERGE`` is
concurrency-safe, the worker takes a SQL Server session-scoped application lock
(``sp_getapplock``). Multiple Uvicorn workers are therefore safe: the losers
skip the pass instead of racing. No external scheduler is required.

Raw events are pruned only after the matching local-day aggregate is committed
*and* marked ``raw_pruned``. A pruned aggregate is never recomputed (that would
overwrite real history with zeros).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.database.session import async_session_factory
from app.repositories.analytics_repository import AnalyticsRepository
from app.services.analytics_time import (
    day_end_exclusive_utc,
    day_start_utc,
    vietnam_today,
)

logger = logging.getLogger(__name__)

LOCK_RESOURCE = f"analytics_rollup:{settings.DATABASE_NAME}"

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
    EXEC sp_releaseapplock
        @Resource = :resource,
        @LockOwner = 'Session';
    """
)


class AnalyticsRollupWorker:
    def __init__(
        self,
        *,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        interval_seconds: float | None = None,
        lookback_days: int | None = None,
        retention_days: int | None = None,
    ) -> None:
        self._session_factory = session_factory or async_session_factory
        self.interval_seconds = float(
            interval_seconds
            if interval_seconds is not None
            else settings.ANALYTICS_ROLLUP_INTERVAL_SECONDS
        )
        self.lookback_days = max(
            0,
            int(
                lookback_days
                if lookback_days is not None
                else settings.ANALYTICS_ROLLUP_LOOKBACK_DAYS
            ),
        )
        self.retention_days = max(
            0,
            int(
                retention_days
                if retention_days is not None
                else settings.ANALYTICS_RAW_RETENTION_DAYS
            ),
        )
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None

    # --------------------------------------------------------------- lifecycle

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._run(), name="analytics-rollup-worker"
        )
        logger.info(
            "Analytics rollup worker started (interval=%.1fs lookback=%dd "
            "retention=%dd)",
            self.interval_seconds,
            self.lookback_days,
            self.retention_days,
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
            logger.warning("Analytics rollup worker stopped with error: %s", exc)
        logger.info("Analytics rollup worker stopped")

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Analytics rollup pass failed: %s", exc)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.interval_seconds
                )
            except asyncio.TimeoutError:
                pass

    # ------------------------------------------------------------------ passes

    async def run_once(self, now: datetime | None = None) -> dict[str, int | bool]:
        """Aggregate completed days and prune safely; returns a summary."""
        moment = now or datetime.now(timezone.utc)
        today = vietnam_today(moment)

        # The lock session must stay checked out for the whole pass. An
        # AsyncSession may return its connection to the pool on commit, and a
        # session-scoped applock would then follow that pooled connection into
        # another request. Keeping an open transaction pins this connection,
        # while the work session commits aggregate rows independently.
        async with self._session_factory() as lock_session:
            if not await self._acquire_lock(lock_session):
                logger.debug("Analytics rollup skipped: another worker holds the lock")
                return {"skipped": True, "days": 0, "pruned_events": 0}
            try:
                days = 0
                pruned = 0
                async with self._session_factory() as session:
                    try:
                        for offset in range(1, self.lookback_days + 1):
                            day = today - timedelta(days=offset)
                            if await self._aggregate_day(session, day, moment):
                                days += 1
                        pruned = await self._prune(session, today, moment)
                        await session.commit()
                    except asyncio.CancelledError:
                        await self._safe_rollback(session)
                        raise
                    except Exception:
                        await self._safe_rollback(session)
                        raise
                return {
                    "skipped": False,
                    "days": days,
                    "pruned_events": pruned,
                }
            finally:
                await self._release_lock(lock_session)
                await self._safe_rollback(lock_session)

    async def _aggregate_day(
        self, session: AsyncSession, day: date, moment: datetime
    ) -> bool:
        repository = AnalyticsRepository(session)
        rows = await repository.raw_view_counts_for_day(
            day_start_utc(day), day_end_exclusive_utc(day)
        )
        if not rows:
            return False

        existing = await repository.aggregate_flags_for_date(day)
        written = False
        for row in rows:
            job_id: uuid.UUID = row["job_id"]
            if existing.get(job_id) is True:
                # Raw events already pruned; the stored aggregate is the only
                # surviving history and must never be recomputed to zero.
                continue
            try:
                await repository.upsert_daily_aggregate(
                    job_id=job_id,
                    company_id=row["company_id"],
                    view_date=day,
                    total_views=int(row["total_views"]),
                    unique_views=int(row["unique_views"]),
                    unverified_views=int(row["unverified_views"]),
                    aggregated_at=moment,
                )
                await session.commit()
                written = True
            except IntegrityError:
                # A concurrent insert won; our UPDATE-then-INSERT is still
                # idempotent, so re-run it against the committed row.
                await session.rollback()
                await repository.upsert_daily_aggregate(
                    job_id=job_id,
                    company_id=row["company_id"],
                    view_date=day,
                    total_views=int(row["total_views"]),
                    unique_views=int(row["unique_views"]),
                    unverified_views=int(row["unverified_views"]),
                    aggregated_at=moment,
                )
                await session.commit()
                written = True
        return written

    async def _prune(
        self, session: AsyncSession, today: date, moment: datetime
    ) -> int:
        if self.retention_days <= 0:
            return 0
        cutoff_day = today - timedelta(days=self.retention_days)
        repository = AnalyticsRepository(session)
        marked = await repository.mark_raw_pruned(cutoff_day, moment)
        await session.commit()
        deleted = await repository.delete_pruned_events(
            day_start_utc(cutoff_day)
        )
        await session.commit()
        if marked or deleted:
            logger.info(
                "Analytics retention marked %d aggregate(s) and pruned %d "
                "raw event(s) older than %s",
                marked,
                deleted,
                cutoff_day,
            )
        return deleted

    # ------------------------------------------------------------------- locks

    async def _acquire_lock(self, session: AsyncSession) -> bool:
        try:
            result = await session.scalar(
                GET_APP_LOCK_SQL, {"resource": LOCK_RESOURCE}
            )
            # Deliberately no commit here: it keeps the transaction (and thus
            # the physical connection that owns the session-scoped applock)
            # pinned until the pass finishes.
            return result is not None and int(result) >= 0
        except Exception as exc:  # noqa: BLE001 - analytics must not crash startup
            logger.warning(
                "Could not acquire analytics rollup lock: %s",
                type(exc).__name__,
            )
            await self._safe_rollback(session)
            return False

    async def _release_lock(self, session: AsyncSession) -> None:
        try:
            await session.execute(
                RELEASE_APP_LOCK_SQL, {"resource": LOCK_RESOURCE}
            )
            await session.commit()
        except Exception:  # noqa: BLE001 - session close releases it anyway
            await self._safe_rollback(session)

    @staticmethod
    async def _safe_rollback(session: AsyncSession) -> None:
        try:
            await session.rollback()
        except Exception:
            pass


_default_worker: Optional[AnalyticsRollupWorker] = None


def get_default_worker() -> AnalyticsRollupWorker:
    global _default_worker
    if _default_worker is None:
        _default_worker = AnalyticsRollupWorker()
    return _default_worker


def reset_default_worker() -> None:
    global _default_worker
    _default_worker = None


async def start_default_worker() -> None:
    if not settings.ANALYTICS_ROLLUP_ENABLED:
        logger.info(
            "Analytics rollup worker disabled (ANALYTICS_ROLLUP_ENABLED=false)"
        )
        return
    await get_default_worker().start()


async def stop_default_worker() -> None:
    global _default_worker
    if _default_worker is not None:
        await _default_worker.stop()
