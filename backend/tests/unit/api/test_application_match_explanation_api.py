from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.v1.endpoints.applications import (
    _get_ai_matching_service,
    _get_match_explanation_service,
)
from app.core.exceptions import AIError, EntityNotFoundException
from app.domain.enums import UserRole
from app.main import app


def _explanation_payload(application_id: uuid.UUID) -> dict:
    return {
        "application_id": str(application_id),
        "overall_score": 77.5,
        "score_breakdown": {
            "overall_score": 77.5,
            "cosine_similarity": 0.71,
            "skill_coverage_score": 0.5,
            "preferred_skill_coverage_score": 0.0,
            "experience_match_score": 1.0,
            "education_score": 0.5,
            "project_score": 0.4,
        },
        "summary": "Deterministic match score 77.50/100.",
        "summary_source": "deterministic",
        "skill_evaluations": [
            {
                "skill_name": "Python",
                "requirement_type": "required",
                "status": "matched_evidenced",
                "explanation": "Listed in skills.",
                "evidence": [
                    {
                        "section": "skills",
                        "field_name": "skills",
                        "item_index": 0,
                        "item_title": None,
                        "quote": "Python",
                    }
                ],
            }
        ],
        "experience_evaluations": [],
        "key_strengths": ["Candidate skills matching the job: Python."],
        "areas_for_inquiry": ["Probe depth of experience with 'Docker'."],
        "evidence": [
            {
                "section": "skills",
                "field_name": "skills",
                "item_index": 0,
                "item_title": None,
                "quote": "Python",
            }
        ],
        "data_limitations": [],
        "confidence": None,
        "model_version": None,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "cache_state": "not_cached",
    }


def _override_user(role: UserRole):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.is_active = True

    async def _override():
        return user

    return _override


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.get_application_match_explanation = AsyncMock()
    return service


@pytest.fixture
def client(mock_service):
    app.dependency_overrides[get_current_user] = _override_user(UserRole.RECRUITER)
    app.dependency_overrides[_get_ai_matching_service] = lambda: MagicMock()
    app.dependency_overrides[_get_match_explanation_service] = lambda: MagicMock()
    with patch(
        "app.api.v1.endpoints.applications.ApplicationService",
        return_value=mock_service,
    ), TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def recruiter_client(client, mock_service):
    mock_service.get_application_match_explanation.return_value = (
        _explanation_payload(uuid.uuid4())
    )
    yield client


@pytest.fixture
def admin_client(client):
    app.dependency_overrides[get_current_user] = _override_user(UserRole.ADMIN)
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


def test_recruiter_gets_explanation(recruiter_client, mock_service):
    application_id = uuid.uuid4()
    mock_service.get_application_match_explanation.return_value = (
        _explanation_payload(application_id)
    )

    resp = recruiter_client.get(
        f"/api/v1/applications/{application_id}/match-explanation"
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["application_id"] == str(application_id)
    assert body["overall_score"] == 77.5
    assert body["score_breakdown"]["cosine_similarity"] == 0.71
    assert body["skill_evaluations"][0]["status"] == "matched_evidenced"
    assert body["skill_evaluations"][0]["evidence"][0]["quote"] == "Python"
    mock_service.get_application_match_explanation.assert_awaited_once()


def test_admin_allowed(admin_client, mock_service):
    mock_service.get_application_match_explanation.return_value = (
        _explanation_payload(uuid.uuid4())
    )

    resp = admin_client.get(
        f"/api/v1/applications/{uuid.uuid4()}/match-explanation"
    )

    assert resp.status_code == 200


def test_candidate_forbidden(candidate_client, mock_service):
    resp = candidate_client.get(
        f"/api/v1/applications/{uuid.uuid4()}/match-explanation"
    )

    assert resp.status_code == 403
    mock_service.get_application_match_explanation.assert_not_awaited()


def test_anonymous_unauthorized(anonymous_client, mock_service):
    resp = anonymous_client.get(
        f"/api/v1/applications/{uuid.uuid4()}/match-explanation"
    )

    assert resp.status_code == 401
    mock_service.get_application_match_explanation.assert_not_awaited()


def test_not_found_returns_404(recruiter_client, mock_service):
    mock_service.get_application_match_explanation.side_effect = (
        EntityNotFoundException("Application abc not found")
    )

    resp = recruiter_client.get(
        f"/api/v1/applications/{uuid.uuid4()}/match-explanation"
    )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Application abc not found"


def test_ai_error_returns_502_without_leaking_details(
    recruiter_client, mock_service
):
    mock_service.get_application_match_explanation.side_effect = AIError(
        "Qdrant is down"
    )

    resp = recruiter_client.get(
        f"/api/v1/applications/{uuid.uuid4()}/match-explanation"
    )

    assert resp.status_code == 502
    assert "AI Match unavailable" in resp.json()["detail"]
    assert "Qdrant" not in resp.json()["detail"]


def test_cached_state_is_returned(recruiter_client, mock_service):
    application_id = uuid.uuid4()
    payload = _explanation_payload(application_id)
    payload["cache_state"] = "cached"
    mock_service.get_application_match_explanation.return_value = payload

    resp = recruiter_client.get(
        f"/api/v1/applications/{application_id}/match-explanation"
    )

    assert resp.status_code == 200
    assert resp.json()["cache_state"] == "cached"


def test_openapi_exposes_both_cache_states():
    schema = app.openapi()["components"]["schemas"][
        "ApplicationMatchExplanationResponse"
    ]

    assert schema["properties"]["cache_state"]["enum"] == [
        "not_cached",
        "cached",
    ]
