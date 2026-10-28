from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.core.exceptions import EntityNotFoundException
from app.domain.enums import ApplicationStatus, UserRole
from app.main import app


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fake_application() -> SimpleNamespace:
    application_id = uuid.uuid4()
    company = SimpleNamespace(name="Acme Corp")
    job = SimpleNamespace(
        id=uuid.uuid4(),
        title="Backend Engineer",
        company=company,
    )
    interview = SimpleNamespace(
        id=uuid.uuid4(),
        application_id=application_id,
        scheduled_at=_now(),
        duration_minutes=60,
        interview_type="technical",
        meeting_url=None,
        location="Room 1",
        candidate_notes=None,
        status="scheduled",
        created_at=_now(),
        updated_at=_now(),
        is_deleted=False,
    )
    return SimpleNamespace(
        id=application_id,
        candidate_id=uuid.uuid4(),
        job_id=job.id,
        status=ApplicationStatus.OFFERED,
        created_at=_now(),
        updated_at=_now(),
        job=job,
        interviews=[interview],
    )


def _override_user(role: UserRole):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.is_active = True

    async def _override():
        return user

    return _override


@pytest.fixture
def mock_require_candidate_application():
    with patch(
        "app.api.v1.endpoints.applications.require_candidate_application",
        new=AsyncMock(),
    ) as helper:
        yield helper


@pytest.fixture
def client(mock_require_candidate_application):
    async def _override_db():
        yield MagicMock()

    app.dependency_overrides[get_current_user] = _override_user(
        UserRole.CANDIDATE
    )
    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def candidate_client(client):
    yield client


@pytest.fixture
def recruiter_client(client):
    app.dependency_overrides[get_current_user] = _override_user(
        UserRole.RECRUITER
    )
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def anonymous_client(client):
    async def _override():
        raise HTTPException(status_code=401)

    app.dependency_overrides[get_current_user] = _override
    yield client
    app.dependency_overrides.pop(get_current_user, None)


def test_get_own_application_returns_candidate_shape(
    candidate_client,
    mock_require_candidate_application,
):
    application = _fake_application()
    mock_require_candidate_application.return_value = application

    resp = candidate_client.get(
        f"/api/v1/applications/mine/{application.id}"
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(application.id)
    assert body["job_id"] == str(application.job_id)
    assert body["job_title"] == "Backend Engineer"
    assert body["company_name"] == "Acme Corp"
    assert body["status"] == "offered"
    assert len(body["interviews"]) == 1
    assert body["interviews"][0]["id"] == str(
        application.interviews[0].id
    )
    assert "notes" not in body["interviews"][0]
    mock_require_candidate_application.assert_awaited_once()


def test_get_foreign_application_returns_404(
    candidate_client,
    mock_require_candidate_application,
):
    application_id = uuid.uuid4()
    mock_require_candidate_application.side_effect = EntityNotFoundException(
        f"Application {application_id} not found"
    )

    resp = candidate_client.get(
        f"/api/v1/applications/mine/{application_id}"
    )

    assert resp.status_code == 404
    assert resp.json()["detail"] == (
        f"Application {application_id} not found"
    )


def test_recruiter_cannot_use_candidate_endpoint(
    recruiter_client,
    mock_require_candidate_application,
):
    resp = recruiter_client.get(
        f"/api/v1/applications/mine/{uuid.uuid4()}"
    )

    assert resp.status_code == 403
    mock_require_candidate_application.assert_not_awaited()


def test_anonymous_cannot_use_candidate_endpoint(
    anonymous_client,
    mock_require_candidate_application,
):
    resp = anonymous_client.get(
        f"/api/v1/applications/mine/{uuid.uuid4()}"
    )

    assert resp.status_code == 401
    mock_require_candidate_application.assert_not_awaited()
