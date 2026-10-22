from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.api.v1.endpoints.users import _get_resume_service
from app.core.exceptions import ConflictException, EntityNotFoundException
from app.domain.enums import UserRole
from app.main import app
from app.services.resume_service import ResumeConfirmationResult

CANDIDATE_ID = uuid.uuid4()
RESUME_ID = uuid.uuid4()
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _resume(
    *,
    is_confirmed: bool = False,
    is_primary: bool = False,
    title: str | None = "Backend Engineer",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=RESUME_ID,
        candidate_id=CANDIDATE_ID,
        title=title,
        is_primary=is_primary,
        is_confirmed=is_confirmed,
        confirmed_at=NOW if is_confirmed else None,
        parsed_data={
            "full_name": "Jane Doe",
            "title": "Backend Engineer",
            "skills": ["Python", "FastAPI"],
        },
        created_at=NOW,
        updated_at=NOW,
    )


def _user(role: UserRole = UserRole.CANDIDATE) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), role=role, is_active=True)


def _override_user(role: UserRole = UserRole.CANDIDATE):
    user = _user(role)

    async def _override():
        return user

    return _override


async def _override_db():
    yield MagicMock()


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.get_draft = AsyncMock()
    service.save_draft = AsyncMock()
    service.confirm_resume = AsyncMock()
    return service


@pytest.fixture
def api(mock_service):
    app.dependency_overrides[get_current_user] = _override_user()
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[_get_resume_service] = lambda: mock_service

    with patch("app.api.v1.endpoints.users.UserService") as user_service_cls:
        user_service = user_service_cls.return_value
        user_service.get_user_with_profile = AsyncMock(
            return_value=SimpleNamespace(
                candidate_profile=SimpleNamespace(id=CANDIDATE_ID)
            )
        )
        with patch("app.api.v1.endpoints.users.ResumeRepository") as repo_cls:
            repo = repo_cls.return_value
            repo.get_primary_by_candidate = AsyncMock()
            client = TestClient(app)
            try:
                yield SimpleNamespace(
                    client=client,
                    service=mock_service,
                    repository=repo,
                )
            finally:
                client.close()

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(_get_resume_service, None)


def test_get_my_resume_returns_confirmed_primary(api):
    api.repository.get_primary_by_candidate.return_value = _resume(
        is_confirmed=True, is_primary=True
    )

    response = api.client.get("/api/v1/users/me/resume")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(RESUME_ID)
    assert body["is_confirmed"] is True
    assert body["is_primary"] is True
    assert body["parsed_data"]["full_name"] == "Jane Doe"
    api.repository.get_primary_by_candidate.assert_awaited_once_with(CANDIDATE_ID)


def test_get_my_resume_returns_404_when_no_confirmed_resume(api):
    api.repository.get_primary_by_candidate.return_value = None

    response = api.client.get("/api/v1/users/me/resume")

    assert response.status_code == 404
    assert response.json()["detail"] == "Confirmed resume not found"


def test_get_my_resume_draft_returns_unconfirmed_draft(api):
    api.service.get_draft.return_value = _resume()

    response = api.client.get("/api/v1/users/me/resume/draft")

    assert response.status_code == 200
    body = response.json()
    assert body["is_confirmed"] is False
    assert body["confirmed_at"] is None
    api.service.get_draft.assert_awaited_once_with(CANDIDATE_ID)


def test_get_my_resume_draft_returns_404_without_draft(api):
    api.service.get_draft.return_value = None

    response = api.client.get("/api/v1/users/me/resume/draft")

    assert response.status_code == 404
    assert response.json()["detail"] == "Resume draft not found"


def test_update_my_resume_draft_persists_parsed_data(api):
    api.service.save_draft.return_value = _resume(title="Updated Title")

    response = api.client.put(
        f"/api/v1/users/me/resume/{RESUME_ID}",
        json={
            "title": "Updated Title",
            "parsed_data": {
                "full_name": "Jane Doe",
                "skills": ["Python", "FastAPI", "SQL Server"],
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Updated Title"
    assert body["is_confirmed"] is False
    call = api.service.save_draft.await_args
    assert call.kwargs["candidate_id"] == CANDIDATE_ID
    assert call.kwargs["resume_id"] == RESUME_ID
    assert call.kwargs["title"] == "Updated Title"
    assert call.kwargs["parsed_data"].skills == [
        "Python",
        "FastAPI",
        "SQL Server",
    ]


def test_update_my_resume_draft_returns_404_for_foreign_resume(api):
    api.service.save_draft.side_effect = EntityNotFoundException(
        "Resume draft not found"
    )

    response = api.client.put(
        f"/api/v1/users/me/resume/{RESUME_ID}",
        json={"parsed_data": {"full_name": "Jane Doe"}},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Resume draft not found"


def test_update_my_resume_draft_returns_409_for_confirmed_resume(api):
    api.service.save_draft.side_effect = ConflictException(
        "Confirmed resumes cannot be edited. Upload a new CV instead."
    )

    response = api.client.put(
        f"/api/v1/users/me/resume/{RESUME_ID}",
        json={"parsed_data": {"full_name": "Jane Doe"}},
    )

    assert response.status_code == 409
    assert "Confirmed resumes cannot be edited" in response.json()["detail"]


def test_confirm_my_resume_returns_indexed_result(api):
    confirmed = _resume(is_confirmed=True, is_primary=True)
    api.service.confirm_resume.return_value = ResumeConfirmationResult(
        resume=confirmed,
        indexing_status="indexed",
        message="CV đã được xác nhận và sẵn sàng cho tìm kiếm, ghép nối.",
    )

    response = api.client.post(
        f"/api/v1/users/me/resume/{RESUME_ID}/confirm"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["resume"]["is_confirmed"] is True
    assert body["resume"]["is_primary"] is True
    assert body["resume"]["confirmed_at"] is not None
    assert body["indexing_status"] == "indexed"
    api.service.confirm_resume.assert_awaited_once_with(
        candidate_id=CANDIDATE_ID,
        resume_id=RESUME_ID,
    )


def test_confirm_my_resume_reports_indexing_failure(api):
    confirmed = _resume(is_confirmed=True, is_primary=True)
    api.service.confirm_resume.return_value = ResumeConfirmationResult(
        resume=confirmed,
        indexing_status="failed",
        message=(
            "CV đã được xác nhận nhưng chưa thể lập chỉ mục tìm kiếm. "
            "Vui lòng thử lại."
        ),
    )

    response = api.client.post(
        f"/api/v1/users/me/resume/{RESUME_ID}/confirm"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["resume"]["is_confirmed"] is True
    assert body["indexing_status"] == "failed"
    assert "thử lại" in body["message"]


def test_confirm_my_resume_returns_404_for_foreign_resume(api):
    api.service.confirm_resume.side_effect = EntityNotFoundException(
        "Resume draft not found"
    )

    response = api.client.post(
        f"/api/v1/users/me/resume/{RESUME_ID}/confirm"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Resume draft not found"


def test_resume_endpoints_require_candidate_role(api):
    app.dependency_overrides[get_current_user] = _override_user(UserRole.RECRUITER)

    response = api.client.get("/api/v1/users/me/resume")

    assert response.status_code == 403
    api.repository.get_primary_by_candidate.assert_not_awaited()
