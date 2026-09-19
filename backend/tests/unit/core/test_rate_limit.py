"""Rate limiting tests for Security-02."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from redis.exceptions import RedisError, ConnectionError, TimeoutError

from app.core.rate_limit import RateLimiter, RateLimitResult, set_rate_limiter, get_rate_limiter
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
        """Test key format."""
        key = rate_limiter._build_key("auth:login", "192.168.1.1")
        assert key == "ratelimit:auth:login:192.168.1.1"

        key = rate_limiter._build_key("ai:chat", "user:123")
        assert key == "ratelimit:ai:chat:user:123"


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
    """Test rate limit key format and collision avoidance."""

    def test_endpoint_identifier_separation(self):
        """Test that endpoint and identifier don't collide."""
        from app.core.rate_limit import RateLimiter
        from unittest.mock import MagicMock

        limiter = RateLimiter(MagicMock())

        # Different endpoints with same identifier
        key1 = limiter._build_key("auth:login", "192.168.1.1")
        key2 = limiter._build_key("auth:register", "192.168.1.1")
        assert key1 != key2
        assert key1 == "ratelimit:auth:login:192.168.1.1"
        assert key2 == "ratelimit:auth:register:192.168.1.1"

    def test_identifier_with_colon(self):
        """Test identifier containing colon."""
        from app.core.rate_limit import RateLimiter
        from unittest.mock import MagicMock

        limiter = RateLimiter(MagicMock())
        key = limiter._build_key("ai:chat", "user:123")
        assert key == "ratelimit:ai:chat:user:123"


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


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])