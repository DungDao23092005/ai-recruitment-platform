from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.v1.endpoints.admin import _get_admin_service
from app.domain.enums import UserRole
from app.main import app
from app.schemas.admin import AdminCompanyListResponse


def _fake_company(
    company_id: uuid.UUID | None = None,
    name: str = "Acme Corp",
    is_deleted: bool = False,
) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": str(company_id or uuid.uuid4()),
        "name": name,
        "slug": "acme",
        "tax_code": "1234567890",
        "size": "sme",
        "is_deleted": is_deleted,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


def _company_mock(company: dict) -> MagicMock:
    mock = MagicMock()
    for key, value in company.items():
        setattr(mock, key, value)
    return mock


def _fake_list_payload() -> AdminCompanyListResponse:
    return AdminCompanyListResponse(
        items=[],
        total=0,
        skip=0,
        limit=10,
    )


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.list_companies = AsyncMock(return_value=([], 0))
    service.get_company = AsyncMock()
    return service


@pytest.fixture
def client(mock_service):
    app.dependency_overrides[_get_admin_service] = lambda: mock_service
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


class TestAdminCompaniesAuthorization:
    def test_anonymous_list_forbidden_401(self, unauthorized_client):
        resp = unauthorized_client.get("/api/v1/admin/companies")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_candidate_list_forbidden(self, candidate_client, mock_service):
        resp = candidate_client.get("/api/v1/admin/companies")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        mock_service.list_companies.assert_not_awaited()

    def test_recruiter_list_forbidden(self, recruiter_client, mock_service):
        resp = recruiter_client.get("/api/v1/admin/companies")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        mock_service.list_companies.assert_not_awaited()

    def test_admin_list_allowed(self, admin_client, mock_service):
        resp = admin_client.get("/api/v1/admin/companies")
        assert resp.status_code == 200
        mock_service.list_companies.assert_awaited_once()


class TestAdminCompaniesList:
    def test_empty_list(self, admin_client, mock_service):
        mock_service.list_companies.return_value = ([], 0)
        resp = admin_client.get("/api/v1/admin/companies")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {
            "items": [],
            "total": 0,
            "skip": 0,
            "limit": 10,
        }

    def test_default_skip_limit_passed_to_service(
        self, admin_client, mock_service
    ):
        admin_client.get("/api/v1/admin/companies")
        mock_service.list_companies.assert_awaited_once_with(
            skip=0, limit=10, search=None
        )

    def test_explicit_params_forwarded(self, admin_client, mock_service):
        admin_client.get(
            "/api/v1/admin/companies",
            params={
                "skip": 20,
                "limit": 25,
                "search": "acme",
            },
        )
        mock_service.list_companies.assert_awaited_once_with(
            skip=20, limit=25, search="acme"
        )

    def test_returns_items_and_total(self, admin_client, mock_service):
        company = _fake_company()
        mock_service.list_companies.return_value = (
            [_company_mock(company)],
            1,
        )
        resp = admin_client.get("/api/v1/admin/companies")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == company["name"]

    def test_limit_bounds_enforced(self, admin_client, mock_service):
        resp = admin_client.get("/api/v1/admin/companies", params={"limit": 0})
        assert resp.status_code == 422


class TestAdminCompaniesListSensitiveFields:
    def test_schema_exposes_only_expected_fields(self, admin_client, mock_service):
        company = _fake_company()
        mock_service.list_companies.return_value = (
            [_company_mock(company)],
            1,
        )
        resp = admin_client.get("/api/v1/admin/companies")
        item = resp.json()["items"][0]
        assert set(item.keys()) == {
            "id",
            "name",
            "slug",
            "tax_code",
            "size",
            "is_deleted",
            "created_at",
            "updated_at",
        }

    def test_locked_company_status_derived_from_is_deleted(
        self, admin_client, mock_service
    ):
        company = _fake_company(is_deleted=True)
        mock_service.list_companies.return_value = (
            [_company_mock(company)],
            1,
        )
        resp = admin_client.get("/api/v1/admin/companies")
        item = resp.json()["items"][0]
        assert item["is_deleted"] is True
        assert "status" not in item