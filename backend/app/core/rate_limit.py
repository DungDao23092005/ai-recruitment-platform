from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from fastapi import Request, HTTPException, status, Depends
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.models import User
from app.api.deps import get_current_active_user

logger = logging.getLogger(__name__)


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
        return email.strip().lower()

    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP with proxy support.

        Only trust X-Forwarded-For when the immediate connecting peer
        is a configured trusted proxy. Otherwise use the immediate
        socket/remote address.
        """
        # Check if we should trust X-Forwarded-For
        client_host = request.client.host if request.client else "unknown"

        # Check if client is a trusted proxy
        trusted_proxies = settings.TRUSTED_PROXIES
        if trusted_proxies and client_host in trusted_proxies:
            # Trusted proxy - use X-Forwarded-For
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                # Take the first IP in the chain (original client)
                return forwarded_for.split(",")[0].strip()

        # Not a trusted proxy or no header - use direct client IP
        return client_host

    def _build_key(self, endpoint: str, identifier: str) -> str:
        """Build rate limit key with consistent format."""
        return f"ratelimit:{endpoint}:{identifier}"

    async def check_limit(
        self,
        endpoint: str,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
    ) -> RateLimitResult:
        """
        Check and consume a rate limit slot.

        Args:
            endpoint: Endpoint identifier (e.g., "auth:login")
            identifier: Unique identifier (IP, email, user_id)
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            RateLimitResult with allow/deny decision and metadata
        """
        if not settings.RATE_LIMIT_ENABLED:
            return RateLimitResult(
                allowed=True,
                current_count=0,
                ttl_remaining=window_seconds,
                reset_time=time.time() + window_seconds,
                limit=limit,
                remaining=limit,
            )

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
            logger.warning(f"Rate limiter Redis error (fail-open): {e}")
            # Fail-open: allow request on Redis failure
            return RateLimitResult(
                allowed=True,
                current_count=0,
                ttl_remaining=window_seconds,
                reset_time=time.time() + window_seconds,
                limit=limit,
                remaining=limit,
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
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {result.ttl_remaining} seconds.",
            headers={"Retry-After": str(result.ttl_remaining)},
        )

    return result


# Convenience functions for common rate limit patterns

def login_ip_rate_limit() -> callable:
    """Rate limit for login by IP."""
    async def dependency(request: Request):
        limiter = get_rate_limiter()
        if limiter is None or not settings.RATE_LIMIT_ENABLED:
            return
        ip = get_rate_limiter()._get_client_ip(Request) if get_rate_limiter() else "unknown"
        # We'll implement this properly below
        pass
    return dependency


async def login_rate_limit(request: Request) -> RateLimitResult:
    """Combined IP + email rate limit for login endpoint (form and JSON)."""
    limiter = get_rate_limiter()
    if limiter is None or not settings.RATE_LIMIT_ENABLED:
        return RateLimitResult(
            allowed=True, current_count=0, ttl_remaining=60,
            reset_time=time.time() + 60, limit=20, remaining=20
        )

    # Get IP
    ip = limiter._get_client_ip(request)

    # Check IP limit
    ip_result = await limiter.check_limit(
        endpoint="auth:login:ip",
        identifier=ip,
        limit=settings.RATE_LIMIT_LOGIN_IP_PER_MINUTE,
        window_seconds=60,
    )

    if not ip_result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {ip_result.ttl_remaining} seconds.",
            headers={"Retry-After": str(ip_result.ttl_remaining)},
        )

    # Get email from form data (for /login) or JSON body (for /login/json)
    email = None
    content_type = request.headers.get("content-type", "")
    try:
        if "application/json" in content_type:
            body = await request.json()
            email = body.get("email")
        else:
            form = await request.form()
            email = form.get("username")  # OAuth2PasswordRequestForm uses "username" for email
    except Exception:
        pass

    # Check email limit if email provided
    if email:
        normalized_email = limiter._normalize_email(email)
        email_result = await limiter.check_limit(
            endpoint="auth:login:email",
            identifier=normalized_email,
            limit=settings.RATE_LIMIT_LOGIN_EMAIL_PER_MINUTE,
            window_seconds=60,
        )

        if not email_result.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for this email. Try again in {email_result.ttl_remaining} seconds.",
                headers={"Retry-After": str(email_result.ttl_remaining)},
            )

        # Return the more restrictive result
        if email_result.remaining < ip_result.remaining:
            return email_result

    return ip_result


async def register_rate_limit(request: Request) -> RateLimitResult:
    """Rate limit for register endpoint (IP-based)."""
    limiter = get_rate_limiter()
    if limiter is None or not settings.RATE_LIMIT_ENABLED:
        return RateLimitResult(
            allowed=True, current_count=0, ttl_remaining=60,
            reset_time=time.time() + 60, limit=10, remaining=10
        )

    ip = limiter._get_client_ip(request)

    result = await limiter.check_limit(
        endpoint="auth:register",
        identifier=ip,
        limit=settings.RATE_LIMIT_REGISTER_IP_PER_MINUTE,
        window_seconds=60,
    )

    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {result.ttl_remaining} seconds.",
            headers={"Retry-After": str(result.ttl_remaining)},
        )

    return result


async def forgot_password_rate_limit(request: Request) -> RateLimitResult:
    """Rate limit for forgot password (IP + email)."""
    limiter = get_rate_limiter()
    if limiter is None or not settings.RATE_LIMIT_ENABLED:
        return RateLimitResult(
            allowed=True, current_count=0, ttl_remaining=60,
            reset_time=time.time() + 60, limit=5, remaining=5
        )

    ip = limiter._get_client_ip(request)

    # Check IP limit
    ip_result = await limiter.check_limit(
        endpoint="auth:forgot_password:ip",
        identifier=ip,
        limit=settings.RATE_LIMIT_FORGOT_PASSWORD_IP_PER_MINUTE,
        window_seconds=60,
    )

    if not ip_result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {ip_result.ttl_remaining} seconds.",
            headers={"Retry-After": str(ip_result.ttl_remaining)},
        )

    # Check email limit
    email = None
    try:
        body = await request.json()
        email = body.get("email")
    except Exception:
        pass

    if email:
        normalized_email = limiter._normalize_email(email)
        email_result = await limiter.check_limit(
            endpoint="auth:forgot_password:email",
            identifier=normalized_email,
            limit=settings.RATE_LIMIT_FORGOT_PASSWORD_EMAIL_PER_MINUTE,
            window_seconds=60,
        )

        if not email_result.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for this email. Try again in {email_result.ttl_remaining} seconds.",
                headers={"Retry-After": str(email_result.ttl_remaining)},
            )

        if email_result.remaining < ip_result.remaining:
            return email_result

    return ip_result


async def verify_otp_rate_limit(request: Request) -> RateLimitResult:
    """Rate limit for verify OTP (IP-based)."""
    limiter = get_rate_limiter()
    if limiter is None or not settings.RATE_LIMIT_ENABLED:
        return RateLimitResult(
            allowed=True, current_count=0, ttl_remaining=60,
            reset_time=time.time() + 60, limit=10, remaining=10
        )

    ip = limiter._get_client_ip(request)

    result = await limiter.check_limit(
        endpoint="auth:verify_otp",
        identifier=ip,
        limit=settings.RATE_LIMIT_VERIFY_OTP_IP_PER_MINUTE,
        window_seconds=60,
    )

    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {result.ttl_remaining} seconds.",
            headers={"Retry-After": str(result.ttl_remaining)},
        )

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
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {result.ttl_remaining} seconds.",
            headers={"Retry-After": str(result.ttl_remaining)},
        )

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
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {result.ttl_remaining} seconds.",
            headers={"Retry-After": str(result.ttl_remaining)},
        )

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
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {result.ttl_remaining} seconds.",
            headers={"Retry-After": str(result.ttl_remaining)},
        )

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
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {result.ttl_remaining} seconds.",
            headers={"Retry-After": str(result.ttl_remaining)},
        )

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
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {result.ttl_remaining} seconds.",
            headers={"Retry-After": str(result.ttl_remaining)},
        )

    return result