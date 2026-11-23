import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import RedisError

from app.core.exceptions import (
    ConflictException,
    EmailTransportError,
    ForbiddenException,
)
from app.core.rate_limit import RateLimiter, set_rate_limiter
from app.domain.enums import UserRole
from app.models import PasswordResetOTP, User
from app.repositories import UserRepository
from app.schemas.user import UserCreate
from app.services.auth_service import AuthService


def make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    return session


def make_user() -> User:
    return User(
        id=uuid.uuid4(),
        email=f"{uuid.uuid4()}@example.com",
        password_hash="hashed",
        role=UserRole.CANDIDATE,
    )


def make_service(session) -> AuthService:
    service = AuthService(session)
    service.users = AsyncMock(spec=UserRepository)
    service.candidate_entitlements = AsyncMock()
    service.workspaces = AsyncMock()
    return service


class TestRegisterUser:
    def test_creates_user(self):
        session = make_session()
        service = make_service(session)
        service.users.get_by_email_including_inactive.return_value = None
        data = UserCreate(
            email="dev@example.com",
            password="password123",
            role=UserRole.RECRUITER,
        )

        user = asyncio.run(service.register_user(data))

        assert user is not None
        assert user.email == "dev@example.com"
        assert user.role == UserRole.RECRUITER
        assert user.password_hash != data.password
        assert user.password_hash.startswith("$")
        session.add.assert_called_once_with(user)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(user)

    def test_duplicate_email_raises_conflict(self):
        session = make_session()
        service = make_service(session)
        service.users.get_by_email_including_inactive.return_value = make_user()
        data = UserCreate(email="dev@example.com", password="password123")

        with pytest.raises(ConflictException):
            asyncio.run(service.register_user(data))

        session.commit.assert_not_awaited()
        session.rollback.assert_not_awaited()

    def test_commit_failure_rolls_back(self):
        session = make_session()
        service = make_service(session)
        service.users.get_by_email_including_inactive.return_value = None
        session.commit.side_effect = RuntimeError("db down")
        data = UserCreate(email="dev@example.com", password="password123")

        with pytest.raises(RuntimeError):
            asyncio.run(service.register_user(data))

        session.rollback.assert_awaited_once()

    def test_admin_role_rejected(self):
        session = make_session()
        service = make_service(session)
        service.users.get_by_email_including_inactive.return_value = None
        # Admin role is now rejected at schema level (Pydantic validation)
        with pytest.raises(ValueError):
            UserCreate(
                email="attacker@example.com",
                password="password123",
                role=UserRole.ADMIN,
            )
        # Service should never be called since validation fails first
        session.commit.assert_not_awaited()


class TestAuthenticateUser:
    def test_valid_credentials_returns_user(self):
        from app.core.security import get_password_hash

        session = make_session()
        service = make_service(session)
        user = make_user()
        user.is_active = True
        user.password_hash = get_password_hash("password123")
        service.users.get_by_email.return_value = user

        result = asyncio.run(
            service.authenticate_user(email=user.email, password="password123")
        )

        assert result is user

    def test_unknown_email_returns_none(self):
        session = make_session()
        service = make_service(session)
        service.users.get_by_email.return_value = None

        result = asyncio.run(
            service.authenticate_user(
                email="missing@example.com",
                password="password123",
            )
        )

        assert result is None

    def test_wrong_password_returns_none(self):
        from app.core.security import get_password_hash

        session = make_session()
        service = make_service(session)
        user = make_user()
        user.is_active = True
        user.password_hash = get_password_hash("password123")
        service.users.get_by_email.return_value = user

        result = asyncio.run(
            service.authenticate_user(email=user.email, password="wrong-password")
        )

        assert result is None


