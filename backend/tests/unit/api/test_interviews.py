from __future__ import annotations
import uuid
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.exceptions import EntityNotFoundException, InvalidTransitionException
from app.domain.enums import UserRole, InterviewStatus, InterviewType
from app.main import app


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.schedule_interview = AsyncMock()
    service.cancel_interview = AsyncMock()
    service.candidate_action_interview = AsyncMock()
    return service


@pytest.fixture
def candidate_client(mock_service):
    async def _override_user():
        user = MagicMock()
        user.id = uuid.uuid4()
        user.role = UserRole.CANDIDATE
        user.is_active = True
        return user

    app.dependency_overrides[get_current_user] = _override_user
    with patch(
        "app.api.v1.endpoints.applications.InterviewService",
        return_value=mock_service,
    ), TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def mock_candidate_with_profile():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = UserRole.CANDIDATE
    user.is_active = True
    candidate_profile = MagicMock()
    candidate_profile.id = uuid.uuid4()
    user.candidate_profile = candidate_profile
    return user


def test_candidate_action_interview_confirm_success(candidate_client, mock_service, mock_candidate_with_profile):
    """Candidate confirms own scheduled interview -> success"""
    app_id = uuid.uuid4()
    interview_id = uuid.uuid4()
    mock_service.candidate_action_interview.return_value = SimpleNamespace(
        id=interview_id,
        application_id=app_id,
        scheduled_at=_now() + timedelta(days=1),
        duration_minutes=60,
        interview_type=InterviewType.TECHNICAL,
        meeting_url=None,
        location=None,
        notes=None,
        candidate_notes="Looking forward to it",
        status=InterviewStatus.CANDIDATE_CONFIRMED,
        created_at=_now(),
        updated_at=_now(),
        is_deleted=False,
    )

    payload = {"action": "confirm", "candidate_notes": "Looking forward to it"}
    resp = candidate_client.patch(f"/api/v1/applications/{app_id}/interviews/{interview_id}/action", json=payload)

    assert resp.status_code == 200
    assert resp.json()["status"] == "candidate_confirmed"
    assert resp.json()["candidate_notes"] == "Looking forward to it"
    mock_service.candidate_action_interview.assert_awaited_once()


def test_candidate_action_interview_decline_success(candidate_client, mock_service, mock_candidate_with_profile):
    """Candidate declines own scheduled interview with notes -> success"""
    app_id = uuid.uuid4()
    interview_id = uuid.uuid4()
    mock_service.candidate_action_interview.return_value = SimpleNamespace(
        id=interview_id,
        application_id=app_id,
        scheduled_at=_now() + timedelta(days=1),
        duration_minutes=60,
        interview_type=InterviewType.TECHNICAL,
        meeting_url=None,
        location=None,
        notes=None,
        candidate_notes="Not interested",
        status=InterviewStatus.CANDIDATE_DECLINED,
        created_at=_now(),
        updated_at=_now(),
        is_deleted=False,
    )

    payload = {"action": "decline", "candidate_notes": "Not interested"}
    resp = candidate_client.patch(f"/api/v1/applications/{app_id}/interviews/{interview_id}/action", json=payload)

    assert resp.status_code == 200
    assert resp.json()["status"] == "candidate_declined"
    assert resp.json()["candidate_notes"] == "Not interested"
    mock_service.candidate_action_interview.assert_awaited_once()


def test_candidate_action_interview_decline_without_notes_400(candidate_client, mock_service):
    """Candidate declines without notes -> 400"""
    app_id = uuid.uuid4()
    interview_id = uuid.uuid4()
    mock_service.candidate_action_interview.side_effect = InvalidTransitionException(
        "Candidate notes are required when declining an interview"
    )

    payload = {"action": "decline", "candidate_notes": ""}
    resp = candidate_client.patch(f"/api/v1/applications/{app_id}/interviews/{interview_id}/action", json=payload)

    assert resp.status_code == 400
    assert "required" in resp.json()["detail"].lower()


