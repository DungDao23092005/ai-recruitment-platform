"""Coordination primitives for quota-controlled match-explanation refreshes.

SQL Server is the authoritative idempotency, lease and billing store. Redis is
used for distributed mutual exclusion and as an optional replay/cache layer.
When Redis is unavailable the SQL leases still serialize refreshes: locking and
cache publication are skipped, while quota accounting and idempotency remain
authoritative. The two systems are deliberately *not* coupled with a fake
two-phase commit: the SQL transaction commits first, then cache publication is
fenced by the current Redis lock owner when Redis is available.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.exceptions import (
    MatchExplanationIdempotencyConflictError,
    MatchExplanationRefreshError,
)
from app.domain.models.base import utc_now
from app.models.ai_match_explanation import (
    AIMatchExplanationApplicationLease,
    AIMatchExplanationIdempotency,
)
from app.schemas.ai_explanation import ApplicationMatchExplanationResponse
from app.services.match_explanation_cache import (
    MatchExplanationCache,
    canonical_json_bytes,
)

logger = logging.getLogger(__name__)

LOCK_KEY_PREFIX = "lock:match_explanation"
IDEMPOTENCY_KEY_PREFIX = "idempotency:match_explanation"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"

HEARTBEAT_INTERVAL_SECONDS = 30.0

LUA_RELEASE_LOCK = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
"""

LUA_RENEW_LOCKS = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    redis.call("EXPIRE", KEYS[1], ARGV[2])
    if redis.call("EXISTS", KEYS[2]) == 1 then
        redis.call("EXPIRE", KEYS[2], ARGV[3])
    end
    return 1
end
return 0
"""

LUA_FENCED_CACHE_PUBLISH = """
local current_owner = redis.call("GET", KEYS[1])
if current_owner == ARGV[1] then
    redis.call("SET", KEYS[2], ARGV[2], "EX", ARGV[3])
    redis.call("SET", KEYS[3], ARGV[2], "EX", ARGV[4])
    return 1
