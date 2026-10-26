from __future__ import annotations

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Request, HTTPException, status, Depends
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import RecruiterProfile, User
from app.api.deps import get_current_active_user, get_db, require_recruiter

logger = logging.getLogger(__name__)


# Uniform, localized client-facing messages. Every authentication rate-limit
# rejection returns the SAME body regardless of which bucket (IP vs account)
# triggered it, so the response cannot be used to discover which limit — or
# whether an account exists — was hit.
RATE_LIMIT_EXCEEDED_MESSAGE = "Quá nhiều yêu cầu. Vui lòng thử lại sau {seconds} giây."
RATE_LIMIT_UNAVAILABLE_MESSAGE = (
    "Dịch vụ tạm thời không khả dụng. Vui lòng thử lại sau."
)
RATE_LIMIT_KEY_PREFIX = "ratelimit"


def normalize_identifier(identifier: str) -> str:
    """Normalize an account identifier (e.g. email) before anonymity hashing."""
    return identifier.strip().lower()


def get_client_ip(request: Request) -> str:
    """Resolve the client IP, honoring ``X-Forwarded-For`` only for configured proxies.

    By default the immediate ASGI peer address is used. A forwarded header is
    only consulted when the connecting peer is listed in ``settings.TRUSTED_PROXIES``,
    so a client cannot rotate its rate-limit bucket by spoofing headers.
    """
    client_host = request.client.host if request.client else "unknown"

    trusted_proxies = settings.TRUSTED_PROXIES
    if trusted_proxies and client_host in trusted_proxies:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first (left-most) address — the original client.
            return forwarded_for.split(",")[0].strip()

    return client_host


def anonymize_identifier(endpoint: str, identifier: str) -> str:
    """Return a stable, non-reversible digest for a rate-limit identifier.

    Uses HMAC-SHA256 with the server secret so that raw identifiers (emails,
    usernames, user ids) never appear in Redis keys. The endpoint is mixed into
    the HMAC input for domain separation between buckets.

    Note: rotating ``SECRET_KEY`` changes all digests, so in-flight rate-limit
    buckets become unreachable and their counters effectively reset for the
    remainder of the current window. This is an accepted, documented trade-off.
    """
    secret = settings.SECRET_KEY.encode("utf-8")
    message = f"{endpoint}:{identifier}".encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def _allowed_result(limit: int, window_seconds: int = 60) -> "RateLimitResult":
    return RateLimitResult(
        allowed=True,
        current_count=0,
        ttl_remaining=window_seconds,
        reset_time=time.time() + window_seconds,
        limit=limit,
        remaining=limit,
    )


def rate_limited_exception(ttl_remaining: int) -> HTTPException:
    """Build the single, uniform 429 response used by every auth limiter."""
    seconds = max(1, int(ttl_remaining))
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=RATE_LIMIT_EXCEEDED_MESSAGE.format(seconds=seconds),
        headers={"Retry-After": str(seconds)},
    )


def rate_limit_unavailable_exception() -> HTTPException:
    """Build the uniform 503 returned when a required limit cannot be evaluated."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=RATE_LIMIT_UNAVAILABLE_MESSAGE,
        headers={"Retry-After": "5"},
    )


# Lua script for atomic fixed-window rate limiting
# Returns: [allowed (0/1), current_count, ttl_remaining, reset_time_unix]
RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local current = redis.call('GET', key)
if current == false then
    -- Key doesn't exist, create it with count 1 and TTL = window
    redis.call('SET', key, 1, 'EX', window)
    return {1, 1, window, now + window}
end

local count = tonumber(current)
if count >= limit then
    -- Rate limit exceeded
    local ttl = redis.call('TTL', key)
    return {0, count, ttl, now + ttl}
end

-- Increment counter
local new_count = redis.call('INCR', key)
local ttl = redis.call('TTL', key)
if ttl < 0 then
    -- Key exists but no TTL (shouldn't happen with our logic), set TTL
    redis.call('EXPIRE', key, window)
    ttl = window
end

return {1, new_count, ttl, now + ttl}
"""


@dataclass
class RateLimitResult:
    allowed: bool
    current_count: int
    ttl_remaining: int
    reset_time: float
    limit: int
    remaining: int