class TestAuthenticateUserLockedAccount:
    def test_locked_user_correct_password_returns_locked_exception(self):
        from app.core.security import get_password_hash
        from app.core.exceptions import LockedAccountException

        session = make_session()
        service = make_service(session)
        user = make_user()
        user.is_active = False
        user.lock_reason = "Test lock reason"
        user.password_hash = get_password_hash("password123")
        service.users.get_by_email.return_value = user

        with pytest.raises(LockedAccountException) as exc_info:
            asyncio.run(
                service.authenticate_user(email=user.email, password="password123")
            )

        assert exc_info.value.reason == "Test lock reason"

    def test_locked_user_wrong_password_returns_none(self):
        from app.core.security import get_password_hash

        session = make_session()
        service = make_service(session)
        user = make_user()
        user.is_active = False
        user.password_hash = get_password_hash("password123")
        service.users.get_by_email.return_value = user

        result = asyncio.run(
            service.authenticate_user(email=user.email, password="wrong-password")
        )

        assert result is None

    def test_active_user_can_login(self):
        from app.core.security import get_password_hash

        session = make_session()
        service = make_service(session)
        user = make_user()
        user.is_active = True
        user.password_hash = get_password_hash("password123")
        service.users.get_by_email.return_value = user

        result = asyncio.run(
            service.authenticate_user(email=user.email, password="password123")
        )

        assert result is user


class TestRegisterUserEmailUniqueness:
    def test_locked_user_email_remains_unique(self):
        session = make_session()
        service = make_service(session)

        # Existing user is locked (inactive)
        locked_user = make_user()
        locked_user.is_active = False
        service.users.get_by_email_including_inactive.return_value = locked_user

        data = UserCreate(email=locked_user.email, password="newpassword123")

        with pytest.raises(ConflictException) as exc_info:
            asyncio.run(service.register_user(data))

        assert "đã được sử dụng" in str(exc_info.value)
        session.commit.assert_not_awaited()

    def test_soft_deleted_user_email_can_be_reused(self):
        """Registration should succeed if email belongs to a soft-deleted user.

        The get_by_email_including_inactive still filters is_deleted=False,
        so soft-deleted users are not considered for uniqueness.
        """
        session = make_session()
        service = make_service(session)

        # Soft-deleted user is NOT returned by get_by_email_including_inactive
        service.users.get_by_email_including_inactive.return_value = None

        data = UserCreate(email="deleted@example.com", password="password123")

        user = asyncio.run(service.register_user(data))

        assert user is not None
        assert user.email == "deleted@example.com"
        session.commit.assert_awaited_once()

    def test_duplicate_email_raises_conflict_still_works(self):
        """Existing active user email should still raise conflict."""
        session = make_session()
        service = make_service(session)
        active_user = make_user()
        active_user.is_active = True
        service.users.get_by_email_including_inactive.return_value = active_user

        data = UserCreate(email=active_user.email, password="password123")

        with pytest.raises(ConflictException):
            asyncio.run(service.register_user(data))

        session.commit.assert_not_awaited()


class TestForgotPassword:
    def _service_with_user(self, *, is_active: bool = True):
        session = make_session()
        service = make_service(session)
        user = make_user()
        user.is_active = is_active
        user.is_deleted = False
        service.users.get_by_email_for_update.return_value = user
        service._get_active_otp = AsyncMock(return_value=None)
        service._invalidate_user_otps = AsyncMock()
        service.email_service = AsyncMock()
        service.email_service.send_password_reset_otp = AsyncMock()
        return session, service, user

    def test_unknown_account_returns_generic_without_writes(self):
        session = make_session()
        service = make_service(session)
        service.users.get_by_email_for_update.return_value = None

        with patch("app.services.auth_service.dummy_otp_hash") as dummy:
            result = asyncio.run(service.forgot_password("missing@example.com"))

        assert result is None
        dummy.assert_called_once()
        session.add.assert_not_called()
        session.commit.assert_not_awaited()
        session.rollback.assert_awaited_once()

    def test_locked_but_not_deleted_user_can_request_otp(self):
        session, service, user = self._service_with_user(is_active=False)

        result = asyncio.run(service.forgot_password(user.email))

        assert result is None
        session.add.assert_called_once()
        added = session.add.call_args.args[0]
        assert isinstance(added, PasswordResetOTP)
        assert added.user_id == user.id
        # Requesting a reset never unlocks/reactivates the account.
        assert user.is_active is False
        session.flush.assert_awaited_once()
        session.commit.assert_awaited_once()
        service.email_service.send_password_reset_otp.assert_awaited_once()

    def test_cooldown_returns_generic_without_sending(self):
        session, service, user = self._service_with_user()
        existing = MagicMock()
        existing.created_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        service._get_active_otp = AsyncMock(return_value=existing)

        with patch("app.services.auth_service.dummy_otp_hash") as dummy:
            result = asyncio.run(service.forgot_password(user.email))

        assert result is None
        dummy.assert_called_once()
        session.add.assert_not_called()
        session.commit.assert_not_awaited()
        session.rollback.assert_awaited_once()
        service.email_service.send_password_reset_otp.assert_not_awaited()

    def test_transport_failure_rolls_back_and_returns_generic(self):
        session, service, user = self._service_with_user()
        service.email_service.send_password_reset_otp.side_effect = (
            EmailTransportError(provider="mailpit", cause_type="OSError")
        )

        result = asyncio.run(service.forgot_password(user.email))

        assert result is None
        session.flush.assert_awaited_once()
        session.commit.assert_not_awaited()
        session.rollback.assert_awaited_once()

    def test_database_commit_failure_is_not_converted(self):
        session, service, user = self._service_with_user()
        session.commit.side_effect = RuntimeError("db down")

        with pytest.raises(RuntimeError, match="db down"):
            asyncio.run(service.forgot_password(user.email))

        session.rollback.assert_awaited_once()


