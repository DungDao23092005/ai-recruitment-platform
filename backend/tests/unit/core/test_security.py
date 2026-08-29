from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jose import jwt

from app.core.config import settings
from app.core.security import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    get_password_hash,
    is_token_valid_after_password_reset,
    verify_password,
)

PLAINTEXT = "super-secret-pass"


def test_password_hash_is_created():
    hashed = get_password_hash(PLAINTEXT)

    assert hashed != PLAINTEXT
    assert hashed.startswith("$2b$")


def test_password_hash_salt_produces_different_hashes():
    assert get_password_hash(PLAINTEXT) != get_password_hash(PLAINTEXT)


def test_verify_password_correct():
    hashed = get_password_hash(PLAINTEXT)

    assert verify_password(PLAINTEXT, hashed) is True


def test_verify_password_wrong():
    hashed = get_password_hash(PLAINTEXT)

    assert verify_password("wrong-password", hashed) is False


def test_create_access_token_returns_string():
    token = create_access_token(subject="user-123")

    assert isinstance(token, str)
    assert token.count(".") == 2


def test_access_token_contains_sub():
    payload = decode_access_token(create_access_token(subject="user-123"))

    assert payload is not None
    assert payload["sub"] == "user-123"


def test_access_token_contains_exp():
    payload = decode_access_token(create_access_token(subject="user-123"))

    assert payload is not None
    assert "exp" in payload
    assert payload["exp"] > 0


def test_access_token_subject_preserved_for_non_string():
    payload = decode_access_token(create_access_token(subject=42))

    assert payload is not None
    assert payload["sub"] == "42"


def test_decode_valid_token_returns_payload():
    token = create_access_token(subject="user-123")
    payload = decode_access_token(token)

    assert payload is not None
    assert set(payload.keys()) == {"sub", "exp", "iat"}
    assert payload["sub"] == "user-123"


def test_decode_invalid_signature_returns_none():
    token = create_access_token(subject="user-123")
    wrong_secret_token = jwt.encode(
        {"sub": "user-123"},
        "a-completely-different-secret-key",
        algorithm=ALGORITHM,
    )

    assert decode_access_token(token) is not None
    assert decode_access_token(wrong_secret_token) is None


def test_decode_malformed_token_returns_none():
    assert decode_access_token("not.a.jwt") is None
    assert decode_access_token("") is None


def test_decode_expired_token_returns_none():
    expired_token = create_access_token(
        subject="user-123",
        expires_delta=timedelta(seconds=-1),
    )

    assert decode_access_token(expired_token) is None


def test_access_token_uses_settings_secret_and_hs256():
    token = create_access_token(subject="user-123")

    header = jwt.get_unverified_header(token)
    assert header["alg"] == "HS256"
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "user-123"


def test_no_hardcoded_secret_in_security_module():
    source = Path(sys.modules["app.core.security"].__file__).read_text(
        encoding="utf-8"
    )

    assert "change-me-in-development-with-a-random-value" not in source


class TestIsTokenValidAfterPasswordReset:
    """Tests for is_token_valid_after_password_reset function.

    Tests the datetime comparison between JWT iat (aware UTC) and
    database last_password_reset (naive or aware).
    """

    def test_no_password_reset_timestamp(self):
        """If last_password_reset is None, token is always valid."""
        payload = {"iat": int(datetime.now(timezone.utc).timestamp())}

        assert is_token_valid_after_password_reset(payload, None) is True

    def test_naive_database_datetime_before_jwt(self):
        """Naive DB datetime (interpreted as UTC) before JWT iat -> token valid."""
        # DB stores naive datetime representing UTC
        last_reset = datetime(2026, 8, 27, 10, 0, 0)
        # JWT issued 1 minute after
        jwt_issued = datetime(2026, 8, 27, 10, 1, 0, tzinfo=timezone.utc)
        payload = {"iat": int(jwt_issued.timestamp())}

        assert is_token_valid_after_password_reset(payload, last_reset) is True

    def test_naive_database_datetime_after_jwt(self):
        """Naive DB datetime after JWT iat -> token invalid."""
        # DB stores naive datetime representing UTC
        last_reset = datetime(2026, 8, 27, 10, 1, 0)
        # JWT issued 1 minute before
        jwt_issued = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)
        payload = {"iat": int(jwt_issued.timestamp())}

        assert is_token_valid_after_password_reset(payload, last_reset) is False

    def test_aware_database_datetime_before_jwt(self):
        """Aware DB datetime before JWT iat -> token valid."""
        last_reset = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)
        jwt_issued = datetime(2026, 8, 27, 10, 1, 0, tzinfo=timezone.utc)
        payload = {"iat": int(jwt_issued.timestamp())}

        assert is_token_valid_after_password_reset(payload, last_reset) is True

    def test_aware_database_datetime_after_jwt(self):
        """Aware DB datetime after JWT iat -> token invalid."""
        last_reset = datetime(2026, 8, 27, 10, 1, 0, tzinfo=timezone.utc)
        jwt_issued = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)
        payload = {"iat": int(jwt_issued.timestamp())}

        assert is_token_valid_after_password_reset(payload, last_reset) is False

    def test_exact_boundary_equal(self):
        """Token issued at exact same time as password reset -> valid."""
        last_reset = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)
        jwt_issued = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)
        payload = {"iat": int(jwt_issued.timestamp())}

        assert is_token_valid_after_password_reset(payload, last_reset) is True

    def test_exact_boundary_naive_db(self):
        """Token at exact same time as naive DB datetime -> valid."""
        last_reset = datetime(2026, 8, 27, 10, 0, 0)  # naive, treated as UTC
        jwt_issued = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)
        payload = {"iat": int(jwt_issued.timestamp())}

        assert is_token_valid_after_password_reset(payload, last_reset) is True

    def test_no_iat_in_payload(self):
        """Missing iat in payload -> token invalid."""
        payload = {"sub": "user-123"}
        last_reset = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)

        assert is_token_valid_after_password_reset(payload, last_reset) is False

    def test_no_typeerror_naive_vs_aware(self):
        """Naive DB datetime + aware JWT MUST NOT raise TypeError."""
        last_reset = datetime(2026, 8, 27, 10, 0, 0)  # naive
        jwt_issued = datetime(2026, 8, 27, 10, 1, 0, tzinfo=timezone.utc)
        payload = {"iat": int(jwt_issued.timestamp())}

        # Should not raise TypeError
        result = is_token_valid_after_password_reset(payload, last_reset)
        assert result is True
