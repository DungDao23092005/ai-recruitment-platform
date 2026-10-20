"""Content-addressed Redis cache for application match explanations.

The cache key is derived only from trusted, server-resolved parsed resume/job
content plus the configured schema/algorithm version. No client-supplied hash,
identifier or payload is ever used as a cache key.

Redis is an optimisation, never a correctness dependency: every read/write
failure degrades to a cache miss and the caller builds a fresh deterministic
explanation. Serialized payloads are validated against the current response
schema before being returned.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import uuid
from typing import Any

from redis.asyncio import Redis

from app.core.config import settings
from app.schemas.ai_explanation import ApplicationMatchExplanationResponse
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_resume import ParsedResumeSchema

logger = logging.getLogger(__name__)

CACHE_KEY_PREFIX = "match_explanation"


class CacheSerializationError(ValueError):
    """Raised when a value cannot be canonicalized into supported JSON."""


def _normalize_json(value: Any) -> Any:
    """Return a JSON-safe copy containing only supported primitives.

    Deliberately rejects arbitrary objects instead of falling back to
    ``str(value)``, which could produce a stable-looking hash for content that
    was never actually represented.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CacheSerializationError("non-finite float is not cacheable")
        return value
    if isinstance(value, list):
        return [_normalize_json(item) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CacheSerializationError("non-string dict key is not cacheable")
            normalized[key] = _normalize_json(item)
        return normalized
    raise CacheSerializationError(
        f"unsupported cache value type: {type(value).__name__}"
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize supported JSON data deterministically as UTF-8 bytes."""
    normalized = _normalize_json(value)
    try:
        text = json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise CacheSerializationError(str(exc)) from exc
    return text.encode("utf-8")


def content_hash(value: Any) -> str:
    """Return the SHA-256 hex digest of canonical JSON content."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _as_json_payload(model: object) -> dict[str, Any]:
    """Return a JSON-mode model dump or raise ``CacheSerializationError``."""
    dump = getattr(model, "model_dump", None)
    if not callable(dump):
        raise CacheSerializationError(
            f"unsupported model type: {type(model).__name__}"
        )
    try:
        payload = dump(mode="json")
    except Exception as exc:  # noqa: BLE001 - serialization boundary
        raise CacheSerializationError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise CacheSerializationError("model dump did not produce an object")
    return payload


class MatchExplanationCache:
    """Read/write validated match explanations using the shared Redis client.

    The client is injected from ``app.state.redis`` so no second connection
    pool is created. ``redis_client=None`` (Redis unavailable at startup) is a
    normal bypass condition.
    """

    def __init__(
        self,
        redis_client: Redis | None = None,
        *,
        enabled: bool | None = None,
        ttl_seconds: int | None = None,
        version: str | None = None,
    ) -> None:
        self.redis = redis_client
        self.enabled = (
            settings.MATCH_EXPLANATION_CACHE_ENABLED
            if enabled is None
            else enabled
        )
        self.ttl_seconds = (
            settings.MATCH_EXPLANATION_CACHE_TTL_SECONDS
            if ttl_seconds is None
            else ttl_seconds
        )
        self.version = (
            settings.MATCH_EXPLANATION_CACHE_VERSION
            if version is None
            else version
        )

    @property
    def available(self) -> bool:
        return self.enabled and self.redis is not None

    def serialize_response(
        self, response: ApplicationMatchExplanationResponse
    ) -> str:
        """Serialize a validated response for durable/SQL replay storage."""
        payload = _as_json_payload(response)
        return canonical_json_bytes(payload).decode("utf-8")

    def build_key(
        self,
        application_id: uuid.UUID | str,
        parsed_resume: ParsedResumeSchema | None,
        parsed_job: ParsedJobSchema | None,
    ) -> str | None:
        """Build the content-addressed key, or ``None`` when uncacheable."""
        if parsed_resume is None or parsed_job is None:
            return None
        try:
            resume_hash = content_hash(_as_json_payload(parsed_resume))
            job_hash = content_hash(_as_json_payload(parsed_job))
        except Exception as exc:  # noqa: BLE001 - never fail the explanation
            logger.warning(
                "match_explanation_cache_key_failed application_id=%s error=%s",
                application_id,
                type(exc).__name__,
            )
            return None
        return (
            f"{CACHE_KEY_PREFIX}:{application_id}:"
            f"{resume_hash}:{job_hash}:{self.version}"
        )

    async def get(
        self,
        key: str,
        *,
        application_id: uuid.UUID | str | None = None,
    ) -> ApplicationMatchExplanationResponse | None:
        """Return a validated cached response, or ``None`` on any failure."""
        if not self.available:
            return None
        try:
            raw = await self.redis.get(key)
        except Exception as exc:  # noqa: BLE001 - cache must not break GET
            logger.warning(
                "match_explanation_cache_get_failed application_id=%s error=%s",
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
                raise ValueError("unexpected cache payload type")
            payload = json.loads(raw)
            response = ApplicationMatchExplanationResponse.model_validate(payload)
            return response.model_copy(update={"cache_state": "cached"})
        except Exception as exc:  # noqa: BLE001 - treat as a cache miss
            logger.warning(
                "match_explanation_cache_invalid_payload application_id=%s "
                "error=%s",
                application_id,
                type(exc).__name__,
            )
            return None

    async def store(
        self,
        key: str,
        response: ApplicationMatchExplanationResponse,
        *,
        application_id: uuid.UUID | str | None = None,
    ) -> bool:
        """Store a valid response with the configured TTL.

        Returns ``True`` only when the write succeeded. Serialization or Redis
        failures are logged with bounded context and reported as ``False``.
        """
        if not self.available or not key:
            return False
        try:
            payload = _as_json_payload(response)
            text = canonical_json_bytes(payload).decode("utf-8")
            await self.redis.set(key, text, ex=self.ttl_seconds)
            return True
        except Exception as exc:  # noqa: BLE001 - cache must not break GET
            logger.warning(
                "match_explanation_cache_set_failed application_id=%s error=%s",
                application_id
                if application_id is not None
                else getattr(response, "application_id", None),
                type(exc).__name__,
            )
            return False