def test_candidate_action_interview_foreign_application_404(candidate_client, mock_service):
    """Candidate tries to access interview from another application -> 404"""
    app_id = uuid.uuid4()
    interview_id = uuid.uuid4()
    mock_service.candidate_action_interview.side_effect = EntityNotFoundException(
        f"Application {app_id} not found"
    )

    payload = {"action": "confirm"}
    resp = candidate_client.patch(f"/api/v1/applications/{app_id}/interviews/{interview_id}/action", json=payload)

    assert resp.status_code == 404


def test_candidate_action_interview_foreign_interview_404(candidate_client, mock_service):
    """Candidate tries to access interview from another application_id -> 404"""
    app_id = uuid.uuid4()
    interview_id = uuid.uuid4()
    mock_service.candidate_action_interview.side_effect = EntityNotFoundException(
        f"Interview {interview_id} not found"
    )

    payload = {"action": "confirm"}
    resp = candidate_client.patch(f"/api/v1/applications/{app_id}/interviews/{interview_id}/action", json=payload)

    assert resp.status_code == 404


def test_candidate_action_interview_completed_blocked_400(candidate_client, mock_service):
    """Candidate tries to act on COMPLETED interview -> 400"""
    app_id = uuid.uuid4()
    interview_id = uuid.uuid4()
    mock_service.candidate_action_interview.side_effect = InvalidTransitionException(
        "Cannot perform action on interview with status completed"
    )

    payload = {"action": "confirm"}
    resp = candidate_client.patch(f"/api/v1/applications/{app_id}/interviews/{interview_id}/action", json=payload)

    assert resp.status_code == 400


def test_candidate_action_interview_cancelled_blocked_400(candidate_client, mock_service):
    """Candidate tries to act on CANCELLED interview -> 400"""
    app_id = uuid.uuid4()
    interview_id = uuid.uuid4()
    mock_service.candidate_action_interview.side_effect = InvalidTransitionException(
        "Cannot perform action on interview with status cancelled"
    )

    payload = {"action": "confirm"}
    resp = candidate_client.patch(f"/api/v1/applications/{app_id}/interviews/{interview_id}/action", json=payload)

    assert resp.status_code == 400


def test_candidate_action_interview_already_confirmed_blocked_400(candidate_client, mock_service):
    """Candidate tries to act on CANDIDATE_CONFIRMED interview -> 400"""
    app_id = uuid.uuid4()
    interview_id = uuid.uuid4()
    mock_service.candidate_action_interview.side_effect = InvalidTransitionException(
        "Cannot perform action on interview with status candidate_confirmed"
    )

    payload = {"action": "confirm"}
    resp = candidate_client.patch(f"/api/v1/applications/{app_id}/interviews/{interview_id}/action", json=payload)

    assert resp.status_code == 400


def test_candidate_action_interview_already_declined_blocked_400(candidate_client, mock_service):
    """Candidate tries to act on CANDIDATE_DECLINED interview -> 400"""
    app_id = uuid.uuid4()
    interview_id = uuid.uuid4()
    mock_service.candidate_action_interview.side_effect = InvalidTransitionException(
        "Cannot perform action on interview with status candidate_declined"
    )

    payload = {"action": "confirm"}
    resp = candidate_client.patch(f"/api/v1/applications/{app_id}/interviews/{interview_id}/action", json=payload)

    assert resp.status_code == 400


def test_candidate_action_interview_soft_deleted_blocked_404(candidate_client, mock_service):
    """Candidate tries to act on soft-deleted interview -> 404"""
    app_id = uuid.uuid4()
    interview_id = uuid.uuid4()
    mock_service.candidate_action_interview.side_effect = EntityNotFoundException(
        f"Interview {interview_id} not found"
    )

    payload = {"action": "confirm"}
    resp = candidate_client.patch(f"/api/v1/applications/{app_id}/interviews/{interview_id}/action", json=payload)

    assert resp.status_code == 404


def test_candidate_action_interview_anonymous_401():
    """Anonymous user -> 401"""
    app.dependency_overrides.clear()
    with TestClient(app) as c:
        app_id = uuid.uuid4()
        interview_id = uuid.uuid4()
        payload = {"action": "confirm"}
        resp = c.patch(f"/api/v1/applications/{app_id}/interviews/{interview_id}/action", json=payload)
        assert resp.status_code == 401
    app.dependency_overrides.clear()