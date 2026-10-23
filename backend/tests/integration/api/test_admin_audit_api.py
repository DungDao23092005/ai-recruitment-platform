from __future__ import annotations

import json
import uuid

import httpx
import pytest
from sqlalchemy import select
from tests.integration.api.conftest import API_V1, PASSWORD
from tests.integration.conftest import run

from app.database.session import async_session_factory
from app.models import AdminAuditLog, User

AUDIT_URL = f"{API_V1}/admin/audit-logs"


def _register(
    client: httpx.AsyncClient, role: str, email: str | None = None
) -> str:
    email = email or f"{role}-{uuid.uuid4()}@example.com"
    resp = run(
        client.post(
            f"{API_V1}/auth/register",
            json={"email": email, "password": PASSWORD, "role": role},
        )
    )
    assert resp.status_code == 201, resp.text
    return email


async def _find_user(email: str) -> User:
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        assert user is not None, f"User {email} not found"
        return user


async def _audit_rows() -> list[AdminAuditLog]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(AdminAuditLog).order_by(
                AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc()
            )
        )
        return list(result.scalars().all())


def _me(auth_client: httpx.AsyncClient) -> dict:
    resp = run(auth_client.get(f"{API_V1}/auth/me"))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _deactivate(admin_client: httpx.AsyncClient, user_id: str, reason: str):
    return run(
        admin_client.patch(
            f"{API_V1}/admin/users/{user_id}/deactivate",
            json={"reason": reason},
        )
    )


class TestAdminAuditAuthorization:
    def test_anonymous_users_401(self, client):
        resp = run(client.get(AUDIT_URL))
        assert resp.status_code == 401, resp.text

    def test_candidate_forbidden(self, candidate_client):
        resp = run(candidate_client.get(AUDIT_URL))
        assert resp.status_code == 403, resp.text

    def test_recruiter_forbidden(self, recruiter_client):
        resp = run(recruiter_client.get(AUDIT_URL))
        assert resp.status_code == 403, resp.text

    def test_admin_can_read_empty_ledger(self, admin_client):
        resp = run(admin_client.get(AUDIT_URL))
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"items": [], "total": 0, "skip": 0, "limit": 20}


class TestAdminAuditMutations:
    def test_lock_is_recorded_with_actor_target_and_safe_details(
        self, client, admin_client
    ):
        email = _register(client, "candidate")
        target = run(_find_user(email))
        admin = _me(admin_client)

        resp = _deactivate(admin_client, str(target.id), "  Vi phạm điều khoản  ")
        assert resp.status_code == 200, resp.text

        resp = run(admin_client.get(AUDIT_URL))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["admin_id"] == admin["id"]
        assert item["admin_email"] == admin["email"]
        assert item["target_user_id"] == str(target.id)
        assert item["target_user_email"] == email
        assert item["action"] == "user_lock"
        assert item["reason"] == "Vi phạm điều khoản"
        assert item["details"] == {
            "was_active": True,
            "target_role": "candidate",
        }
        assert item["created_at"].endswith("Z") or "+00:00" in item["created_at"]
        assert set(item) == {
            "id",
            "admin_id",
            "admin_email",
            "target_user_id",
            "target_user_email",
            "action",
            "reason",
            "details",
            "created_at",
        }

    def test_unlock_is_recorded(self, client, admin_client):
        email = _register(client, "candidate")
        target = run(_find_user(email))
        _deactivate(admin_client, str(target.id), "Initial lock")

        resp = run(
            admin_client.patch(f"{API_V1}/admin/users/{target.id}/activate")
        )
        assert resp.status_code == 200, resp.text

        resp = run(admin_client.get(AUDIT_URL, params={"action": "user_unlock"}))
        data = resp.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["target_user_id"] == str(target.id)
        assert item["details"] == {
            "was_active": False,
            "target_role": "candidate",
        }

    def test_delete_keeps_audit_and_does_not_store_original_email(
        self, client, admin_client
    ):
        email = _register(client, "recruiter")
        target = run(_find_user(email))

        resp = run(admin_client.delete(f"{API_V1}/admin/users/{target.id}"))
        assert resp.status_code == 200, resp.text

        resp = run(admin_client.get(AUDIT_URL, params={"action": "user_delete"}))
        data = resp.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["target_user_id"] == str(target.id)
        assert item["target_user_email"].endswith("@anonymized.local")
        assert item["target_user_email"] != email
        assert item["details"] == {
            "was_active": True,
            "was_already_deleted": False,
            "target_role": "recruiter",
        }
        assert email not in json.dumps(item)

    def test_failed_mutation_creates_no_audit(self, admin_client):
        resp = run(
            admin_client.patch(
                f"{API_V1}/admin/users/{uuid.uuid4()}/deactivate",
                json={"reason": "No such user"},
            )
        )
        assert resp.status_code == 404

        rows = run(_audit_rows())
        assert rows == []

    def test_audit_rows_are_append_only_via_api(self, admin_client):
        for method in ("post", "put", "patch", "delete"):
            resp = run(getattr(admin_client, method)(AUDIT_URL))
            assert resp.status_code in {404, 405}, resp.text


