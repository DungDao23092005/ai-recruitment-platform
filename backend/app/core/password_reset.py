from __future__ import annotations

import secrets

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def generate_otp() -> str:
    """Generate a cryptographically secure 6-digit OTP."""
    return f"{secrets.randbelow(1000000):06d}"


def hash_otp(otp: str) -> str:
    """Hash an OTP using the project's password hashing mechanism."""
    return pwd_context.hash(otp)


def verify_otp(plain_otp: str, hashed_otp: str) -> bool:
    """Verify a plaintext OTP against a stored bcrypt hash."""
    return pwd_context.verify(plain_otp, hashed_otp)


def generate_reset_token() -> str:
    """Generate a cryptographically secure reset token."""
    return secrets.token_urlsafe(32)


def hash_reset_token(token: str) -> str:
    """Hash a reset token using the project's password hashing mechanism."""
    return pwd_context.hash(token)


def verify_reset_token(plain_token: str, hashed_token: str) -> bool:
    """Verify a plaintext reset token against a stored bcrypt hash."""
    return pwd_context.verify(plain_token, hashed_token)