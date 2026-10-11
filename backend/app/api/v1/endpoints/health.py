from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis
from qdrant_client import AsyncQdrantClient

from app.core.config import settings
from app.database.session import get_db_session

router = APIRouter()


def _sanitize_error() -> str:
    """Sanitize error messages for client responses."""
    # In production, we don't expose internal error details to clients
    return "Component unavailable"


async def check_database(db: AsyncSession = Depends(get_db_session)) -> Dict[str, Any]:
    """Check database connectivity with a lightweight query."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy"}
    except Exception:
        return {"status": "unhealthy", "error": _sanitize_error()}


def _sanitize_error() -> str:
    """Sanitize error messages for client responses."""
    # In production, we don't expose internal error details to clients
    return "Component unavailable"


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

    all_healthy = all(c.get("status") == "healthy" for c in components.values())

    response = {
        "status": "healthy" if all_healthy else "degraded",
        "service": f"{settings.PROJECT_NAME} API",
        "components": components,
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