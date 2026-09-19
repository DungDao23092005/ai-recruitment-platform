"""Tests for SECURITY-04: Safe Security Headers.

Verifies that security headers are present on API responses and CORS behavior is preserved.
"""

import importlib
import sys

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import run


class TestFastAPISecurityHeaders:
    """Test security headers on FastAPI API responses."""

    def test_normal_response_has_security_headers(self, client):
        """Normal API response contains required security headers."""
        resp = run(client.get("/api/v1/health"))
        # Health endpoint may return 200 or 503 depending on DB availability
        assert resp.status_code in (200, 503)

        # Required security headers
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        # CSP for API
        csp = resp.headers.get("Content-Security-Policy")
        assert csp is not None
        assert "default-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_error_response_has_security_headers(self, client):
        """Error responses (404) still contain security headers."""
        resp = run(client.get("/api/v1/nonexistent"))
        assert resp.status_code == 404

        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        csp = resp.headers.get("Content-Security-Policy")
        assert csp is not None
        assert "default-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_rate_limited_response_has_security_headers(self, client):
        """Rate-limited responses (429) still contain security headers."""
        # Make a request that will get a 401 or 429 - login endpoint expects form data
        resp = run(
            client.post(
                "/api/v1/auth/login",
                data={"username": "test@example.com", "password": "wrong"},
            )
        )
        # Should be 401 (unauthorized) or 429 (rate limited)
        assert resp.status_code in (401, 429)

        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


class TestCORSNotBroken:
    """Test that CORS behavior is preserved with security headers."""

    def test_cors_preflight_works(self, client):
        """CORS preflight requests work correctly."""
        resp = run(
            client.options(
                "/api/v1/health",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Content-Type",
                },
            )
        )
        # CORS preflight should succeed
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert "GET" in resp.headers.get("access-control-allow-methods", "")

    def test_cors_actual_request_works(self, client):
        """Actual CORS requests work with credentials."""
        resp = run(
            client.get(
                "/api/v1/health",
                headers={"Origin": "http://localhost:5173"},
            )
        )
        assert resp.status_code in (200, 503)
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_cors_headers_preserved_with_security_headers(self, client):
        """Both CORS and security headers present on same response."""
        resp = run(
            client.get(
                "/api/v1/health",
                headers={"Origin": "http://localhost:5173"},
            )
        )
        assert resp.status_code in (200, 503)

        # CORS headers
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert resp.headers.get("access-control-allow-credentials") == "true"

        # Security headers
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        csp = resp.headers.get("Content-Security-Policy")
        assert csp is not None


class TestForbiddenHeadersNotPresent:
    """Test that forbidden headers are NOT introduced."""

    def test_no_hsts_header(self, client):
        """Strict-Transport-Security header is NOT present."""
        resp = run(client.get("/api/v1/health"))
        assert resp.status_code in (200, 503)
        assert "strict-transport-security" not in {k.lower() for k in resp.headers.keys()}

    def test_no_https_redirect(self, client):
        """No HTTPS redirect behavior introduced."""
        # Request to HTTP endpoint should not redirect to HTTPS
        resp = run(client.get("/api/v1/health"))
        assert resp.status_code in (200, 503)
        # Should not be a redirect
        assert resp.status_code not in (301, 302, 307, 308)

    def test_no_proxy_header_trust_changes(self, client):
        """No proxy-header trust middleware added."""
        # This is verified by the fact that we only added SecurityHeadersMiddleware
        # and no TrustedHostMiddleware or ProxyHeadersMiddleware
        from app.main import app
        middleware_names = [m.cls.__name__ for m in app.user_middleware]
        assert "TrustedHostMiddleware" not in middleware_names
        assert "ProxyHeadersMiddleware" not in middleware_names


