"""Background worker that materializes expired job statuses and reconciles Qdrant.

Step 1: Materialize expired jobs in SQL (status=expired, is_qdrant_synced=0).
Step 2: Fetch oldest pending expired jobs (status=expired, is_qdrant_synced=0).
Step 3: Call Qdrant set_payload(collection_name="jobs", payload={"status": "expired"}, points=[...]).
Step 4: Checkpoint acknowledged point IDs by updating is_qdrant_synced=1.

Concurrency:
SQL Server session-scoped distributed lock (sp_getapplock) ensures single-worker
execution across multiple application instances.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.database.session import async_session_factory
from app.domain.enums import JobStatus
from app.models import Job
from app.services.job_realtime import (
    ACTION_EXPIRED,
    schedule_job_listing_event,
)

logger = logging.getLogger(__name__)

LOCK_RESOURCE = f"job_expiration:{settings.DATABASE_NAME}"

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


class JobExpirationWorker:
    def __init__(
        self,
        *,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        vector_repository=None,
        interval_seconds: float | None = None,
        batch_size: int | None = None,
        sync_batch_size: int | None = None,
    ) -> None:
        self._session_factory = session_factory or async_session_factory
        self.vector_repository = vector_repository
        self.interval_seconds = float(
            interval_seconds
            if interval_seconds is not None
            else settings.JOB_EXPIRATION_INTERVAL_SECONDS
        )
        self.batch_size = max(
            1,
            int(
                batch_size
                if batch_size is not None
                else settings.JOB_EXPIRATION_BATCH_SIZE
            ),
        )
        self.sync_batch_size = max(
            1,
            int(
                sync_batch_size
                if sync_batch_size is not None
                else settings.JOB_EXPIRATION_SYNC_BATCH_SIZE
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
        self._last_expired = 0
        self._last_synced = 0
        self._quarantined_ids: set[uuid.UUID] = set()

    def _get_vector_repository(self):
        if self.vector_repository is not None:
            return self.vector_repository
        from app.ai.vector_db.qdrant_client import QdrantVectorRepository
        self.vector_repository = QdrantVectorRepository()
        return self.vector_repository

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._started_at = datetime.now(timezone.utc)
        self._task = asyncio.create_task(
            self._run(), name="job-expiration-worker"
        )
        logger.info(
            "Job expiration worker started (interval=%.1fs batch=%d sync_batch=%d)",
            self.interval_seconds,
            self.batch_size,
            self.sync_batch_size,
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
                "Job expiration worker stopped with error: %s", exc
            )
        logger.info("Job expiration worker stopped")

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Job expiration pass failed: %s", exc)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.interval_seconds
                )
            except asyncio.TimeoutError:
                pass

    async def run_once(
        self, now: datetime | None = None
    ) -> dict[str, int | bool]:
        moment = now or datetime.now(timezone.utc)
        try:
            result = await self._run_pass(moment)
        except asyncio.CancelledError:
            self._record_outcome("cancelled")
            raise
        except Exception as exc:
            self._record_outcome("failure", exc)
            raise
        self._record_outcome(
            "skipped" if result["skipped"] else "success",
            expired=int(result["expired"]),
            synced=int(result["synced"]),
        )
        return result

    async def _run_pass(
        self, moment: datetime
    ) -> dict[str, int | bool]:
        async with self._session_factory() as lock_session:
            if not await self._acquire_lock(lock_session):
                logger.debug(
                    "Job expiration skipped: another worker holds the lock"
                )
                return {"skipped": True, "expired": 0, "synced": 0}
            try:
                expired_count = await self._materialize_expired_jobs(moment)
                synced_count = await self._reconcile_qdrant_sync()
                return {
                    "skipped": False,
                    "expired": expired_count,
                    "synced": synced_count,
                }
            finally:
                await self._release_lock(lock_session)
                await self._safe_rollback(lock_session)

    async def _materialize_expired_jobs(self, moment: datetime) -> int:
        """Step 1: Find published jobs past expires_at, update to expired and is_qdrant_synced=0.

        Drains multiple batches if more than batch_size jobs have expired.
        """
        total_materialized = 0
        while True:
            async with self._session_factory() as session:
                try:
                    stmt = (
                        select(Job.id)
                        .where(
                            Job.status == JobStatus.PUBLISHED,
                            Job.is_deleted == False,  # noqa: E712
                            Job.expires_at.is_not(None),
                            Job.expires_at <= moment,
                        )
                        .order_by(Job.expires_at.asc(), Job.id.asc())
                        .limit(self.batch_size)
                    )
                    result = await session.execute(stmt)
                    expired_ids = list(result.scalars().all())

                    if not expired_ids:
                        break

                    update_stmt = (
                        update(Job)
                        .where(Job.id.in_(expired_ids))
                        .values(
                            status=JobStatus.EXPIRED,
                            is_qdrant_synced=False,
                            updated_at=moment,
                        )
                    )
                    await session.execute(update_stmt)
                    schedule_job_listing_event(
                        session,
                        action=ACTION_EXPIRED,
                        affected_count=len(expired_ids),
                    )
                    await session.commit()
                    total_materialized += len(expired_ids)
                    logger.info(
                        "Materialized batch of %d expired job postings", len(expired_ids)
                    )
                    if len(expired_ids) < self.batch_size:
                        break
                except asyncio.CancelledError:
                    await self._safe_rollback(session)
                    raise
                except Exception:
                    await self._safe_rollback(session)
                    raise
        return total_materialized

    @staticmethod
    def _is_transient_service_error(exc: Exception) -> bool:
        """Classify whether an exception represents a service-wide transient outage.

        Transient: connection errors, network timeouts, 502/503/504 gateway/service
        unavailable, response handling errors.
        Non-transient: 400 bad request, 404 point not found, 422 unprocessable, ValueError,
        point-specific schema or payload errors.
        """
        if isinstance(
            exc,
            (
                TimeoutError,
                asyncio.TimeoutError,
                ConnectionError,
                ConnectionRefusedError,
                ConnectionResetError,
                OSError,
            ),
        ):
            return True

        exc_type = type(exc).__name__
        exc_str = str(exc).lower()

        status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
        if status is not None:
            if status in (408, 429, 500, 502, 503, 504):
                return True
            if 400 <= status < 500:
                return False

        if any(
            t in exc_type.lower()
            for t in (
                "connecterror",
                "connecttimeouterror",
                "timeouterror",
                "networkerror",
                "responsehandlingexception",
                "serviceunavailable",
            )
        ):
            return True

        transient_keywords = (
            "connection refused",
            "connection reset",
            "timed out",
            "timeout",
            "service unavailable",
            "temporarily unavailable",
            "unavailable",
            "name resolution",
            "cannot connect",
        )
        if any(kw in exc_str for kw in transient_keywords):
            return True

        return False

    async def _sync_points_to_qdrant(self, point_ids: list[str]) -> None:
        """Issue set_payload call to Qdrant vector repository without holding any DB session."""
        vector_repo = self._get_vector_repository()
        if hasattr(vector_repo, "set_payload"):
            await vector_repo.set_payload(
                collection_name="jobs",
                payload={"status": JobStatus.EXPIRED.value},
                points=point_ids,
            )
        elif hasattr(vector_repo, "client") and hasattr(
            vector_repo.client, "set_payload"
        ):
            await vector_repo.client.set_payload(
                collection_name="jobs",
                payload={"status": JobStatus.EXPIRED.value},
                points=point_ids,
            )
        else:
            raise RuntimeError("Vector repository does not support set_payload")

    async def _reconcile_qdrant_sync(self) -> int:
        """Steps 2, 3, 4: Sync unsynced expired jobs to Qdrant and checkpoint.

        - Closes read session before any Qdrant network call.
        - Isolates point-specific failures to prevent starvation of healthy jobs.
        - Drains across multiple batches (> 100 pending jobs).
        - Opens a separate short-lived session for checkpoint updates.
        - Checkpoints ONLY acknowledged IDs.
        - Retains SQL Server distributed application lock.
        """
        total_synced = 0
        excluded_ids: set[uuid.UUID] = set(self._quarantined_ids)

        while True:
            # Step 2a: Short-lived read session to fetch pending job IDs
            async with self._session_factory() as read_session:
                try:
                    stmt = (
                        select(Job.id)
                        .where(
                            Job.status == JobStatus.EXPIRED,
                            Job.is_qdrant_synced == False,  # noqa: E712
                            Job.is_deleted == False,  # noqa: E712
                        )
                    )
                    if excluded_ids:
                        stmt = stmt.where(Job.id.not_in(excluded_ids))
                    stmt = stmt.order_by(
                        Job.updated_at.asc(), Job.id.asc()
                    ).limit(self.sync_batch_size)
                    result = await read_session.execute(stmt)
                    batch_ids = list(result.scalars().all())
                except asyncio.CancelledError:
                    await self._safe_rollback(read_session)
                    raise
                except Exception:
                    await self._safe_rollback(read_session)
                    raise

            # Read session is now closed before Qdrant network calls!
            if not batch_ids:
                break

            point_ids = [str(jid) for jid in batch_ids]
            acknowledged_ids: list[uuid.UUID] = []

            # Step 2b: Network call to Qdrant (without any active DB session)
            try:
                await self._sync_points_to_qdrant(point_ids)
                acknowledged_ids = batch_ids
            except Exception as sync_exc:
                if self._is_transient_service_error(sync_exc):
                    logger.warning(
                        "Transient error syncing expired jobs to Qdrant: %s. Aborting sync pass.",
                        sync_exc,
                    )
                    # Service-wide outage: leave unacknowledged IDs pending, avoid aggressive per-point retries
                    break
                else:
                    # Point-specific or batch error: fallback to bounded per-point isolation
                    logger.warning(
                        "Batch Qdrant sync failed with non-transient error (%s); falling back to per-point sync.",
                        sync_exc,
                    )
                    for jid in batch_ids:
                        pid = str(jid)
                        try:
                            await self._sync_points_to_qdrant([pid])
                            acknowledged_ids.append(jid)
                        except Exception as pt_exc:
                            if self._is_transient_service_error(pt_exc):
                                logger.warning(
                                    "Transient error during per-point Qdrant sync: %s",
                                    pt_exc,
                                )
                                break
                            logger.error(
                                "Point %s failed Qdrant sync (%s); isolating point to prevent starvation.",
                                pid,
                                pt_exc,
                            )
                            excluded_ids.add(jid)
                            self._quarantined_ids.add(jid)

            # Step 2c: Separate short-lived session for checkpoint updates
            if acknowledged_ids:
                async with self._session_factory() as checkpoint_session:
                    try:
                        chk_stmt = (
                            update(Job)
                            .where(Job.id.in_(acknowledged_ids))
                            .values(is_qdrant_synced=True)
                        )
                        await checkpoint_session.execute(chk_stmt)
                        await checkpoint_session.commit()
                        total_synced += len(acknowledged_ids)
                        logger.info(
                            "Checkpointed %d expired jobs in Qdrant (total synced: %d)",
                            len(acknowledged_ids),
                            total_synced,
                        )
                    except asyncio.CancelledError:
                        await self._safe_rollback(checkpoint_session)
                        raise
                    except Exception:
                        await self._safe_rollback(checkpoint_session)
                        raise

            # If this batch was smaller than sync_batch_size, no further pending jobs exist
            if len(batch_ids) < self.sync_batch_size:
                break

            # Starvation guard: if nothing was acknowledged and no new IDs were excluded, break to avoid infinite loop
            if not acknowledged_ids and not any(jid in excluded_ids for jid in batch_ids):
                break

        return total_synced

    def _record_outcome(
        self,
        outcome: str,
        exc: Exception | None = None,
        *,
        expired: int = 0,
        synced: int = 0,
    ) -> None:
        moment = datetime.now(timezone.utc)
        self._last_run_at = moment
        self._last_heartbeat_at = moment
        self._last_outcome = outcome
        self._last_expired = expired
        self._last_synced = synced

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
            "enabled": bool(settings.JOB_EXPIRATION_WORKER_ENABLED),
            "running": self._task is not None and not self._task.done(),
            "started_at": _isoformat(self._started_at),
            "last_heartbeat_at": _isoformat(self._last_heartbeat_at),
            "last_run_at": _isoformat(self._last_run_at),
            "last_success_at": _isoformat(self._last_success_at),
            "last_outcome": self._last_outcome,
            "consecutive_failures": self._consecutive_failures,
            "last_error_type": self._last_error_type,
            "last_expired": self._last_expired,
            "last_synced": self._last_synced,
            "heartbeat_timeout_seconds": max(
                float(self.interval_seconds) * 3, 300.0
            ),
        }

    async def _acquire_lock(self, session: AsyncSession) -> bool:
        bind = session.bind
        dialect_name = bind.dialect.name if bind is not None else ""
        if dialect_name != "mssql":
            # For non-MSSQL environments (e.g. SQLite in unit tests), permit execution
            return True
        try:
            result = await session.scalar(
                GET_APP_LOCK_SQL, {"resource": LOCK_RESOURCE}
            )
        except Exception:
            await self._safe_rollback(session)
            raise
        return result is not None and int(result) >= 0

    async def _release_lock(self, session: AsyncSession) -> None:
        bind = session.bind
        dialect_name = bind.dialect.name if bind is not None else ""
        if dialect_name != "mssql":
            return
        try:
            result = await session.scalar(
                RELEASE_APP_LOCK_SQL, {"resource": LOCK_RESOURCE}
            )
            if result is None or int(result) < 0:
                logger.error(
                    "Job expiration lock release returned %s", result
                )
                await self._discard_lock_connection(session)
                return
            await session.commit()
        except Exception as exc:  # noqa: BLE001 - must not crash shutdown
            logger.error(
                "Job expiration lock release failed type=%s",
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


_default_worker: Optional[JobExpirationWorker] = None


def get_default_worker() -> JobExpirationWorker:
    global _default_worker
    if _default_worker is None:
        _default_worker = JobExpirationWorker()
    return _default_worker


def reset_default_worker() -> None:
    global _default_worker
    _default_worker = None


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


async def start_default_worker() -> None:
    if not settings.JOB_EXPIRATION_WORKER_ENABLED:
        logger.info(
            "Job expiration worker disabled "
            "(JOB_EXPIRATION_WORKER_ENABLED=false)"
        )
        return
    await get_default_worker().start()


async def stop_default_worker() -> None:
    global _default_worker
    if _default_worker is not None:
        await _default_worker.stop()
