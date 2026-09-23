import os
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


class TestLogoutRateLimitDisabled:
    """Test JWT revocation when RATE_LIMIT_ENABLED=false.

    This verifies that token revocation works independently of rate limiting.
    """

    def test_logout_revokes_token_when_rate_limit_disabled(self, client, run_async):
        """Test that token is revoked after logout even when rate limiting is disabled."""
        # Temporarily disable rate limiting for this test
        from app.core.config import settings
        original_setting = settings.RATE_LIMIT_ENABLED
        settings.RATE_LIMIT_ENABLED = False
        try:
            email, _ = register(client, run_async)
            token = run_async(
                client.post(
                    f"{API_V1}/auth/login/json",
                    json={"email": email, "password": PASSWORD},
                )
            ).json()["access_token"]

            # Verify token works before logout
            resp = run_async(
                client.get(
                    f"{API_V1}/auth/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
            )
            assert resp.status_code == 200

            # Logout
            resp = run_async(
                client.post(
                    f"{API_V1}/auth/logout",
                    headers={"Authorization": f"Bearer {token}"},
                )
            )
            assert resp.status_code == 200

            # Try to use the same token - should be revoked
            resp = run_async(
                client.get(
                    f"{API_V1}/auth/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
            )
            assert resp.status_code == 401
            assert "thu hồi" in resp.json()["detail"].lower()
        finally:
            settings.RATE_LIMIT_ENABLED = original_setting

    def test_logout_idempotent_when_rate_limit_disabled(self, client, run_async):
        """Test that calling logout twice with same token is safe when rate limiting is disabled."""
        from app.core.config import settings
        original_setting = settings.RATE_LIMIT_ENABLED
        settings.RATE_LIMIT_ENABLED = False
        try:
            email, _ = register(client, run_async)
            token = run_async(
                client.post(
                    f"{API_V1}/auth/login/json",
                    json={"email": email, "password": PASSWORD},
                )
            ).json()["access_token"]

            # First logout
            resp = run_async(
                client.post(
                    f"{API_V1}/auth/logout",
                    headers={"Authorization": f"Bearer {token}"},
                )
            )
            assert resp.status_code == 200

            # Second logout with same (now invalid) token
            resp = run_async(
                client.post(
                    f"{API_V1}/auth/logout",
                    headers={"Authorization": f"Bearer {token}"},
                )
            )
            assert resp.status_code == 200
            assert resp.json()["message"] == "Đăng xuất thành công"
        finally:
            settings.RATE_LIMIT_ENABLED = original_setting


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

    def test_register_recruiter_creates_user(self, client, run_async):
        email, resp = register(client, run_async, role="recruiter")

        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == email
        assert body["role"] == "recruiter"
        assert body["is_active"] is True
        assert body["id"]
        assert body["created_at"]

    def test_admin_registration_rejected(self, client, run_async):
        """Public registration with role=admin must fail (mass-assignment protection)."""
        resp = run_async(
            client.post(
                f"{API_V1}/auth/register",
                json={
                    "email": "attacker@example.com",
                    "password": "Password123!",
                    "role": "admin",
                },
            )
        )

        # Pydantic validation rejects role="admin" at schema level (422)
        assert resp.status_code == 422
        assert "role" in resp.json()["detail"][0]["loc"]
        assert "Input should be" in resp.json()["detail"][0]["msg"]

        # Verify no admin user was created
        from app.database.session import async_session_factory
        from app.domain.enums import UserRole
        from app.models import User
        from sqlalchemy import select

        async def check_no_admin():
            async with async_session_factory() as session:
                result = await session.execute(
                    select(User).where(User.email == "attacker@example.com")
                )
                return result.scalars().first()

        attacker = run_async(check_no_admin())
        assert attacker is None, "Admin user should not have been created"

    def test_duplicate_email_returns_conflict(self, client, run_async):
        email, _ = register(client, run_async)
        _, resp = register(client, run_async, email=email)

        assert resp.status_code == 400
        assert "đã được sử dụng" in resp.json()["detail"]

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


class TestLogout:
    def test_logout_success(self, client, run_async):
        """Test successful logout with valid token."""
        email, _ = register(client, run_async)
        token = run_async(
            client.post(
                f"{API_V1}/auth/login/json",
                json={"email": email, "password": PASSWORD},
            )
        ).json()["access_token"]

        # Verify token works before logout
        resp = run_async(
            client.get(
                f"{API_V1}/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        )
        assert resp.status_code == 200

        # Logout
        resp = run_async(
            client.post(
                f"{API_V1}/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
            )
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Đăng xuất thành công"

    def test_logout_revokes_token(self, client, run_async):
        """Test that token is revoked after logout."""
        email, _ = register(client, run_async)
        token = run_async(
            client.post(
                f"{API_V1}/auth/login/json",
                json={"email": email, "password": PASSWORD},
            )
        ).json()["access_token"]

        # Logout
        resp = run_async(
            client.post(
                f"{API_V1}/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
            )
        )
        assert resp.status_code == 200

        # Try to use the same token - should be revoked
        resp = run_async(
            client.get(
                f"{API_V1}/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        )
        assert resp.status_code == 401
        assert "thu hồi" in resp.json()["detail"].lower()

    def test_logout_idempotent(self, client, run_async):
        """Test that calling logout twice with same token is safe."""
        email, _ = register(client, run_async)
        token = run_async(
            client.post(
                f"{API_V1}/auth/login/json",
                json={"email": email, "password": PASSWORD},
            )
        ).json()["access_token"]

        # First logout
        resp = run_async(
            client.post(
                f"{API_V1}/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
            )
        )
        assert resp.status_code == 200

        # Second logout with same (now invalid) token
        resp = run_async(
            client.post(
                f"{API_V1}/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
            )
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Đăng xuất thành công"

    def test_logout_expired_token_idempotent(self, client, run_async):
        """Test logout with already expired token returns success (idempotent)."""
        from datetime import timedelta
        from app.core.security import create_access_token

        email, reg = register(client, run_async)
        user_id = reg.json()["id"]
        expired_token = create_access_token(
            subject=str(user_id),
            expires_delta=timedelta(seconds=-1),
        )

        # Logout with expired token should still return 200 (idempotent)
        resp = run_async(
            client.post(
                f"{API_V1}/auth/logout",
                headers={"Authorization": f"Bearer {expired_token}"},
            )
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Đăng xuất thành công"

    def test_logout_missing_token_returns_401(self, client, run_async):
        """Test logout without token returns 401."""
        resp = run_async(
            client.post(f"{API_V1}/auth/logout")
        )
        assert resp.status_code == 401

    def test_logout_invalid_token_returns_200(self, client, run_async):
        """Test logout with invalid token returns 200 (idempotent)."""
        resp = run_async(
            client.post(
                f"{API_V1}/auth/logout",
                headers={"Authorization": "Bearer not.a.valid.jwt"},
            )
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Đăng xuất thành công"