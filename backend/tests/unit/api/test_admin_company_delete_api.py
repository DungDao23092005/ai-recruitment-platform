from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.v1.endpoints.companies import _get_company_service
from app.core.exceptions import AIError, EntityNotFoundException
from app.domain.enums import UserRole
from app.main import app


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.delete_company = AsyncMock()
    return service


@pytest.fixture
def client(mock_service):
    app.dependency_overrides[_get_company_service] = lambda: mock_service
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _override_user(user):
    async def _override():
        return user

    return _override


def _fake_user(role: UserRole) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.is_active = True
    return user


@pytest.fixture
def admin_client(client):
    app.dependency_overrides[get_current_user] = _override_user(
        _fake_user(UserRole.ADMIN)
    )
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def candidate_client(client):
    app.dependency_overrides[get_current_user] = _override_user(
        _fake_user(UserRole.CANDIDATE)
    )
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def recruiter_client(client):
    app.dependency_overrides[get_current_user] = _override_user(
        _fake_user(UserRole.RECRUITER)
    )
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def unauthorized_client(client):
    async def _override():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    app.dependency_overrides[get_current_user] = _override
    yield client
    app.dependency_overrides.pop(get_current_user, None)


class TestAdminCompanyDeleteAuthorization:
    def test_anonymous_delete_forbidden_401(self, unauthorized_client):
        resp = unauthorized_client.delete(
            f"/api/v1/companies/{uuid.uuid4()}"
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_candidate_delete_forbidden(self, candidate_client, mock_service):
        resp = candidate_client.delete(f"/api/v1/companies/{uuid.uuid4()}")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        mock_service.delete_company.assert_not_awaited()

    def test_recruiter_delete_forbidden(self, recruiter_client, mock_service):
        resp = recruiter_client.delete(f"/api/v1/companies/{uuid.uuid4()}")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        mock_service.delete_company.assert_not_awaited()

    def test_admin_delete_allowed(self, admin_client, mock_service):
        company_id = uuid.uuid4()
        resp = admin_client.delete(f"/api/v1/companies/{company_id}")
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        mock_service.delete_company.assert_awaited_once()
        call = mock_service.delete_company.await_args
        assert call.args[1] == company_id


class TestAdminCompanyDelete:
    def test_unknown_company_returns_404(self, admin_client, mock_service):
        mock_service.delete_company.side_effect = EntityNotFoundException(
            f"Company {uuid.uuid4()} not found"
        )
        resp = admin_client.delete(f"/api/v1/companies/{uuid.uuid4()}")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_ai_failure_returns_502(self, admin_client, mock_service):
        mock_service.delete_company.side_effect = AIError(
            "Failed to delete vector from collection 'jobs'"
        )
        resp = admin_client.delete(f"/api/v1/companies/{uuid.uuid4()}")
        assert resp.status_code == status.HTTP_502_BAD_GATEWAY

    def test_non_uuid_path_rejected(self, admin_client, mock_service):
        resp = admin_client.delete("/api/v1/companies/not-a-uuid")
        assert resp.status_code == 422