class TestResetPassword:
    def _setup(self):
        session = make_session()
        service = make_service(session)
        user = make_user()
        token = "valid-reset-token"
        record = PasswordResetOTP(
            id=uuid.uuid4(),
            user_id=user.id,
            email=user.email,
            otp_hash="otp-hash",
            reset_token_hash="reset-token-hash",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            attempts=0,
            max_attempts=5,
            is_used=True,
            reset_token_used=False,
        )
        service.users.get_by_email.return_value = user
        return session, service, user, record, token

    def test_failed_atomic_consume_does_not_change_password_or_enqueue(self):
        session, service, user, record, token = self._setup()

        select_result = MagicMock()
        select_result.scalar_one_or_none.return_value = record
        update_result = MagicMock()
        update_result.rowcount = 0
        session.execute = AsyncMock(side_effect=[select_result, update_result])
        original_hash = user.password_hash

        with patch(
            "app.services.auth_service.verify_reset_token", return_value=True
        ), patch(
            "app.services.auth_service.schedule_password_changed_confirmation",
            new=AsyncMock(),
        ) as schedule:
            result = asyncio.run(
                service.reset_password(user.email, token, "newpassword123")
            )

        assert result is False
        assert user.password_hash == original_hash
        schedule.assert_not_awaited()
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()

    def test_successful_reset_consumes_record_and_enqueues_confirmation(self):
        session, service, user, record, token = self._setup()

        select_result = MagicMock()
        select_result.scalar_one_or_none.return_value = record
        update_result = MagicMock()
        update_result.rowcount = 1
        session.execute = AsyncMock(side_effect=[select_result, update_result])

        with patch(
            "app.services.auth_service.verify_reset_token", return_value=True
        ), patch(
            "app.services.auth_service.get_password_hash",
            return_value="new-password-hash",
        ), patch(
            "app.services.auth_service.schedule_password_changed_confirmation",
            new=AsyncMock(),
        ) as schedule:
            result = asyncio.run(
                service.reset_password(user.email, token, "newpassword123")
            )

        assert result is True
        assert user.password_hash == "new-password-hash"
        assert user.last_password_reset is not None
        schedule.assert_awaited_once()
        assert schedule.call_args.kwargs["idempotency_key"] == (
            f"password_changed:{user.id}:{record.id}"
        )
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()


