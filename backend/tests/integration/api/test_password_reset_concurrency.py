"""Integration tests for password-reset OTP attempt accounting under concurrency.

These tests run against the disposable integration test database and exercise
the real service + SQL layer. They guard the atomic, single-use semantics of
password-reset OTPs that a naive read-modify-write implementation would break.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from tests.integration.conftest import run
from app.core.config import settings
from app.core.password_reset import hash_otp
from app.core.security import get_password_hash
from app.database.session import async_session_factory
from app.domain.enums import UserRole
from app.models import PasswordResetOTP, User
from app.services.auth_service import AuthService

PASSWORD = "password123"
NEW_PASSWORD = "newpassword123"


async def _create_user(email: str) -> str:
    async with async_session_factory() as session:
        user = User(
            email=email,
            password_hash=get_password_hash(PASSWORD),
            role=UserRole.CANDIDATE,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return str(user.id)


async def _create_otp(
    user_id: str,
    email: str,
    otp: str,
    *,
    attempts: int = 0,
    max_attempts: int = 5,
    is_used: bool = False,
    expires_in_seconds: int = 300,
) -> str:
    async with async_session_factory() as session:
        record = PasswordResetOTP(
            user_id=uuid.UUID(user_id),
            email=email,
            otp_hash=hash_otp(otp),
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=expires_in_seconds),
            attempts=attempts,
            max_attempts=max_attempts,
            is_used=is_used,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return str(record.id)


async def _get_otp(otp_id: str) -> PasswordResetOTP:
    async with async_session_factory() as session:
        result = await session.execute(
            select(PasswordResetOTP).where(
                PasswordResetOTP.id == uuid.UUID(otp_id)
            )
        )
        return result.scalar_one()


async def _concurrent_verify(client, email: str, otp: str, count: int):
    url = f"{settings.API_V1_STR}/auth/verify-reset-otp"
    return await asyncio.gather(
        *[client.post(url, json={"email": email, "otp": otp}) for _ in range(count)]
    )


def test_concurrent_invalid_attempts_do_not_lose_increments(client):
    """N concurrent wrong guesses must each bump the attempt counter."""
    email = f"otp-race-{uuid.uuid4()}@test.com"
    user_id = run(_create_user(email))
    otp_id = run(_create_otp(user_id, email, "123456"))

    responses = run(_concurrent_verify(client, email, "000000", 8))
    assert all(r.status_code == 400 for r in responses), [
        r.status_code for r in responses
    ]

    record = run(_get_otp(otp_id))
    # Bounded by max_attempts, and every increment is persisted.
    assert record.attempts == 5
    assert record.is_used is False


def test_atomic_increment_applies_for_stale_concurrent_reads():
    """Two sessions that both read attempts=0 must both increment.

    Deterministically reproduces the lost-update scenario the old
    read-modify-write logic suffered from.
    """
    email = f"otp-atomic-{uuid.uuid4()}@test.com"
    user_id = run(_create_user(email))
    otp_id = run(_create_otp(user_id, email, "123456"))

    async def _scenario():
        async with async_session_factory() as s1, async_session_factory() as s2:
            r1 = await s1.execute(
                select(PasswordResetOTP).where(PasswordResetOTP.id == uuid.UUID(otp_id))
            )
            r2 = await s2.execute(
                select(PasswordResetOTP).where(PasswordResetOTP.id == uuid.UUID(otp_id))
            )
            assert r1.scalar_one().attempts == 0
            assert r2.scalar_one().attempts == 0
            # Release read locks before mutating (mirrors the service flow).
            await s1.rollback()
            await s2.rollback()
            await AuthService(s1)._increment_otp_attempts(uuid.UUID(otp_id))
            await AuthService(s2)._increment_otp_attempts(uuid.UUID(otp_id))

    run(_scenario())

    record = run(_get_otp(otp_id))
    assert record.attempts == 2


def test_concurrent_valid_requests_yield_single_reset_token(client):
    """A single-use OTP must produce at most one reset token under concurrency."""
    email = f"otp-single-{uuid.uuid4()}@test.com"
    user_id = run(_create_user(email))
    otp_id = run(_create_otp(user_id, email, "123456"))

    responses = run(_concurrent_verify(client, email, "123456", 4))
    successes = [r for r in responses if r.status_code == 200]
    assert len(successes) == 1, [r.status_code for r in responses]

    record = run(_get_otp(otp_id))
    assert record.is_used is True
    assert record.reset_token_hash is not None


def test_correct_otp_rejected_after_max_attempts(client):
    """Once max_attempts is reached the OTP is dead even for the right code."""
    email = f"otp-locked-{uuid.uuid4()}@test.com"
    user_id = run(_create_user(email))
    run(_create_otp(user_id, email, "123456", attempts=5))

    resp = run(
        client.post(
            f"{settings.API_V1_STR}/auth/verify-reset-otp",
            json={"email": email, "otp": "123456"},
        )
    )
    assert resp.status_code == 400, resp.text


def test_expired_otp_rejected(client):
    """Expired OTPs are rejected without consuming the correct code."""
    email = f"otp-expired-{uuid.uuid4()}@test.com"
    user_id = run(_create_user(email))
    run(_create_otp(user_id, email, "123456", expires_in_seconds=-1))

    resp = run(
        client.post(
            f"{settings.API_V1_STR}/auth/verify-reset-otp",
            json={"email": email, "otp": "123456"},
        )
    )
    assert resp.status_code == 400, resp.text


GENERIC_FORGOT_MESSAGE = "Nếu tài khoản tồn tại, mã OTP đã được gửi đến email."


def test_forgot_password_is_generic_and_cooldown_safe(client):
    """Forgot-password returns a generic 200 for existing and unknown emails.

    The immediate resend (cooldown still active) must also succeed generically
    without raising, and must not reveal whether the account exists.
    """
    email = f"forgot-{uuid.uuid4()}@test.com"
    run(_create_user(email))

    first = run(
        client.post(
            f"{settings.API_V1_STR}/auth/forgot-password",
            json={"email": email},
        )
    )
    assert first.status_code == 200, first.text
    assert first.json()["message"] == GENERIC_FORGOT_MESSAGE

    # Within cooldown: still generic 200, no new OTP / no error.
    second = run(
        client.post(
            f"{settings.API_V1_STR}/auth/forgot-password",
            json={"email": email},
        )
    )
    assert second.status_code == 200, second.text
    assert second.json()["message"] == GENERIC_FORGOT_MESSAGE

    unknown = run(
        client.post(
            f"{settings.API_V1_STR}/auth/forgot-password",
            json={"email": f"unknown-{uuid.uuid4()}@test.com"},
        )
    )
    assert unknown.status_code == 200, unknown.text
    assert unknown.json()["message"] == GENERIC_FORGOT_MESSAGE


def test_full_reset_flow_preserves_single_use_semantics(client):
    """End-to-end: verify -> reset -> old password fails, new password works."""
    email = f"otp-flow-{uuid.uuid4()}@test.com"
    user_id = run(_create_user(email))
    run(_create_otp(user_id, email, "123456"))

    verify_resp = run(
        client.post(
            f"{settings.API_V1_STR}/auth/verify-reset-otp",
            json={"email": email, "otp": "123456"},
        )
    )
    assert verify_resp.status_code == 200, verify_resp.text
    reset_token = verify_resp.json()["reset_token"]

    # OTP is single use - a second verification fails.
    again = run(
        client.post(
            f"{settings.API_V1_STR}/auth/verify-reset-otp",
            json={"email": email, "otp": "123456"},
        )
    )
    assert again.status_code == 400, again.text

    reset_resp = run(
        client.post(
            f"{settings.API_V1_STR}/auth/reset-password",
            json={
                "email": email,
                "reset_token": reset_token,
                "new_password": NEW_PASSWORD,
                "confirm_password": NEW_PASSWORD,
            },
        )
    )
    assert reset_resp.status_code == 200, reset_resp.text

    old_login = run(
        client.post(
            f"{settings.API_V1_STR}/auth/login/json",
            json={"email": email, "password": PASSWORD},
        )
    )
    assert old_login.status_code == 401, old_login.text

    new_login = run(
        client.post(
            f"{settings.API_V1_STR}/auth/login/json",
            json={"email": email, "password": NEW_PASSWORD},
        )
    )
    assert new_login.status_code == 200, new_login.text
