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
from app.schemas.admin import AdminUserListResponse


def _fake_admin_user(
    user_id: uuid.UUID | None = None,
    email: str = "someone@example.com",
    role: UserRole = UserRole.CANDIDATE,
    is_deleted: bool = False,
) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": str(user_id or uuid.uuid4()),
        "email": email,
        "role": role.value,
        "is_active": True,
        "is_deleted": is_deleted,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


def _fake_list_payload() -> AdminUserListResponse:
    return AdminUserListResponse(
        items=[],
        total=0,
        skip=0,
        limit=10,
    )


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.list_users = AsyncMock(return_value=([], 0))
    service.get_user = AsyncMock()
    service.deactivate_user = AsyncMock()
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


class TestAdminUsersAuthorization:
    def test_anonymous_list_forbidden_401(self, unauthorized_client):
        resp = unauthorized_client.get("/api/v1/admin/users")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_candidate_list_forbidden(self, candidate_client, mock_service):
        resp = candidate_client.get("/api/v1/admin/users")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        mock_service.list_users.assert_not_awaited()

    def test_recruiter_list_forbidden(self, recruiter_client, mock_service):
        resp = recruiter_client.get("/api/v1/admin/users")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        mock_service.list_users.assert_not_awaited()

    def test_admin_list_allowed(self, admin_client, mock_service):
        resp = admin_client.get("/api/v1/admin/users")
        assert resp.status_code == 200
        mock_service.list_users.assert_awaited_once()

    def test_anonymous_detail_forbidden_401(self, unauthorized_client):
        resp = unauthorized_client.get(
            f"/api/v1/admin/users/{uuid.uuid4()}"
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_candidate_detail_forbidden(self, candidate_client, mock_service):
        resp = candidate_client.get(f"/api/v1/admin/users/{uuid.uuid4()}")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_recruiter_detail_forbidden(self, recruiter_client, mock_service):
        resp = recruiter_client.get(f"/api/v1/admin/users/{uuid.uuid4()}")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_deactivate_forbidden_401(self, unauthorized_client):
        resp = unauthorized_client.patch(
            f"/api/v1/admin/users/{uuid.uuid4()}/deactivate"
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_candidate_deactivate_forbidden(self, candidate_client, mock_service):
        resp = candidate_client.patch(
            f"/api/v1/admin/users/{uuid.uuid4()}/deactivate"
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_recruiter_deactivate_forbidden(self, recruiter_client, mock_service):
        resp = recruiter_client.patch(
            f"/api/v1/admin/users/{uuid.uuid4()}/deactivate"
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class TestAdminUsersList:
    def test_empty_list(self, admin_client, mock_service):
        mock_service.list_users.return_value = ([], 0)
        resp = admin_client.get("/api/v1/admin/users")
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
        admin_client.get("/api/v1/admin/users")
        mock_service.list_users.assert_awaited_once_with(
            skip=0, limit=10, search=None, role=None
        )

    def test_explicit_params_forwarded(self, admin_client, mock_service):
        admin_client.get(
            "/api/v1/admin/users",
            params={
                "skip": 20,
                "limit": 25,
                "search": "acme",
                "role": "recruiter",
            },
        )
        mock_service.list_users.assert_awaited_once_with(
            skip=20, limit=25, search="acme", role=UserRole.RECRUITER
        )

    def test_returns_items_and_total(self, admin_client, mock_service):
        user = _fake_admin_user()
        mock_service.list_users.return_value = (
            [MagicMock(**{k: v for k, v in user.items()})],
            1,
        )
        resp = admin_client.get("/api/v1/admin/users")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["email"] == user["email"]

    def test_limit_bounds_enforced(self, admin_client, mock_service):
        resp = admin_client.get("/api/v1/admin/users", params={"limit": 0})
        assert resp.status_code == 422

    def test_invalid_role_filter_rejected(self, admin_client, mock_service):
        resp = admin_client.get(
            "/api/v1/admin/users", params={"role": "superadmin"}
        )
        assert resp.status_code == 422


class TestAdminUsersListSensitiveFields:
    def test_no_password_hash_exposed(self, admin_client, mock_service):
        user = _fake_admin_user()
        user["password_hash"] = "super-secret"
        mock_service.list_users.return_value = (
            [MagicMock(**{k: v for k, v in user.items()})],
            1,
        )
        resp = admin_client.get("/api/v1/admin/users")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert "password_hash" not in item
        assert "token" not in item
        assert "secret" not in item

    def test_schema_exposes_only_expected_fields(self, admin_client, mock_service):
        user = _fake_admin_user()
        mock_service.list_users.return_value = (
            [MagicMock(**{k: v for k, v in user.items()})],
            1,
        )
        resp = admin_client.get("/api/v1/admin/users")
        item = resp.json()["items"][0]
        assert set(item.keys()) == {
            "id",
            "email",
            "role",
            "is_active",
            "is_deleted",
            "created_at",
            "updated_at",
        }


class TestAdminUsersDetail:
    def test_admin_can_view_user(self, admin_client, mock_service):
        user = _fake_admin_user(role=UserRole.RECRUITER)
        mock_service.get_user.return_value = MagicMock(
            **{k: v for k, v in user.items()}
        )
        resp = admin_client.get(f"/api/v1/admin/users/{user['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == user["id"]
        assert data["role"] == "recruiter"

    def test_unknown_user_returns_404(self, admin_client, mock_service):
        mock_service.get_user.side_effect = HTTPException(
            status.HTTP_404_NOT_FOUND
        )
        resp = admin_client.get(f"/api/v1/admin/users/{uuid.uuid4()}")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_non_uuid_path_rejected(self, admin_client, mock_service):
        resp = admin_client.get("/api/v1/admin/users/not-a-uuid")
        assert resp.status_code == 422


class TestAdminUsersDeactivate:
    def test_admin_can_deactivate_user(self, admin_client, mock_service):
        user = _fake_admin_user(is_deleted=False)
        mock_service.deactivate_user.return_value = MagicMock(
            **{k: v for k, v in user.items()}
        )
        resp = admin_client.patch(
            f"/api/v1/admin/users/{user['id']}/deactivate"
        )
        assert resp.status_code == 200
        mock_service.deactivate_user.assert_awaited_once()

    def test_unknown_user_returns_404(self, admin_client, mock_service):
        mock_service.deactivate_user.side_effect = HTTPException(
            status.HTTP_404_NOT_FOUND
        )
        resp = admin_client.patch(
            f"/api/v1/admin/users/{uuid.uuid4()}/deactivate"
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
