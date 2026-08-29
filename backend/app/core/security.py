from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    subject: str | Any,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token (HS256) containing `sub`, `exp`, and `iat`."""
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"sub": str(subject), "exp": expire, "iat": int(now.timestamp())}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Decode and validate a JWT access token.

    Returns the payload for valid tokens, or ``None`` for invalid/expired ones.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
        )
    except JWTError:
        return None
    return payload


def is_token_valid_after_password_reset(payload: dict, last_password_reset: datetime | None) -> bool:
    """Check if a JWT token is still valid after a password reset.

    A token is invalid if it was issued before the last password reset.
    """
    if last_password_reset is None:
        return True

    iat = payload.get("iat")
    if iat is None:
        return False

    token_issued_at = datetime.fromtimestamp(iat, tz=timezone.utc)

    # SQL Server DATETIME/DATETIME2 does not preserve timezone metadata,
    # so last_password_reset loaded from DB is offset-naive but represents UTC.
    # Make it timezone-aware (UTC) for safe comparison with aware token_issued_at.
    if last_password_reset.tzinfo is None:
        last_password_reset = last_password_reset.replace(tzinfo=timezone.utc)

    return token_issued_at >= last_password_reset
