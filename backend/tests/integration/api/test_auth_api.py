import uuid

import pytest

from tests.integration.api.conftest import API_V1, PASSWORD


def register(client, run_async, role="candidate", email=None):
    email = email or f"{uuid.uuid4()}@example.com"
    resp = run_async(
        client.post(
            f"{API_V1}/auth/register",
            json={"email": email, "password": PASSWORD, "role": role},
        )
    )
    return email, resp


class TestRegister:
    def test_register_candidate_creates_user(self, client, run_async):
        email, resp = register(client, run_async)

        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == email
        assert body["role"] == "candidate"
        assert body["is_active"] is True
        assert body["id"]
        assert body["created_at"]

    def test_duplicate_email_returns_conflict(self, client, run_async):
        email, _ = register(client, run_async)
        _, resp = register(client, run_async, email=email)

        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_short_password_rejected(self, client, run_async):
        resp = run_async(
            client.post(
                f"{API_V1}/auth/register",
                json={"email": "x@example.com", "password": "short"},
            )
        )

        assert resp.status_code == 422


class TestLoginForm:
    def test_valid_credentials_returns_jwt(self, client, run_async):
        email, _ = register(client, run_async)

        resp = run_async(
            client.post(
                f"{API_V1}/auth/login",
                data={"username": email, "password": PASSWORD},
            )
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert len(body["access_token"].split(".")) == 3

    def test_wrong_password_returns_401(self, client, run_async):
        email, _ = register(client, run_async)

        resp = run_async(
            client.post(
                f"{API_V1}/auth/login",
                data={"username": email, "password": "wrong-password"},
            )
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Incorrect email or password"

    def test_unknown_email_returns_401(self, client, run_async):
        resp = run_async(
            client.post(
                f"{API_V1}/auth/login",
                data={"username": "nobody@example.com", "password": PASSWORD},
            )
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Incorrect email or password"


class TestLoginJson:
    def test_valid_credentials_returns_jwt(self, client, run_async):
        email, _ = register(client, run_async)

        resp = run_async(
            client.post(
                f"{API_V1}/auth/login/json",
                json={"email": email, "password": PASSWORD},
            )
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]

    def test_wrong_password_returns_401(self, client, run_async):
        email, _ = register(client, run_async)

        resp = run_async(
            client.post(
                f"{API_V1}/auth/login/json",
                json={"email": email, "password": "wrong-password"},
            )
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Incorrect email or password"


class TestGetMe:
    def test_returns_current_user(self, client, run_async):
        email, _ = register(client, run_async)
        token = run_async(
            client.post(
                f"{API_V1}/auth/login",
                data={"username": email, "password": PASSWORD},
            )
        ).json()["access_token"]

        resp = run_async(
            client.get(
                f"{API_V1}/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        )

        assert resp.status_code == 200
        assert resp.json()["email"] == email

    def test_missing_token_returns_401(self, client, run_async):
        resp = run_async(client.get(f"{API_V1}/auth/me"))

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Not authenticated"

    def test_invalid_token_returns_401(self, client, run_async):
        resp = run_async(
            client.get(
                f"{API_V1}/auth/me",
                headers={"Authorization": "Bearer not.a.jwt"},
            )
        )

        assert resp.status_code == 401

    def test_expired_token_returns_401(self, client, run_async):
        from datetime import timedelta

        from app.core.security import create_access_token

        email, reg = register(client, run_async)
        user_id = reg.json()["id"]
        token = create_access_token(
            subject=str(user_id),
            expires_delta=timedelta(seconds=-1),
        )

        resp = run_async(
            client.get(
                f"{API_V1}/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        )

        assert resp.status_code == 401