import sys
from datetime import timedelta
from pathlib import Path

import pytest
from jose import jwt

from app.core.config import settings
from app.core.security import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    get_password_hash,
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
