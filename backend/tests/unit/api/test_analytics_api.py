from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import analytics as analytics_endpoint
from app.core.exceptions import EntityNotFoundException, ValidationError
from app.main import app
from app.services.analytics_service import AnalyticsService


class FakeUser:
    id = "user"


@pytest.mark.asyncio
async def test_endpoint_returns_dashboard_for_authenticated_recruiter(monkeypatch):
    expected = SimpleNamespace(marker="dashboard")
    calls = {}

    async def fake_dashboard(self, current_user, **kwargs):
        calls["user"] = current_user
        calls.update(kwargs)
        return expected

    monkeypatch.setattr(
        AnalyticsService, "get_recruiter_dashboard", fake_dashboard
    )

    result = await analytics_endpoint.get_recruiter_analytics(
        current_user=FakeUser(),
        db=SimpleNamespace(),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        job_id=None,
    )

    assert result is expected
    assert calls["start_date"] == date(2026, 1, 1)
    assert calls["end_date"] == date(2026, 1, 31)
    assert calls["job_id"] is None


@pytest.mark.asyncio
async def test_invalid_range_maps_to_422(monkeypatch):
    async def fake_dashboard(self, current_user, **kwargs):
        raise ValidationError("start_date must be on or before end_date")

    monkeypatch.setattr(
        AnalyticsService, "get_recruiter_dashboard", fake_dashboard
    )

    with pytest.raises(HTTPException) as excinfo:
        await analytics_endpoint.get_recruiter_analytics(
            current_user=FakeUser(),
            db=SimpleNamespace(),
            start_date=date(2026, 1, 2),
            end_date=date(2026, 1, 1),
            job_id=None,
        )

    assert excinfo.value.status_code == 422


@pytest.mark.asyncio
async def test_missing_or_foreign_company_maps_to_404(monkeypatch):
    async def fake_dashboard(self, current_user, **kwargs):
        raise EntityNotFoundException("Recruiter company not found")

    monkeypatch.setattr(
        AnalyticsService, "get_recruiter_dashboard", fake_dashboard
    )

    with pytest.raises(HTTPException) as excinfo:
        await analytics_endpoint.get_recruiter_analytics(
            current_user=FakeUser(),
            db=SimpleNamespace(),
            start_date=None,
            end_date=None,
            job_id=None,
        )

    assert excinfo.value.status_code == 404


def test_analytics_route_is_registered():
    paths = app.openapi()["paths"]
    assert "/api/v1/analytics/recruiter-dashboard" in paths
