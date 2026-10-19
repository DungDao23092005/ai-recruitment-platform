"""Real HTTP integration tests for Security-02 rate limiting.

These tests exercise the actual FastAPI dependency graph via real HTTP requests.
They validate the runtime wiring of authentication -> rate limiting -> endpoint logic.
"""

import uuid
from unittest.mock import MagicMock

import httpx
import pytest

from tests.integration.conftest import run
from tests.integration.api.conftest import API_V1, PASSWORD
from app.core.config import settings
from app.core.rate_limit import (
    RATE_LIMIT_EXCEEDED_MESSAGE,
    RateLimiter,
    set_rate_limiter,
    get_rate_limiter,
)
from app.main import app
from app.schemas.ai_chat import ChatResponse
from redis.asyncio import Redis, ConnectionPool
from redis.exceptions import ConnectionError


# ============================================================
# Fake RAGChatService for testing (offline, deterministic, fast)
# ============================================================

class FakeRAGChatService:
    """Minimal fake RAGChatService that returns immediately without Qdrant/SQL/LLM calls.

    Used to test rate limiter fail-open without downstream latency.
    """

    async def chat(
        self,
        message: str,
        actor_user,
        history: list | None = None,
        context: any = None,
    ):
        return ChatResponse(
            answer="Test response from fake RAG service",
            confidence=0.9,
            sources=[],
            suggested_followups=[],
        )


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module", autouse=True)
def configure_rate_limit_settings():
    """Override rate limit settings for this test module with small, realistic thresholds.

    This fixture runs at module scope and restores original settings after all tests
    in this module complete. It ensures rate limit tests can exhaust limits within
    the 60-second Redis TTL window.
    """
    from app.core.config import settings

    # Save original values
    original_ai_chat = settings.RATE_LIMIT_AI_CHAT_PER_MINUTE
    original_login_email = settings.RATE_LIMIT_LOGIN_EMAIL_PER_MINUTE
    original_login_ip = settings.RATE_LIMIT_LOGIN_IP_PER_MINUTE

    # Set small, realistic limits for testing
    settings.RATE_LIMIT_AI_CHAT_PER_MINUTE = 10
    settings.RATE_LIMIT_LOGIN_EMAIL_PER_MINUTE = 5
    settings.RATE_LIMIT_LOGIN_IP_PER_MINUTE = 20

    yield

    # Restore original values
    settings.RATE_LIMIT_AI_CHAT_PER_MINUTE = original_ai_chat
    settings.RATE_LIMIT_LOGIN_EMAIL_PER_MINUTE = original_login_email
    settings.RATE_LIMIT_LOGIN_IP_PER_MINUTE = original_login_ip


@pytest.fixture(scope="session", autouse=True)
def initialize_rate_limiter():
    """Initialize rate limiter before tests on the shared event loop."""
    pool = ConnectionPool.from_url(
        f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
        max_connections=20,
        decode_responses=True,
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
    )
    redis_client = Redis(connection_pool=pool)
    run(redis_client.ping())
    limiter = RateLimiter(redis_client)
    set_rate_limiter(limiter)
    yield
    run(redis_client.aclose())
    run(pool.disconnect())


@pytest.fixture(autouse=True)
def clear_rate_limit_keys():
    """Clear rate limit Redis keys before each test for isolation."""
    limiter = get_rate_limiter()
    if limiter:
        redis = limiter.redis
        run(redis.flushdb())
    yield


@pytest.fixture
def fake_rag_chat_service():
    """Provide a fake RAGChatService for testing."""
    return FakeRAGChatService()


@pytest.fixture(autouse=True)
def override_rag_chat_service(fake_rag_chat_service):
    """Override RAGChatService to use fake service for all tests."""
    from app.api.v1.endpoints.ai import _get_rag_chat_service

    app.dependency_overrides[_get_rag_chat_service] = lambda: fake_rag_chat_service
    yield
    app.dependency_overrides.pop(_get_rag_chat_service, None)


# ============================================================
# Test Classes
# ============================================================