end
return 0
"""


class HeartbeatLeaseRenewalError(RuntimeError):
    """Both SQL leases could not be renewed atomically."""


async def _watch_disconnect(
    request: Any, worker_task: asyncio.Task[Any]
) -> None:
    """Poll the ASGI receive channel and cancel the worker on disconnect."""
    try:
        while not worker_task.done():
            if await request.is_disconnected():
                logger.info("asgi_client_disconnected_cancelling_refresh")
                worker_task.cancel()
                return
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        return
    except Exception:  # noqa: BLE001 - disconnect detection is best effort
        logger.warning("asgi_disconnect_watcher_failed")


def hash_idempotency_key(user_id: uuid.UUID | str, raw_key: str) -> str:
    """Hash a user-scoped idempotency key before persistence or Redis use."""
    material = f"{user_id}:{raw_key}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def build_lock_key(application_id: uuid.UUID | str) -> str:
    return f"{LOCK_KEY_PREFIX}:{application_id}"


def build_idempotency_key(user_id: uuid.UUID | str, key_hash: str) -> str:
    return f"{IDEMPOTENCY_KEY_PREFIX}:{user_id}:{key_hash}"


async def _renew_sql_leases(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    record_id: uuid.UUID,
    application_id: uuid.UUID,
    owner_token: str,
    lease_seconds: int,
) -> bool:
    """Atomically extend both SQL leases, or return ``False``.

    The context manager commits only when both conditional updates affected
    exactly one row. A mismatch raises internally so ``session.begin()`` rolls
    the whole transaction back; the helper reports the failure as ``False`` so
    the heartbeat supervisor never has to manage transaction state itself.
    """
    now = utc_now()
    expires_at = now + timedelta(seconds=lease_seconds)
    try:
        async with session_factory() as session:
            async with session.begin():
                idem_result = await session.execute(
                    update(AIMatchExplanationIdempotency)
                    .where(
                        AIMatchExplanationIdempotency.id == record_id,
                        AIMatchExplanationIdempotency.owner_token
                        == owner_token,
                        AIMatchExplanationIdempotency.status
                        == STATUS_IN_PROGRESS,
                        AIMatchExplanationIdempotency.application_id
                        == application_id,
                        AIMatchExplanationIdempotency.lease_expires_at
                        > now,
                    )
                    .values(lease_expires_at=expires_at, updated_at=now)
                )
                lease_result = await session.execute(
                    update(AIMatchExplanationApplicationLease)
                    .where(
                        AIMatchExplanationApplicationLease.application_id
                        == application_id,
                        AIMatchExplanationApplicationLease.owner_token
                        == owner_token,
                        AIMatchExplanationApplicationLease.lease_expires_at
                        > now,
                    )
                    .values(lease_expires_at=expires_at, updated_at=now)
                )
                if idem_result.rowcount != 1 or lease_result.rowcount != 1:
                    raise HeartbeatLeaseRenewalError(
                        "lease ownership changed during heartbeat"
                    )
        return True
    except HeartbeatLeaseRenewalError:
        return False
    except Exception as exc:  # noqa: BLE001 - normalized for supervisor
        logger.error(
            "match_explanation_sql_lease_renewal_failed error=%s",
            type(exc).__name__,
        )
        return False


renew_sql_leases = _renew_sql_leases


class MatchExplanationCoordinator:
    """Request coordination for the public refresh endpoint.

    The coordinator owns only Redis/SQL coordination. Provider generation and
    quota accounting remain in ``ApplicationService`` so the transaction
    boundaries stay explicit.
    """

    def __init__(
        self,
        redis_client: Redis | None,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        cache_service: MatchExplanationCache | None = None,
        lock_ttl_seconds: int | None = None,
        in_progress_ttl_seconds: int | None = None,
        idempotency_ttl_seconds: int | None = None,
        schema_version: str | None = None,
        heartbeat_interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        self.redis = redis_client
        self.session_factory = session_factory
        self.cache = cache_service or MatchExplanationCache(redis_client)
        self.lock_ttl_seconds = (
            settings.MATCH_EXPLANATION_LOCK_TTL_SECONDS
            if lock_ttl_seconds is None
            else lock_ttl_seconds
        )
        self.in_progress_ttl_seconds = (
            settings.MATCH_EXPLANATION_IN_PROGRESS_TTL_SECONDS
            if in_progress_ttl_seconds is None
            else in_progress_ttl_seconds
        )
        self.idempotency_ttl_seconds = (
            settings.MATCH_EXPLANATION_IDEMPOTENCY_TTL_SECONDS
            if idempotency_ttl_seconds is None
            else idempotency_ttl_seconds
        )
        self.schema_version = (
            settings.MATCH_EXPLANATION_IDEMPOTENCY_SCHEMA_VERSION
            if schema_version is None
            else schema_version
        )
        self.heartbeat_interval_seconds = heartbeat_interval_seconds

    # ------------------------------------------------------------------
    # In-process duplicate guard
    # ------------------------------------------------------------------
    @staticmethod
    def get_active_task(
        application_id: uuid.UUID,
    ) -> asyncio.Task[Any] | None:
        task = _active_application_tasks.get(application_id)
        if task is not None and task.done():
            _active_application_tasks.pop(application_id, None)
            return None
        return task

    @staticmethod
    def register_active_task(
        application_id: uuid.UUID, task: asyncio.Task[Any]
    ) -> None:
        _active_application_tasks[application_id] = task

    @staticmethod
    def unregister_active_task(
        application_id: uuid.UUID, task: asyncio.Task[Any]
    ) -> None:
        if _active_application_tasks.get(application_id) is task:
            _active_application_tasks.pop(application_id, None)

    # ------------------------------------------------------------------
    # Distributed lock
    # ------------------------------------------------------------------
    async def acquire_lock(
        self, application_id: uuid.UUID, owner_token: str
    ) -> bool:
        """Acquire the optional Redis lock, degrading to SQL on outage.

        Returns ``True`` when the Redis lock is held. A missing client or a
        Redis error returns ``False`` so the caller can continue with the SQL
        application lease. An actual conflicting lock owner still raises 409.
        """
        if self.redis is None:
            logger.warning(
                "match_explanation_refresh_lock_skipped application_id=%s "
                "reason=redis_unavailable",
                application_id,
            )
            return False
        try:
            acquired = await self.redis.set(
                build_lock_key(application_id),
                owner_token,
                nx=True,
                ex=self.lock_ttl_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - SQL lease takes over
            logger.warning(
                "match_explanation_refresh_lock_skipped application_id=%s "
                "error=%s",
                application_id,
                type(exc).__name__,
            )
            return False
        if not acquired:
            raise MatchExplanationRefreshError(
                "application_refresh_in_progress",
                http_status=409,
                retry_after=5,
            )
        return True

    async def renew_lock(
        self,
        application_id: uuid.UUID,
        owner_token: str,
        *,
        user_id: uuid.UUID | None = None,
        key_hash: str | None = None,
    ) -> bool:
        if self.redis is None:
            return False
        idempotency_key = (
            build_idempotency_key(user_id, key_hash)
            if user_id is not None and key_hash is not None
            else ""
        )
        try:
            result = await self.redis.eval(
                LUA_RENEW_LOCKS,
                2,
                build_lock_key(application_id),
                idempotency_key,
                owner_token,
                self.lock_ttl_seconds,
                self.idempotency_ttl_seconds,
            )
            return int(result) == 1
        except Exception as exc:  # noqa: BLE001 - heartbeat cancels worker
            logger.error(
                "match_explanation_heartbeat_redis_error application_id=%s "
                "error=%s",
                application_id,
                type(exc).__name__,
            )
            return False

    async def release_lock(
        self, application_id: uuid.UUID, owner_token: str
    ) -> None:
        if self.redis is None:
            return
        try:
            await self.redis.eval(
                LUA_RELEASE_LOCK,
                1,
                build_lock_key(application_id),
                owner_token,
            )
        except Exception as exc:  # noqa: BLE001 - best effort unlock
            logger.warning(
                "match_explanation_lock_release_failed application_id=%s "
                "error=%s",
                application_id,
                type(exc).__name__,
            )

    # ------------------------------------------------------------------
    # Redis idempotency replay and fenced publication
    # ------------------------------------------------------------------
    async def read_idempotency_cache(
        self,
        user_id: uuid.UUID,
        key_hash: str,
        application_id: uuid.UUID,
    ) -> ApplicationMatchExplanationResponse | None:
        if self.redis is None:
            return None
        try:
            raw = await self.redis.get(
                build_idempotency_key(user_id, key_hash)
            )
        except Exception as exc:  # noqa: BLE001 - fall back to SQL tombstone
            logger.warning(
                "match_explanation_idempotency_cache_read_failed "
                "application_id=%s error=%s",
                application_id,
                type(exc).__name__,
            )
            return None
        if raw is None:
            return None
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            if not isinstance(raw, str):
                raise ValueError("unexpected idempotency payload type")
            payload = json.loads(raw)
            response = ApplicationMatchExplanationResponse.model_validate(
                payload
            )
        except Exception as exc:  # noqa: BLE001 - never call the LLM on bad data
            logger.error(
                "match_explanation_idempotency_cache_invalid application_id=%s "
                "error=%s",
                application_id,
                type(exc).__name__,
            )
            raise MatchExplanationRefreshError(
                "invalid_idempotency_cache", http_status=500
            ) from exc
        if response.application_id != application_id:
            raise MatchExplanationIdempotencyConflictError(
                "The idempotency key has already been used for another "
                "application."
            )
        return response.model_copy(update={"cache_state": "cached"})

    async def publish_fenced_cache(
        self,
        *,
        application_id: uuid.UUID,
        content_key: str,
        user_id: uuid.UUID,
        key_hash: str,
        owner_token: str,
        response: ApplicationMatchExplanationResponse,
    ) -> bool:
        """Publish content/idempotency cache entries behind the lock fence."""
        if self.redis is None:
            return False
        try:
            payload = canonical_json_bytes(
                response.model_dump(mode="json")
            ).decode("utf-8")
            result = await self.redis.eval(
                LUA_FENCED_CACHE_PUBLISH,
                3,
                build_lock_key(application_id),
                content_key,
                build_idempotency_key(user_id, key_hash),
                owner_token,
                payload,
                self.cache.ttl_seconds,
                self.idempotency_ttl_seconds,
            )
            return int(result) == 1
        except Exception as exc:  # noqa: BLE001 - SQL is already committed
            logger.warning(
                "match_explanation_cache_publish_failed application_id=%s "
                "error=%s",
                application_id,
                type(exc).__name__,
            )
            return False

    # ------------------------------------------------------------------
    # SQL idempotency / application lease registration
    # ------------------------------------------------------------------
    async def register_refresh(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        key_hash: str,
        application_id: uuid.UUID,
        owner_token: str,
    ) -> tuple[uuid.UUID, ApplicationMatchExplanationResponse | None]:
        """Register or replay an idempotent refresh and acquire the SQL lease.

        Returns ``(record_id, replay_response)``. A non-null response means a
        completed tombstone was found and no lease/quota/provider work may run.
        """
        now = utc_now()
        expires_at = now + timedelta(seconds=self.in_progress_ttl_seconds)
        existing = await self._get_idempotency_record(
            session, user_id, key_hash
        )
        if existing is not None:
            if existing.application_id != application_id:
                raise MatchExplanationIdempotencyConflictError(
                    "The idempotency key has already been used for another "
                    "application."
                )
            if existing.schema_version != self.schema_version:
                raise MatchExplanationRefreshError(
                    "idempotency_schema_incompatible",
                    http_status=409,
                    retry_after=5,
                )
            if existing.status == STATUS_COMPLETED:
                return existing.id, self._replay_sql_record(
                    existing, application_id
                )
            if (
                existing.status == STATUS_IN_PROGRESS
                and _is_future(existing.lease_expires_at, now)
            ):
                raise MatchExplanationRefreshError(
                    "idempotency_in_progress",
                    http_status=409,
                    retry_after=5,
                )

        await self._acquire_application_lease(
            session,
            application_id=application_id,
            owner_token=owner_token,
            key_hash=key_hash,
            expires_at=expires_at,
            now=now,
        )

        try:
            if existing is not None:
                result = await session.execute(
                    update(AIMatchExplanationIdempotency)
                    .where(
                        AIMatchExplanationIdempotency.id == existing.id,
                        AIMatchExplanationIdempotency.status
                        != STATUS_COMPLETED,
                    )
                    .values(
                        status=STATUS_IN_PROGRESS,
                        owner_token=owner_token,
                        lease_expires_at=expires_at,
                        schema_version=self.schema_version,
                        response_payload=None,
                        completed_at=None,
                        updated_at=now,
                    )
                )
                if result.rowcount != 1:
                    raise MatchExplanationRefreshError(
                        "idempotency_registration_conflict",
                        http_status=409,
                        retry_after=5,
                    )
                return existing.id, None

            record = AIMatchExplanationIdempotency(
                id=uuid.uuid4(),
                user_id=user_id,
                key_hash=key_hash,
                application_id=application_id,
                status=STATUS_IN_PROGRESS,
                owner_token=owner_token,
                lease_expires_at=expires_at,
                schema_version=self.schema_version,
                response_payload=None,
                completed_at=None,
            )
            session.add(record)
            await session.flush()
            return record.id, None
        except IntegrityError as exc:
            await self._safe_rollback(session)
            raced = await self._get_idempotency_record(
                session, user_id, key_hash
            )
            if (
                raced is not None
                and raced.application_id == application_id
                and raced.status == STATUS_COMPLETED
            ):
                return raced.id, self._replay_sql_record(
                    raced, application_id
                )
            raise MatchExplanationRefreshError(
                "idempotency_registration_conflict",
                http_status=409,
                retry_after=5,
            ) from exc

    async def _get_idempotency_record(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        key_hash: str,
    ) -> AIMatchExplanationIdempotency | None:
        result = await session.execute(
            select(AIMatchExplanationIdempotency).where(
                AIMatchExplanationIdempotency.user_id == user_id,
                AIMatchExplanationIdempotency.key_hash == key_hash,
            )
        )
        return result.scalar_one_or_none()

    async def _acquire_application_lease(
        self,
        session: AsyncSession,
        *,
        application_id: uuid.UUID,
        owner_token: str,
        key_hash: str,
        expires_at: datetime,
        now: datetime,
    ) -> None:
        lease = await session.get(
            AIMatchExplanationApplicationLease, application_id
        )
        if lease is None:
            session.add(
                AIMatchExplanationApplicationLease(
                    application_id=application_id,
                    owner_token=owner_token,
                    idempotency_key_hash=key_hash,
                    lease_expires_at=expires_at,
                )
            )
            try:
                await session.flush()
            except IntegrityError as exc:
                await self._safe_rollback(session)
                raise MatchExplanationRefreshError(
                    "application_refresh_in_progress",
                    http_status=409,
                    retry_after=5,
                ) from exc
            return

        result = await session.execute(
            update(AIMatchExplanationApplicationLease)
            .where(
                AIMatchExplanationApplicationLease.application_id
                == application_id,
                (
                    AIMatchExplanationApplicationLease.owner_token
                    == owner_token
                )
                | (
                    AIMatchExplanationApplicationLease.lease_expires_at
                    <= now
                ),
            )
            .values(
                owner_token=owner_token,
                idempotency_key_hash=key_hash,
                lease_expires_at=expires_at,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            raise MatchExplanationRefreshError(
                "application_refresh_in_progress",
                http_status=409,
                retry_after=5,
            )

    def _replay_sql_record(
        self,
        record: AIMatchExplanationIdempotency,
        application_id: uuid.UUID,
    ) -> ApplicationMatchExplanationResponse:
        if record.application_id != application_id:
            raise MatchExplanationIdempotencyConflictError(
                "The idempotency key has already been used for another "
                "application."
            )
        if not record.response_payload:
            raise MatchExplanationRefreshError(
                "idempotency_payload_unavailable",
                http_status=409,
                retry_after=5,
            )
        try:
            payload = json.loads(record.response_payload)
            response = ApplicationMatchExplanationResponse.model_validate(
                payload
            )
        except Exception as exc:  # noqa: BLE001 - never regenerate silently
            logger.error(
                "match_explanation_sql_idempotency_invalid application_id=%s",
                application_id,
            )
            raise MatchExplanationRefreshError(
                "idempotency_payload_invalid", http_status=500
            ) from exc
        if response.application_id != application_id:
            raise MatchExplanationRefreshError(
                "idempotency_payload_invalid", http_status=500
            )
        return response.model_copy(update={"cache_state": "db_replay"})

    @staticmethod
    async def _safe_rollback(session: AsyncSession) -> None:
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001 - preserve original failure
            logger.error("match_explanation_registration_rollback_failed")

    # ------------------------------------------------------------------
    # Heartbeat / disconnect supervision
    # ------------------------------------------------------------------
    def start_heartbeat(
        self,
        *,
        worker_task: asyncio.Task[Any],
        record_id: uuid.UUID,
        application_id: uuid.UUID,
        user_id: uuid.UUID,
        key_hash: str,
        owner_token: str,
    ) -> asyncio.Task[None] | None:
        if self.session_factory is None:
            return None
        return asyncio.create_task(
            self._heartbeat_loop(
                worker_task=worker_task,
                record_id=record_id,
                application_id=application_id,
                user_id=user_id,
                key_hash=key_hash,
                owner_token=owner_token,
            )
        )

    async def _heartbeat_loop(
        self,
        *,
        worker_task: asyncio.Task[Any],
        record_id: uuid.UUID,
        application_id: uuid.UUID,
        user_id: uuid.UUID,
        key_hash: str,
        owner_token: str,
    ) -> None:
        try:
            while not worker_task.done():
                await asyncio.sleep(self.heartbeat_interval_seconds)
                if worker_task.done():
                    return
                renewed = await _renew_sql_leases(
                    self.session_factory,  # type: ignore[arg-type]
                    record_id=record_id,
                    application_id=application_id,
                    owner_token=owner_token,
                    lease_seconds=self.lock_ttl_seconds,
                )
                if not renewed:
                    logger.error(
                        "match_explanation_heartbeat_sql_renewal_failed "
                        "application_id=%s",
                        application_id,
                    )
                    worker_task.cancel()
                    return
                if not await self.renew_lock(
                    application_id,
                    owner_token,
                    user_id=user_id,
                    key_hash=key_hash,
                ):
                    logger.warning(
                        "match_explanation_heartbeat_redis_renewal_failed "
                        "application_id=%s sql_lease_remains_authoritative",
                        application_id,
                    )
        except asyncio.CancelledError:
            return
        except Exception:  # noqa: BLE001 - never leave an unobserved task
            logger.exception(
                "match_explanation_heartbeat_unexpected_error "
                "application_id=%s",
                application_id,
            )
            worker_task.cancel()

    async def watch_disconnect(
        self,
        request: Any,
        worker_task: asyncio.Task[Any],
    ) -> None:
        await _watch_disconnect(request, worker_task)


_active_application_tasks: dict[uuid.UUID, asyncio.Task[Any]] = {}


def _is_future(value: datetime, now: datetime) -> bool:
    if value.tzinfo is None:
        return value > now.replace(tzinfo=None)
    return value > now
