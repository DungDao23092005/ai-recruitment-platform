"""Rate limiting tests for Security-02."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from redis.exceptions import RedisError, ConnectionError, TimeoutError

from app.core.rate_limit import (
    RateLimiter,
    RateLimitResult,
    reset_password_rate_limit,
    set_rate_limiter,
    get_rate_limiter,
)
from app.core.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def force_rate_limit_enabled(monkeypatch):
    """Isolate unit tests from global state mutations caused by other tests.

    The FastAPI lifespan in app/main.py mutates settings.RATE_LIMIT_ENABLED = False
    when Redis is unavailable. This fixture ensures unit tests always see
    RATE_LIMIT_ENABLED=True so they test the mocked Redis path.
    """
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)


class TestRateLimiterUnit:
    """Unit tests for RateLimiter class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock(spec=Redis)
        mock_script = AsyncMock()
        redis.register_script = MagicMock(return_value=mock_script)
        return redis, mock_script

    @pytest.fixture
    def rate_limiter(self, mock_redis):
        """Create a RateLimiter with mock Redis."""
        redis, _ = mock_redis
        return RateLimiter(redis)

    @pytest.mark.asyncio
    async def test_check_limit_allowed(self, rate_limiter, mock_redis):
        """Test that requests under limit are allowed."""
        _, mock_script = mock_redis
        # Mock script return: [allowed=1, count=1, ttl=60, reset_time=now+60]
        mock_script.return_value = [1, 1, 60, 1234567860]

        result = await rate_limiter.check_limit(
            endpoint="test:endpoint",
            identifier="test_user",
            limit=10,
            window_seconds=60,
        )

        assert result.allowed is True
        assert result.current_count == 1
        assert result.ttl_remaining == 60
        assert result.remaining == 9
        assert result.limit == 10

    @pytest.mark.asyncio
    async def test_check_limit_exceeded(self, rate_limiter, mock_redis):
        """Test that requests over limit are denied."""
        _, mock_script = mock_redis
        # Mock script return: [allowed=0, count=10, ttl=30, reset_time=now+30]
        mock_script.return_value = [0, 10, 30, 1234567830]

        result = await rate_limiter.check_limit(
            endpoint="test:endpoint",
            identifier="test_user",
            limit=10,
            window_seconds=60,
        )

        assert result.allowed is False
        assert result.current_count == 10
        assert result.ttl_remaining == 30
        assert result.remaining == 0
        assert result.limit == 10

    @pytest.mark.asyncio
    async def test_check_limit_redis_error_fail_open(self, rate_limiter, mock_redis):
        """Test fail-open behavior on Redis error."""
        _, mock_script = mock_redis
        mock_script.side_effect = RedisError("Connection refused")

        result = await rate_limiter.check_limit(
            endpoint="test:endpoint",
            identifier="test_user",
            limit=10,
            window_seconds=60,
        )

        # Fail-open: should allow request
        assert result.allowed is True
        assert result.current_count == 0
        assert result.remaining == 10

    @pytest.mark.asyncio
    async def test_normalize_email(self, rate_limiter):
        """Test email normalization."""
        assert rate_limiter._normalize_email("  Test@Example.COM  ") == "test@example.com"
        assert rate_limiter._normalize_email("test@example.com") == "test@example.com"
        assert rate_limiter._normalize_email("USER@DOMAIN.ORG") == "user@domain.org"

    def test_build_key(self, rate_limiter):
        """Keys are namespaced by endpoint and hide the raw identifier."""
        key = rate_limiter._build_key("auth:login", "192.168.1.1")
        assert key.startswith("ratelimit:auth:login:")
        assert "192.168.1.1" not in key

        key = rate_limiter._build_key("ai:chat", "user:123")
        assert key.startswith("ratelimit:ai:chat:")
        assert "user:123" not in key


