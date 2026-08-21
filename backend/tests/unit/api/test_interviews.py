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
    return service

@pytest.fixture
def client(mock_service):
    async def _override_user():
        user = MagicMock()
        user.id = uuid.uuid4()
        user.role = UserRole.RECRUITER
        user.is_active = True
        return user

    app.dependency_overrides[get_current_user] = _override_user
    with patch(
        "app.api.v1.endpoints.applications.InterviewService",
        return_value=mock_service,
    ), TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_schedule_interview_api(client, mock_service):
    interview_id = uuid.uuid4()
    mock_service.schedule_interview.return_value = SimpleNamespace(
        id=interview_id,
        application_id=uuid.uuid4(),
        scheduled_at=_now() + timedelta(days=1),
        duration_minutes=60,
        interview_type=InterviewType.TECHNICAL,
        meeting_url="https://meet.google.com/abc",
        location=None,
        notes=None,
        status=InterviewStatus.SCHEDULED,
        created_at=_now(),
        updated_at=_now(),
        is_deleted=False,
    )

    app_id = uuid.uuid4()
    payload = {
        "scheduled_at": (_now() + timedelta(days=1)).isoformat(),
        "duration_minutes": 60,
        "interview_type": "technical",
        "meeting_url": "https://meet.google.com/abc",
    }
    
    resp = client.post(f"/api/v1/applications/{app_id}/interviews", json=payload)
    
    assert resp.status_code == 201
    assert resp.json()["id"] == str(interview_id)
    assert resp.json()["interview_type"] == "technical"
    mock_service.schedule_interview.assert_awaited_once()

def test_cancel_interview_api(client, mock_service):
    interview_id = uuid.uuid4()
    mock_service.cancel_interview.return_value = SimpleNamespace(
        id=interview_id,
        application_id=uuid.uuid4(),
        scheduled_at=_now() + timedelta(days=1),
        duration_minutes=60,
        interview_type=InterviewType.TECHNICAL,
        meeting_url=None,
        location=None,
        notes=None,
        status=InterviewStatus.CANCELLED,
        created_at=_now(),
        updated_at=_now(),
        is_deleted=True,
    )
    
    resp = client.delete(f"/api/v1/applications/interviews/{interview_id}")
    
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    mock_service.cancel_interview.assert_awaited_once()
