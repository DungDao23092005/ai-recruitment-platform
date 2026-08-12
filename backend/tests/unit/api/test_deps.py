import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException, status

from app.api import deps
from app.core.security import create_access_token
from app.domain.enums import UserRole
from app.models import User
from app.services import UserService

ALGORITHM = "HS256"


def make_user(
    user_id: uuid.UUID | None = None,
    role: UserRole = UserRole.CANDIDATE,
    is_active: bool = True,
) -> User:
    return User(
        id=user_id or uuid.uuid4(),
        email=f"{uuid.uuid4()}@example.com",
        password_hash="hashed",
        role=role,
        is_active=is_active,
    )


def assert_unauthorized(exc: HTTPException) -> None:
    assert exc.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc.detail == "Could not validate credentials"
    assert exc.headers == {"WWW-Authenticate": "Bearer"}


def stub_get_user_by_id(monkeypatch, user):
    async def fake_get_user_by_id(self, user_id):
        assert user_id == user.id
        return user

    monkeypatch.setattr(UserService, "get_user_by_id", fake_get_user_by_id)


class TestGetCurrentUser:
    def test_valid_token_returns_user(self, monkeypatch):
        user = make_user()
        stub_get_user_by_id(monkeypatch, user)
        token = create_access_token(subject=str(user.id))

        result = asyncio.run(deps.get_current_user(token=token, db=None))

        assert result is user

    def test_expired_token(self, monkeypatch):
        user = make_user()
        stub_get_user_by_id(monkeypatch, user)
        token = create_access_token(
            subject=str(user.id),
            expires_delta=timedelta(seconds=-1),
        )

        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps.get_current_user(token=token, db=None))
        assert_unauthorized(exc.value)

    def test_malformed_token(self, monkeypatch):
        stub_get_user_by_id(monkeypatch, make_user())

        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps.get_current_user(token="not.a.jwt", db=None))
        assert_unauthorized(exc.value)

    def test_invalid_signature_token(self, monkeypatch):
        from jose import jwt as jose_jwt

        from app.core.config import settings

        stub_get_user_by_id(monkeypatch, make_user())
        wrong_payload = {
            "sub": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        }
        token = jose_jwt.encode(wrong_payload, "wrong-secret", algorithm=ALGORITHM)
        assert settings.SECRET_KEY != "wrong-secret"

        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps.get_current_user(token=token, db=None))
        assert_unauthorized(exc.value)

    def test_missing_sub(self, monkeypatch):
        from jose import jwt as jose_jwt

        from app.core.config import settings

        stub_get_user_by_id(monkeypatch, make_user())
        token = jose_jwt.encode({"foo": "bar"}, settings.SECRET_KEY, algorithm=ALGORITHM)

        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps.get_current_user(token=token, db=None))
        assert_unauthorized(exc.value)

    def test_invalid_uuid_sub(self, monkeypatch):
        stub_get_user_by_id(monkeypatch, make_user())
        token = create_access_token(subject="not-a-uuid")

        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps.get_current_user(token=token, db=None))
        assert_unauthorized(exc.value)

    def test_user_not_found(self, monkeypatch):
        async def fake_get_user_by_id(self, user_id):
            return None

        monkeypatch.setattr(UserService, "get_user_by_id", fake_get_user_by_id)
        token = create_access_token(subject=str(uuid.uuid4()))

        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps.get_current_user(token=token, db=None))
        assert_unauthorized(exc.value)


class TestGetCurrentActiveUser:
    def test_inactive_user_raises_403(self):
        user = make_user(is_active=False)

        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps.get_current_active_user(current_user=user))

        assert exc.value.status_code == status.HTTP_403_FORBIDDEN
        assert exc.value.detail == "Inactive user"

    def test_active_user_passes(self):
        user = make_user(is_active=True)

        result = asyncio.run(deps.get_current_active_user(current_user=user))

        assert result is user


class TestRequireRole:
    def _call_guard(self, guard, user):
        return asyncio.run(guard(current_user=user))

    def test_allowed_role_succeeds(self):
        user = make_user(role=UserRole.RECRUITER)
        guard = deps.require_role([UserRole.RECRUITER])

        assert self._call_guard(guard, user) is user

    def test_insufficient_role_raises_403(self):
        user = make_user(role=UserRole.CANDIDATE)
        guard = deps.require_role([UserRole.RECRUITER])

        with pytest.raises(HTTPException) as exc:
            self._call_guard(guard, user)

        assert exc.value.status_code == status.HTTP_403_FORBIDDEN
        assert exc.value.detail == "Not enough permissions"

    def test_admin_not_in_allowed_roles_does_not_bypass(self):
        user = make_user(role=UserRole.ADMIN)
        guard = deps.require_role([UserRole.CANDIDATE])

        with pytest.raises(HTTPException) as exc:
            self._call_guard(guard, user)

        assert exc.value.status_code == status.HTTP_403_FORBIDDEN
        assert exc.value.detail == "Not enough permissions"


class TestDefaultGuards:
    def test_require_admin_membership(self):
        admin = deps.require_admin
        assert asyncio.run(admin(current_user=make_user(role=UserRole.ADMIN))) is not None

    def test_require_recruiter_allows_recruiter_and_admin(self):
        assert asyncio.run(
            deps.require_recruiter(current_user=make_user(role=UserRole.RECRUITER))
        ) is not None
        assert asyncio.run(
            deps.require_recruiter(current_user=make_user(role=UserRole.ADMIN))
        ) is not None

    def test_require_candidate_allows_candidate_and_admin(self):
        assert asyncio.run(
            deps.require_candidate(current_user=make_user(role=UserRole.CANDIDATE))
        ) is not None
        assert asyncio.run(
            deps.require_candidate(current_user=make_user(role=UserRole.ADMIN))
        ) is not None

    def test_require_candidate_rejects_recruiter(self):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                deps.require_candidate(current_user=make_user(role=UserRole.RECRUITER))
            )
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN
        assert exc.value.detail == "Not enough permissions"