class TestRevokeToken:
    def make_service_with_redis(self, session, redis_client=None):
        """Create AuthService with optional mocked Redis client."""
        from app.core.rate_limit import set_rate_limiter
        from app.core.rate_limit import RateLimiter
        from app.main import app
        from redis.asyncio import Redis

        service = AuthService(session)
        service.users = AsyncMock(spec=UserRepository)

        if redis_client is not None:
            # Create a RateLimiter with the mocked Redis
            limiter = RateLimiter(redis_client)
            set_rate_limiter(limiter)
            # Also set app.state.redis for AuthService
            app.state.redis = redis_client
        else:
            set_rate_limiter(None)
            app.state.redis = None

        return service

    @pytest.mark.asyncio
    async def test_revoke_token_success(self):
        """Test revoke_token successfully adds jti to Redis blocklist with TTL."""
        from redis.asyncio import Redis

        session = make_session()
        mock_redis = AsyncMock(spec=Redis)
        mock_redis.set = AsyncMock(return_value=True)

        service = self.make_service_with_redis(None, mock_redis)

        jti = "test-jti-123"
        exp = datetime.now(timezone.utc) + timedelta(hours=1)

        result = await service.revoke_token(jti, exp)

        assert result is True
        mock_redis.set.assert_awaited_once()
        call_args = mock_redis.set.call_args
        assert call_args.args[0] == f"auth:blocklist:{jti}"
        assert call_args.args[1] == "1"
        assert call_args.kwargs["ex"] > 0

    @pytest.mark.asyncio
    async def test_revoke_token_expired_token_returns_false(self):
        """Test revoke_token returns False for already expired tokens."""
        session = make_session()
        mock_redis = AsyncMock()

        service = self.make_service_with_redis(None, mock_redis)

        jti = "test-jti-expired"
        exp = datetime.now(timezone.utc) - timedelta(seconds=10)

        result = await service.revoke_token(jti, exp)

        assert result is False
        mock_redis.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_revoke_token_no_redis_returns_false(self):
        """Test revoke_token returns False when Redis is unavailable."""
        session = make_session()
        service = self.make_service_with_redis(None, None)

        jti = "test-jti-no-redis"
        exp = datetime.now(timezone.utc) + timedelta(hours=1)

        result = await service.revoke_token(jti, exp)

        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_token_redis_error_returns_false_and_logs(self, caplog):
        """Test revoke_token returns False and logs warning on Redis error."""
        from redis.exceptions import RedisError

        session = make_session()
        mock_redis = AsyncMock()
        mock_redis.set.side_effect = RedisError("Connection failed")

        service = self.make_service_with_redis(None, mock_redis)

        jti = "test-jti-error"
        exp = datetime.now(timezone.utc) + timedelta(hours=1)

        result = await service.revoke_token(jti, exp)

        assert result is False
        assert "Failed to revoke token in Redis" in caplog.text


class TestIsTokenRevoked:
    def make_service_with_redis(self, session, redis_client=None):
        from app.core.rate_limit import set_rate_limiter
        from app.core.rate_limit import RateLimiter
        from app.main import app

        service = AuthService(session)
        service.users = AsyncMock(spec=UserRepository)

        if redis_client is not None:
            from app.core.rate_limit import RateLimiter
            limiter = RateLimiter(redis_client)
            set_rate_limiter(limiter)
            # Also set app.state.redis for AuthService
            app.state.redis = redis_client
        else:
            set_rate_limiter(None)
            app.state.redis = None

        return service

    @pytest.mark.asyncio
    async def test_is_token_revoked_true_when_key_exists(self):
        """Test is_token_revoked returns True when key exists in Redis."""
        from redis.asyncio import Redis

        session = make_session()
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=1)

        service = self.make_service_with_redis(None, mock_redis)

        jti = "test-jti-revoked"
        result = await service.is_token_revoked(jti)

        assert result is True
        mock_redis.exists.assert_awaited_once_with("auth:blocklist:test-jti-revoked")

    @pytest.mark.asyncio
    async def test_is_token_revoked_false_when_key_absent(self):
        """Test is_token_revoked returns False when key does not exist."""
        from redis.asyncio import Redis

        session = make_session()
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=0)

        service = self.make_service_with_redis(None, mock_redis)

        jti = "test-jti-not-revoked"
        result = await service.is_token_revoked(jti)

        assert result is False
        mock_redis.exists.assert_awaited_once_with("auth:blocklist:test-jti-not-revoked")

    @pytest.mark.asyncio
    async def test_is_token_revoked_false_when_no_redis(self):
        """Test is_token_revoked returns False when Redis is unavailable."""
        session = make_session()
        service = self.make_service_with_redis(None, None)

        result = await service.is_token_revoked("any-jti")

        assert result is False

    @pytest.mark.asyncio
    async def test_is_token_revoked_false_on_redis_error(self, caplog):
        """Test is_token_revoked returns False and logs warning on Redis error."""
        from redis.exceptions import RedisError

        session = make_session()
        mock_redis = AsyncMock()
        mock_redis.exists.side_effect = RedisError("Connection failed")

        service = self.make_service_with_redis(None, mock_redis)

        result = await service.is_token_revoked("test-jti-error")

        assert result is False
        assert "Redis blocklist lookup failed (fail-open)" in caplog.text