class TestSecurityHeadersMiddlewareOrder:
    """Test that middleware order is correct (CORS before SecurityHeaders)."""

    def test_middleware_order_in_app(self):
        """Verify SecurityHeadersMiddleware is added after CORSMiddleware.

        Starlette's add_middleware inserts at index 0, so the LAST added
        middleware appears at index 0 in user_middleware. We verify CORS
        was added first (higher index) and SecurityHeaders added second (index 0).
        """
        from app.main import app
        middleware_names = [m.cls.__name__ for m in app.user_middleware]
        cors_index = middleware_names.index("CORSMiddleware")
        security_index = middleware_names.index("SecurityHeadersMiddleware")
        # SecurityHeaders added last -> index 0; CORS added first -> index 1
        assert security_index == 0, "SecurityHeadersMiddleware should be at index 0 (added last)"
        assert cors_index == 1, "CORSMiddleware should be at index 1 (added first)"


class TestDocsBehaviorPreserved:
    """Test SECURITY-03 production docs behavior still works."""

    def test_docs_available_in_development(self, monkeypatch):
        """Swagger UI available in development mode."""
        from app.core.config import settings
        mp = pytest.MonkeyPatch()
        mp.setattr(settings, "ENVIRONMENT", "development")
        if "app.main" in sys.modules:
            importlib.reload(sys.modules["app.main"])
        from app.main import app
        client = TestClient(app)
        resp = client.get("/docs")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        # Security headers should also be on docs
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        # CSP should NOT be on docs (allows Swagger UI to load)
        assert "Content-Security-Policy" not in resp.headers
        mp.undo()

    def test_redoc_available_in_development(self, monkeypatch):
        """ReDoc available in development mode."""
        from app.core.config import settings
        mp = pytest.MonkeyPatch()
        mp.setattr(settings, "ENVIRONMENT", "development")
        if "app.main" in sys.modules:
            importlib.reload(sys.modules["app.main"])
        from app.main import app
        client = TestClient(app)
        resp = client.get("/redoc")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        # CSP should NOT be on redoc (allows ReDoc to load)
        assert "Content-Security-Policy" not in resp.headers
        mp.undo()

    def test_openapi_json_available_in_development(self, monkeypatch):
        """OpenAPI JSON available in development mode."""
        from app.core.config import settings
        mp = pytest.MonkeyPatch()
        mp.setattr(settings, "ENVIRONMENT", "development")
        if "app.main" in sys.modules:
            importlib.reload(sys.modules["app.main"])
        from app.main import app
        client = TestClient(app)
        resp = client.get("/api/v1/openapi.json")
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("application/json")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        # CSP SHOULD be on openapi.json (it's an API endpoint, not HTML docs)
        csp = resp.headers.get("Content-Security-Policy")
        assert csp is not None
        assert "default-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp
        mp.undo()

    def test_docs_subroutes_excluded_from_csp(self, monkeypatch):
        """Documentation subroutes (e.g., /docs/oauth2-redirect) are excluded from CSP."""
        from app.core.config import settings
        mp = pytest.MonkeyPatch()
        mp.setattr(settings, "ENVIRONMENT", "development")
        if "app.main" in sys.modules:
            importlib.reload(sys.modules["app.main"])
        from app.main import app
        client = TestClient(app)
        # FastAPI's Swagger UI OAuth2 redirect route
        resp = client.get("/docs/oauth2-redirect")
        # May be 200 (if Swagger UI uses it) or 404, but CSP should not be present
        assert "Content-Security-Policy" not in resp.headers
        mp.undo()


class TestRateLimitingUnaffected:
    """Test that Security-02 rate limiting is unaffected."""

    def test_rate_limit_headers_present(self, client):
        """Rate limit responses still work with security headers."""
        # Login endpoint has rate limiting
        # Make a few requests to ensure rate limiter is active
        for _ in range(3):
            resp = run(
                client.post(
                    "/api/v1/auth/login",
                    json={"email": "test@example.com", "password": "wrong"},
                )
            )
            # Should have security headers
            assert resp.headers.get("X-Content-Type-Options") == "nosniff"
            assert resp.headers.get("X-Frame-Options") == "DENY"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])