class TestRateLimiterIPExtraction:
    """Test client IP extraction with proxy handling."""

    def test_direct_client_ip(self):
        """Test IP extraction without proxy."""
        from app.core.rate_limit import RateLimiter
        from fastapi import Request
        from unittest.mock import MagicMock

        limiter = RateLimiter(MagicMock())
        request = MagicMock(spec=Request)
        request.client = MagicMock()
        request.client.host = "192.168.1.100"
        request.headers = {}

        # No trusted proxies - use direct IP
        settings.TRUSTED_PROXIES = []

        ip = limiter._get_client_ip(request)
        assert ip == "192.168.1.100"

    def test_trusted_proxy_xff(self):
        """Test IP extraction with trusted proxy."""
        from app.core.rate_limit import RateLimiter
        from fastapi import Request
        from unittest.mock import MagicMock

        limiter = RateLimiter(MagicMock())
        request = MagicMock(spec=Request)
        request.client = MagicMock()
        request.client.host = "10.0.0.1"  # Trusted proxy IP
        request.headers = {"X-Forwarded-For": "192.168.1.100, 10.0.0.2"}

        # Trust the proxy
        settings.TRUSTED_PROXIES = ["10.0.0.1"]

        ip = limiter._get_client_ip(request)
        assert ip == "192.168.1.100"

    def test_untrusted_proxy_xff_ignored(self):
        """Test X-Forwarded-For ignored for untrusted proxy."""
        from app.core.rate_limit import RateLimiter
        from fastapi import Request
        from unittest.mock import MagicMock

        limiter = RateLimiter(MagicMock())
        request = MagicMock(spec=Request)
        request.client = MagicMock()
        request.client.host = "192.168.1.50"  # Not a trusted proxy
        request.headers = {"X-Forwarded-For": "192.168.1.100"}

        settings.TRUSTED_PROXIES = ["10.0.0.1"]

        ip = limiter._get_client_ip(request)
        # Should use direct client IP, not X-Forwarded-For
        assert ip == "192.168.1.50"


class TestRateLimiterFailOpen:
    """Test fail-open behavior on Redis failures."""

    @pytest.mark.asyncio
    async def test_redis_connection_error_fail_open(self):
        """Test fail-open on Redis connection error."""
        from app.core.rate_limit import RateLimiter, RateLimitResult
        from redis.exceptions import ConnectionError
        from unittest.mock import AsyncMock, MagicMock

        mock_redis = AsyncMock()
        mock_script = AsyncMock()
        mock_redis.register_script = MagicMock(return_value=mock_script)
        mock_script.side_effect = ConnectionError("Redis unavailable")

        limiter = RateLimiter(mock_redis)
        result = await limiter.check_limit("test", "user", 10, 60)

        assert result.allowed is True
        assert result.current_count == 0

    @pytest.mark.asyncio
    async def test_redis_timeout_fail_open(self):
        """Test fail-open on Redis timeout."""
        from app.core.rate_limit import RateLimiter
        from redis.exceptions import TimeoutError
        from unittest.mock import AsyncMock, MagicMock

        mock_redis = AsyncMock()
        mock_script = AsyncMock()
        mock_redis.register_script = MagicMock(return_value=mock_script)
        mock_script.side_effect = TimeoutError("Redis timeout")

        limiter = RateLimiter(mock_redis)
        result = await limiter.check_limit("test", "user", 10, 60)

        assert result.allowed is True
        assert result.current_count == 0