class RateLimiter:
    """
    Redis-backed fixed-window rate limiter with atomic Lua script.

    Uses a single atomic Lua script to:
    - Increment counter atomically
    - Set TTL on first request
    - Return allow/deny decision with metadata
    """

    def __init__(self, redis_client: Optional[Redis] = None):
        if redis_client is not None:
            self.redis = redis_client
        else:
            from app.main import app
            self.redis = getattr(app.state, "redis", None)
        self._script = None

    async def _get_script(self):
        if self._script is None:
            self._script = self.redis.register_script(RATE_LIMIT_SCRIPT)
        return self._script

    def _normalize_email(self, email: str) -> str:
        """Normalize email for consistent rate limiting keys."""
        return normalize_identifier(email)

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP with safe, opt-in proxy support."""
        return get_client_ip(request)

    def _build_key(self, endpoint: str, identifier: str) -> str:
        """Build an anonymized rate limit key.

        The identifier is HMAC-SHA256 hashed with the server secret, so raw
        emails/usernames/user ids are never persisted in Redis.
        """
        digest = anonymize_identifier(endpoint, identifier)
        return f"{RATE_LIMIT_KEY_PREFIX}:{endpoint}:{digest}"

    async def check_limit(
        self,
        endpoint: str,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
        fail_closed: bool = False,
    ) -> RateLimitResult:
        """
        Check and consume a rate limit slot.

        Args:
            endpoint: Endpoint identifier (e.g., "auth:login")
            identifier: Unique identifier (IP, email, user_id)
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds
            fail_closed: When True, a Redis failure raises HTTP 503 instead of
                allowing the request. Used by authentication endpoints where an
                unenforceable limit must not silently fail open.

        Returns:
            RateLimitResult with allow/deny decision and metadata
        """
        if not settings.RATE_LIMIT_ENABLED:
            return _allowed_result(limit, window_seconds)

        key = self._build_key(endpoint, identifier)
        script = await self._get_script()
        now = int(time.time())

        try:
            result = await script(
                keys=[key],
                args=[limit, window_seconds, now],
            )
            allowed = bool(result[0])
            current_count = int(result[1])
            ttl_remaining = int(result[2])
            reset_time = float(result[3])
            remaining = max(0, limit - current_count)

            return RateLimitResult(
                allowed=allowed,
                current_count=current_count,
                ttl_remaining=ttl_remaining,
                reset_time=reset_time,
                limit=limit,
                remaining=remaining,
            )
        except RedisError as e:
            # Never log the raw identifier/digest or the exception message
            # (which may include connection details).
            if fail_closed:
                logger.warning(
                    "Rate limiter Redis error (fail-closed 503): %s",
                    type(e).__name__,
                )
                raise rate_limit_unavailable_exception() from None
            logger.warning(
                "Rate limiter Redis error (fail-open): %s", type(e).__name__
            )
            return _allowed_result(limit, window_seconds)

    async def reset(self, endpoint: str, identifier: str) -> None:
        """Best-effort removal of a rate limit bucket (e.g. after a login success)."""
        key = self._build_key(endpoint, identifier)
        try:
            await self.redis.delete(key)
        except RedisError as e:
            logger.warning(
                "Rate limiter reset failed: %s", type(e).__name__
            )


# Global rate limiter instance (initialized in main.py)
_rate_limiter: Optional["RateLimiter"] = None


def get_rate_limiter() -> Optional["RateLimiter"]:
    """Get the global rate limiter instance."""
    return _rate_limiter


def set_rate_limiter(limiter: "RateLimiter") -> None:
    """Set the global rate limiter instance."""
    global _rate_limiter
    _rate_limiter = limiter


async def rate_limit_dependency(
    request: Request,
    endpoint: str,
    limit: int,
    window_seconds: int = 60,
    identifier_extractor: Optional[callable] = None,
) -> RateLimitResult:
    """
    FastAPI dependency for rate limiting.

    Usage:
        @router.post("/endpoint", dependencies=[Depends(rate_limit_dependency)])
        async def endpoint(...):
            ...
    """
    limiter = get_rate_limiter()
    if limiter is None or not settings.RATE_LIMIT_ENABLED:
        return RateLimitResult(
            allowed=True,
            current_count=0,
            ttl_remaining=window_seconds,
            reset_time=time.time() + window_seconds,
            limit=limit,
            remaining=limit,
        )

    # Extract identifier
    if identifier_extractor:
        identifier = identifier_extractor(request)
    else:
        # Default: IP-based
        identifier = limiter._get_client_ip(request)

    result = await limiter.check_limit(
        endpoint=endpoint,
        identifier=identifier,
        limit=limit,
        window_seconds=60,
    )

    if not result.allowed:
        raise rate_limited_exception(result.ttl_remaining)

    return result


# Convenience functions for authentication rate limits

# Account-scoped bucket for failed login credential checks. Kept separate from
# the pre-auth IP bucket so that exhausting it can never block a valid login.
LOGIN_FAILURE_ENDPOINT = "auth:login:account"


async def _safe_json_body(request: Request) -> Optional[dict]:
    """Parse a JSON body defensively; return None on any failure."""
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        return None
    try:
        body = await request.json()
    except Exception:
        return None
    return body if isinstance(body, dict) else None


async def _enforce_auth_limit(
    endpoint: str,
    identifier: str,
    limit: int,
    window_seconds: int = 60,
) -> RateLimitResult:
    """Consume an authentication rate-limit slot, failing closed on outage.

    When rate limiting is enabled but Redis (or the limiter) is unavailable the
    request is rejected with a uniform 503 rather than silently failing open.
    """
    limiter = get_rate_limiter()
    if limiter is None:
        if settings.RATE_LIMIT_ENABLED:
            logger.warning(
                "Rate limiter unavailable; rejecting %s (fail-closed)", endpoint
            )
            raise rate_limit_unavailable_exception()
        return _allowed_result(limit, window_seconds)

    result = await limiter.check_limit(
        endpoint=endpoint,
        identifier=identifier,
        limit=limit,
        window_seconds=window_seconds,
        fail_closed=True,
    )

    if not result.allowed:
        raise rate_limited_exception(result.ttl_remaining)

    return result


async def login_rate_limit(request: Request) -> RateLimitResult:
    """Volumetric pre-auth IP limit for the login endpoints (form and JSON).

    Only the source IP is limited here. Per-account throttling is applied
    *after* credential verification (see ``record_login_failure``) so that a
    correct password can never be locked out by an attacker exhausting an
    account bucket.
    """
    ip = get_client_ip(request)
    return await _enforce_auth_limit(
        endpoint="auth:login:ip",
        identifier=ip,
        limit=settings.RATE_LIMIT_LOGIN_IP_PER_MINUTE,
    )


async def record_login_failure(email: str) -> None:
    """Record one failed credential verification for the account identifier.

    Must only be called after ``authenticate_user`` determined the credentials
    are invalid, which guarantees the account throttle can never reject a valid
    password. Raises a uniform 429 once the bounded failure threshold is hit.
    """
    limiter = get_rate_limiter()
    if limiter is None:
        if settings.RATE_LIMIT_ENABLED:
            raise rate_limit_unavailable_exception()
        return

    normalized = limiter._normalize_email(email)
    result = await limiter.check_limit(
        endpoint=LOGIN_FAILURE_ENDPOINT,
        identifier=normalized,
        limit=settings.RATE_LIMIT_LOGIN_EMAIL_PER_MINUTE,
        window_seconds=60,
        fail_closed=True,
    )
    if not result.allowed:
        raise rate_limited_exception(result.ttl_remaining)


async def clear_login_failures(email: str) -> None:
    """Clear the account failure counter after a successful authentication.

    The IP bucket is intentionally left untouched (success clears the account
    counter only).
    """
    limiter = get_rate_limiter()
    if limiter is None or not settings.RATE_LIMIT_ENABLED:
        return
    await limiter.reset(LOGIN_FAILURE_ENDPOINT, limiter._normalize_email(email))


async def register_rate_limit(request: Request) -> RateLimitResult:
    """Rate limit for register endpoint (IP-based, fail-open on outage)."""
    limiter = get_rate_limiter()
    if limiter is None or not settings.RATE_LIMIT_ENABLED:
        return _allowed_result(settings.RATE_LIMIT_REGISTER_IP_PER_MINUTE)

    ip = get_client_ip(request)
    result = await limiter.check_limit(
        endpoint="auth:register",
        identifier=ip,
        limit=settings.RATE_LIMIT_REGISTER_IP_PER_MINUTE,
        window_seconds=60,
    )
    if not result.allowed:
        raise rate_limited_exception(result.ttl_remaining)
    return result


async def forgot_password_rate_limit(request: Request) -> RateLimitResult:
    """Rate limit for forgot-password / OTP resend (IP + account identifier).

    The account bucket is keyed on the normalized identifier regardless of
    whether the account exists, so it cannot be used for enumeration. Rejection
    happens before the endpoint runs, so a throttled resend never invalidates
    or replaces an existing OTP.
    """
    ip = get_client_ip(request)
    ip_result = await _enforce_auth_limit(
        endpoint="auth:forgot_password:ip",
        identifier=ip,
        limit=settings.RATE_LIMIT_FORGOT_PASSWORD_IP_PER_MINUTE,
    )

    body = await _safe_json_body(request)
    email = body.get("email") if body else None
    if email:
        normalized_email = normalize_identifier(email)
        email_result = await _enforce_auth_limit(
            endpoint="auth:forgot_password:email",
            identifier=normalized_email,
            limit=settings.RATE_LIMIT_FORGOT_PASSWORD_EMAIL_PER_MINUTE,
        )
        if email_result.remaining < ip_result.remaining:
            return email_result

    return ip_result


async def verify_otp_rate_limit(request: Request) -> RateLimitResult:
    """Rate limit for OTP verification (IP + account identifier).

    Adds an account-scoped bucket alongside the IP bucket so that a distributed
    brute force cannot bypass the limit by rotating source IPs.
    """
    ip = get_client_ip(request)
    ip_result = await _enforce_auth_limit(
        endpoint="auth:verify_otp:ip",
        identifier=ip,
        limit=settings.RATE_LIMIT_VERIFY_OTP_IP_PER_MINUTE,
    )

    body = await _safe_json_body(request)
    email = body.get("email") if body else None
    if email:
        normalized_email = normalize_identifier(email)
        email_result = await _enforce_auth_limit(
            endpoint="auth:verify_otp:email",
            identifier=normalized_email,
            limit=settings.RATE_LIMIT_VERIFY_OTP_EMAIL_PER_MINUTE,
        )
        if email_result.remaining < ip_result.remaining:
            return email_result

    return ip_result


async def reset_password_rate_limit(request: Request) -> RateLimitResult:
    """Rate limit for password reset (IP + account identifier).

    Both buckets are consumed before the endpoint can touch the database or
    verify the reset token. The account bucket is keyed on the submitted email
    regardless of whether the account or token is valid, so it cannot be used
    for enumeration. The reset token is never included in a Redis key.
    """
    ip = get_client_ip(request)
    ip_result = await _enforce_auth_limit(
        endpoint="auth:reset_password:ip",
        identifier=ip,
        limit=settings.RATE_LIMIT_RESET_PASSWORD_IP_PER_MINUTE,
    )

    body = await _safe_json_body(request)
    email = body.get("email") if body else None
    if isinstance(email, str) and email.strip():
        normalized_email = normalize_identifier(email)
        email_result = await _enforce_auth_limit(
            endpoint="auth:reset_password:email",
            identifier=normalized_email,
            limit=settings.RATE_LIMIT_RESET_PASSWORD_EMAIL_PER_MINUTE,
        )
        if email_result.remaining < ip_result.remaining:
            return email_result

    return ip_result


EXPLANATION_REFRESH_ENDPOINT = "match_explanation_refresh"


async def explanation_refresh_rate_limit(
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> RateLimitResult:
    """Limit AI match-explanation refreshes per tenant.

    Recruiters are bucketed by their company so every recruiter in the same
    company shares one budget. Admins or accounts without a company fall back
    to their user ID. Redis is a best-effort cost guard here: if it is
    unavailable the refresh proceeds and SQL leases plus quota enforcement
    remain authoritative, matching the refresh degraded-mode contract.
    """
    limit = settings.RATE_LIMIT_EXPLANATION_REFRESH_PER_MINUTE
    limiter = get_rate_limiter()
    if not settings.RATE_LIMIT_ENABLED:
        return _allowed_result(limit)

    if limiter is None:
        logger.warning(
            "Rate limiter unavailable; allowing %s (fail-open, SQL lease "
            "remains authoritative)",
            EXPLANATION_REFRESH_ENDPOINT,
        )
        return _allowed_result(limit)

    company_id = await db.scalar(
        select(RecruiterProfile.company_id).where(
            RecruiterProfile.user_id == current_user.id,
            RecruiterProfile.is_deleted == False,  # noqa: E712
        )
    )
    tenant_key = (
        f"company:{company_id}"
        if company_id
        else f"user:{current_user.id}"
    )
    result = await limiter.check_limit(
        endpoint=EXPLANATION_REFRESH_ENDPOINT,
        identifier=tenant_key,
        limit=limit,
        window_seconds=60,
        fail_closed=False,
    )
    if not result.allowed:
        raise rate_limited_exception(result.ttl_remaining)
    return result


async def ai_chat_rate_limit(
    current_user: User = Depends(get_current_active_user),
) -> RateLimitResult:
    """Rate limit for AI chat (authenticated user ID)."""
    limiter = get_rate_limiter()
    if limiter is None or not settings.RATE_LIMIT_ENABLED:
        return RateLimitResult(
            allowed=True, current_count=0, ttl_remaining=60,
            reset_time=time.time() + 60, limit=10, remaining=10
        )

    identifier = f"user:{current_user.id}"

    result = await limiter.check_limit(
        endpoint="ai:chat",
        identifier=identifier,
        limit=settings.RATE_LIMIT_AI_CHAT_PER_MINUTE,
        window_seconds=60,
    )

    if not result.allowed:
        raise rate_limited_exception(result.ttl_remaining)

    return result


async def parse_resume_rate_limit(
    current_user: User = Depends(get_current_active_user),
) -> RateLimitResult:
    """Rate limit for parse resume (authenticated user ID)."""
    limiter = get_rate_limiter()
    if limiter is None or not settings.RATE_LIMIT_ENABLED:
        return RateLimitResult(
            allowed=True, current_count=0, ttl_remaining=60,
            reset_time=time.time() + 60, limit=5, remaining=5
        )

    identifier = f"user:{current_user.id}"

    result = await limiter.check_limit(
        endpoint="ai:parse_resume",
        identifier=identifier,
        limit=settings.RATE_LIMIT_PARSE_RESUME_PER_MINUTE,
        window_seconds=60,
    )

    if not result.allowed:
        raise rate_limited_exception(result.ttl_remaining)

    return result


async def parse_jd_rate_limit(
    current_user: User = Depends(get_current_active_user),
) -> RateLimitResult:
    """Rate limit for parse JD (authenticated user ID)."""
    limiter = get_rate_limiter()
    if limiter is None or not settings.RATE_LIMIT_ENABLED:
        return RateLimitResult(
            allowed=True, current_count=0, ttl_remaining=60,
            reset_time=time.time() + 60, limit=5, remaining=5
        )

    identifier = f"user:{current_user.id}"

    result = await limiter.check_limit(
        endpoint="ai:parse_jd",
        identifier=identifier,
        limit=settings.RATE_LIMIT_PARSE_JD_PER_MINUTE,
        window_seconds=60,
    )

    if not result.allowed:
        raise rate_limited_exception(result.ttl_remaining)

    return result


async def match_rate_limit(
    current_user: User = Depends(get_current_active_user),
) -> RateLimitResult:
    """Rate limit for match endpoint (authenticated user ID)."""
    limiter = get_rate_limiter()
    if limiter is None or not settings.RATE_LIMIT_ENABLED:
        return RateLimitResult(
            allowed=True, current_count=0, ttl_remaining=60,
            reset_time=time.time() + 60, limit=10, remaining=10
        )

    identifier = f"user:{current_user.id}"

    result = await limiter.check_limit(
        endpoint="ai:match",
        identifier=identifier,
        limit=settings.RATE_LIMIT_MATCH_PER_MINUTE,
        window_seconds=60,
    )

    if not result.allowed:
        raise rate_limited_exception(result.ttl_remaining)

    return result


async def recommendations_rate_limit(
    current_user: User = Depends(get_current_active_user),
) -> RateLimitResult:
    """Rate limit for recommendations (authenticated user ID)."""
    limiter = get_rate_limiter()
    if limiter is None or not settings.RATE_LIMIT_ENABLED:
        return RateLimitResult(
            allowed=True, current_count=0, ttl_remaining=60,
            reset_time=time.time() + 60, limit=10, remaining=10
        )

    identifier = f"user:{current_user.id}"

    result = await limiter.check_limit(
        endpoint="ai:recommendations",
        identifier=identifier,
        limit=settings.RATE_LIMIT_RECOMMENDATIONS_PER_MINUTE,
        window_seconds=60,
    )

    if not result.allowed:
        raise rate_limited_exception(result.ttl_remaining)

    return result