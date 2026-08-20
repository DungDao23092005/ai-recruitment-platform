from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.v1.endpoints.companies import _get_company_service
from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
)
from app.domain.enums import CompanySize, UserRole
from app.main import app
from app.models import Company


def _fake_company() -> Company:
    now = datetime.now(timezone.utc)
    return Company(
        id=uuid.uuid4(),
        name="Acme Corp",
        slug="acme-corp",
        tax_code="123456789",
        size=CompanySize.STARTUP,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.update_owned_company = AsyncMock()
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
def recruiter_client(client):
    app.dependency_overrides[get_current_user] = _override_user(
        _fake_user(UserRole.RECRUITER)
    )
    yield client
    app.dependency_overrides.pop(get_current_user, None)


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


class TestCompanyUpdateAuthorization:
    def test_anonymous_update_401(self, unauthorized_client):
        resp = unauthorized_client.patch(
            f"/api/v1/companies/{uuid.uuid4()}",
            json={"name": "Renamed"},
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_candidate_update_forbidden(self, candidate_client, mock_service):
        resp = candidate_client.patch(
            f"/api/v1/companies/{uuid.uuid4()}",
            json={"name": "Renamed"},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        mock_service.update_owned_company.assert_not_awaited()

    def test_recruiter_update_forbidden_for_foreign_company(
        self, recruiter_client, mock_service
    ):
        mock_service.update_owned_company.side_effect = ForbiddenException(
            "Not allowed to update company"
        )
        resp = recruiter_client.patch(
            f"/api/v1/companies/{uuid.uuid4()}",
            json={"name": "Renamed"},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        mock_service.update_owned_company.assert_awaited_once()

    def test_recruiter_update_own_company_allowed(
        self, recruiter_client, mock_service
    ):
        company = _fake_company()
        mock_service.update_owned_company.return_value = company
        resp = recruiter_client.patch(
            f"/api/v1/companies/{company.id}",
            json={"name": "Renamed"},
        )
        assert resp.status_code == status.HTTP_200_OK
        call = mock_service.update_owned_company.await_args
        assert call.args[1] == company.id
        assert call.args[2].name == "Renamed"

    def test_admin_update_allowed(self, admin_client, mock_service):
        company = _fake_company()
        mock_service.update_owned_company.return_value = company
        resp = admin_client.patch(
            f"/api/v1/companies/{company.id}",
            json={"name": "Renamed"},
        )
        assert resp.status_code == status.HTTP_200_OK
        mock_service.update_owned_company.assert_awaited_once()


class TestCompanyUpdate:
    def test_unknown_company_returns_404(self, recruiter_client, mock_service):
        mock_service.update_owned_company.side_effect = EntityNotFoundException(
            f"Company {uuid.uuid4()} not found"
        )
        resp = recruiter_client.patch(
            f"/api/v1/companies/{uuid.uuid4()}",
            json={"name": "Renamed"},
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_duplicate_slug_returns_400(self, recruiter_client, mock_service):
        mock_service.update_owned_company.side_effect = ConflictException(
            "Company with slug 'taken' already exists"
        )
        resp = recruiter_client.patch(
            f"/api/v1/companies/{uuid.uuid4()}",
            json={"slug": "taken"},
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_duplicate_tax_code_returns_400(self, recruiter_client, mock_service):
        mock_service.update_owned_company.side_effect = ConflictException(
            "Company with tax_code '123' already exists"
        )
        resp = recruiter_client.patch(
            f"/api/v1/companies/{uuid.uuid4()}",
            json={"tax_code": "123"},
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_response_serializes_company(self, recruiter_client, mock_service):
        company = _fake_company()
        mock_service.update_owned_company.return_value = company
        resp = recruiter_client.patch(
            f"/api/v1/companies/{company.id}",
            json={"name": "Renamed"},
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["id"] == str(company.id)
        assert data["name"] == company.name

    def test_partial_update_only_passes_provided_fields(
        self, recruiter_client, mock_service
    ):
        company = _fake_company()
        mock_service.update_owned_company.return_value = company
        recruiter_client.patch(
            f"/api/v1/companies/{company.id}",
            json={"size": "enterprise"},
        )
        call = mock_service.update_owned_company.await_args
        payload = call.args[2]
        assert payload.size == CompanySize.ENTERPRISE
        assert payload.name is None

    def test_invalid_body_returns_422(self, recruiter_client, mock_service):
        resp = recruiter_client.patch(
            f"/api/v1/companies/{uuid.uuid4()}",
            json={"size": "not-a-size"},
        )
        assert resp.status_code == 422
        mock_service.update_owned_company.assert_not_awaited()

    def test_non_uuid_path_rejected(self, recruiter_client, mock_service):
        resp = recruiter_client.patch(
            "/api/v1/companies/not-a-uuid",
            json={"name": "Renamed"},
        )
        assert resp.status_code == 422

    def test_empty_body_is_valid_partial_update(
        self, recruiter_client, mock_service
    ):
        company = _fake_company()
        mock_service.update_owned_company.return_value = company
        resp = recruiter_client.patch(
            f"/api/v1/companies/{company.id}",
            json={},
        )
        assert resp.status_code == status.HTTP_200_OK
        mock_service.update_owned_company.assert_awaited_once()
