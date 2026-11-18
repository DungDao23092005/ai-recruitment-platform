"""Integration tests for password-reset OTP attempt accounting under concurrency.

These tests run against the disposable integration test database and exercise
the real service + SQL layer. They guard the atomic, single-use semantics of
password-reset OTPs that a naive read-modify-write implementation would break.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from tests.integration.conftest import run
from app.core.config import settings
from app.core.exceptions import EmailTransportError
from app.core.password_reset import hash_otp, hash_reset_token
from app.core.security import get_password_hash, verify_password
from app.database.session import async_session_factory
from app.domain.enums import UserRole
from app.models import PasswordResetOTP, User
from app.services.auth_service import AuthService
from app.services.email_service import EmailService

PASSWORD = "password123"
NEW_PASSWORD = "newpassword123"


async def _create_user(
    email: str,
    *,
    is_active: bool = True,
    is_deleted: bool = False,
) -> str:
    async with async_session_factory() as session:
        user = User(
            email=email,
            password_hash=get_password_hash(PASSWORD),
            role=UserRole.CANDIDATE,
            is_active=is_active,
            is_deleted=is_deleted,
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


async def _create_reset_record(
    user_id: str,
    email: str,
    token: str,
    *,
    created_at: datetime | None = None,
    expires_in_seconds: int = 900,
    reset_token_used: bool = False,
) -> str:
    moment = created_at or datetime.now(timezone.utc)
    async with async_session_factory() as session:
        record = PasswordResetOTP(
            user_id=uuid.UUID(user_id),
            email=email,
            otp_hash=hash_otp("000000"),
            reset_token_hash=hash_reset_token(token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=expires_in_seconds),
            attempts=0,
            max_attempts=5,
            is_used=True,
            reset_token_used=reset_token_used,
            created_at=moment,
            updated_at=moment,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return str(record.id)


async def _get_reset_record(record_id: str) -> PasswordResetOTP:
    async with async_session_factory() as session:
        result = await session.execute(
            select(PasswordResetOTP).where(
                PasswordResetOTP.id == uuid.UUID(record_id)
            )
        )
        return result.scalar_one()


async def _get_user(user_id: str) -> User:
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.id == uuid.UUID(user_id))
        )
        return result.scalar_one()


async def _count_user_otps(user_id: str) -> int:
    async with async_session_factory() as session:
        return int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(PasswordResetOTP)
                    .where(PasswordResetOTP.user_id == uuid.UUID(user_id))
                )
            ).scalar_one()
        )


async def _count_active_otps(user_id: str) -> int:
    async with async_session_factory() as session:
        return int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(PasswordResetOTP)
                    .where(
                        PasswordResetOTP.user_id == uuid.UUID(user_id),
                        PasswordResetOTP.is_used == False,  # noqa: E712
                        PasswordResetOTP.expires_at
                        > datetime.now(timezone.utc),
                    )
                )
            ).scalar_one()
        )


async def _post_reset(
    client, email: str, token: str, password: str = NEW_PASSWORD
):
    return await client.post(
        f"{settings.API_V1_STR}/auth/reset-password",
        json={
            "email": email,
            "reset_token": token,
            "new_password": password,
            "confirm_password": password,
        },
    )


async def _attempt_reset(email: str, token: str, password: str) -> bool:
    async with async_session_factory() as session:
        return await AuthService(session).reset_password(
            email, token, password
        )


async def _concurrent_forgot(client, email: str, count: int):
    return await asyncio.gather(
        *[
            client.post(
                f"{settings.API_V1_STR}/auth/forgot-password",
                json={"email": email},
            )
            for _ in range(count)
        ]
    )


async def _concurrent_reset(email: str, token: str, count: int):
    return await asyncio.gather(
        *[
            _attempt_reset(email, token, NEW_PASSWORD)
            for _ in range(count)
        ]
    )


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


# ---------------------------------------------------------------------------
# Account policy and provider-failure behaviour for forgot-password
# ---------------------------------------------------------------------------


def test_locked_but_not_deleted_account_can_request_otp_and_stays_locked(client):
    email = f"locked-forgot-{uuid.uuid4()}@test.com"
    user_id = run(_create_user(email, is_active=False))

    resp = run(
        client.post(
            f"{settings.API_V1_STR}/auth/forgot-password",
            json={"email": email},
        )
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["message"] == GENERIC_FORGOT_MESSAGE
    assert run(_count_user_otps(user_id)) == 1
    assert run(_get_user(user_id)).is_active is False


def test_deleted_account_cannot_request_password_reset(client):
    email = f"deleted-forgot-{uuid.uuid4()}@test.com"
    user_id = run(_create_user(email, is_deleted=True))

    resp = run(
        client.post(
            f"{settings.API_V1_STR}/auth/forgot-password",
            json={"email": email},
        )
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["message"] == GENERIC_FORGOT_MESSAGE
    assert run(_count_user_otps(user_id)) == 0


def test_provider_transport_failure_returns_generic_and_rolls_back(client):
    email = f"transport-failure-{uuid.uuid4()}@test.com"
    user_id = run(_create_user(email))

    failure = EmailTransportError(provider="mailpit", cause_type="OSError")
    with patch.object(
        EmailService,
        "send_password_reset_otp",
        new=AsyncMock(side_effect=failure),
    ):
        resp = run(
            client.post(
                f"{settings.API_V1_STR}/auth/forgot-password",
                json={"email": email},
            )
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["message"] == GENERIC_FORGOT_MESSAGE
    # The pending OTP and cooldown state were rolled back.
    assert run(_count_user_otps(user_id)) == 0

    # Because no cooldown was committed, a retry can create the OTP.
    retry = run(
        client.post(
            f"{settings.API_V1_STR}/auth/forgot-password",
            json={"email": email},
        )
    )
    assert retry.status_code == 200, retry.text
    assert run(_count_user_otps(user_id)) == 1


def test_concurrent_forgot_password_requests_create_single_active_otp(client):
    email = f"forgot-race-{uuid.uuid4()}@test.com"
    user_id = run(_create_user(email))

    responses = run(_concurrent_forgot(client, email, 4))

    assert all(r.status_code == 200 for r in responses), [
        r.status_code for r in responses
    ]
    assert run(_count_active_otps(user_id)) == 1


# ---------------------------------------------------------------------------
# Reset-token newest-record selection and atomic consumption
# ---------------------------------------------------------------------------


def test_newest_valid_reset_token_can_be_consumed_once(client):
    email = f"reset-once-{uuid.uuid4()}@test.com"
    user_id = run(_create_user(email))
    token = f"token-{uuid.uuid4()}"
    record_id = run(_create_reset_record(user_id, email, token))

    first = run(_post_reset(client, email, token))
    assert first.status_code == 200, first.text
    assert run(_get_reset_record(record_id)).reset_token_used is True

    second = run(_post_reset(client, email, token))
    assert second.status_code == 400, second.text


def test_two_concurrent_resets_with_same_token_only_one_succeeds():
    email = f"reset-race-{uuid.uuid4()}@test.com"
    user_id = run(_create_user(email))
    token = f"token-{uuid.uuid4()}"
    record_id = run(_create_reset_record(user_id, email, token))

    results = run(_concurrent_reset(email, token, 2))

    assert results.count(True) == 1, results
    assert run(_get_reset_record(record_id)).reset_token_used is True
    user = run(_get_user(user_id))
    assert verify_password(NEW_PASSWORD, user.password_hash)


def test_older_unexpired_token_rejected_when_newest_is_consumed(client):
    email = f"reset-newer-used-{uuid.uuid4()}@test.com"
    user_id = run(_create_user(email))
    now = datetime.now(timezone.utc)
    old_token = f"old-{uuid.uuid4()}"
    new_token = f"new-{uuid.uuid4()}"
    run(
        _create_reset_record(
            user_id,
            email,
            old_token,
            created_at=now - timedelta(minutes=10),
        )
    )
    run(
        _create_reset_record(
            user_id,
            email,
            new_token,
            created_at=now,
            reset_token_used=True,
        )
    )

    resp = run(_post_reset(client, email, old_token))

    assert resp.status_code == 400, resp.text
    user = run(_get_user(user_id))
    assert verify_password(PASSWORD, user.password_hash)


def test_older_unexpired_token_rejected_when_newest_is_expired(client):
    email = f"reset-newer-expired-{uuid.uuid4()}@test.com"
    user_id = run(_create_user(email))
    now = datetime.now(timezone.utc)
    old_token = f"old-{uuid.uuid4()}"
    new_token = f"new-{uuid.uuid4()}"
    run(
        _create_reset_record(
            user_id,
            email,
            old_token,
            created_at=now - timedelta(minutes=10),
        )
    )
    run(
        _create_reset_record(
            user_id,
            email,
            new_token,
            created_at=now,
            expires_in_seconds=-60,
        )
    )

    resp = run(_post_reset(client, email, old_token))

    assert resp.status_code == 400, resp.text
    user = run(_get_user(user_id))
    assert verify_password(PASSWORD, user.password_hash)


def test_locked_but_not_deleted_account_can_reset_without_unlocking(client):
    email = f"reset-locked-{uuid.uuid4()}@test.com"
    user_id = run(_create_user(email, is_active=False))
    token = f"token-{uuid.uuid4()}"
    run(_create_reset_record(user_id, email, token))

    resp = run(_post_reset(client, email, token))

    assert resp.status_code == 200, resp.text
    user = run(_get_user(user_id))
    assert verify_password(NEW_PASSWORD, user.password_hash)
    # Resetting the password must not silently reactivate a locked account.
    assert user.is_active is False


def test_deleted_account_cannot_reset_password(client):
    email = f"reset-deleted-{uuid.uuid4()}@test.com"
    user_id = run(_create_user(email, is_deleted=True))
    token = f"token-{uuid.uuid4()}"
    record_id = run(_create_reset_record(user_id, email, token))

    resp = run(_post_reset(client, email, token))

    assert resp.status_code == 400, resp.text
    assert run(_get_reset_record(record_id)).reset_token_used is False
    user = run(_get_user(user_id))
    assert verify_password(PASSWORD, user.password_hash)


def test_expired_newest_token_cannot_fall_back_to_older_token(client):
    email = f"reset-expired-newest-{uuid.uuid4()}@test.com"
    user_id = run(_create_user(email))
    now = datetime.now(timezone.utc)
    old_token = f"old-{uuid.uuid4()}"
    new_token = f"new-{uuid.uuid4()}"
    run(
        _create_reset_record(
            user_id,
            email,
            old_token,
            created_at=now - timedelta(minutes=10),
        )
    )
    run(
        _create_reset_record(
            user_id,
            email,
            new_token,
            created_at=now,
            expires_in_seconds=-60,
        )
    )

    # Neither the expired newest token nor the older token can be used.
    assert run(_post_reset(client, email, new_token)).status_code == 400
    assert run(_post_reset(client, email, old_token)).status_code == 400

    user = run(_get_user(user_id))
    assert verify_password(PASSWORD, user.password_hash)
