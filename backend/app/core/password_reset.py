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


# A fixed, non-secret bcrypt hash used to perform equivalent work for
# enumeration-resistant timing when no real credential exists. This is NOT a
# secret (it hashes a constant string); it exists purely to equalize latency.
_DUMMY_OTP_HASH = pwd_context.hash("000000")


def dummy_otp_verify() -> None:
    """Run one bcrypt verification without touching any real credential.

    Called on OTP-verification paths where no active OTP exists, so the
    response latency does not reveal whether an account/OTP is present. The
    cost is bounded because the endpoint is rate limited before this runs.
    """
    pwd_context.verify("000000", _DUMMY_OTP_HASH)


def dummy_otp_hash() -> None:
    """Run one bcrypt hash without touching any real credential.

    Called on forgot-password paths where the account does not exist (or is in
    cooldown), so the response latency matches the real hashing path. Bounded
    by the forgot-password rate limit.
    """
    pwd_context.hash("000000")
