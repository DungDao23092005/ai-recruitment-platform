from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.exceptions import AIError, EntityNotFoundException
from app.domain.enums import UserRole
from app.main import app


def _match_result_body() -> dict:
    return {
        "overall_score": 85.0,
        "cosine_similarity": 0.9,
        "skill_coverage_score": 0.5,
        "experience_match_score": 1.0,
        "matching_skills": ["Python"],
        "skill_gap": ["Docker"],
        "match_reasons": ["✓ Matching skills: Python"],
    }


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.get_application_match = AsyncMock(
        return_value=SimpleNamespace(
            overall_score=85.0,
            cosine_similarity=0.9,
            skill_coverage_score=0.5,
            experience_match_score=1.0,
            matching_skills=["Python"],
            skill_gap=["Docker"],
            match_reasons=["✓ Matching skills: Python"],
        )
    )
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


def test_get_match_returns_match_result(recruiter_client, mock_service):
    application_id = uuid.uuid4()

    resp = recruiter_client.get(
        f"/api/v1/applications/{application_id}/match"
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_score"] == 85.0
    assert body["cosine_similarity"] == 0.9
    assert body["skill_coverage_score"] == 0.5
    assert body["experience_match_score"] == 1.0
    assert body["matching_skills"] == ["Python"]
    assert body["skill_gap"] == ["Docker"]
    mock_service.get_application_match.assert_awaited_once_with(
        current_user=mock_service.get_application_match.call_args.kwargs[
            "current_user"
        ],
        application_id=application_id,
        matching_service=mock_service.get_application_match.call_args.kwargs[
            "matching_service"
        ],
    )


def test_get_match_admin_allowed(admin_client, mock_service):
    resp = admin_client.get(f"/api/v1/applications/{uuid.uuid4()}/match")

    assert resp.status_code == 200


def test_get_match_candidate_forbidden(candidate_client, mock_service):
    resp = candidate_client.get(f"/api/v1/applications/{uuid.uuid4()}/match")

    assert resp.status_code == 403
    mock_service.get_application_match.assert_not_awaited()


def test_get_match_anonymous_returns_401(anonymous_client, mock_service):
    resp = anonymous_client.get(f"/api/v1/applications/{uuid.uuid4()}/match")

    assert resp.status_code == 401
    mock_service.get_application_match.assert_not_awaited()


def test_get_match_404_when_application_not_found(
    recruiter_client, mock_service
):
    mock_service.get_application_match.side_effect = EntityNotFoundException(
        "Application not found"
    )

    resp = recruiter_client.get(f"/api/v1/applications/{uuid.uuid4()}/match")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Application not found"


def test_get_match_502_when_ai_unavailable(
    recruiter_client, mock_service
):
    mock_service.get_application_match.side_effect = AIError("Qdrant is down")

    resp = recruiter_client.get(f"/api/v1/applications/{uuid.uuid4()}/match")

    assert resp.status_code == 502
    assert "AI Match unavailable" in resp.json()["detail"]
    assert "Qdrant" not in resp.json()["detail"]