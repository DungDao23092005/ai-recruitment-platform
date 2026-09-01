"""Tests for maintenance endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_run_reconcile():
    """Mock the run_reconcile function."""
    with patch("app.api.v1.endpoints.maintenance.run_reconcile", new_callable=AsyncMock) as mock:
        mock.return_value = {
            "sql_jobs": 0,
            "scanned": 22,
            "valid": 0,
            "stale": 22,
            "deleted": 0,
            "failed": 0,
        }
        yield mock


class TestMaintenanceReconcileQdrantJobs:
    """Tests for POST /api/v1/maintenance/reconcile-qdrant-jobs endpoint."""

    def test_missing_token_rejected(self, client):
        """Missing X-Maintenance-Token header should return 401 when token is configured."""
        with patch("app.api.v1.endpoints.maintenance.settings") as mock_settings:
            mock_settings.MAINTENANCE_TOKEN = "correct-secret-token"
            response = client.post("/api/v1/maintenance/reconcile-qdrant-jobs")
        assert response.status_code == 401
        assert "Missing maintenance token" in response.json()["detail"]

    def test_empty_configured_token_rejected(self, client):
        """Empty MAINTENANCE_TOKEN in config should reject all requests."""
        with patch("app.api.v1.endpoints.maintenance.settings") as mock_settings:
            mock_settings.MAINTENANCE_TOKEN = ""
            response = client.post(
                "/api/v1/maintenance/reconcile-qdrant-jobs",
                headers={"X-Maintenance-Token": "any-token"},
            )
        assert response.status_code == 403
        assert "not configured" in response.json()["detail"]

    def test_wrong_token_rejected(self, client, mock_run_reconcile):
        """Wrong token should return 401."""
        with patch("app.api.v1.endpoints.maintenance.settings") as mock_settings:
            mock_settings.MAINTENANCE_TOKEN = "correct-secret-token"
            response = client.post(
                "/api/v1/maintenance/reconcile-qdrant-jobs",
                headers={"X-Maintenance-Token": "wrong-token"},
            )
        assert response.status_code == 401
        assert "Invalid maintenance token" in response.json()["detail"]

    def test_correct_token_accepted_dry_run(self, client, mock_run_reconcile):
        """Correct token with dry_run=true should succeed."""
        with patch("app.api.v1.endpoints.maintenance.settings") as mock_settings:
            mock_settings.MAINTENANCE_TOKEN = "correct-secret-token"
            response = client.post(
                "/api/v1/maintenance/reconcile-qdrant-jobs?dry_run=true",
                headers={"X-Maintenance-Token": "correct-secret-token"},
            )
        assert response.status_code == 200
        assert response.json()["sql_jobs"] == 0
        assert response.json()["scanned"] == 22
        assert response.json()["stale"] == 22
        assert response.json()["deleted"] == 0

    def test_dry_run_passes_correctly(self, client, mock_run_reconcile):
        """Verify dry_run parameter is passed correctly."""
        with patch("app.api.v1.endpoints.maintenance.settings") as mock_settings:
            mock_settings.MAINTENANCE_TOKEN = "correct-secret-token"
            client.post(
                "/api/v1/maintenance/reconcile-qdrant-jobs?dry_run=true",
                headers={"X-Maintenance-Token": "correct-secret-token"},
            )
        # Verify run_reconcile was called with dry_run=True
        mock_run_reconcile.assert_called_once_with(dry_run=True)

    def test_execute_mode_passes_dry_run_false(self, client, mock_run_reconcile):
        """Verify dry_run=False is passed when execute mode requested."""
        with patch("app.api.v1.endpoints.maintenance.settings") as mock_settings:
            mock_settings.MAINTENANCE_TOKEN = "correct-secret-token"
            client.post(
                "/api/v1/maintenance/reconcile-qdrant-jobs?dry_run=false",
                headers={"X-Maintenance-Token": "correct-secret-token"},
            )
        mock_run_reconcile.assert_called_once_with(dry_run=False)

    def test_response_structure(self, client, mock_run_reconcile):
        """Verify response contains expected structured counters."""
        with patch("app.api.v1.endpoints.maintenance.settings") as mock_settings:
            mock_settings.MAINTENANCE_TOKEN = "correct-secret-token"
            response = client.post(
                "/api/v1/maintenance/reconcile-qdrant-jobs?dry_run=true",
                headers={"X-Maintenance-Token": "correct-secret-token"},
            )
        assert response.status_code == 200
        data = response.json()
        # Verify all expected fields present
        assert "sql_jobs" in data
        assert "scanned" in data
        assert "valid" in data
        assert "stale" in data
        assert "deleted" in data
        assert "failed" in data
        # Verify types
        assert isinstance(data["sql_jobs"], int)
        assert isinstance(data["scanned"], int)
        assert isinstance(data["valid"], int)
        assert isinstance(data["stale"], int)
        assert isinstance(data["deleted"], int)
        assert isinstance(data["failed"], int)

    def test_no_token_in_response(self, client, mock_run_reconcile):
        """Verify maintenance token is never in response."""
        with patch("app.api.v1.endpoints.maintenance.settings") as mock_settings:
            mock_settings.MAINTENANCE_TOKEN = "correct-secret-token"
            response = client.post(
                "/api/v1/maintenance/reconcile-qdrant-jobs?dry_run=true",
                headers={"X-Maintenance-Token": "correct-secret-token"},
            )
        assert "correct-secret-token" not in response.text
        assert "MAINTENANCE_TOKEN" not in response.text

    def test_empty_configured_token_blocks_empty_header(self, client):
        """Empty MAINTENANCE_TOKEN should reject even empty header."""
        with patch("app.api.v1.endpoints.maintenance.settings") as mock_settings:
            mock_settings.MAINTENANCE_TOKEN = ""
            response = client.post(
                "/api/v1/maintenance/reconcile-qdrant-jobs",
                headers={"X-Maintenance-Token": ""},
            )
        assert response.status_code == 403

    def test_reconciliation_failure_surfaced(self, client):
        """Reconciliation failure should be surfaced as 500 without exposing secrets."""
        with patch("app.api.v1.endpoints.maintenance.run_reconcile", new_callable=AsyncMock) as mock:
            mock.side_effect = Exception("Qdrant connection failed")
            with patch("app.api.v1.endpoints.maintenance.settings") as mock_settings:
                mock_settings.MAINTENANCE_TOKEN = "correct-secret-token"
                response = client.post(
                    "/api/v1/maintenance/reconcile-qdrant-jobs?dry_run=true",
                    headers={"X-Maintenance-Token": "correct-secret-token"},
                )
        assert response.status_code == 500
        assert "correct-secret-token" not in response.text