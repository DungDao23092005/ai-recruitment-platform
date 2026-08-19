from __future__ import annotations

import uuid

import httpx
from tests.integration.api.conftest import API_V1, PASSWORD
from tests.integration.conftest import run

from app.main import app


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


def _login(client: httpx.AsyncClient, email: str) -> httpx.AsyncClient:
    resp = run(
        client.post(
            f"{API_V1}/auth/login",
            data={"username": email, "password": PASSWORD},
        )
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )


class TestAdminUsersAuthorization:
    def test_anonymous_users_401(self, client):
        for method, url in [
            ("GET", f"{API_V1}/admin/users"),
            ("GET", f"{API_V1}/admin/users/{uuid.uuid4()}"),
            ("PATCH", f"{API_V1}/admin/users/{uuid.uuid4()}/deactivate"),
        ]:
            resp = run(client.request(method, url))
            assert resp.status_code == 401, resp.text

    def test_candidate_forbidden(self, candidate_client):
        resp = run(candidate_client.get(f"{API_V1}/admin/users"))
        assert resp.status_code == 403

    def test_recruiter_forbidden(self, recruiter_client):
        resp = run(recruiter_client.get(f"{API_V1}/admin/users"))
        assert resp.status_code == 403


class TestAdminUsersList:
    def test_admin_sees_own_account(self, admin_client):
        resp = run(admin_client.get(f"{API_V1}/admin/users"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert any(item["role"] == "admin" for item in data["items"])

    def test_lists_all_users_with_total(self, client, admin_client):
        _register(client, "candidate")
        _register(client, "recruiter")

        resp = run(admin_client.get(f"{API_V1}/admin/users"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 3
        assert len(data["items"]) == data["total"]
        assert {item["role"] for item in data["items"]} >= {
            "candidate",
            "recruiter",
            "admin",
        }

    def test_pagination(self, client, admin_client):
        for _ in range(5):
            _register(client, "candidate")

        resp = run(
            admin_client.get(
                f"{API_V1}/admin/users", params={"limit": 2, "skip": 0}
            )
        )
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] >= 5

        resp2 = run(
            admin_client.get(
                f"{API_V1}/admin/users", params={"limit": 2, "skip": 2}
            )
        )
        data2 = resp2.json()
        assert len(data2["items"]) == 2
        assert data2["items"][0]["id"] != data["items"][0]["id"]

    def test_search_filters_by_email_substring(self, client, admin_client):
        unique = uuid.uuid4().hex[:8]
        email = _register(client, "candidate", f"{unique}-finder@example.com")
        _register(client, "candidate")

        resp = run(
            admin_client.get(
                f"{API_V1}/admin/users", params={"search": unique}
            )
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["email"] == email

    def test_search_is_case_insensitive(self, client, admin_client):
        unique = uuid.uuid4().hex[:8].upper()
        email = _register(client, "candidate", f"{unique}@example.com")

        resp = run(
            admin_client.get(
                f"{API_V1}/admin/users", params={"search": unique.lower()}
            )
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["email"] == email

    def test_role_filter(self, client, admin_client):
        _register(client, "candidate", f"c-{uuid.uuid4()}@example.com")

        resp = run(
            admin_client.get(
                f"{API_V1}/admin/users", params={"role": "recruiter"}
            )
        )
        data = resp.json()
        assert data["items"] == []

        _register(client, "recruiter", f"r-{uuid.uuid4()}@example.com")
        resp = run(
            admin_client.get(
                f"{API_V1}/admin/users", params={"role": "recruiter"}
            )
        )
        data = resp.json()
        assert data["total"] >= 1
        assert all(item["role"] == "recruiter" for item in data["items"])

    def test_no_sensitive_fields_exposed(self, client, admin_client):
        _register(client, "candidate")

        resp = run(admin_client.get(f"{API_V1}/admin/users"))
        data = resp.json()
        for item in data["items"]:
            assert "password_hash" not in item
            assert "password" not in item
            assert "token" not in item
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
    def test_admin_views_existing_user(self, client, admin_client):
        email = _register(client, "recruiter")

        list_resp = run(admin_client.get(f"{API_V1}/admin/users"))
        target = next(u for u in list_resp.json()["items"] if u["email"] == email)

        resp = run(admin_client.get(f"{API_V1}/admin/users/{target['id']}"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == target["id"]
        assert data["email"] == email
        assert data["role"] == "recruiter"
        assert "password_hash" not in data

    def test_unknown_user_404(self, admin_client):
        resp = run(admin_client.get(f"{API_V1}/admin/users/{uuid.uuid4()}"))
        assert resp.status_code == 404

    def test_candidate_forbidden(self, candidate_client):
        resp = run(candidate_client.get(f"{API_V1}/admin/users/{uuid.uuid4()}"))
        assert resp.status_code == 403


class TestAdminUsersDeactivate:
    def test_deactivate_user(self, client, admin_client):
        email = _register(client, "candidate")

        list_resp = run(admin_client.get(f"{API_V1}/admin/users"))
        target = next(u for u in list_resp.json()["items"] if u["email"] == email)
        assert target["is_deleted"] is False

        resp = run(
            admin_client.patch(
                f"{API_V1}/admin/users/{target['id']}/deactivate"
            )
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == target["id"]
        assert data["is_deleted"] is True

    def test_deactivated_user_appears_in_admin_list(self, client, admin_client):
        email = _register(client, "candidate")
        list_resp = run(admin_client.get(f"{API_V1}/admin/users"))
        target = next(u for u in list_resp.json()["items"] if u["email"] == email)

        run(admin_client.patch(f"{API_V1}/admin/users/{target['id']}/deactivate"))

        resp = run(admin_client.get(f"{API_V1}/admin/users"))
        data = resp.json()
        match = next(u for u in data["items"] if u["id"] == target["id"])
        assert match["is_deleted"] is True

    def test_deactivate_already_deactivated_404(self, client, admin_client):
        email = _register(client, "candidate")
        list_resp = run(admin_client.get(f"{API_V1}/admin/users"))
        target = next(u for u in list_resp.json()["items"] if u["email"] == email)

        first = run(
            admin_client.patch(
                f"{API_V1}/admin/users/{target['id']}/deactivate"
            )
        )
        assert first.status_code == 200
        second = run(
            admin_client.patch(
                f"{API_V1}/admin/users/{target['id']}/deactivate"
            )
        )
        assert second.status_code == 404

    def test_deactivate_unknown_user_404(self, admin_client):
        resp = run(
            admin_client.patch(f"{API_V1}/admin/users/{uuid.uuid4()}/deactivate")
        )
        assert resp.status_code == 404

    def test_candidate_forbidden(self, candidate_client):
        resp = run(
            candidate_client.patch(
                f"{API_V1}/admin/users/{uuid.uuid4()}/deactivate"
            )
        )
        assert resp.status_code == 403

    def test_deactivated_user_cannot_authenticate(
        self, client, admin_client
    ):
        email = _register(client, "candidate")
        user_client = _login(client, email)

        list_resp = run(admin_client.get(f"{API_V1}/admin/users"))
        target = next(u for u in list_resp.json()["items"] if u["email"] == email)
        deact = run(
            admin_client.patch(
                f"{API_V1}/admin/users/{target['id']}/deactivate"
            )
        )
        assert deact.status_code == 200

        me = run(user_client.get(f"{API_V1}/auth/me"))
        assert me.status_code == 401
        run(user_client.aclose())
