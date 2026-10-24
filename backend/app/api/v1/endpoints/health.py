import re
from datetime import datetime, timezone
from typing import Any, Dict

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, status
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_db_session
from app.services.analytics_rollup_worker import (
    default_worker_health as analytics_worker_health,
)
from app.services.email_outbox_worker import (
    default_worker_health as email_outbox_worker_health,
)

router = APIRouter()

_ERROR_TYPE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_OUTCOMES = {
    "not_started",
    "success",
    "failure",
    "skipped",
    "cancelled",
    "stopped",
}


def _sanitize_error() -> str:
    """Sanitize error messages for client responses."""
    return "Component unavailable"


def _sanitize_timestamp(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _sanitize_error_type(value: object) -> str | None:
    if isinstance(value, str) and _ERROR_TYPE_PATTERN.fullmatch(value):
        return value
    return None


def _sanitize_outcome(value: object) -> str:
    return value if isinstance(value, str) and value in _OUTCOMES else "unknown"


def _sanitize_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, min(value, 1_000_000_000))


def _sanitize_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 300.0
    return max(1.0, min(float(value), 86_400.0))


def _sanitize_cleanup(value: object) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "last_attempt_at": _sanitize_timestamp(
            source.get("last_attempt_at")
        ),
        "last_success_at": _sanitize_timestamp(
            source.get("last_success_at")
        ),
        "last_outcome": _sanitize_outcome(source.get("last_outcome")),
        "consecutive_failures": _sanitize_count(
            source.get("consecutive_failures")
        ),
        "last_error_type": _sanitize_error_type(
            source.get("last_error_type")
        ),
        "deleted_total": _sanitize_count(source.get("deleted_total")),
        "release_failures": _sanitize_count(
            source.get("release_failures")
        ),
        "next_attempt_at": _sanitize_timestamp(source.get("next_attempt_at")),
    }


def _worker_status(entry: dict[str, Any], now: datetime) -> str:
    if not entry["enabled"]:
        return "disabled"
    if entry["last_outcome"] == "not_started":
        return "not_started"
    if entry["consecutive_failures"] > 0 or entry["last_outcome"] == "failure":
        return "degraded"
    if not entry["running"]:
        return "degraded"
    heartbeat = entry["last_heartbeat_at"]
    if heartbeat is None:
        return "degraded"
    age = (now - datetime.fromisoformat(heartbeat)).total_seconds()
    if age > entry["heartbeat_timeout_seconds"]:
        return "degraded"
    return "healthy"


def _sanitize_worker_snapshot(
    snapshot: object, *, now: datetime, include_cleanup: bool
) -> dict[str, Any]:
    source = snapshot if isinstance(snapshot, dict) else {}
    entry: dict[str, Any] = {
        "enabled": bool(source.get("enabled")),
        "running": bool(source.get("running")),
        "started_at": _sanitize_timestamp(source.get("started_at")),
        "last_heartbeat_at": _sanitize_timestamp(
            source.get("last_heartbeat_at")
        ),
        "last_run_at": _sanitize_timestamp(source.get("last_run_at")),
        "last_success_at": _sanitize_timestamp(
            source.get("last_success_at")
        ),
        "last_outcome": _sanitize_outcome(source.get("last_outcome")),
        "consecutive_failures": _sanitize_count(
            source.get("consecutive_failures")
        ),
        "last_error_type": _sanitize_error_type(
            source.get("last_error_type")
        ),
        "heartbeat_timeout_seconds": _sanitize_timeout(
            source.get("heartbeat_timeout_seconds")
        ),
    }
    if include_cleanup:
        entry["delivered_total"] = _sanitize_count(
            source.get("delivered_total")
        )
        entry["delivery_failures_total"] = _sanitize_count(
            source.get("delivery_failures_total")
        )
        entry["cleanup"] = _sanitize_cleanup(source.get("cleanup"))
    else:
        entry["last_processed_days"] = _sanitize_count(
            source.get("last_processed_days")
        )
        entry["last_pruned_events"] = _sanitize_count(
            source.get("last_pruned_events")
        )
    entry["status"] = _worker_status(entry, now)
    return entry


def build_workers_health() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "email_outbox": _sanitize_worker_snapshot(
            email_outbox_worker_health(),
            now=now,
            include_cleanup=True,
        ),
        "analytics_rollup": _sanitize_worker_snapshot(
            analytics_worker_health(),
            now=now,
            include_cleanup=False,
        ),
    }


async def check_database(db: AsyncSession = Depends(get_db_session)) -> Dict[str, Any]:
    """Check database connectivity with a lightweight query."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy"}
    except Exception:
        return {"status": "unhealthy", "error": _sanitize_error()}


async def check_redis() -> Dict[str, Any]:
    """Check Redis connectivity with a lightweight ping."""
    client = None
    try:
        # Build Redis URL with password if configured
        redis_url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}"
        if settings.REDIS_PASSWORD:
            redis_url = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}"

        client = redis.from_url(
            redis_url,
            db=settings.REDIS_DB,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        await client.ping()
        return {"status": "healthy"}
    except Exception:
        return {"status": "unhealthy", "error": _sanitize_error()}
    finally:
        if client:
            await client.close()


async def check_qdrant() -> Dict[str, Any]:
    """Check Qdrant connectivity with a lightweight health check."""
    client = None
    try:
        if settings.QDRANT_URL:
            client = AsyncQdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY,
                timeout=2,
            )
        else:
            client = AsyncQdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                timeout=2,
            )
        await client.get_collections()
        return {"status": "healthy"}
    except Exception:
        return {"status": "unhealthy", "error": _sanitize_error()}
    finally:
        if client:
            await client.close()


@router.get("/health", response_model=Dict[str, Any])
async def health_check(db: AsyncSession = Depends(get_db_session)) -> Dict[str, Any]:
    """
    Comprehensive health check endpoint.
    Verifies connectivity to all critical infrastructure components.
    """
    db_health = await check_database(db)
    redis_health = await check_redis()
    qdrant_health = await check_qdrant()

    components = {
        "database": db_health,
        "redis": redis_health,
        "qdrant": qdrant_health,
    }
    workers = build_workers_health()

    all_healthy = all(c.get("status") == "healthy" for c in components.values())
    workers_degraded = any(
        worker.get("status") == "degraded" for worker in workers.values()
    )

    response = {
        "status": (
            "healthy"
            if all_healthy and not workers_degraded
            else "degraded"
        ),
        "service": f"{settings.PROJECT_NAME} API",
        "components": components,
        "workers": workers,
    }

    if not all_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response,
        )

    return response


@router.get("/health/live")
async def liveness_check() -> Dict[str, str]:
    """
    Liveness probe - simple endpoint to verify the service is running.
    Does not check dependencies.
    """
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness_check(db: AsyncSession = Depends(get_db_session)) -> Dict[str, Any]:
    """
    Readiness probe - verifies service is ready to accept traffic.
    Checks critical dependencies.
    """
    db_health = await check_database(db)
    redis_health = await check_redis()

    components = {
        "database": db_health,
        "redis": redis_health,
    }

    all_healthy = all(c.get("status") == "healthy" for c in components.values())

    response = {
        "status": "ready" if all_healthy else "not_ready",
        "components": components,
    }

    if not all_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response,
        )

    return response