class TestRateLimitKeyFormat:
    """Test that rate limit keys are anonymized and collision-resistant."""

    def test_endpoint_identifier_separation(self):
        """Different endpoints with the same identifier do not collide."""
        from app.core.rate_limit import RateLimiter
        from unittest.mock import MagicMock

        limiter = RateLimiter(MagicMock())

        key1 = limiter._build_key("auth:login", "192.168.1.1")
        key2 = limiter._build_key("auth:register", "192.168.1.1")
        assert key1 != key2
        assert key1.startswith("ratelimit:auth:login:")
        assert key2.startswith("ratelimit:auth:register:")

    def test_identifier_with_colon_anonymized(self):
        """Identifiers containing colons are still hashed, not embedded."""
        from app.core.rate_limit import RateLimiter
        from unittest.mock import MagicMock

        limiter = RateLimiter(MagicMock())
        key = limiter._build_key("ai:chat", "user:123")
        assert key.startswith("ratelimit:ai:chat:")
        assert "user:123" not in key

    def test_raw_email_never_in_key(self):
        """A raw email address must never appear in a rate limit key."""
        from app.core.rate_limit import RateLimiter
        from unittest.mock import MagicMock

        limiter = RateLimiter(MagicMock())
        key = limiter._build_key("auth:login:account", "Victim@Example.COM")
        assert "Victim@Example.COM" not in key
        assert "victim@example.com" not in key
        assert "example.com" not in key
        assert "victim" not in key

    def test_key_is_stable_within_config(self):
        """The same endpoint+identifier yields the same digest (stable bucket)."""
        from app.core.rate_limit import RateLimiter
        from unittest.mock import MagicMock

        limiter = RateLimiter(MagicMock())
        assert limiter._build_key("auth:login:account", "a@b.com") == \
            limiter._build_key("auth:login:account", "a@b.com")

    def test_distinct_identifiers_differ(self):
        """Different identifiers map to different buckets."""
        from app.core.rate_limit import RateLimiter
        from unittest.mock import MagicMock

        limiter = RateLimiter(MagicMock())
        assert limiter._build_key("auth:login:account", "a@b.com") != \
            limiter._build_key("auth:login:account", "c@d.com")

    def test_uses_hmac_not_plain_sha256(self):
        """Keys use keyed HMAC-SHA256, not a plain (unkeyed) SHA-256 digest."""
        import hashlib
        from app.core.rate_limit import anonymize_identifier

        digest = anonymize_identifier("auth:login", "a@b.com")
        assert len(digest) == 64
        int(digest, 16)  # valid hex
        assert digest != hashlib.sha256(b"a@b.com").hexdigest()


class TestRateLimiterFailClosed:
    """Authentication limiters must fail closed (503) on Redis outage."""

    @pytest.mark.asyncio
    async def test_redis_error_raises_503_when_fail_closed(self):
        from app.core.rate_limit import RateLimiter
        from fastapi import HTTPException
        from unittest.mock import AsyncMock, MagicMock

        mock_redis = AsyncMock()
        mock_script = AsyncMock()
        mock_redis.register_script = MagicMock(return_value=mock_script)
        mock_script.side_effect = ConnectionError("Redis unavailable")

        limiter = RateLimiter(mock_redis)
        with pytest.raises(HTTPException) as excinfo:
            await limiter.check_limit(
                "auth:login:ip", "1.2.3.4", 20, 60, fail_closed=True
            )
        assert excinfo.value.status_code == 503
        assert "Retry-After" in excinfo.value.headers


class TestUniformRateLimitMessage:
    """All auth rejections share one message that reveals no bucket details."""

    def test_rate_limited_exception_shape(self):
        from app.core.rate_limit import (
            RATE_LIMIT_EXCEEDED_MESSAGE,
            rate_limited_exception,
        )

        exc = rate_limited_exception(7)
        assert exc.status_code == 429
        assert exc.headers["Retry-After"] == "7"
        assert exc.detail == RATE_LIMIT_EXCEEDED_MESSAGE.format(seconds=7)

    def test_rate_limit_unavailable_exception_shape(self):
        from app.core.rate_limit import rate_limit_unavailable_exception

        exc = rate_limit_unavailable_exception()
        assert exc.status_code == 503
        assert exc.headers["Retry-After"] == "5"



