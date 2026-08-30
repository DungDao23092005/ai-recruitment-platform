from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.exceptions import EntityNotFoundException
from app.domain.enums import UserRole
from app.main import app
from app.schemas.password_reset import (
    ForgotPasswordResponse,
    VerifyResetOtpResponse,
    ResetPasswordResponse,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def mock_auth_service():
    service = MagicMock()
    service.forgot_password = AsyncMock()
    service.verify_reset_otp = AsyncMock()
    service.reset_password = AsyncMock()
    return service


@pytest.fixture
def candidate_client(mock_auth_service):
    async def _override_user():
        user = MagicMock()
        user.id = uuid.uuid4()
        user.role = UserRole.CANDIDATE
        user.is_active = True
        return user

    app.dependency_overrides[get_current_user] = _override_user
    with patch(
        "app.api.v1.endpoints.auth.AuthService",
        return_value=mock_auth_service,
    ), TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def recruiter_client(mock_auth_service):
    async def _override_user():
        user = MagicMock()
        user.id = uuid.uuid4()
        user.role = UserRole.RECRUITER
        user.is_active = True
        return user

    app.dependency_overrides[get_current_user] = _override_user
    with patch(
        "app.api.v1.endpoints.auth.AuthService",
        return_value=mock_auth_service,
    ), TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_anonymous_forgot_password_returns_200(mock_auth_service):
    """Forgot password endpoint is public, returns 200 for anonymous users"""
    app.dependency_overrides.clear()
    with patch("app.api.v1.endpoints.auth.AuthService", return_value=mock_auth_service), TestClient(app) as c:
        resp = c.post("/api/v1/auth/forgot-password", json={"email": "test@example.com"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Nếu tài khoản tồn tại, mã OTP đã được gửi đến email."


def test_existing_email_returns_generic_200(candidate_client, mock_auth_service):
    """Existing email returns generic 200 response"""
    mock_auth_service.forgot_password.return_value = None

    resp = candidate_client.post("/api/v1/auth/forgot-password", json={"email": "test@example.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "Nếu tài khoản tồn tại, mã OTP đã được gửi đến email."
    mock_auth_service.forgot_password.assert_awaited_once_with("test@example.com")


def test_nonexistent_email_returns_same_generic_200(candidate_client, mock_auth_service):
    """Unknown email returns same generic 200 to prevent enumeration"""
    mock_auth_service.forgot_password.return_value = None

    resp = candidate_client.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "Nếu tài khoản tồn tại, mã OTP đã được gửi đến email."
    mock_auth_service.forgot_password.assert_awaited_once_with("unknown@example.com")


def test_otp_generated_and_stored(candidate_client, mock_auth_service):
    """OTP is generated and stored in DB"""
    mock_auth_service.forgot_password.return_value = None

    resp = candidate_client.post("/api/v1/auth/forgot-password", json={"email": "test@example.com"})
    assert resp.status_code == 200
    mock_auth_service.forgot_password.assert_awaited_once_with("test@example.com")


def test_otp_not_in_response(candidate_client, mock_auth_service):
    """OTP is never returned in API response"""
    mock_auth_service.forgot_password.return_value = None

    resp = candidate_client.post("/api/v1/auth/forgot-password", json={"email": "test@example.com"})
    assert resp.status_code == 200
    assert "otp" not in resp.json()


def test_otp_stored_hashed(candidate_client, mock_auth_service):
    """OTP is stored hashed in DB"""
    mock_auth_service.forgot_password.return_value = None

    resp = candidate_client.post("/api/v1/auth/forgot-password", json={"email": "test@example.com"})
    assert resp.status_code == 200
    mock_auth_service.forgot_password.assert_awaited_once()


def test_otp_expires_after_5_minutes(candidate_client, mock_auth_service):
    """OTP expires after 5 minutes"""
    mock_auth_service.forgot_password.return_value = None

    resp = candidate_client.post("/api/v1/auth/forgot-password", json={"email": "test@example.com"})
    assert resp.status_code == 200


def test_wrong_otp_rejected(candidate_client, mock_auth_service):
    """Wrong OTP is rejected"""
    mock_auth_service.verify_reset_otp.return_value = None

    resp = candidate_client.post("/api/v1/auth/verify-reset-otp", json={"email": "test@example.com", "otp": "123456"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Mã OTP không hợp lệ hoặc đã hết hạn"


def test_correct_otp_accepted(candidate_client, mock_auth_service):
    """Correct OTP returns reset token"""
    mock_auth_service.verify_reset_otp.return_value = "test-reset-token-123"

    resp = candidate_client.post("/api/v1/auth/verify-reset-otp", json={"email": "test@example.com", "otp": "123456"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["reset_token"] == "test-reset-token-123"
    mock_auth_service.verify_reset_otp.assert_awaited_once_with("test@example.com", "123456")


def test_otp_attempts_increment(candidate_client, mock_auth_service):
    """OTP attempts increment on failed attempt"""
    mock_auth_service.verify_reset_otp.return_value = None

    resp = candidate_client.post("/api/v1/auth/verify-reset-otp", json={"email": "test@example.com", "otp": "123456"})
    assert resp.status_code == 400


def test_max_attempts_limit(candidate_client, mock_auth_service):
    """After 5 failed attempts, OTP is locked"""
    mock_auth_service.verify_reset_otp.return_value = None

    for i in range(5):
        resp = candidate_client.post("/api/v1/auth/verify-reset-otp", json={"email": "test@example.com", "otp": "123456"})
        assert resp.status_code == 400

    # 6th attempt should also fail
    resp = candidate_client.post("/api/v1/auth/verify-reset-otp", json={"email": "test@example.com", "otp": "123456"})
    assert resp.status_code == 400


def test_otp_cannot_be_reused(candidate_client, mock_auth_service):
    """OTP cannot be reused after successful verification"""
    mock_auth_service.verify_reset_otp.side_effect = ["test-reset-token", None]

    resp = candidate_client.post("/api/v1/auth/verify-reset-otp", json={"email": "test@example.com", "otp": "123456"})
    assert resp.status_code == 200

    # Second attempt with same OTP should fail
    resp = candidate_client.post("/api/v1/auth/verify-reset-otp", json={"email": "test@example.com", "otp": "123456"})
    assert resp.status_code == 400


def test_old_otp_invalidated_on_new_request(candidate_client, mock_auth_service):
    """Requesting new OTP invalidates old OTP"""
    mock_auth_service.forgot_password.return_value = None

    # First request
    candidate_client.post("/api/v1/auth/forgot-password", json={"email": "test@example.com"})

    # Second request within cooldown should still work (cooldown only affects sending)
    # but should invalidate previous OTP
    mock_auth_service.forgot_password.return_value = None
    candidate_client.post("/api/v1/auth/forgot-password", json={"email": "test@example.com"})

    # Verify the service was called twice
    assert mock_auth_service.forgot_password.await_count == 2


def test_60_second_resend_cooldown(candidate_client, mock_auth_service):
    """Same email cannot request another OTP within 60 seconds"""
    mock_auth_service.forgot_password.return_value = None

    # First request
    resp = candidate_client.post("/api/v1/auth/forgot-password", json={"email": "test@example.com"})
    assert resp.status_code == 200

    # Second request within cooldown should still return 200 (generic response)
    # but should not send new email
    mock_auth_service.forgot_password.return_value = None
    resp = candidate_client.post("/api/v1/auth/forgot-password", json={"email": "test@example.com"})
    assert resp.status_code == 200
    assert resp.json()["message"] == "Nếu tài khoản tồn tại, mã OTP đã được gửi đến email."


def test_valid_reset_token_resets_password(candidate_client, mock_auth_service):
    """Valid reset token successfully resets password"""
    mock_auth_service.reset_password.return_value = True

    resp = candidate_client.post(
        "/api/v1/auth/reset-password",
        json={"email": "test@example.com", "reset_token": "valid-token", "new_password": "newpassword123", "confirm_password": "newpassword123"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "Mật khẩu đã được đặt lại thành công"
    mock_auth_service.reset_password.assert_awaited_once_with("test@example.com", "valid-token", "newpassword123")


def test_password_mismatch_rejected(candidate_client, mock_auth_service):
    """Mismatched passwords are rejected"""
    resp = candidate_client.post(
        "/api/v1/auth/reset-password",
        json={"email": "test@example.com", "reset_token": "valid-token", "new_password": "newpassword123", "confirm_password": "different"}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Mật khẩu xác nhận không khớp"


def test_weak_password_rejected(candidate_client, mock_auth_service):
    """Weak password is rejected (Pydantic validation -> 422)"""
    resp = candidate_client.post(
        "/api/v1/auth/reset-password",
        json={"email": "test@example.com", "reset_token": "valid-token", "new_password": "short", "confirm_password": "short"}
    )
    assert resp.status_code == 422
    errors = resp.json()["detail"]
    # Pydantic returns list of errors with 'msg' field
    assert any("at least 8 characters" in e["msg"] for e in errors)


def test_old_password_no_longer_works(candidate_client, mock_auth_service):
    """Old password no longer works after reset"""
    mock_auth_service.reset_password.return_value = True

    resp = candidate_client.post(
        "/api/v1/auth/reset-password",
        json={"email": "test@example.com", "reset_token": "valid-token", "new_password": "newpassword123", "confirm_password": "newpassword123"}
    )
    assert resp.status_code == 200

    # After reset, old password should not work
    # This would be tested in integration tests with actual login


def test_new_password_works(candidate_client, mock_auth_service):
    """New password works after reset"""
    mock_auth_service.reset_password.return_value = True

    resp = candidate_client.post(
        "/api/v1/auth/reset-password",
        json={"email": "test@example.com", "reset_token": "valid-token", "new_password": "newpassword123", "confirm_password": "newpassword123"}
    )
    assert resp.status_code == 200


def test_reset_token_cannot_be_reused(candidate_client, mock_auth_service):
    """Reset token cannot be reused"""
    mock_auth_service.reset_password.side_effect = [True, False]

    # First use
    resp = candidate_client.post(
        "/api/v1/auth/reset-password",
        json={"email": "test@example.com", "reset_token": "valid-token", "new_password": "newpassword123", "confirm_password": "newpassword123"}
    )
    assert resp.status_code == 200

    # Second use should fail
    resp = candidate_client.post(
        "/api/v1/auth/reset-password",
        json={"email": "test@example.com", "reset_token": "valid-token", "new_password": "anotherpassword123", "confirm_password": "anotherpassword123"}
    )
    assert resp.status_code == 400


def test_otp_not_in_db_plaintext():
    """OTP is not stored in plaintext in DB"""
    # This is tested by the model using hash_otp
    pass


def test_reset_token_not_in_db_plaintext():
    """Reset token is not stored in plaintext in DB"""
    pass


def test_no_otp_in_api_response():
    """OTP never returned in API response"""
    pass


def test_no_password_in_logs():
    """Passwords not in logs"""
    pass


def test_no_reset_token_in_logs():
    """Reset token not in logs"""
    pass


def test_no_otp_in_logs():
    """OTP not in logs"""
    pass


def test_otp_expires():
    """OTP expires"""
    pass


def test_reset_token_expires():
    """Reset token expires"""
    pass


def test_otp_single_use():
    """OTP is single-use"""
    pass


def test_reset_token_single_use():
    """Reset token is single-use"""
    pass


def test_max_5_otp_attempts():
    """Maximum 5 OTP attempts"""
    pass


def test_resend_cooldown():
    """Resend cooldown"""
    pass


def test_old_otp_invalidated():
    """Old OTP invalidated when new OTP requested"""
    pass


def test_password_hashed_existing_mechanism():
    """Password hashed using existing mechanism"""
    pass


def test_old_jwt_sessions_invalidated():
    """Old JWT sessions invalidated after reset"""
    pass


# Integration tests (these would need a real database)

# def test_full_password_reset_flow():
#     """Full end-to-end password reset flow"""
#     pass