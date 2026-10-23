"""Best-effort job-view telemetry.

A job detail request must never fail because analytics failed. This service
therefore swallows every telemetry error after logging it at debug level.

Unique-view semantics are shared across the system:

* Redis ``SET NX`` scoped to (job, Vietnam-local day, visitor digest) decides
  whether this is the first view of that job by that visitor that day;
* ``True`` / ``False`` is persisted on the raw event;
* ``None`` is persisted when the Redis check could not run (outage, disabled
  client), and is reported separately as "unverified" instead of being guessed.

The visitor digest is an HMAC of the client IP and User-Agent. Raw IPs and
User-Agents are never stored, and the digest is not persisted at all.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.rate_limit import get_client_ip
from app.database.session import async_session_factory
from app.models import Job
from app.repositories.analytics_repository import AnalyticsRepository
from app.services.analytics_time import vietnam_date_of

logger = logging.getLogger(__name__)

UNIQUE_VIEW_KEY_PREFIX = "analytics:jobview"

# Atomically delete the dedup key only when it still holds our token. A plain
# GET+DEL could race with another request that reclaimed the key after expiry.
_RELEASE_CLAIM_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


class JobViewTelemetryService:
    def __init__(
        self,
        *,
        redis_client: Any | None = None,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        ttl_seconds: int | None = None,
    ) -> None:
        self.redis = redis_client
        self.session_factory = session_factory or async_session_factory
        self.ttl_seconds = int(
            ttl_seconds
            if ttl_seconds is not None
            else settings.ANALYTICS_UNIQUE_VIEW_TTL_SECONDS
        )

    def _visitor_digest(self, job_id: uuid.UUID, request: Request, day: str) -> str:
        client_ip = get_client_ip(request)
        user_agent = (request.headers.get("user-agent") or "")[:512]
        message = f"{job_id}:{day}:{client_ip}|{user_agent}".encode("utf-8")
        return hmac.new(
            settings.SECRET_KEY.encode("utf-8"), message, hashlib.sha256
        ).hexdigest()

    async def _claim_uniqueness(
        self, job_id: uuid.UUID, request: Request, viewed_at: datetime
    ) -> tuple[bool | None, str | None, str | None]:
        """Atomically claim a unique view.

        Returns ``(is_unique, key, ownership_token)``. The token is present
        only when this call created the key and is therefore allowed to roll
        it back if SQL persistence fails.
        """
        if self.redis is None:
            return None, None, None
        day = vietnam_date_of(viewed_at).isoformat()
        digest = self._visitor_digest(job_id, request, day)
        key = f"{UNIQUE_VIEW_KEY_PREFIX}:{job_id}:{day}:{digest}"
        token = uuid.uuid4().hex
        try:
            stored = await self.redis.set(
                key, token, ex=self.ttl_seconds, nx=True
            )
        except Exception as exc:  # noqa: BLE001 - fail open, mark unverified
            logger.debug(
                "Job-view uniqueness check failed: %s", type(exc).__name__
            )
            return None, None, None
        if stored:
            return True, key, token
        return False, key, None

    async def _release_claim(self, key: str | None, token: str | None) -> bool:
        """Best-effort atomic compare-and-delete of our dedup claim."""
        if key is None or token is None or self.redis is None:
            return False
        eval_method = getattr(self.redis, "eval", None)
        if eval_method is None:
            logger.debug(
                "Redis client has no eval; keeping dedup claim to avoid "
                "deleting another request's key"
            )
            return False
        try:
            deleted = await eval_method(_RELEASE_CLAIM_LUA, 1, key, token)
        except Exception as exc:  # noqa: BLE001 - telemetry is best-effort
            logger.debug(
                "Job-view dedup rollback failed: %s", type(exc).__name__
            )
            return False
        return bool(deleted)

    @staticmethod
    async def _rollback(session: AsyncSession) -> bool:
        try:
            await session.rollback()
        except Exception as exc:  # noqa: BLE001 - report rollback failure
            logger.debug(
                "Job-view telemetry rollback failed: %s", type(exc).__name__
            )
            return False
        return True

    async def record_view(self, request: Request, job: Job) -> bool:
        """Record one view; return True when the event was persisted."""
        viewed_at = datetime.now(timezone.utc)
        is_unique, dedup_key, dedup_token = await self._claim_uniqueness(
            job.id, request, viewed_at
        )
        try:
            async with self.session_factory() as session:
                try:
                    await AnalyticsRepository(session).record_view(
                        job_id=job.id,
                        company_id=job.company_id,
                        is_unique=is_unique,
                        viewed_at=viewed_at,
                    )
                    await session.commit()
                except Exception:
                    rollback_ok = await self._rollback(session)
                    if rollback_ok:
                        # The event was not persisted, so the visitor may
                        # legitimately count as unique on a later attempt.
                        # Never release the claim after a failed rollback:
                        # persistence is uncertain in that case.
                        await self._release_claim(dedup_key, dedup_token)
                    raise
            return True
        except Exception as exc:  # noqa: BLE001 - analytics is best-effort
            logger.debug(
                "Job-view telemetry dropped for job %s: %s",
                job.id,
                type(exc).__name__,
            )
            return False


def get_job_view_telemetry_service(request: Request) -> JobViewTelemetryService:
    return JobViewTelemetryService(
        redis_client=getattr(request.app.state, "redis", None)
    )