class TestRateLimitEndpoints:
    """Test rate limiting on actual endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_register_rate_limit(self):
        """Test register endpoint rate limiting."""
        from app.api.v1.endpoints.auth import router
        register_route = [r for r in router.routes if r.path == "/register" and "POST" in r.methods][0]
        # Check that the rate limit dependency is present
        assert len(register_route.dependencies) > 0

    def test_login_rate_limit(self):
        """Test login endpoint has rate limiting."""
        from app.api.v1.endpoints.auth import router
        login_route = [r for r in router.routes if r.path == "/login" and "POST" in r.methods][0]
        assert len(login_route.dependencies) > 0

    def test_forgot_password_rate_limit(self):
        """Test forgot password rate limiting."""
        from app.api.v1.endpoints.auth import router
        route = [r for r in router.routes if r.path == "/forgot-password" and "POST" in r.methods][0]
        assert len(route.dependencies) > 0

    def test_verify_otp_rate_limit(self):
        """Test verify OTP rate limiting."""
        from app.api.v1.endpoints.auth import router
        route = [r for r in router.routes if r.path == "/verify-reset-otp" and "POST" in r.methods][0]
        assert len(route.dependencies) > 0

    def test_reset_password_rate_limit(self):
        """Test reset-password rate limiting is wired to the route."""
        from app.api.v1.endpoints.auth import router
        route = [r for r in router.routes if r.path == "/reset-password" and "POST" in r.methods][0]
        assert len(route.dependencies) > 0


def _reset_password_request(
    payload: dict,
    client_host: str = "203.0.113.10",
) -> Request:
    body = json.dumps(payload).encode("utf-8")
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/auth/reset-password",
        "raw_path": b"/api/v1/auth/reset-password",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": (client_host, 50000),
        "server": ("testserver", 80),
    }
    return Request(scope, receive)


def _rate_limit_result(
    *,
    allowed: bool,
    limit: int,
    current_count: int | None = None,
    ttl_remaining: int = 60,
) -> RateLimitResult:
    count = current_count if current_count is not None else (1 if allowed else limit)
    return RateLimitResult(
        allowed=allowed,
        current_count=count,
        ttl_remaining=ttl_remaining,
        reset_time=1234567860,
        limit=limit,
        remaining=max(0, limit - count),
    )


class TestResetPasswordRateLimit:
    """Reset-password consumes both IP and email buckets before reset work."""

    @pytest.mark.asyncio
    async def test_checks_ip_then_normalized_email(self, monkeypatch):
        monkeypatch.setattr(settings, "TRUSTED_PROXIES", [])
        calls = []

        def _check(**kwargs):
            calls.append(kwargs)
            return _rate_limit_result(allowed=True, limit=kwargs["limit"])

        limiter = MagicMock()
        limiter.check_limit = AsyncMock(side_effect=_check)
        monkeypatch.setattr("app.core.rate_limit._rate_limiter", limiter)

        request = _reset_password_request(
            {
                "email": "  Victim@Example.COM ",
                "reset_token": "never-log-this-token",
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            }
        )
        result = await reset_password_rate_limit(request)

        assert result.allowed is True
        assert [call["endpoint"] for call in calls] == [
            "auth:reset_password:ip",
            "auth:reset_password:email",
        ]
        assert calls[0]["identifier"] == "203.0.113.10"
        assert calls[1]["identifier"] == "victim@example.com"
        assert calls[0]["limit"] == settings.RATE_LIMIT_RESET_PASSWORD_IP_PER_MINUTE
        assert calls[1]["limit"] == settings.RATE_LIMIT_RESET_PASSWORD_EMAIL_PER_MINUTE
        assert all(call["fail_closed"] is True for call in calls)
        assert all(
            "never-log-this-token" not in str(call) for call in calls
        )

    @pytest.mark.asyncio
    async def test_email_bucket_rejection_returns_429(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr(settings, "TRUSTED_PROXIES", [])

        def _check(**kwargs):
            if kwargs["endpoint"] == "auth:reset_password:email":
                return _rate_limit_result(
                    allowed=False,
                    limit=settings.RATE_LIMIT_RESET_PASSWORD_EMAIL_PER_MINUTE,
                    ttl_remaining=42,
                )
            return _rate_limit_result(allowed=True, limit=kwargs["limit"])

        limiter = MagicMock()
        limiter.check_limit = AsyncMock(side_effect=_check)
        monkeypatch.setattr("app.core.rate_limit._rate_limiter", limiter)

        request = _reset_password_request({"email": "victim@example.com"})
        with pytest.raises(HTTPException) as excinfo:
            await reset_password_rate_limit(request)

        assert excinfo.value.status_code == 429
        assert excinfo.value.headers["Retry-After"] == "42"

    @pytest.mark.asyncio
    async def test_ip_bucket_rejection_stops_before_email(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr(settings, "TRUSTED_PROXIES", [])
        calls = []

        def _check(**kwargs):
            calls.append(kwargs)
            return _rate_limit_result(
                allowed=False,
                limit=settings.RATE_LIMIT_RESET_PASSWORD_IP_PER_MINUTE,
                ttl_remaining=30,
            )

        limiter = MagicMock()
        limiter.check_limit = AsyncMock(side_effect=_check)
        monkeypatch.setattr("app.core.rate_limit._rate_limiter", limiter)

        request = _reset_password_request({"email": "victim@example.com"})
        with pytest.raises(HTTPException) as excinfo:
            await reset_password_rate_limit(request)

        assert excinfo.value.status_code == 429
        assert [call["endpoint"] for call in calls] == [
            "auth:reset_password:ip"
        ]

    @pytest.mark.asyncio
    async def test_redis_outage_fails_closed_with_503(self, monkeypatch):
        from fastapi import HTTPException
        from redis.exceptions import ConnectionError as RedisConnectionError

        monkeypatch.setattr(settings, "TRUSTED_PROXIES", [])
        mock_redis = AsyncMock()
        mock_script = AsyncMock(
            side_effect=RedisConnectionError("Redis unavailable")
        )
        mock_redis.register_script = MagicMock(return_value=mock_script)
        limiter = RateLimiter(mock_redis)
        monkeypatch.setattr("app.core.rate_limit._rate_limiter", limiter)

        request = _reset_password_request({"email": "victim@example.com"})
        with pytest.raises(HTTPException) as excinfo:
            await reset_password_rate_limit(request)

        assert excinfo.value.status_code == 503
        assert excinfo.value.headers["Retry-After"] == "5"


class TestRedisResilienceAndRecovery:
    """Tests for Redis resilience, startup retries, runtime recovery, and health consistency."""

    @pytest.fixture(autouse=True)
    def isolate_global_rate_limiter(self):
        """Ensure each test restores module-level _rate_limiter to its original state."""
        from app.core.rate_limit import get_rate_limiter, set_rate_limiter

        original_limiter = get_rate_limiter()
        try:
            yield
        finally:
            set_rate_limiter(original_limiter)

    @pytest.mark.asyncio
    async def test_startup_retry_succeeds(self, monkeypatch):
        """Test A: Startup retry succeeds after initial transient PING failures."""
        from app.main import lifespan, app
        from app.core.rate_limit import get_rate_limiter

        mock_redis = AsyncMock(spec=Redis)
        mock_redis.ping = AsyncMock(
            side_effect=[ConnectionError("fail1"), ConnectionError("fail2"), True]
        )
        mock_redis.aclose = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.disconnect = AsyncMock()

        monkeypatch.setattr(
            "app.main.ConnectionPool.from_url", MagicMock(return_value=mock_pool)
        )
        monkeypatch.setattr("app.main.Redis", MagicMock(return_value=mock_redis))

        # Mock other lifespan services
        monkeypatch.setattr("app.main.QdrantVectorRepository", MagicMock())
        monkeypatch.setattr("app.main.pubsub_manager", AsyncMock())
        monkeypatch.setattr(
            "app.services.email_outbox_worker.start_default_worker", AsyncMock()
        )
        monkeypatch.setattr(
            "app.services.email_outbox_worker.stop_default_worker", AsyncMock()
        )
        monkeypatch.setattr(
            "app.services.analytics_rollup_worker.start_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.analytics_rollup_worker.stop_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.quota_reconciliation_worker.start_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.quota_reconciliation_worker.stop_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.subscription_expiration_worker.start_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.subscription_expiration_worker.stop_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.candidate_quota_reset_worker.start_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.candidate_quota_reset_worker.stop_default_worker",
            AsyncMock(),
        )

        sleep_mock = AsyncMock()
        monkeypatch.setattr("asyncio.sleep", sleep_mock)

        async with lifespan(app):
            assert app.state.redis is mock_redis
            limiter = get_rate_limiter()
            assert limiter is not None
            assert limiter.redis is mock_redis
            assert mock_redis.ping.call_count == 3
            assert sleep_mock.call_count == 2
            # Verify exponential backoff intervals with jitter:
            delays = [call.args[0] for call in sleep_mock.call_args_list]
            assert 0.5 <= delays[0] <= 1.0
            assert 1.0 <= delays[1] <= 2.0

    @pytest.mark.asyncio
    async def test_startup_retry_exponential_backoff_and_jitter(self, monkeypatch):
        """Verify startup retries follow bounded exponential backoff with equal jitter capped at 5.0s."""
        from app.main import lifespan, app

        mock_redis = AsyncMock(spec=Redis)
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("fail"))
        mock_redis.aclose = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.disconnect = AsyncMock()

        monkeypatch.setattr(
            "app.main.ConnectionPool.from_url", MagicMock(return_value=mock_pool)
        )
        monkeypatch.setattr("app.main.Redis", MagicMock(return_value=mock_redis))
        monkeypatch.setattr("app.main.QdrantVectorRepository", MagicMock())
        monkeypatch.setattr("app.main.pubsub_manager", AsyncMock())
        monkeypatch.setattr(
            "app.services.email_outbox_worker.start_default_worker", AsyncMock()
        )
        monkeypatch.setattr(
            "app.services.email_outbox_worker.stop_default_worker", AsyncMock()
        )
        monkeypatch.setattr(
            "app.services.analytics_rollup_worker.start_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.analytics_rollup_worker.stop_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.quota_reconciliation_worker.start_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.quota_reconciliation_worker.stop_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.subscription_expiration_worker.start_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.subscription_expiration_worker.stop_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.candidate_quota_reset_worker.start_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.candidate_quota_reset_worker.stop_default_worker",
            AsyncMock(),
        )

        sleep_mock = AsyncMock()
        monkeypatch.setattr("asyncio.sleep", sleep_mock)

        # Mock random.uniform to return midpoint for deterministic verification:
        # delay = (capped / 2) + (capped / 4) = 0.75 * capped
        monkeypatch.setattr(
            "random.uniform",
            MagicMock(side_effect=lambda a, b: (a + b) / 2.0),
        )

        async with lifespan(app):
            # 5 retries configured -> 4 sleeps between retries
            assert sleep_mock.call_count == settings.REDIS_STARTUP_RETRIES - 1
            delays = [call.args[0] for call in sleep_mock.call_args_list]

            # Attempt 1: capped = min(5.0, 1.0 * 2^0) = 1.0 -> delay = 0.5 + 0.25 = 0.75
            assert delays[0] == 0.75
            # Attempt 2: capped = min(5.0, 1.0 * 2^1) = 2.0 -> delay = 1.0 + 0.5 = 1.50
            assert delays[1] == 1.5
            # Attempt 3: capped = min(5.0, 1.0 * 2^2) = 4.0 -> delay = 2.0 + 1.0 = 3.0
            assert delays[2] == 3.0
            # Attempt 4: capped = min(5.0, 1.0 * 2^3) = 5.0 (capped) -> delay = 2.5 + 1.25 = 3.75
            assert delays[3] == 3.75

            # Strictly positive and capped at 5.0
            for d in delays:
                assert 0.0 < d <= 5.0

    @pytest.mark.asyncio
    async def test_redis_unavailable_after_retries(self, monkeypatch):
        """Test B: Bounded retries exhausted; shared client and limiter retained in fail-closed state."""
        from app.main import lifespan, app
        from app.core.rate_limit import get_rate_limiter, _enforce_auth_limit
        from fastapi import HTTPException

        mock_redis = AsyncMock(spec=Redis)
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("fail"))
        mock_redis.aclose = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.disconnect = AsyncMock()

        mock_script = AsyncMock(side_effect=ConnectionError("still down"))
        mock_redis.register_script = MagicMock(return_value=mock_script)

        monkeypatch.setattr(
            "app.main.ConnectionPool.from_url", MagicMock(return_value=mock_pool)
        )
        monkeypatch.setattr("app.main.Redis", MagicMock(return_value=mock_redis))
        monkeypatch.setattr("app.main.QdrantVectorRepository", MagicMock())
        monkeypatch.setattr("app.main.pubsub_manager", AsyncMock())
        monkeypatch.setattr(
            "app.services.email_outbox_worker.start_default_worker", AsyncMock()
        )
        monkeypatch.setattr(
            "app.services.email_outbox_worker.stop_default_worker", AsyncMock()
        )
        monkeypatch.setattr(
            "app.services.analytics_rollup_worker.start_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.analytics_rollup_worker.stop_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.quota_reconciliation_worker.start_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.quota_reconciliation_worker.stop_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.subscription_expiration_worker.start_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.subscription_expiration_worker.stop_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.candidate_quota_reset_worker.start_default_worker",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.candidate_quota_reset_worker.stop_default_worker",
            AsyncMock(),
        )

        sleep_mock = AsyncMock()
        monkeypatch.setattr("asyncio.sleep", sleep_mock)

        async with lifespan(app):
            assert app.state.redis is mock_redis
            limiter = get_rate_limiter()
            assert limiter is not None
            assert limiter.redis is mock_redis
            assert mock_redis.ping.call_count == settings.REDIS_STARTUP_RETRIES

            with pytest.raises(HTTPException) as excinfo:
                await _enforce_auth_limit("auth:login:ip", "1.2.3.4", 20, 60)
            assert excinfo.value.status_code == 503

    @pytest.mark.asyncio
    async def test_redis_becomes_available_after_startup(self, monkeypatch):
        """Test C: Subsequent request recovers without process restart when Redis comes online."""
        from app.core.rate_limit import (
            RateLimiter,
            get_rate_limiter,
            _enforce_auth_limit,
        )
        from fastapi import HTTPException

        mock_redis = AsyncMock(spec=Redis)
        mock_script = AsyncMock()
        mock_redis.register_script = MagicMock(return_value=mock_script)

        mock_script.side_effect = [
            ConnectionError("Redis down"),
            [1, 1, 60, 1234567890],
        ]

        limiter = RateLimiter(mock_redis)
        monkeypatch.setattr("app.core.rate_limit._rate_limiter", limiter)

        with pytest.raises(HTTPException) as excinfo:
            await _enforce_auth_limit("auth:login:ip", "10.0.0.1", 20, 60)
        assert excinfo.value.status_code == 503

        result = await _enforce_auth_limit("auth:login:ip", "10.0.0.1", 20, 60)
        assert result.allowed is True
        assert result.current_count == 1
        assert get_rate_limiter() is limiter

    @pytest.mark.asyncio
    async def test_runtime_redis_disconnection_and_recovery(self, monkeypatch):
        """Test D: Runtime connection drop returns 503, then recovers on same client."""
        from app.core.rate_limit import RateLimiter, _enforce_auth_limit
        from fastapi import HTTPException

        mock_redis = AsyncMock(spec=Redis)
        mock_script = AsyncMock()
        mock_redis.register_script = MagicMock(return_value=mock_script)

        mock_script.side_effect = [
            [1, 1, 60, 1234567890],
            ConnectionError("Socket drop"),
            [1, 2, 59, 1234567890],
        ]

        limiter = RateLimiter(mock_redis)
        monkeypatch.setattr("app.core.rate_limit._rate_limiter", limiter)

        res1 = await _enforce_auth_limit("auth:login:ip", "10.0.0.2", 20, 60)
        assert res1.allowed is True
        assert res1.current_count == 1

        with pytest.raises(HTTPException) as excinfo:
            await _enforce_auth_limit("auth:login:ip", "10.0.0.2", 20, 60)
        assert excinfo.value.status_code == 503

        res3 = await _enforce_auth_limit("auth:login:ip", "10.0.0.2", 20, 60)
        assert res3.allowed is True
        assert res3.current_count == 2
        assert limiter.redis is mock_redis

    @pytest.mark.asyncio
    async def test_rate_limit_counter_and_ttl_integrity(self, monkeypatch):
        """Test E: Counter and TTL integrity preserved through transient errors and recovery."""
        from app.core.rate_limit import RateLimiter, _enforce_auth_limit
        from fastapi import HTTPException

        mock_redis = AsyncMock(spec=Redis)
        mock_script = AsyncMock()
        mock_redis.register_script = MagicMock(return_value=mock_script)

        mock_script.side_effect = [
            [1, 10, 30, 1234567890],
            TimeoutError("Redis timeout"),
            [0, 11, 25, 1234567895],
        ]

        limiter = RateLimiter(mock_redis)
        monkeypatch.setattr("app.core.rate_limit._rate_limiter", limiter)

        res1 = await _enforce_auth_limit("auth:login:ip", "10.0.0.3", 10, 60)
        assert res1.allowed is True
        assert res1.current_count == 10

        with pytest.raises(HTTPException) as excinfo:
            await _enforce_auth_limit("auth:login:ip", "10.0.0.3", 10, 60)
        assert excinfo.value.status_code == 503

        with pytest.raises(HTTPException) as excinfo:
            await _enforce_auth_limit("auth:login:ip", "10.0.0.3", 10, 60)
        assert excinfo.value.status_code == 429
        assert excinfo.value.headers["Retry-After"] == "25"

    def test_global_rate_limiter_isolated(self):
        """Verify that _rate_limiter is isolated and not leaked across tests."""
        from app.core.rate_limit import get_rate_limiter

        limiter = get_rate_limiter()
        # Verify that no test leaked a mock Redis instance into the module global
        if limiter is not None and getattr(limiter, "redis", None) is not None:
            assert not isinstance(limiter.redis, AsyncMock)

    @pytest.mark.asyncio
    async def test_lua_script_noscript_recovery(self):
        """Test F: redis-py AsyncScript automatically handles NOSCRIPT and reloads."""
        from redis.commands.core import AsyncScript
        from redis.exceptions import NoScriptError

        mock_client = AsyncMock(spec=Redis)
        script_text = b"return 1"
        script = AsyncScript(mock_client, script_text)

        mock_client.evalsha = AsyncMock(
            side_effect=[NoScriptError("NOSCRIPT No matching script"), 1]
        )
        mock_client.script_load = AsyncMock(return_value="new_sha_123")

        result = await script()
        assert result == 1
        assert mock_client.evalsha.call_count == 2
        mock_client.script_load.assert_awaited_once_with(script_text)

    @pytest.mark.asyncio
    async def test_readiness_and_liveness_consistency(self):
        """Test H: Readiness accurately checks shared client, returns 503 on outage, 200 on recovery; liveness stays alive."""
        from app.api.v1.endpoints.health import (
            check_redis,
            readiness_check,
            liveness_check,
        )
        from fastapi import HTTPException

        mock_request = MagicMock(spec=Request)
        mock_request.app = MagicMock()
        mock_redis = AsyncMock(spec=Redis)
        mock_request.app.state.redis = mock_redis

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()

        # 1. Redis outage -> readiness returns 503
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("Down"))
        redis_health = await check_redis(mock_request)
        assert redis_health["status"] == "unhealthy"

        with pytest.raises(HTTPException) as excinfo:
            await readiness_check(mock_request, db=mock_db)
        assert excinfo.value.status_code == 503
        assert excinfo.value.detail["status"] == "not_ready"

        # Liveness probe remains healthy
        live = await liveness_check()
        assert live["status"] == "alive"

        # 2. Redis recovery -> readiness returns 200
        mock_redis.ping = AsyncMock(return_value=True)
        redis_health = await check_redis(mock_request)
        assert redis_health["status"] == "healthy"

        ready = await readiness_check(mock_request, db=mock_db)
        assert ready["status"] == "ready"


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