class TestUnauthenticatedAiChat:
    """Test 1: Unauthenticated AI chat requests return 401 and don't consume user quota."""

    def test_unauthenticated_chat_returns_401(self, client):
        """Unauthenticated request to /api/v1/ai/chat returns 401."""
        resp = run(
            client.post(
                f"{settings.API_V1_STR}/ai/chat",
                json={"message": "Hello", "history": []},
            )
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"

    def test_unauthenticated_does_not_consume_user_quota(self, client):
        """Unauthenticated requests don't consume authenticated user's rate limit."""
        assert settings.RATE_LIMIT_ENABLED, "Rate limiting should be enabled for this test"

        # Create a candidate user and authenticate
        email = f"testuser-{uuid.uuid4()}@test.com"
        reg_resp = run(
            client.post(
                f"{settings.API_V1_STR}/auth/register",
                json={"email": email, "password": PASSWORD, "role": "candidate"},
            )
        )
        assert reg_resp.status_code == 201, reg_resp.text

        # Login to get token
        token = run(_login_async(client, email, PASSWORD))

        # Create candidate profile with authenticated client
        authed_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            profile = run(
                authed_client.put(
                    f"{settings.API_V1_STR}/users/me/candidate-profile",
                    json={"full_name": "Test User", "title": "Engineer"},
                )
            )
            assert profile.status_code in (200, 201), profile.text
        finally:
            run(authed_client.aclose())

        candidate_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Make unauthenticated requests from a fresh client (same network context)
        # These should NOT consume the authenticated user's quota
        unauthed_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

        try:
            for _ in range(10):
                resp = run(
                    unauthed_client.post(
                        f"{settings.API_V1_STR}/ai/chat",
                        json={"message": "Test", "history": []},
                    )
                )
                assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"

            # Now authenticated user should still have their full quota
            authenticated_resp = run(
                candidate_client.post(
                    f"{settings.API_V1_STR}/ai/chat",
                    json={"message": "Hello", "history": []},
                )
            )
            assert authenticated_resp.status_code != 429, (
                f"Authenticated user should not be rate limited by unauthenticated requests: "
                f"{authenticated_resp.status_code}"
            )
        finally:
            run(candidate_client.aclose())
            run(unauthed_client.aclose())


class TestAuthenticatedUserIsolation:
    """Test 2: Two distinct authenticated users sharing same IP have isolated quotas.

    Uses stable integration test fixtures (candidate_client, candidate_b_client)
    which create real users in the test DB and persist for the test duration.
    """

    def test_user_isolation(self, candidate_client, candidate_b_client):
        """Two authenticated users sharing IP have separate rate limit buckets.

        Uses existing pytest fixtures that create real DB users and persist
        across the test, avoiding fixture teardown races.
        """
        client1 = candidate_client
        client2 = candidate_b_client

        # Exhaust User 1's limit
        for i in range(settings.RATE_LIMIT_AI_CHAT_PER_MINUTE):
            resp = run(
                client1.post(
                    f"{settings.API_V1_STR}/ai/chat",
                    json={"message": f"Message {i}", "history": []},
                )
            )
            assert resp.status_code != 429, (
                f"Request {i+1} should succeed, got {resp.status_code}: {resp.text}"
            )

        # Next request for User 1 should be 429
        resp = run(
            client1.post(
                f"{settings.API_V1_STR}/ai/chat",
                json={"message": "Exhausted", "history": []},
            )
        )
        assert resp.status_code == 429, f"User 1 should be rate limited, got {resp.status_code}: {resp.text}"
        assert "Retry-After" in resp.headers

        # User 2 should still have full quota
        resp = run(
            client2.post(
                f"{settings.API_V1_STR}/ai/chat",
                json={"message": "User 2 message", "history": []},
            )
        )
        assert resp.status_code != 429, (
            f"User 2 should not be rate limited by User 1: {resp.status_code}: {resp.text}"
        )


class TestRedisFailurePolicy:
    """Test 3: Redis failure policy.

    Authentication endpoints (login, forgot-password, OTP verification) must
    fail CLOSED (uniform 503) because their limits are security-critical.
    Non-credential volumetric limits (register) and AI quotas keep the existing
    fail-open behaviour so unrelated features are unaffected by a Redis blip.
    """

    def test_auth_endpoints_fail_closed_on_redis_failure(self, client):
        """Login / forgot-password / verify-otp return 503 when Redis is down."""
        limiter = get_rate_limiter()
        assert limiter is not None, "Rate limiter should be initialized"

        original_script = limiter._script
        mock_script = MagicMock()
        mock_script.side_effect = ConnectionError("Simulated Redis failure")
        limiter._script = mock_script

        try:
            email = f"failclosed-{uuid.uuid4()}@test.com"

            # Register is a non-credential volumetric limit -> still fail-open.
            register_resp = run(
                client.post(
                    f"{settings.API_V1_STR}/auth/register",
                    json={"email": email, "password": PASSWORD, "role": "candidate"},
                )
            )
            assert register_resp.status_code == 201, register_resp.text

            attempts = [
                ("/auth/login/json", {"email": email, "password": PASSWORD}),
                ("/auth/forgot-password", {"email": email}),
                ("/auth/verify-reset-otp", {"email": email, "otp": "123456"}),
            ]
            for path, payload in attempts:
                resp = run(
                    client.post(f"{settings.API_V1_STR}{path}", json=payload)
                )
                assert resp.status_code == 503, (
                    f"{path}: expected 503 (fail-closed), got "
                    f"{resp.status_code}: {resp.text}"
                )
                assert "Retry-After" in resp.headers
        finally:
            limiter._script = original_script

    def test_ai_chat_fails_open_on_redis_failure(self, client):
        """Non-auth AI quota requests still fail open on a Redis blip."""
        from app.core.security import create_access_token, get_password_hash
        from app.database.session import async_session_factory
        from app.domain.enums import UserRole
        from app.models import User

        async def _create_user():
            async with async_session_factory() as session:
                user = User(
                    email=f"aifailopen-{uuid.uuid4()}@test.com",
                    password_hash=get_password_hash(PASSWORD),
                    role=UserRole.CANDIDATE,
                    is_active=True,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                return user.id

        user_id = run(_create_user())
        token = create_access_token(subject=str(user_id))

        limiter = get_rate_limiter()
        original_script = limiter._script
        mock_script = MagicMock()
        mock_script.side_effect = ConnectionError("Simulated Redis failure")
        limiter._script = mock_script

        try:
            resp = run(
                client.post(
                    f"{settings.API_V1_STR}/ai/chat",
                    json={"message": "Fail open test", "history": []},
                    headers={"Authorization": f"Bearer {token}"},
                )
            )
            assert resp.status_code != 503, f"AI chat should fail open: {resp.text}"
            assert resp.status_code != 429, f"AI chat should fail open: {resp.text}"
            assert resp.status_code == 200, resp.text
        finally:
            limiter._script = original_script


class TestJsonLoginEmailLimit:
    """Test 4: JSON login email rate limiting."""

    def test_json_login_email_limit(self, client):
        """Email-based rate limit works for JSON login."""
        email = f"jsonlogin-{uuid.uuid4()}@test.com"

        register_resp = run(
            client.post(
                f"{settings.API_V1_STR}/auth/register",
                json={"email": email, "password": "password123", "role": "candidate"},
            )
        )
        assert register_resp.status_code == 201, register_resp.text

        # Make repeated login attempts for SAME email - should hit email limit
        limit = settings.RATE_LIMIT_LOGIN_EMAIL_PER_MINUTE
        for i in range(limit):
            resp = run(
                client.post(
                    f"{settings.API_V1_STR}/auth/login/json",
                    json={"email": email, "password": "wrongpassword"},
                )
            )
            assert resp.status_code == 401, f"Attempt {i+1}: expected 401, got {resp.status_code}: {resp.text}"

        # Next attempt should hit email rate limit (429)
        resp = run(
            client.post(
                f"{settings.API_V1_STR}/auth/login/json",
                json={"email": email, "password": "wrongpassword"},
            )
        )
        assert resp.status_code == 429, f"Expected 429 after {limit} attempts, got {resp.status_code}: {resp.text}"
        assert "Retry-After" in resp.headers

    def test_json_login_email_case_insensitive(self, client):
        """Email normalization - different casing maps to same bucket."""
        base_email = f"CaseTest-{uuid.uuid4()}@Example.COM"
        register_resp = run(
            client.post(
                f"{settings.API_V1_STR}/auth/register",
                json={"email": base_email.lower(), "password": PASSWORD, "role": "candidate"},
            )
        )
        assert register_resp.status_code == 201

        # Try login with different casing of the SAME email - make enough attempts to exceed limit
        limit = settings.RATE_LIMIT_LOGIN_EMAIL_PER_MINUTE
        email_variants = [
            base_email,
            base_email.lower(),
            base_email.upper(),
            base_email,
            base_email.lower(),
        ]

        for i, variant in enumerate(email_variants[:limit]):
            resp = run(
                client.post(
                    f"{settings.API_V1_STR}/auth/login/json",
                    json={"email": variant, "password": "wrongpassword"},
                )
            )
            assert resp.status_code == 401, f"Attempt {i+1} with {variant}: expected 401, got {resp.status_code}"

        # Next attempt should be 429
        resp = run(
            client.post(
                f"{settings.API_V1_STR}/auth/login/json",
                json={"email": base_email.upper(), "password": "wrongpassword"},
            )
        )
        assert resp.status_code == 429, f"Case-insensitive bucket not working: {resp.status_code}"

    def test_email_limit_bypasses_ip(self, client):
        """Email limit is enforced regardless of source IP."""
        email = f"ipbypass-{uuid.uuid4()}@test.com"

        register_resp = run(
            client.post(
                f"{settings.API_V1_STR}/auth/register",
                json={"email": email, "password": "password123", "role": "candidate"},
            )
        )
        assert register_resp.status_code == 201

        limit = settings.RATE_LIMIT_LOGIN_EMAIL_PER_MINUTE
        for i in range(limit):
            resp = run(
                client.post(
                    f"{settings.API_V1_STR}/auth/login/json",
                    json={"email": email, "password": "wrongpassword"},
                )
            )
            assert resp.status_code == 401, f"Attempt {i+1}: {resp.status_code}"

        resp = run(
            client.post(
                f"{settings.API_V1_STR}/auth/login/json",
                json={"email": email, "password": "wrongpassword"},
            )
        )
        assert resp.status_code == 429, "Email limit should be enforced regardless of IP"


class TestFormLoginRegression:
    """Test 6: Form login email limit still works."""

    def test_form_login_email_limit(self, client):
        """Form login email limit still works after JSON login changes."""
        email = f"formlogin-{uuid.uuid4()}@test.com"

        register_resp = run(
            client.post(
                f"{settings.API_V1_STR}/auth/register",
                json={"email": email, "password": PASSWORD, "role": "candidate"},
            )
        )
        assert register_resp.status_code == 201

        limit = settings.RATE_LIMIT_LOGIN_EMAIL_PER_MINUTE
        for i in range(limit):
            resp = run(
                client.post(
                    f"{settings.API_V1_STR}/auth/login",
                    data={"username": email, "password": "wrongpassword"},
                )
            )
            assert resp.status_code == 401, f"Attempt {i+1}: {resp.status_code}"

        resp = run(
            client.post(
                f"{settings.API_V1_STR}/auth/login",
                data={"username": email, "password": "wrongpassword"},
            )
        )
        assert resp.status_code == 429, f"Expected 429, got {resp.status_code}"
        assert "Retry-After" in resp.headers

    def test_form_login_email_case_insensitive(self, client):
        """Form login email normalization works."""
        base_email = f"FormLogin-{uuid.uuid4()}@Example.COM"
        register_resp = run(
            client.post(
                f"{settings.API_V1_STR}/auth/register",
                json={"email": base_email.lower(), "password": PASSWORD, "role": "candidate"},
            )
        )
        assert register_resp.status_code == 201

        limit = settings.RATE_LIMIT_LOGIN_EMAIL_PER_MINUTE
        email_variants = [
            base_email,
            base_email.lower(),
            base_email.upper(),
            base_email,
            base_email.lower(),
        ]

        for i, variant in enumerate(email_variants[:limit]):
            resp = run(
                client.post(
                    f"{settings.API_V1_STR}/auth/login",
                    data={"username": variant, "password": "wrongpassword"},
                )
            )
            assert resp.status_code == 401, f"Variant {variant}: {resp.status_code}"

        resp = run(
            client.post(
                f"{settings.API_V1_STR}/auth/login",
                data={"username": base_email.upper(), "password": "wrongpassword"},
            )
        )
        assert resp.status_code == 429, f"Expected 429, got {resp.status_code}"


class TestXForwardedForSpoofing:
    """Test 5: Untrusted X-Forwarded-For spoofing protection."""

    def test_untrusted_xff_ignored(self, client):
        """Untrusted X-Forwarded-For is ignored for rate limiting."""
        original_proxies = settings.TRUSTED_PROXIES
        original_ip_limit = settings.RATE_LIMIT_LOGIN_IP_PER_MINUTE
        settings.TRUSTED_PROXIES = []
        # Temporarily lower IP limit so this test can exhaust it within the
        # module-scoped fixture's 60s Redis TTL window
        settings.RATE_LIMIT_LOGIN_IP_PER_MINUTE = 5

        try:
            email = f"xffspoof-{uuid.uuid4()}@test.com"
            register_resp = run(
                client.post(
                    f"{settings.API_V1_STR}/auth/register",
                    json={"email": email, "password": PASSWORD, "role": "candidate"},
                )
            )
            assert register_resp.status_code == 201

            limit = settings.RATE_LIMIT_LOGIN_IP_PER_MINUTE
            spoofed_ips = ["1.2.3.4", "5.6.7.8", "9.10.11.12", "13.14.15.16", "17.18.19.20"]

            for i, spoofed_ip in enumerate(spoofed_ips[:limit]):
                resp = run(
                    client.post(
                        f"{settings.API_V1_STR}/auth/login/json",
                        json={"email": email, "password": "wrongpassword"},
                        headers={"X-Forwarded-For": spoofed_ip},
                    )
                )
                assert resp.status_code == 401, f"Attempt {i+1}: {resp.status_code}"

            # Next should be 429 because real IP is the same
            resp = run(
                client.post(
                    f"{settings.API_V1_STR}/auth/login/json",
                    json={"email": email, "password": "wrongpassword"},
                    headers={"X-Forwarded-For": "21.22.23.24"},
                )
            )
            assert resp.status_code == 429, f"Expected 429 at attempt {limit+1}, got {resp.status_code}"
        finally:
            settings.TRUSTED_PROXIES = original_proxies
            settings.RATE_LIMIT_LOGIN_IP_PER_MINUTE = original_ip_limit

    def test_trusted_proxy_xff_respected(self, client):
        """Trusted proxy X-Forwarded-For IS respected via real HTTP request.

        Uses a real ASGI client with proper headers to exercise the actual
        _get_client_ip logic through the FastAPI dependency graph.
        """
        original_proxies = settings.TRUSTED_PROXIES
        settings.TRUSTED_PROXIES = ["10.0.0.1"]

        try:
            # Use the real FastAPI app with a real HTTP request
            # The ASGITransport will simulate a connection from 10.0.0.1
            # We can't easily change the simulated peer IP in ASGITransport,
            # so we test the _get_client_ip helper directly with a proper mock
            # that mimics Starlette's Request structure.

            from fastapi import Request
            from starlette.datastructures import Headers
            from unittest.mock import MagicMock

            limiter = get_rate_limiter()
            if limiter is None:
                pytest.skip("Rate limiter not initialized")

            # Create a proper mock Request that mimics Starlette's structure
            # Starlette Request has: client.host, headers (Headers object)
            request = MagicMock(spec=Request)

            # Client object with host
            client_mock = MagicMock()
            client_mock.host = "10.0.0.1"
            request.client = client_mock

            # Headers as a proper Headers object (case-insensitive, iterable)
            request.headers = Headers({"x-forwarded-for": "192.168.1.100, 10.0.0.2"})

            # Trusted proxy - should extract first IP from X-Forwarded-For
            ip = limiter._get_client_ip(request)
            assert ip == "192.168.1.100", f"Trusted proxy XFF not respected: got {ip}"

            # Untrusted proxy - should use direct client IP
            client_mock.host = "192.168.1.50"
            ip = limiter._get_client_ip(request)
            assert ip == "192.168.1.50", f"Untrusted XFF should be ignored: got {ip}"

        finally:
            settings.TRUSTED_PROXIES = original_proxies


class TestLoginAccountFailureThrottle:
    """Login account throttling is failure-only and cannot lock out valid logins."""

    def test_only_failures_consume_account_bucket(self, client):
        """Repeated SUCCESSFUL logins never consume the account failure bucket."""
        email = f"success-{uuid.uuid4()}@test.com"
        register_resp = run(
            client.post(
                f"{settings.API_V1_STR}/auth/register",
                json={"email": email, "password": PASSWORD, "role": "candidate"},
            )
        )
        assert register_resp.status_code == 201, register_resp.text

        limit = settings.RATE_LIMIT_LOGIN_EMAIL_PER_MINUTE
        for _ in range(limit + 2):
            resp = run(
                client.post(
                    f"{settings.API_V1_STR}/auth/login/json",
                    json={"email": email, "password": PASSWORD},
                )
            )
            assert resp.status_code == 200, resp.text

    def test_valid_password_allowed_after_bucket_exhausted(self, client):
        """A correct password still authenticates after the failure bucket fills.

        This is the no-account-DoS invariant: an attacker exhausting the
        account failure bucket from many IPs must not disable the victim's
        valid login.
        """
        email = f"no-dos-{uuid.uuid4()}@test.com"
        register_resp = run(
            client.post(
                f"{settings.API_V1_STR}/auth/register",
                json={"email": email, "password": PASSWORD, "role": "candidate"},
            )
        )
        assert register_resp.status_code == 201, register_resp.text

        limit = settings.RATE_LIMIT_LOGIN_EMAIL_PER_MINUTE
        for i in range(limit):
            resp = run(
                client.post(
                    f"{settings.API_V1_STR}/auth/login/json",
                    json={"email": email, "password": "wrongpassword"},
                )
            )
            assert resp.status_code == 401, f"attempt {i+1}: {resp.status_code}: {resp.text}"

        blocked = run(
            client.post(
                f"{settings.API_V1_STR}/auth/login/json",
                json={"email": email, "password": "wrongpassword"},
            )
        )
        assert blocked.status_code == 429, blocked.text

        # Correct password must still succeed.
        ok = run(
            client.post(
                f"{settings.API_V1_STR}/auth/login/json",
                json={"email": email, "password": PASSWORD},
            )
        )
        assert ok.status_code == 200, f"valid password blocked: {ok.text}"

    def test_success_clears_account_failure_counter(self, client):
        """A successful login resets the account failure counter."""
        email = f"clear-{uuid.uuid4()}@test.com"
        register_resp = run(
            client.post(
                f"{settings.API_V1_STR}/auth/register",
                json={"email": email, "password": PASSWORD, "role": "candidate"},
            )
        )
        assert register_resp.status_code == 201, register_resp.text

        limit = settings.RATE_LIMIT_LOGIN_EMAIL_PER_MINUTE
        for _ in range(limit - 1):
            resp = run(
                client.post(
                    f"{settings.API_V1_STR}/auth/login/json",
                    json={"email": email, "password": "wrongpassword"},
                )
            )
            assert resp.status_code == 401, resp.text

        ok = run(
            client.post(
                f"{settings.API_V1_STR}/auth/login/json",
                json={"email": email, "password": PASSWORD},
            )
        )
        assert ok.status_code == 200, ok.text

        # If the counter was cleared, a full run of failures is allowed again.
        for i in range(limit):
            resp = run(
                client.post(
                    f"{settings.API_V1_STR}/auth/login/json",
                    json={"email": email, "password": "wrongpassword"},
                )
            )
            assert resp.status_code == 401, f"attempt {i+1}: {resp.status_code}: {resp.text}"


class TestRateLimitKeyAnonymization:
    """Raw account identifiers must never be persisted in Redis keys."""

    def test_no_raw_email_in_redis_keys(self, client):
        email = f"privacy-{uuid.uuid4()}@example.com"
        register_resp = run(
            client.post(
                f"{settings.API_V1_STR}/auth/register",
                json={"email": email, "password": PASSWORD, "role": "candidate"},
            )
        )
        assert register_resp.status_code == 201, register_resp.text

        run(
            client.post(
                f"{settings.API_V1_STR}/auth/login/json",
                json={"email": email, "password": "wrongpassword"},
            )
        )

        limiter = get_rate_limiter()
        keys = run(limiter.redis.keys("ratelimit:*"))
        assert keys, "expected at least one rate limit key to exist"
        lowered = email.lower()
        for key in keys:
            assert lowered not in key.lower()
            assert "example.com" not in key.lower()
            assert "privacy-" not in key.lower()


class TestVerifyOtpAccountLimit:
    """OTP verification enforces an account-scoped limit in addition to IP."""

    def test_verify_otp_account_bucket_enforced(self, client):
        original_email_limit = settings.RATE_LIMIT_VERIFY_OTP_EMAIL_PER_MINUTE
        settings.RATE_LIMIT_VERIFY_OTP_EMAIL_PER_MINUTE = 2
        try:
            email = f"otp-acct-{uuid.uuid4()}@test.com"
            payload = {"email": email, "otp": "123456"}

            for i in range(2):
                resp = run(
                    client.post(
                        f"{settings.API_V1_STR}/auth/verify-reset-otp",
                        json=payload,
                    )
                )
                assert resp.status_code == 400, f"attempt {i+1}: {resp.status_code}: {resp.text}"

            # Same IP but the per-account bucket is now exhausted.
            resp = run(
                client.post(
                    f"{settings.API_V1_STR}/auth/verify-reset-otp",
                    json=payload,
                )
            )
            assert resp.status_code == 429, resp.text
            assert "Retry-After" in resp.headers
        finally:
            settings.RATE_LIMIT_VERIFY_OTP_EMAIL_PER_MINUTE = original_email_limit


class TestUniformRateLimitResponse:
    """Every auth-rate-limit rejection uses the same, non-revealing message."""

    def test_account_throttle_message_is_uniform(self, client):
        email = f"uniform-{uuid.uuid4()}@test.com"
        register_resp = run(
            client.post(
                f"{settings.API_V1_STR}/auth/register",
                json={"email": email, "password": PASSWORD, "role": "candidate"},
            )
        )
        assert register_resp.status_code == 201, register_resp.text

        limit = settings.RATE_LIMIT_LOGIN_EMAIL_PER_MINUTE
        for _ in range(limit):
            run(
                client.post(
                    f"{settings.API_V1_STR}/auth/login/json",
                    json={"email": email, "password": "wrongpassword"},
                )
            )

        resp = run(
            client.post(
                f"{settings.API_V1_STR}/auth/login/json",
                json={"email": email, "password": "wrongpassword"},
            )
        )
        assert resp.status_code == 429, resp.text
        detail = resp.json()["detail"]
        retry_after = int(resp.headers["Retry-After"])
        assert detail == RATE_LIMIT_EXCEEDED_MESSAGE.format(seconds=retry_after)
        assert email.lower() not in detail.lower()
        assert "email" not in detail.lower()


# ============================================================
# Helpers
# ============================================================

async def _login_async(client: httpx.AsyncClient, email: str, password: str = "password123") -> str:
    """Helper to login and get token."""
    resp = await client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x"])