class TestAdminAuditFilters:
    def _seed(self, client, admin_client) -> tuple[User, User]:
        first_email = _register(client, "candidate")
        first = run(_find_user(first_email))
        second_email = _register(client, "recruiter")
        second = run(_find_user(second_email))
        _deactivate(admin_client, str(first.id), "Alpha unique lock")
        _deactivate(admin_client, str(second.id), "Beta unique lock")
        run(admin_client.patch(f"{API_V1}/admin/users/{first.id}/activate"))
        return first, second

    def test_target_filter(self, client, admin_client):
        first, _ = self._seed(client, admin_client)

        resp = run(
            admin_client.get(
                AUDIT_URL, params={"target_user_id": str(first.id)}
            )
        )
        data = resp.json()
        assert data["total"] == 2
        assert all(item["target_user_id"] == str(first.id) for item in data["items"])

    def test_action_filter(self, client, admin_client):
        self._seed(client, admin_client)

        resp = run(admin_client.get(AUDIT_URL, params={"action": "user_lock"}))
        data = resp.json()
        assert data["total"] == 2
        assert all(item["action"] == "user_lock" for item in data["items"])

    def test_reason_and_email_search(self, client, admin_client):
        first, second = self._seed(client, admin_client)

        resp = run(
            admin_client.get(AUDIT_URL, params={"search": "Alpha unique"})
        )
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["target_user_id"] == str(first.id)

        resp = run(
            admin_client.get(AUDIT_URL, params={"search": second.email.upper()})
        )
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["target_user_id"] == str(second.id)

    def test_like_wildcards_are_literal(self, client, admin_client):
        self._seed(client, admin_client)

        resp = run(admin_client.get(AUDIT_URL, params={"search": "%"}))
        assert resp.json()["total"] == 0
        resp = run(admin_client.get(AUDIT_URL, params={"search": "_"}))
        assert resp.json()["total"] == 0

    def test_date_range_is_inclusive_and_validated(self, client, admin_client):
        self._seed(client, admin_client)

        future = run(
            admin_client.get(
                AUDIT_URL, params={"created_from": "2099-01-01T00:00:00Z"}
            )
        )
        assert future.json()["total"] == 0

        past = run(
            admin_client.get(
                AUDIT_URL, params={"created_to": "2000-01-01T00:00:00Z"}
            )
        )
        assert past.json()["total"] == 0

        invalid = run(
            admin_client.get(
                AUDIT_URL,
                params={
                    "created_from": "2026-02-01T00:00:00Z",
                    "created_to": "2026-01-01T00:00:00Z",
                },
            )
        )
        assert invalid.status_code == 422, invalid.text

    def test_pagination_is_database_backed_and_deterministic(
        self, client, admin_client
    ):
        first, _ = self._seed(client, admin_client)

        resp = run(admin_client.get(AUDIT_URL, params={"limit": 2, "skip": 0}))
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3
        assert data["skip"] == 0
        assert data["limit"] == 2

        resp2 = run(admin_client.get(AUDIT_URL, params={"limit": 2, "skip": 2}))
        data2 = resp2.json()
        assert len(data2["items"]) == 1
        assert data2["total"] == 3
        assert data2["items"][0]["id"] != data["items"][0]["id"]

        all_rows = run(
            admin_client.get(
                AUDIT_URL,
                params={"target_user_id": str(first.id), "limit": 100},
            )
        )
        assert all_rows.json()["total"] == 2

    @pytest.mark.parametrize(
        "params",
        [
            {"limit": 0},
            {"limit": 101},
            {"skip": -1},
            {"action": "not_an_action"},
            {"target_user_id": "not-a-uuid"},
        ],
    )
    def test_invalid_query_parameters_are_rejected(self, admin_client, params):
        resp = run(admin_client.get(AUDIT_URL, params=params))
        assert resp.status_code == 422, resp.text
