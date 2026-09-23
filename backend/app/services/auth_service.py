from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictException, ForbiddenException, LockedAccountException
from app.core.password_reset import (
    generate_otp,
    generate_reset_token,
    hash_otp,
    hash_reset_token,
    verify_otp,
    verify_reset_token,
)
from app.core.security import get_password_hash, verify_password
from app.domain.enums import UserRole
from app.models import PasswordResetOTP, User
from app.repositories import UserRepository
from app.schemas.user import UserCreate
from app.services.email_service import EmailService


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session, User)
        self.email_service = EmailService()

    async def register_user(self, data: UserCreate) -> User:
        # Check for existing user with this email (including locked/inactive users)
        # but exclude soft-deleted users
        existing = await self.users.get_by_email_including_inactive(data.email)
        if existing is not None:
            raise ConflictException(
                f"Email {data.email!r} đã được sử dụng."
            )

        # Prevent mass-assignment: public registration cannot create admin accounts
        if data.role == UserRole.ADMIN:
            raise ForbiddenException("Admin role cannot be assigned via public registration")

        user = User(
            email=data.email,
            password_hash=get_password_hash(data.password),
            role=data.role,
        )
        self.session.add(user)
        try:
            await self.session.commit()
            await self.session.refresh(user)
        except Exception:
            await self.session.rollback()
            raise
        return user

    async def authenticate_user(
        self,
        email: str,
        password: str,
    ) -> User | None:
        user = await self.users.get_by_email(email)
        if user is None:
            return None
        if not verify_password(password, user.password_hash):
            return None
        if not user.is_active:
            raise LockedAccountException(
                user.lock_reason or "Tài khoản của bạn đã bị khóa. Vui lòng liên hệ quản trị viên để biết thêm thông tin."
            )
        return user

    async def forgot_password(self, email: str) -> None:
        """Request a password reset OTP for the given email.
        
        Always returns the same generic response to prevent account enumeration.
        """
        user = await self.users.get_by_email(email)
        
        # Always return generic response to prevent account enumeration
        # but only proceed with OTP generation if user exists
        if user is None:
            return
        
        # Check for existing active OTP with cooldown
        existing_otp = await self._get_active_otp(user.id)
        if existing_otp:
            time_since_created = datetime.now(timezone.utc) - existing_otp.created_at
            if time_since_created < timedelta(seconds=60):
                # Cooldown active - still return generic response
                return
        
        # Invalidate previous active OTPs for this user
        await self._invalidate_user_otps(user.id)
        
        # Generate new OTP
        otp = generate_otp()
        otp_hash = hash_otp(otp)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        
        otp_record = PasswordResetOTP(
            user_id=user.id,
            email=user.email,
            otp_hash=otp_hash,
            expires_at=expires_at,
        )
        self.session.add(otp_record)
        
        try:
            await self.session.commit()
            # Send OTP email
            await self.email_service.send_password_reset_otp(user.email, otp)
        except Exception:
            await self.session.rollback()
            raise

    async def verify_reset_otp(self, email: str, otp: str) -> str | None:
        """Verify the OTP and return a reset token if valid.
        
        Returns the plaintext reset token if successful, None otherwise.
        """
        user = await self.users.get_by_email(email)
        if user is None:
            return None
        
        otp_record = await self._get_active_otp(user.id)
        if otp_record is None:
            return None
        
        if otp_record.is_used:
            return None
        
        if datetime.now(timezone.utc) > otp_record.expires_at:
            return None
        
        if otp_record.attempts >= otp_record.max_attempts:
            # Mark as used to prevent further attempts
            otp_record.is_used = True
            otp_record.used_at = datetime.now(timezone.utc)
            await self.session.commit()
            return None
        
        # Increment attempts
        otp_record.attempts += 1
        
        # Verify OTP
        if not verify_otp(otp, otp_record.otp_hash):
            await self.session.commit()
            return None
        
        # OTP is valid - mark as used and generate reset token
        otp_record.is_used = True
        otp_record.used_at = datetime.now(timezone.utc)
        
        reset_token = generate_reset_token()
        reset_token_hash = hash_reset_token(reset_token)
        otp_record.reset_token_hash = reset_token_hash
        otp_record.expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        
        try:
            await self.session.commit()
            return reset_token
        except Exception:
            await self.session.rollback()
            raise

    async def reset_password(self, email: str, reset_token: str, new_password: str) -> bool:
        """Reset the user's password using the reset token.
        
        Returns True if successful, False otherwise.
        """
        user = await self.users.get_by_email(email)
        if user is None:
            return False
        
        # Find the OTP record with this reset token
        stmt = select(PasswordResetOTP).where(
            PasswordResetOTP.user_id == user.id,
            PasswordResetOTP.is_used == True,
            PasswordResetOTP.reset_token_hash.isnot(None),
        ).order_by(PasswordResetOTP.created_at.desc())
        result = await self.session.execute(stmt)
        otp_record = result.scalars().first()
        
        if otp_record is None:
            return False
        
        if not verify_reset_token(reset_token, otp_record.reset_token_hash):
            return False
        
        if datetime.now(timezone.utc) > otp_record.expires_at:
            return False
        
        # Update password and mark reset token as used
        user.password_hash = get_password_hash(new_password)
        user.last_password_reset = datetime.now(timezone.utc)
        otp_record.expires_at = datetime.now(timezone.utc)  # Invalidate reset token
        
        try:
            await self.session.commit()
            return True
        except Exception:
            await self.session.rollback()
            raise

    async def _get_active_otp(self, user_id: Any) -> PasswordResetOTP | None:
        """Get the most recent active OTP for a user."""
        stmt = select(PasswordResetOTP).where(
            PasswordResetOTP.user_id == user_id,
            PasswordResetOTP.is_used == False,
            PasswordResetOTP.expires_at > datetime.now(timezone.utc),
        ).order_by(PasswordResetOTP.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def _invalidate_user_otps(self, user_id: Any) -> None:
        """Invalidate all active OTPs for a user."""
        stmt = select(PasswordResetOTP).where(
            PasswordResetOTP.user_id == user_id,
            PasswordResetOTP.is_used == False,
        )
        result = await self.session.execute(stmt)
        otps = result.scalars().all()
        for otp in otps:
            otp.is_used = True
            otp.used_at = datetime.now(timezone.utc)
        await self.session.flush()

    # ===== Redis JWT Blocklist =====

    def _get_redis_client(self) -> Optional[Redis]:
        """Get Redis client from app state."""
        from app.main import app
        return getattr(app.state, "redis", None)

    async def revoke_token(self, jti: str, exp: datetime) -> bool:
        """
        Add a JWT ID to the Redis blocklist.

        Args:
            jti: The JWT ID to revoke
            exp: The token expiration timestamp

        Returns:
            True if revoked successfully, False if token already expired or Redis unavailable
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            return False

        # Calculate remaining TTL
        now = datetime.now(timezone.utc)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        remaining_ttl = int((exp - datetime.now(timezone.utc)).total_seconds())

        if remaining_ttl <= 0:
            # Token already expired, no need to blocklist
            return False

        key = f"auth:blocklist:{jti}"
        try:
            await redis_client.set(key, "1", ex=remaining_ttl)
            return True
        except RedisError as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to revoke token in Redis: {e}")
            return False

    async def is_token_revoked(self, jti: str) -> bool:
        """
        Check if a JWT ID is in the Redis blocklist.

        Uses fail-open policy: if Redis is unavailable, return False (allow token).

        Args:
            jti: The JWT ID to check

        Returns:
            True if revoked, False if not revoked or Redis unavailable
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            return False

        key = f"auth:blocklist:{jti}"
        try:
            result = await redis_client.exists(key)
            return result > 0
        except RedisError as e:
            import logging
            logging.getLogger(__name__).warning(f"Redis blocklist lookup failed (fail-open): {e}")
            return False

    async def logout(self, jti: str, exp: datetime) -> bool:
        """
        Revoke a token on logout.

        Args:
            jti: The JWT ID to revoke
            exp: The token expiration timestamp

        Returns:
            True if revoked successfully, False if token already expired or Redis unavailable
        """
        return await self.revoke_token(jti, exp)