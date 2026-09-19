"""Tests for SECURITY-03: Production Documentation Exposure.

Verifies that documentation endpoints are available in development/testing
but disabled in production.
"""

import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def dev_settings(monkeypatch):
    """Configure settings for development environment."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "API_V1_STR", "/api/v1")
    # Force reload the main module to pick up new settings
    if "app.main" in sys.modules:
        importlib.reload(sys.modules["app.main"])


@pytest.fixture
def prod_settings(monkeypatch):
    """Configure settings for production environment."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "API_V1_STR", "/api/v1")
    # Force reload the main module to pick up new settings
    if "app.main" in sys.modules:
        importlib.reload(sys.modules["app.main"])


@pytest.fixture
def reset_settings(monkeypatch):
    """Reset settings to development after test."""
    yield
    from app.core.config import settings
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    if "app.main" in sys.modules:
        importlib.reload(sys.modules["app.main"])


class TestDevelopmentModeDocs:
    """Test documentation availability in development/testing mode."""

    def test_docs_available(self, dev_settings):
        """GET /docs returns Swagger UI in development."""
        from app.main import app
        client = TestClient(app)
        resp = client.get("/docs")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "swagger-ui" in resp.text.lower() or "swagger" in resp.text.lower()

    def test_redoc_available(self, dev_settings):
        """GET /redoc returns ReDoc in development."""
        from app.main import app
        client = TestClient(app)
        resp = client.get("/redoc")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "redoc" in resp.text.lower()

    def test_openapi_json_available(self, dev_settings):
        """GET /api/v1/openapi.json returns valid OpenAPI spec in development."""
        from app.main import app
        client = TestClient(app)
        resp = client.get("/api/v1/openapi.json")
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("application/json")
        data = resp.json()
        assert "openapi" in data
        assert "info" in data
        assert data["info"]["title"] == "AI Recruitment Platform"
        assert "paths" in data

    def test_app_config_has_docs_urls(self, dev_settings):
        """FastAPI app has docs URLs configured in development."""
        from app.main import app
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"
        assert app.openapi_url == "/api/v1/openapi.json"


class TestProductionModeDocs:
    """Test documentation disabled in production mode."""

    def test_docs_returns_404(self, prod_settings, reset_settings):
        """GET /docs returns 404 in production."""
        from app.main import app
        client = TestClient(app)
        resp = client.get("/docs")
        assert resp.status_code == 404

    def test_redoc_returns_404(self, prod_settings, reset_settings):
        """GET /redoc returns 404 in production."""
        from app.main import app
        client = TestClient(app)
        resp = client.get("/redoc")
        assert resp.status_code == 404

    def test_openapi_json_returns_404(self, prod_settings, reset_settings):
        """GET /api/v1/openapi.json returns 404 in production."""
        from app.main import app
        client = TestClient(app)
        resp = client.get("/api/v1/openapi.json")
        assert resp.status_code == 404

    def test_app_config_no_docs_urls(self, prod_settings, reset_settings):
        """FastAPI app has no docs URLs configured in production."""
        from app.main import app
        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None


class TestDocsSecurityVerification:
    """Verify documentation security behavior."""

    def test_no_docs_routes_in_production_openapi(self, prod_settings, reset_settings):
        """Production OpenAPI spec doesn't include docs routes."""
        # In production, openapi.json itself returns 404, so this is implicit
        from app.main import app
        assert app.openapi_url is None

    def test_root_endpoint_still_works(self, prod_settings, reset_settings):
        """Root endpoint works in production even without docs."""
        from app.main import app
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert "health" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])