class TestLogout:
    def make_service_with_redis(self, session, redis_client=None):
        from app.core.rate_limit import set_rate_limiter
        from app.core.rate_limit import RateLimiter
        from app.main import app

        service = AuthService(session)
        service.users = AsyncMock(spec=UserRepository)

        if redis_client is not None:
            from app.core.rate_limit import RateLimiter
            limiter = RateLimiter(redis_client)
            set_rate_limiter(limiter)
            # Also set app.state.redis for AuthService
            app.state.redis = redis_client
        else:
            set_rate_limiter(None)
            app.state.redis = None

        return service

    @pytest.mark.asyncio
    async def test_logout_calls_revoke_token(self):
        """Test logout calls revoke_token with correct parameters."""
        from redis.asyncio import Redis

        session = make_session()
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        service = self.make_service_with_redis(None, mock_redis)

        jti = "test-jti-logout"
        exp = datetime.now(timezone.utc) + timedelta(hours=1)

        result = await service.logout(jti, exp)

        assert result is True


class TestRegisterInvitationSync:
    def test_register_calls_sync_pending_invitations(self):
        session = make_session()
        service = make_service(session)
        service.users.get_by_email_including_inactive.return_value = None
        data = UserCreate(
            email="newrecruiter@example.com",
            password="password123",
            role=UserRole.RECRUITER,
        )

        user = asyncio.run(service.register_user(data))

        service.workspaces.sync_pending_invitations_for_user.assert_awaited_once_with(
            user
        )

    def test_sync_pending_invitations_calls_notify_idempotently(self):
        from app.services.workspace_service import WorkspaceService
        from app.models import CompanyInvitation, Company
        from app.domain.enums import MembershipRole, InvitationStatus

        session = make_session()
        workspace_service = WorkspaceService(session)
        workspace_service.invitations = AsyncMock()
        workspace_service.notifications = AsyncMock()

        user = make_user()
        user.email = "test@example.com"
        invitation = CompanyInvitation(
            id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            email="test@example.com",
            role=MembershipRole.RECRUITER,
            token_hash="hash",
            status=InvitationStatus.PENDING,
            invited_by_id=uuid.uuid4(),
        )
        invitation.company = Company(id=invitation.company_id, name="Test Co", slug="test-co")
        workspace_service.invitations.list_pending_by_email.return_value = [invitation]

        # Setup savepoint mock
        session.begin_nested.return_value.__aenter__ = AsyncMock()
        session.begin_nested.return_value.__aexit__ = AsyncMock()

        asyncio.run(
            workspace_service.sync_pending_invitations_for_user(user)
        )

        workspace_service.notifications.notify_company_invitation.assert_awaited_once_with(
            user_id=user.id,
            invitation_id=invitation.id,
            company_name="Test Co",
            role_label="Nhà tuyển dụng",
        )

    def test_sync_pending_invitations_swallows_duplicate_key_error(self):
        from app.services.workspace_service import WorkspaceService
        from app.models import CompanyInvitation, Company
        from app.domain.enums import MembershipRole, InvitationStatus
        from sqlalchemy.exc import IntegrityError

        session = make_session()
        workspace_service = WorkspaceService(session)
        workspace_service.invitations = AsyncMock()
        workspace_service.notifications = AsyncMock()
        workspace_service.notifications.notify_company_invitation.side_effect = IntegrityError(
            "statement", {}, Exception("Violation of PRIMARY KEY constraint 'PK_notifications'")
        )

        user = make_user()
        user.email = "test@example.com"
        invitation = CompanyInvitation(
            id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            email="test@example.com",
            role=MembershipRole.RECRUITER,
            token_hash="hash",
            status=InvitationStatus.PENDING,
            invited_by_id=uuid.uuid4(),
        )
        invitation.company = Company(id=invitation.company_id, name="Test Co", slug="test-co")
        workspace_service.invitations.list_pending_by_email.return_value = [invitation]

        session.begin_nested.return_value.__aenter__ = AsyncMock()
        session.begin_nested.return_value.__aexit__ = AsyncMock()

        # Should not raise exception
        asyncio.run(
            workspace_service.sync_pending_invitations_for_user(user)
        )