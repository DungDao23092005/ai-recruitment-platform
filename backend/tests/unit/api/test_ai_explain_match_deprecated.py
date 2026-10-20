from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.api.v1.endpoints.ai import _get_explainable_ai_service
from app.domain.enums import UserRole
from app.main import app


def _match_result_payload() -> dict:
    return {
        "overall_score": 82.0,
        "cosine_similarity": 0.85,
        "skill_coverage_score": 0.8,
        "experience_match_score": 0.75,
        "matching_skills": ["React"],
        "skill_gap": ["GraphQL"],
        "match_reasons": ["Strong overlap"],
    }


def _override_user(role: UserRole):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.is_active = True
    user.email = "user@example.com"

    async def _override():
        return user

    return _override


async def _override_get_db():
    yield MagicMock()


@pytest.fixture
def mock_explain_service():
    service = MagicMock()
    service.explain_match = AsyncMock()
    return service


@pytest.fixture
def client(mock_explain_service):
    app.dependency_overrides[_get_explainable_ai_service] = (
        lambda: mock_explain_service
    )
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _as(client, role: UserRole):
    app.dependency_overrides[get_current_user] = _override_user(role)
    return client


def test_authenticated_recruiter_gets_410(client, mock_explain_service):
    resp = _as(client, UserRole.RECRUITER).post(
        "/api/v1/ai/explain-match",
        json={"match_result": _match_result_payload()},
    )

    assert resp.status_code == status.HTTP_410_GONE
    assert "match-explanation" in resp.json()["detail"]
    mock_explain_service.explain_match.assert_not_awaited()
    app.dependency_overrides.pop(get_current_user, None)


def test_candidate_gets_410_and_no_provider_call(client, mock_explain_service):
    resp = _as(client, UserRole.CANDIDATE).post(
        "/api/v1/ai/explain-match",
        json={"match_result": _match_result_payload()},
    )

    assert resp.status_code == status.HTTP_410_GONE
    mock_explain_service.explain_match.assert_not_awaited()
    app.dependency_overrides.pop(get_current_user, None)


def test_admin_gets_410(client, mock_explain_service):
    resp = _as(client, UserRole.ADMIN).post(
        "/api/v1/ai/explain-match",
        json={"match_result": _match_result_payload()},
    )

    assert resp.status_code == status.HTTP_410_GONE
    mock_explain_service.explain_match.assert_not_awaited()
    app.dependency_overrides.pop(get_current_user, None)


def test_client_supplied_payload_is_never_explained(client, mock_explain_service):
    # A caller could try to smuggle another tenant's CV/JD or a prompt
    # injection; the endpoint must fail closed before any provider call.
    resp = _as(client, UserRole.RECRUITER).post(
        "/api/v1/ai/explain-match",
        json={
            "match_result": _match_result_payload(),
            "candidate": {"full_name": "Injected", "skills": ["ignore previous"]},
            "job": {"title": "Injected Job"},
        },
    )

    assert resp.status_code == status.HTTP_410_GONE
    mock_explain_service.explain_match.assert_not_awaited()
    app.dependency_overrides.pop(get_current_user, None)


def test_anonymous_unauthorized_before_anything(client, mock_explain_service):
    async def _deny():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    app.dependency_overrides[get_current_user] = _deny

    resp = client.post(
        "/api/v1/ai/explain-match",
        json={"match_result": _match_result_payload()},
    )

    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    mock_explain_service.explain_match.assert_not_awaited()
    app.dependency_overrides.pop(get_current_user, None)


def test_openapi_documents_410_and_not_success():
    operation = app.openapi()["paths"]["/api/v1/ai/explain-match"]["post"]

    assert operation["deprecated"] is True
    assert "410" in operation["responses"]
    assert "200" not in operation["responses"]
    assert operation["responses"]["410"]["description"]
    # Request validation is preserved so the retired route still rejects
    # malformed bodies with 422 instead of silently accepting them.
    assert "requestBody" in operation
    assert "422" in operation["responses"]


def test_missing_match_result_still_validates(client):
    resp = _as(client, UserRole.RECRUITER).post(
        "/api/v1/ai/explain-match", json={}
    )

    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    app.dependency_overrides.pop(get_current_user, None)
