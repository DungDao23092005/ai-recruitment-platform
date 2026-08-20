from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.exceptions import EntityNotFoundException
from app.domain.enums import ApplicationStatus, UserRole
from app.main import app


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fake_application() -> SimpleNamespace:
    company = SimpleNamespace(name="Acme Corp")
    job = SimpleNamespace(id=uuid.uuid4(), title="Backend Engineer", company=company)
    candidate = SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Jane Doe",
        title="Engineer",
    )
    return SimpleNamespace(
        id=uuid.uuid4(),
        candidate_id=candidate.id,
        job_id=job.id,
        status=ApplicationStatus.APPLIED,
        created_at=_now(),
        updated_at=_now(),
        job=job,
        candidate=candidate,
    )


def _fake_resume(candidate_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        candidate_id=candidate_id,
        title="cv.pdf",
        is_primary=True,
        parsed_data={"full_name": "Jane Doe", "skills": ["Python"]},
        created_at=_now(),
        updated_at=_now(),
    )


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.get_application_detail = AsyncMock()
    return service


@pytest.fixture
def client(mock_service):
    async def _override_db():
        yield MagicMock()

    app.dependency_overrides[get_current_user] = _override_user(
        UserRole.RECRUITER
    )
    with patch(
        "app.api.v1.endpoints.applications.ApplicationService",
        return_value=mock_service,
    ), TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _override_user(role: UserRole):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.is_active = True

    async def _override():
        return user

    return _override


@pytest.fixture
def recruiter_client(client):
    yield client


@pytest.fixture
def admin_client(client):
    app.dependency_overrides[get_current_user] = _override_user(
        UserRole.ADMIN
    )
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def candidate_client(client):
    app.dependency_overrides[get_current_user] = _override_user(
        UserRole.CANDIDATE
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


def test_get_detail_returns_application_with_resume(
    recruiter_client, mock_service
):
    application = _fake_application()
    resume = _fake_resume(application.candidate_id)
    mock_service.get_application_detail.return_value = (application, resume)

    resp = recruiter_client.get(f"/api/v1/applications/{application.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(application.id)
    assert body["job_id"] == str(application.job_id)
    assert body["job_title"] == "Backend Engineer"
    assert body["company_name"] == "Acme Corp"
    assert body["status"] == "applied"
    assert body["candidate"]["full_name"] == "Jane Doe"
    assert body["resume"] is not None
    assert body["resume"]["parsed_data"]["skills"] == ["Python"]
    mock_service.get_application_detail.assert_awaited_once()


def test_get_detail_returns_resume_null_when_no_resume(
    recruiter_client, mock_service
):
    application = _fake_application()
    mock_service.get_application_detail.return_value = (application, None)

    resp = recruiter_client.get(f"/api/v1/applications/{application.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["resume"] is None
    assert body["candidate"]["full_name"] == "Jane Doe"


def test_get_detail_404_when_application_not_found(
    recruiter_client, mock_service
):
    mock_service.get_application_detail.side_effect = EntityNotFoundException(
        "Application not found"
    )

    resp = recruiter_client.get(f"/api/v1/applications/{uuid.uuid4()}")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Application not found"


def test_get_detail_admin_allowed(admin_client, mock_service):
    application = _fake_application()
    mock_service.get_application_detail.return_value = (application, None)

    resp = admin_client.get(f"/api/v1/applications/{application.id}")

    assert resp.status_code == 200
    assert resp.json()["id"] == str(application.id)


def test_get_detail_candidate_forbidden(candidate_client, mock_service):
    resp = candidate_client.get(f"/api/v1/applications/{uuid.uuid4()}")

    assert resp.status_code == 403
    mock_service.get_application_detail.assert_not_awaited()


def test_get_detail_anonymous_returns_401(anonymous_client, mock_service):
    resp = anonymous_client.get(f"/api/v1/applications/{uuid.uuid4()}")

    assert resp.status_code == 401
    mock_service.get_application_detail.assert_not_awaited()