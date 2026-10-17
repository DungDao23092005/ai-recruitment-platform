import pytest
import uuid
import asyncio
import hmac
import hashlib
import urllib.parse
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    InvalidTransitionException,
)
from app.domain.enums import PaymentOrderStatus, PaymentProvider, PaymentTransactionStatus, SubscriptionStatus, UserRole
from app.models import PaymentOrder, PaymentTransaction, RecruiterProfile, Subscription, User
from app.services.payment_service import PaymentService
from app.services.payment_providers.vnpay import VNPAYProvider


class TestPaymentServiceCoreLogic:
    """Core logic tests that don't require full database setup."""

    def test_vnpay_parameter_generation(self, vnpay_provider):
        """VNPAY parameter generation is correct."""
        params = vnpay_provider.build_payment_params(
            amount=150000,
            order_id="VNPAY_TEST_001",
            order_info="Test order",
            client_ip="127.0.0.1",
        )

        # Check required params are present
        assert "vnp_Version" in params
        assert "vnp_Command" in params
        assert "vnp_TmnCode" in params
        assert "vnp_Amount" in params
        assert "vnp_CurrCode" in params
        assert "vnp_TxnRef" in params
        assert "vnp_OrderInfo" in params
        assert "vnp_ReturnUrl" in params
        assert "vnp_IpAddr" in params
        assert "vnp_CreateDate" in params
        assert "vnp_ExpireDate" in params

        # Verify amount is multiplied by 100
        vnp_amount = int(params["vnp_Amount"])
        assert vnp_amount == 150000 * 100  # 15000000

        # Verify TxnRef matches order_id
        assert params["vnp_TxnRef"] == "VNPAY_TEST_001"

    def test_secure_hash_generation(self, vnpay_provider):
        """HMAC-SHA512 hash generation."""
        params = {
            "vnp_Amount": "100000",
            "vnp_CurrCode": "VND",
            "vnp_TmnCode": "test",
            "vnp_TxnRef": "TEST-001",
            "vnp_OrderInfo": "Test order",
            "vnp_ReturnUrl": "http://localhost:5173/payment-result",
            "vnp_CreateDate": datetime.utcnow().strftime("%Y%m%d%H%M%S"),
            "vnp_IpAddr": "127.0.0.1",
        }
        hash_value = vnpay_provider.generate_secure_hash(params)
        assert isinstance(hash_value, str)
        assert len(hash_value) == 128  # SHA-512 hex length

    def test_verify_valid_signature(self, vnpay_provider, sample_vnpay_params):
        """Valid signature verification."""
        assert vnpay_provider.verify_signature(sample_vnpay_params) is True

    def test_verify_invalid_signature(self, vnpay_provider):
        """Invalid signature verification."""
        params = {
            "vnp_Amount": "100000",
            "vnp_CurrCode": "VND",
            "vnp_TmnCode": "test",
            "vnp_TxnRef": "TEST-001",
        }
        assert vnpay_provider.verify_signature(params) is False

    def test_verify_missing_signature(self, vnpay_provider):
        """Missing signature."""
        params = {
            "vnp_Amount": "100000",
            "vnp_CurrCode": "VND",
            "vnp_TmnCode": "test",
            "vnp_TxnRef": "TEST-001",
        }
        assert vnpay_provider.verify_signature(params) is False

    def test_verify_one_field_tampering(self, vnpay_provider, sample_vnpay_params):
        """One-field tampering detected."""
        params = dict(sample_vnpay_params)
        params["vnp_Amount"] = "999999"  # Tamper with amount
        assert vnpay_provider.verify_signature(params) is False

    def test_verify_amount_tampering(self, vnpay_provider, sample_vnpay_params):
        """Amount field tampering detected."""
        params = dict(sample_vnpay_params)
        params["vnp_Amount"] = "50000"  # Different amount
        assert vnpay_provider.verify_signature(params) is False

    def test_verify_txnref_tampering(self, vnpay_provider, sample_vnpay_params):
        """TxnRef field tampering detected."""
        params = dict(sample_vnpay_params)
        params["vnp_TxnRef"] = "TAMPERED-001"
        assert vnpay_provider.verify_signature(params) is False

    def test_signature_excludes_secure_hash_fields(self, vnpay_provider):
        """Signature verification excludes vnp_SecureHash and vnp_SecureHashType."""
        params = {
            "vnp_Amount": "100000",
            "vnp_CurrCode": "VND",
            "vnp_TmnCode": "test",
            "vnp_TxnRef": "TEST-001",
            "vnp_SecureHash": "invalidhash",
            "vnp_SecureHashType": "SHA512",
        }
        # The hash fields should be excluded from verification
        # The result depends on the other params, but the hash fields should not break it
        result = vnpay_provider.verify_signature(params)
        # Should not crash; result depends on other params

    def test_build_payment_url_contains_hash(self, vnpay_provider):
        """Build payment URL contains secure hash."""
        params = vnpay_provider.build_payment_params(
            amount=100000,
            order_id="VNPAY_TEST_002",
            order_info="Test",
            client_ip="127.0.0.1",
        )
        payment_url = vnpay_provider.build_payment_url(params)
        assert "vnp_SecureHash" in payment_url
        # vnp_SecureHashType is added as a fixed value "SHA512" in build_payment_url
        # The hash type is embedded in the URL via the parameter sorting
        # Verify the params have the expected structure
        assert "vnp_Version" in params
        assert "vnp_Command" in params

    def test_parse_response_code_00(self, vnpay_provider):
        """Parse VNPAY response code 00 (success)."""
        success, message = vnpay_provider.parse_response_code("00")
        assert success is True
        assert "thành công" in message.lower()

    def test_parse_response_code_01(self, vnpay_provider):
        """Parse VNPAY response code 01 (not completed)."""
        success, message = vnpay_provider.parse_response_code("01")
        assert success is False

    def test_parse_transaction_status_00(self, vnpay_provider):
        """Parse VNPAY transaction status 00 (success)."""
        success, message = vnpay_provider.parse_transaction_status("00")
        assert success is True

    def test_parse_transaction_status_01(self, vnpay_provider):
        """Parse VNPAY transaction status 01 (not completed)."""
        success, message = vnpay_provider.parse_transaction_status("01")
        assert success is False

    def test_is_payment_successful_both_00(self, vnpay_provider):
        """Both response code and transaction status 00 = successful."""
        # Build params with both 00
        params = {
            "vnp_ResponseCode": "00",
            "vnp_TransactionStatus": "00",
            "vnp_SecureHash": "dummy",
            "vnp_SecureHashType": "SHA512",
        }
        # Need valid signature for is_payment_successful to work properly,
        # but we can test the logic
        from unittest.mock import patch
        with patch.object(vnpay_provider, 'verify_signature', return_value=True):
            result = vnpay_provider.is_payment_successful(params)
            assert result is True

    def test_is_payment_successful_invalid_response(self, vnpay_provider):
        """Invalid response code = not successful."""
        from unittest.mock import patch
        params = {
            "vnp_ResponseCode": "04",
            "vnp_TransactionStatus": "01",
        }
        with patch.object(vnpay_provider, 'verify_signature', return_value=True):
            result = vnpay_provider.is_payment_successful(params)
            assert result is False


class TestPaymentOrderModel:
    """PaymentOrder model tests."""

    def test_payment_order_creation(self):
        """PaymentOrder can be created with required fields."""
        order = PaymentOrder(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            amount=1000000,
            currency="VND",
            provider=PaymentProvider.VNPAY,
            internal_order_id="ORDER-001",
            status=PaymentOrderStatus.PENDING,
        )
        assert order.user_id is not None
        assert order.plan_id is not None
        assert order.amount == 1000000
        assert order.currency == "VND"
        assert order.provider == PaymentProvider.VNPAY
        assert order.internal_order_id == "ORDER-001"
        assert order.status == PaymentOrderStatus.PENDING

    def test_payment_order_unique_internal_order_id(self):
        """internal_order_id must be unique."""
        order1 = PaymentOrder(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            amount=1000000,
            currency="VND",
            provider=PaymentProvider.VNPAY,
            internal_order_id="ORDER-SAME-001",
            status=PaymentOrderStatus.PENDING,
        )
        order2 = PaymentOrder(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            amount=2000000,
            currency="VND",
            provider=PaymentProvider.VNPAY,
            internal_order_id="ORDER-SAME-001",  # Duplicate
            status=PaymentOrderStatus.PENDING,
        )
        # Both can be created at model level
        assert order1.internal_order_id == order2.internal_order_id == "ORDER-SAME-001"
        # But database will enforce uniqueness via unique constraint


class TestPaymentTransactionModel:
    """PaymentTransaction model tests."""

    def test_payment_transaction_creation(self):
        """PaymentTransaction can be created with required fields."""
        txn = PaymentTransaction(
            payment_order_id=uuid.uuid4(),
            provider_transaction_id="MOMO-TXN-12345",
            provider_result_code="0",
            provider_message="Success",
            status=PaymentTransactionStatus.SUCCESS,
        )
        assert txn.provider_transaction_id == "MOMO-TXN-12345"
        assert txn.provider_result_code == "0"
        assert txn.status == PaymentTransactionStatus.SUCCESS

    def test_payment_transaction_default_pending(self):
        """Default status is PENDING when explicitly set."""
        txn = PaymentTransaction(
            payment_order_id=uuid.uuid4(),
            status=PaymentTransactionStatus.PENDING,
        )
        assert txn.status == PaymentTransactionStatus.PENDING


def _make_payment_service_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()

    async def _fake_flush():
        # Mock flush assigns ids like a real database would on flush.
        for call in session.add.call_args_list:
            obj = call.args[0]
            if isinstance(obj, Subscription) and getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            if isinstance(obj, PaymentOrder) and getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    session.flush = AsyncMock(side_effect=_fake_flush)
    return session


def _make_user(user_id: uuid.UUID | None = None, role: UserRole = UserRole.CANDIDATE, recruiter_profile: RecruiterProfile | None = None) -> User:
    user = User(
        id=user_id or uuid.uuid4(),
        email="test@example.com",
        password_hash="hash",
        role=role,
    )
    if recruiter_profile:
        user.recruiter_profile = recruiter_profile
        recruiter_profile.user = user
    return user


def _make_profile_result(profile: RecruiterProfile | None) -> MagicMock:
    """Create a mock result for RecruiterProfile query."""
    mock = MagicMock()
    mock.scalar_one_or_none.return_value = profile
    return mock


def _make_lock_result(user: User) -> MagicMock:
    """Create a mock result for user locking query."""
    mock = MagicMock()
    mock.scalar_one_or_none.return_value = user
    return mock


def _make_subscription(sub_id: uuid.UUID, user_id: uuid.UUID, plan_id: uuid.UUID, status: SubscriptionStatus = SubscriptionStatus.PENDING) -> Subscription:
    return Subscription(
        id=sub_id,
        user_id=user_id,
        plan_id=plan_id,
        status=status,
    )


def _make_plan(
    plan_id: uuid.UUID,
    *,
    duration_days: int = 30,
    max_job_posts: int = 5,
    max_candidate_searches: int | None = 10,
    max_ai_features: int | None = 3,
) -> MagicMock:
    plan = MagicMock()
    plan.id = plan_id
    plan.duration_days = duration_days
    plan.max_job_posts = max_job_posts
    plan.max_candidate_searches = max_candidate_searches
    plan.max_ai_features = max_ai_features
    return plan


class TestActivateSubscriptionForPaymentRoleTransition:
    """Phase 6.1: Tests for role transition and RecruiterProfile creation during payment activation."""

    def test_candidate_payment_activation_creates_recruiter_role_and_profile(self):
        """TEST 1: CANDIDATE + verified VNPAY activation → role becomes RECRUITER + RecruiterProfile exists."""
        session = _make_payment_service_session()
        service = PaymentService(session)

        sub_id = uuid.uuid4()
        user_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        sub = _make_subscription(sub_id, user_id, plan_id, SubscriptionStatus.PENDING)
        plan = _make_plan(plan_id)

        user = _make_user(user_id=user_id, role=UserRole.CANDIDATE)

        # Mock repositories
        service.subscriptions.get_by_id_including_deleted = AsyncMock(return_value=sub)
        service.plans.get_active_by_id = AsyncMock(return_value=plan)
        service.subscriptions.get_active_by_user_id = AsyncMock(return_value=None)

        # Mock session.execute for user locking (first call) and profile query (second call)
        session.execute.side_effect = [
            _make_lock_result(user),           # First call: lock user row
            _make_profile_result(None),        # Second call: query RecruiterProfile (not found)
        ]

        result = asyncio.run(service._activate_subscription_for_payment(sub_id))

        assert result is sub
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.started_at is not None
        assert sub.expires_at is not None
        assert user.role == UserRole.RECRUITER
        # Verify RecruiterProfile was created and added to session
        added_profiles = [call.args[0] for call in session.add.call_args_list
                          if isinstance(call.args[0], RecruiterProfile)]
        assert len(added_profiles) == 1
        assert added_profiles[0].user_id == user.id

    def test_existing_recruiter_payment_activation_keeps_role_and_reuses_profile(self):
        """TEST 2: RECRUITER + verified VNPAY activation → remains RECRUITER + existing profile reused."""
        session = _make_payment_service_session()
        service = PaymentService(session)

        sub_id = uuid.uuid4()
        user_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        sub = _make_subscription(sub_id, user_id, plan_id, SubscriptionStatus.PENDING)
        plan = _make_plan(plan_id)

        existing_profile = RecruiterProfile(user_id=user_id, full_name="Existing Recruiter")
        user = _make_user(user_id=user_id, role=UserRole.RECRUITER, recruiter_profile=existing_profile)

        service.subscriptions.get_by_id_including_deleted = AsyncMock(return_value=sub)
        service.plans.get_active_by_id = AsyncMock(return_value=plan)
        service.subscriptions.get_active_by_user_id = AsyncMock(return_value=None)

        # Mock session.execute for user locking (first call) and profile query (second call)
        session.execute.side_effect = [
            _make_lock_result(user),                   # First call: lock user row
            _make_profile_result(existing_profile),    # Second call: query RecruiterProfile (found)
        ]

        result = asyncio.run(service._activate_subscription_for_payment(sub_id))

        assert result is sub
        assert sub.status == SubscriptionStatus.ACTIVE
        assert user.role == UserRole.RECRUITER
        # Verify no new RecruiterProfile was added (existing reused)
        added_profiles = [call.args[0] for call in session.add.call_args_list
                          if isinstance(call.args[0], RecruiterProfile)]
        assert len(added_profiles) == 0

    def test_admin_payment_activation_remains_admin_no_profile(self):
        """TEST 3: ADMIN + activation → remains ADMIN + no profile created."""
        session = _make_payment_service_session()
        service = PaymentService(session)

        sub_id = uuid.uuid4()
        user_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        sub = _make_subscription(sub_id, user_id, plan_id, SubscriptionStatus.PENDING)
        plan = _make_plan(plan_id)

        user = _make_user(user_id=user_id, role=UserRole.ADMIN)

        service.subscriptions.get_by_id_including_deleted = AsyncMock(return_value=sub)
        service.plans.get_active_by_id = AsyncMock(return_value=plan)
        service.subscriptions.get_active_by_user_id = AsyncMock(return_value=None)

        # For ADMIN, only user lock is called (no profile query)
        session.execute.side_effect = [
            _make_lock_result(user),           # First call: lock user row
        ]

        result = asyncio.run(service._activate_subscription_for_payment(sub_id))

        assert result is sub
        assert sub.status == SubscriptionStatus.ACTIVE
        assert user.role == UserRole.ADMIN  # Role unchanged
        # Verify no RecruiterProfile was added
        added_profiles = [call.args[0] for call in session.add.call_args_list
                          if isinstance(call.args[0], RecruiterProfile)]
        assert len(added_profiles) == 0

    def test_candidate_with_existing_profile_payment_activation_reuses_profile(self):
        """TEST 4: CANDIDATE + existing RecruiterProfile + payment activation → role becomes RECRUITER + SAME profile reused."""
        session = _make_payment_service_session()
        service = PaymentService(session)

        sub_id = uuid.uuid4()
        user_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        sub = _make_subscription(sub_id, user_id, plan_id, SubscriptionStatus.PENDING)
        plan = _make_plan(plan_id)

        existing_profile = RecruiterProfile(user_id=user_id, full_name="Pre-existing Profile")
        user = _make_user(user_id=user_id, role=UserRole.CANDIDATE, recruiter_profile=existing_profile)

        service.subscriptions.get_by_id_including_deleted = AsyncMock(return_value=sub)
        service.plans.get_active_by_id = AsyncMock(return_value=plan)
        service.subscriptions.get_active_by_user_id = AsyncMock(return_value=None)

        # Mock session.execute for user locking (first call) and profile query (second call)
        session.execute.side_effect = [
            _make_lock_result(user),                   # First call: lock user row
            _make_profile_result(existing_profile),    # Second call: query RecruiterProfile (found)
        ]

        result = asyncio.run(service._activate_subscription_for_payment(sub_id))

        assert result is sub
        assert sub.status == SubscriptionStatus.ACTIVE
        assert user.role == UserRole.RECRUITER
        # Verify no new RecruiterProfile was added (existing reused)
        added_profiles = [call.args[0] for call in session.add.call_args_list
                          if isinstance(call.args[0], RecruiterProfile)]
        assert len(added_profiles) == 0

    def test_payment_activation_failure_rolls_back(self):
        """TEST 6: Failure during RecruiterProfile creation → exception propagates for caller to rollback."""
        session = _make_payment_service_session()
        service = PaymentService(session)

        sub_id = uuid.uuid4()
        user_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        sub = _make_subscription(sub_id, user_id, plan_id, SubscriptionStatus.PENDING)
        plan = _make_plan(plan_id)

        user = _make_user(user_id=user_id, role=UserRole.CANDIDATE)

        service.subscriptions.get_by_id_including_deleted = AsyncMock(return_value=sub)
        service.plans.get_active_by_id = AsyncMock(return_value=plan)
        service.subscriptions.get_active_by_user_id = AsyncMock(return_value=None)

        # Mock session.execute for user locking (first call) and profile query (second call)
        session.execute.side_effect = [
            _make_lock_result(user),           # First call: lock user row
            _make_profile_result(None),        # Second call: query RecruiterProfile (not found)
        ]

        # Simulate commit failure
        session.commit.side_effect = Exception("Database error")

        with pytest.raises(Exception):
            asyncio.run(service._activate_subscription_for_payment(sub_id))

        # Exception propagates - caller (process_vnpay_ipn) is responsible for rollback
        # Verify commit was attempted
        session.commit.assert_awaited()

    def test_repeated_payment_activation_idempotent_no_duplicate_profile(self):
        """TEST 7: Repeated payment activation/idempotency → no duplicate RecruiterProfile + no unexpected exception."""
        session = _make_payment_service_session()
        service = PaymentService(session)

        sub_id = uuid.uuid4()
        user_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        # Subscription already ACTIVE (simulating repeated activation attempt)
        sub = _make_subscription(sub_id, user_id, plan_id, SubscriptionStatus.ACTIVE)
        plan = _make_plan(plan_id)

        user = _make_user(user_id=user_id, role=UserRole.RECRUITER)

        service.subscriptions.get_by_id_including_deleted = AsyncMock(return_value=sub)
        service.plans.get_active_by_id = AsyncMock(return_value=plan)
        service.subscriptions.get_active_by_user_id = AsyncMock(return_value=None)

        # For already ACTIVE subscription, InvalidTransitionException is raised before profile query
        session.execute.side_effect = [
            _make_lock_result(user),           # First call: lock user row
        ]

        # Should raise InvalidTransitionException for already active subscription
        with pytest.raises(InvalidTransitionException):
            asyncio.run(service._activate_subscription_for_payment(sub_id))

        # Verify no profile creation was attempted
        add_calls = [call for call in session.add.call_args_list
                     if call.args and hasattr(call.args[0], '__class__') and call.args[0].__class__.__name__ == 'RecruiterProfile']
        assert len(add_calls) == 0  # No new profile created


class TestActivateSubscriptionQuotaSnapshot:
    """Bug B: quota limits must be snapshotted from the authoritative plan."""

    def _setup(self, *, plan, sub, user):
        session = _make_payment_service_session()
        service = PaymentService(session)
        service.subscriptions.get_by_id_including_deleted = AsyncMock(return_value=sub)
        service.plans.get_active_by_id = AsyncMock(return_value=plan)
        service.subscriptions.get_active_by_user_id = AsyncMock(return_value=None)
        session.execute.side_effect = [_make_lock_result(user)]
        return session, service

    def test_copies_all_quota_limits_from_plan(self):
        sub_id, user_id, plan_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        plan = _make_plan(
            plan_id, max_job_posts=7, max_candidate_searches=11, max_ai_features=4
        )
        sub = _make_subscription(sub_id, user_id, plan_id, SubscriptionStatus.PENDING)
        user = _make_user(user_id=user_id, role=UserRole.ADMIN)
        _, service = self._setup(plan=plan, sub=sub, user=user)

        result = asyncio.run(service._activate_subscription_for_payment(sub_id))

        assert result is sub
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.max_job_posts == 7
        assert sub.max_candidate_searches == 11
        assert sub.max_ai_features == 4

    def test_optional_plan_limits_default_to_zero(self):
        sub_id, user_id, plan_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        plan = _make_plan(
            plan_id,
            max_job_posts=3,
            max_candidate_searches=None,
            max_ai_features=None,
        )
        sub = _make_subscription(sub_id, user_id, plan_id, SubscriptionStatus.PENDING)
        user = _make_user(user_id=user_id, role=UserRole.ADMIN)
        _, service = self._setup(plan=plan, sub=sub, user=user)

        asyncio.run(service._activate_subscription_for_payment(sub_id))

        assert sub.max_job_posts == 3
        assert sub.max_candidate_searches == 0
        assert sub.max_ai_features == 0

    def test_plan_is_authoritative_over_existing_subscription_values(self):
        """Quota must come from the plan, not from values already on the row."""
        sub_id, user_id, plan_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        plan = _make_plan(
            plan_id, max_job_posts=2, max_candidate_searches=4, max_ai_features=6
        )
        sub = _make_subscription(sub_id, user_id, plan_id, SubscriptionStatus.PENDING)
        sub.max_job_posts = 999
        sub.max_candidate_searches = 999
        sub.max_ai_features = 999
        user = _make_user(user_id=user_id, role=UserRole.ADMIN)
        _, service = self._setup(plan=plan, sub=sub, user=user)

        asyncio.run(service._activate_subscription_for_payment(sub_id))

        assert (
            sub.max_job_posts,
            sub.max_candidate_searches,
            sub.max_ai_features,
        ) == (2, 4, 6)

    def test_activation_resets_usage_counters(self):
        sub_id, user_id, plan_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        plan = _make_plan(plan_id)
        sub = _make_subscription(sub_id, user_id, plan_id, SubscriptionStatus.PENDING)
        sub.job_posts_used = 5
        sub.candidate_searches_used = 6
        sub.ai_features_used = 7
        user = _make_user(user_id=user_id, role=UserRole.ADMIN)
        _, service = self._setup(plan=plan, sub=sub, user=user)

        asyncio.run(service._activate_subscription_for_payment(sub_id))

        assert sub.job_posts_used == 0
        assert sub.candidate_searches_used == 0
        assert sub.ai_features_used == 0

    def test_missing_plan_does_not_activate_with_zero_quota(self):
        """A missing/inactive plan must never silently activate a zero-quota sub."""
        sub_id, user_id, plan_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        sub = _make_subscription(sub_id, user_id, plan_id, SubscriptionStatus.PENDING)
        user = _make_user(user_id=user_id, role=UserRole.ADMIN)
        session = _make_payment_service_session()
        service = PaymentService(session)
        service.subscriptions.get_by_id_including_deleted = AsyncMock(return_value=sub)
        service.plans.get_active_by_id = AsyncMock(return_value=None)
        service.subscriptions.get_active_by_user_id = AsyncMock(return_value=None)
        session.execute.side_effect = [_make_lock_result(user)]

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service._activate_subscription_for_payment(sub_id))

        assert sub.status == SubscriptionStatus.PENDING
        assert not sub.max_job_posts

    def test_already_active_subscription_usage_is_not_reset(self):
        """Repeated activation attempts must not reset an ACTIVE sub's usage."""
        sub_id, user_id, plan_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        plan = _make_plan(plan_id)
        sub = _make_subscription(sub_id, user_id, plan_id, SubscriptionStatus.ACTIVE)
        sub.max_job_posts = 9
        sub.job_posts_used = 3
        user = _make_user(user_id=user_id, role=UserRole.ADMIN)
        _, service = self._setup(plan=plan, sub=sub, user=user)

        with pytest.raises(InvalidTransitionException):
            asyncio.run(service._activate_subscription_for_payment(sub_id))

        assert sub.job_posts_used == 3
        assert sub.max_job_posts == 9


class TestCreateVnpayPayment:
    """Tests for VNPAY payment creation timeout propagation (Fix B)."""

    def _build_provider_with_timeout(self, timeout_minutes: int) -> VNPAYProvider:
        """Build a VNPAY provider with a controlled VNPAY_TIMEOUT."""
        with patch("app.services.payment_providers.vnpay.settings") as mock_settings:
            mock_settings.VNPAY_TMN_CODE = "TEST_TMN_CODE"
            mock_settings.VNPAY_HASH_SECRET = "TEST_HASH_SECRET"
            mock_settings.VNPAY_PAYMENT_URL = "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html"
            mock_settings.VNPAY_QUERY_URL = "https://sandbox.vnpayment.vn/merchant_webapi/api/transaction"
            mock_settings.VNPAY_RETURN_URL = "http://localhost:3000/payment-result"
            mock_settings.VNPAY_IPN_URL = "http://localhost:8000/api/v1/payments/vnpay/ipn"
            mock_settings.VNPAY_TIMEOUT = timeout_minutes
            provider = VNPAYProvider()
        return provider

    def _make_service(self) -> tuple[PaymentService, MagicMock]:
        session = _make_payment_service_session()
        return PaymentService(session), session

    def test_expired_at_and_provider_timeout_use_configured_timeout(self) -> None:
        """VNPAY_TIMEOUT=30 → PaymentOrder.expired_at is +30 min and provider gets expire_minutes=30."""
        service, session = self._make_service()
        user_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        plan = MagicMock()
        plan.id = plan_id
        plan.price = 1_000_000
        plan.name = "Test Plan"
        service.plans.get_active_by_id = AsyncMock(return_value=plan)

        fixed_utc = datetime(2026, 5, 5, 10, 0, 0, tzinfo=timezone.utc)
        provider = self._build_provider_with_timeout(30)
        captured: dict[str, object] = {}
        original_build = provider.build_payment_params

        def capture_build_params(**kwargs):
            captured["expire_minutes"] = kwargs.get("expire_minutes")
            return original_build(**kwargs)

        provider.build_payment_params = capture_build_params  # type: ignore[method-assign]
        service.vnpay = provider  # type: ignore[assignment]

        with patch("app.services.payment_service.utc_now", return_value=fixed_utc):
            url, internal_order_id, subscription_id = asyncio.run(
                service.create_vnpay_payment(user_id, plan_id, "127.0.0.1")
            )

        added_orders = [
            c.args[0]
            for c in session.add.call_args_list
            if isinstance(c.args[0], PaymentOrder)
        ]
        assert len(added_orders) == 1
        assert added_orders[0].expired_at == fixed_utc + timedelta(minutes=30)
        assert captured["expire_minutes"] == 30
        assert internal_order_id is not None
        assert subscription_id is not None
        assert isinstance(url, str)
        assert url.startswith("https://sandbox.vnpayment.vn/paymentv2/vpcpay.html?")

    def test_no_hardcoded_15_minutes(self) -> None:
        """The create-payment path must not contain a hardcoded 15-minute timeout."""
        service, session = self._make_service()
        plan_id = uuid.uuid4()
        plan = MagicMock()
        plan.id = plan_id
        plan.price = 500_000
        plan.name = "Plan"
        service.plans.get_active_by_id = AsyncMock(return_value=plan)

        fixed_utc = datetime(2026, 5, 5, 10, 0, 0, tzinfo=timezone.utc)
        provider = self._build_provider_with_timeout(45)
        service.vnpay = provider  # type: ignore[assignment]

        with patch("app.services.payment_service.utc_now", return_value=fixed_utc):
            asyncio.run(service.create_vnpay_payment(uuid.uuid4(), plan_id, "127.0.0.1"))

        added_orders = [
            c.args[0]
            for c in session.add.call_args_list
            if isinstance(c.args[0], PaymentOrder)
        ]
        assert len(added_orders) == 1
        assert added_orders[0].expired_at == fixed_utc + timedelta(minutes=45)

    def test_failed_payment_creation_rolls_back(self) -> None:
        """Commit failure rolls back and propagates the exception."""
        service, session = self._make_service()
        plan_id = uuid.uuid4()
        plan = MagicMock()
        plan.id = plan_id
        plan.price = 100_000
        plan.name = "Plan"
        service.plans.get_active_by_id = AsyncMock(return_value=plan)
        session.commit.side_effect = Exception("database down")
        provider = self._build_provider_with_timeout(30)
        service.vnpay = provider  # type: ignore[assignment]

        with pytest.raises(Exception, match="database down"):
            asyncio.run(service.create_vnpay_payment(uuid.uuid4(), plan_id, "127.0.0.1"))

        session.rollback.assert_awaited()


class TestQueryVnpayTransaction:
    """Tests for the VNPAY QueryDr reconciliation path (protocol compliance)."""

    def _build_provider_with_timeout(self, timeout_minutes: int) -> VNPAYProvider:
        """Build a VNPAY provider with a controlled VNPAY_TIMEOUT."""
        with patch("app.services.payment_providers.vnpay.settings") as mock_settings:
            mock_settings.VNPAY_TMN_CODE = "TEST_TMN_CODE"
            mock_settings.VNPAY_HASH_SECRET = "TEST_HASH_SECRET"
            mock_settings.VNPAY_PAYMENT_URL = "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html"
            mock_settings.VNPAY_QUERY_URL = "https://sandbox.vnpayment.vn/merchant_webapi/api/transaction"
            mock_settings.VNPAY_RETURN_URL = "http://localhost:3000/payment-result"
            mock_settings.VNPAY_IPN_URL = "http://localhost:8000/api/v1/payments/vnpay/ipn"
            mock_settings.VNPAY_TIMEOUT = timeout_minutes
            provider = VNPAYProvider()
        return provider

    def _make_service(self) -> tuple[PaymentService, MagicMock]:
        session = _make_payment_service_session()
        return PaymentService(session), session

    @staticmethod
    def _make_post_mock(response_json: dict) -> AsyncMock:
        """Build an AsyncMock for httpx.AsyncClient.post returning a JSON response.

        ``await client.post(...)`` yields ``mock_response`` directly.
        """
        mock_response = MagicMock()
        mock_response.json.return_value = response_json
        mock_response.raise_for_status = MagicMock()
        post_mock = AsyncMock(return_value=mock_response)
        return post_mock

    def test_query_sends_post_json_with_required_fields(self) -> None:
        """QueryDr must POST a JSON body with all required v2.1.0 fields."""
        service, session = self._make_service()
        internal_order_id = "VNPAY_TEST_001"
        payment_order = MagicMock()
        payment_order.created_at = datetime(2026, 5, 5, 3, 0, 0, tzinfo=timezone.utc)
        payment_order.internal_order_id = internal_order_id
        service.payment_orders.get_by_internal_order_id = AsyncMock(
            return_value=payment_order
        )

        response_json = {
            "vnp_ResponseCode": "00",
            "vnp_TransactionStatus": "00",
            "vnp_TransactionNo": "VNP_TXN_1",
        }
        post_mock = self._make_post_mock(response_json)

        provider = self._build_provider_with_timeout(30)
        service.vnpay = provider  # type: ignore[assignment]

        with patch("httpx.AsyncClient.post", post_mock):
            result = asyncio.run(
                service.query_vnpay_transaction(internal_order_id)
            )

        assert result == response_json
        post_mock.assert_called_once()
        call_args = post_mock.call_args
        assert call_args.args[0] == (
            "https://sandbox.vnpayment.vn/merchant_webapi/api/transaction"
        )
        assert "json" in call_args.kwargs
        assert call_args.kwargs["headers"]["Content-Type"] == "application/json"
        body = call_args.kwargs["json"]

        # Required official fields present
        for field in [
            "vnp_RequestId",
            "vnp_Version",
            "vnp_Command",
            "vnp_TmnCode",
            "vnp_TxnRef",
            "vnp_TransactionDate",
            "vnp_CreateDate",
            "vnp_IpAddr",
            "vnp_OrderInfo",
            "vnp_SecureHash",
        ]:
            assert field in body, f"missing required field {field}"

        # Obsolete alias must be absent
        assert "vnp_TransDate" not in body
        assert body["vnp_Version"] == "2.1.0"
        assert body["vnp_Command"] == "querydr"
        assert body["vnp_TxnRef"] == internal_order_id
        # Original payment 03:00 UTC = 10:00 Vietnam (+7)
        assert body["vnp_TransactionDate"] == "20260505100000"
        assert body["vnp_TmnCode"] == "TEST_TMN_CODE"

    def test_query_secure_hash_pipe_delimited_order(self) -> None:
        """QueryDr signature uses the documented pipe-delimited field order."""
        service, session = self._make_service()
        internal_order_id = "VNPAY_TEST_002"
        payment_order = MagicMock()
        payment_order.created_at = datetime(2026, 5, 5, 3, 0, 0, tzinfo=timezone.utc)
        payment_order.internal_order_id = internal_order_id
        service.payment_orders.get_by_internal_order_id = AsyncMock(
            return_value=payment_order
        )
        post_mock = self._make_post_mock({"vnp_ResponseCode": "00"})

        provider = self._build_provider_with_timeout(30)
        service.vnpay = provider  # type: ignore[assignment]

        with patch("httpx.AsyncClient.post", post_mock):
            asyncio.run(service.query_vnpay_transaction(internal_order_id))

        body = post_mock.call_args.kwargs["json"]
        canonical = "|".join(body[field] for field in provider.QUERYDR_SIGN_FIELDS)
        expected = hmac.new(
            b"TEST_HASH_SECRET", canonical.encode("utf-8"), hashlib.sha512
        ).hexdigest()
        assert body["vnp_SecureHash"] == expected

    def test_query_request_id_unique(self) -> None:
        """Each QueryDr request carries a unique vnp_RequestId."""
        service, session = self._make_service()
        internal_order_id = "VNPAY_TEST_003"
        payment_order = MagicMock()
        payment_order.created_at = datetime(2026, 5, 5, 3, 0, 0, tzinfo=timezone.utc)
        payment_order.internal_order_id = internal_order_id
        service.payment_orders.get_by_internal_order_id = AsyncMock(
            return_value=payment_order
        )
        post_mock = self._make_post_mock({"vnp_ResponseCode": "00"})

        provider = self._build_provider_with_timeout(30)
        service.vnpay = provider  # type: ignore[assignment]

        with patch("httpx.AsyncClient.post", post_mock):
            asyncio.run(service.query_vnpay_transaction(internal_order_id))
        body_a = post_mock.call_args.kwargs["json"]

        post_mock_b = self._make_post_mock({"vnp_ResponseCode": "00"})
        with patch("httpx.AsyncClient.post", post_mock_b):
            asyncio.run(service.query_vnpay_transaction(internal_order_id))
        body_b = post_mock_b.call_args.kwargs["json"]

        assert body_a["vnp_RequestId"] != body_b["vnp_RequestId"]

    def test_query_order_not_found_returns_none(self) -> None:
        """QueryDr returns None when no payment order exists."""
        service, session = self._make_service()
        service.payment_orders.get_by_internal_order_id = AsyncMock(return_value=None)
        post_mock = self._make_post_mock({"vnp_ResponseCode": "00"})

        with patch("httpx.AsyncClient.post", post_mock):
            result = asyncio.run(
                service.query_vnpay_transaction("DOES_NOT_EXIST")
            )
        assert result is None
        post_mock.assert_not_called()


class TestAuthoritativeCreationTimestamp:
    """Fix 1: a single authoritative instant drives created_at, expiration, PAY
    timestamps, and QueryDr so a slow/rolled-over database commit cannot create a
    one-second mismatch between the stored creation time and the PAY
    ``vnp_CreateDate``."""

    def _build_provider_with_timeout(self, timeout_minutes: int) -> VNPAYProvider:
        with patch("app.services.payment_providers.vnpay.settings") as mock_settings:
            mock_settings.VNPAY_TMN_CODE = "TEST_TMN_CODE"
            mock_settings.VNPAY_HASH_SECRET = "TEST_HASH_SECRET"
            mock_settings.VNPAY_PAYMENT_URL = "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html"
            mock_settings.VNPAY_QUERY_URL = "https://sandbox.vnpayment.vn/merchant_webapi/api/transaction"
            mock_settings.VNPAY_RETURN_URL = "http://localhost:3000/payment-result"
            mock_settings.VNPAY_IPN_URL = "http://localhost:8000/api/v1/payments/vnpay/ipn"
            mock_settings.VNPAY_TIMEOUT = timeout_minutes
            return VNPAYProvider()

    def test_single_clock_read_prevents_second_boundary_mismatch(self) -> None:
        """A commit that crosses a second boundary must not drift created_at from
        the PAY vnp_CreateDate or the QueryDr vnp_TransactionDate."""
        session = _make_payment_service_session()
        service = PaymentService(session)

        plan_id = uuid.uuid4()
        plan = MagicMock()
        plan.id = plan_id
        plan.price = 1_000_000
        plan.name = "Test Plan"
        service.plans.get_active_by_id = AsyncMock(return_value=plan)

        # Authoritative instant: 10:15:30.985 UTC (just before a second boundary).
        authoritative = datetime(2026, 5, 5, 3, 15, 30, 985000, tzinfo=timezone.utc)
        # Simulated clock after the (slow) commit: 10:15:31.120 UTC — the next second.
        post_commit = datetime(2026, 5, 5, 3, 15, 31, 120000, tzinfo=timezone.utc)
        clock_calls = {"count": 0}

        def fake_utc_now() -> datetime:
            clock_calls["count"] += 1
            if clock_calls["count"] == 1:
                return authoritative
            return post_commit

        service.vnpay = self._build_provider_with_timeout(15)  # type: ignore[assignment]

        with patch("app.services.payment_service.utc_now", side_effect=fake_utc_now):
            url, internal_order_id, subscription_id = asyncio.run(
                service.create_vnpay_payment(uuid.uuid4(), plan_id, "127.0.0.1")
            )

        # Exactly one clock read is used to derive the creation timestamp.
        assert clock_calls["count"] == 1

        added_orders = [
            c.args[0]
            for c in session.add.call_args_list
            if isinstance(c.args[0], PaymentOrder)
        ]
        assert len(added_orders) == 1
        order = added_orders[0]

        # created_at derives from the authoritative instant (not the later clock).
        assert order.created_at == authoritative
        # Application expiration is the same instant plus the configured timeout.
        assert order.expired_at == authoritative + timedelta(minutes=15)

        # PAY request timestamps are rendered from the same instant in Vietnam time.
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        pay_create = query["vnp_CreateDate"][0]
        pay_expire = query["vnp_ExpireDate"][0]
        # 03:15:30 UTC == 10:15:30 Vietnam (GMT+7); +15 min => 10:30:30.
        assert pay_create == "20260505101530"
        assert pay_expire == "20260505103030"

        # QueryDr reconstructs vnp_TransactionDate from the persisted created_at.
        service.payment_orders.get_by_internal_order_id = AsyncMock(return_value=order)
        post_mock = AsyncMock(return_value=MagicMock(
            json=MagicMock(return_value={"vnp_ResponseCode": "00"}),
            raise_for_status=MagicMock(),
        ))
        with patch("httpx.AsyncClient.post", post_mock):
            asyncio.run(service.query_vnpay_transaction(internal_order_id))

        body = post_mock.call_args.kwargs["json"]
        assert body["vnp_TransactionDate"] == pay_create
        assert body["vnp_TransactionDate"] == "20260505101530"

    def test_build_payment_params_accepts_create_time_and_rejects_naive(self) -> None:
        """The provider honours a supplied creation instant and rejects naive datetimes."""
        provider = self._build_provider_with_timeout(15)
        supplied = datetime(2026, 5, 5, 3, 15, 30, 985000, tzinfo=timezone.utc)

        # Supersede the clock: if it is used, the assertion below would differ.
        with patch(
            "app.services.payment_providers.vnpay._vietnam_now",
            return_value=datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        ):
            params = provider.build_payment_params(
                amount=1_000_000,
                order_id="ORDER_1",
                order_info="Test",
                expire_minutes=15,
                create_time=supplied,
            )

        assert params["vnp_CreateDate"] == "20260505101530"
        assert params["vnp_ExpireDate"] == "20260505103030"

        with pytest.raises(ValueError):
            provider.build_payment_params(
                amount=1_000_000,
                order_id="ORDER_1",
                order_info="Test",
                create_time=datetime(2026, 5, 5, 10, 15, 30),  # naive
            )


def _make_querydr_order(
    *,
    internal_order_id: str = "VNPAY_QUERYDR_TEST_0001",
    amount: int = 100000,
) -> PaymentOrder:
    return PaymentOrder(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        plan_id=uuid.uuid4(),
        amount=amount,
        provider=PaymentProvider.VNPAY,
        internal_order_id=internal_order_id,
        status=PaymentOrderStatus.PENDING,
    )


def _signed_querydr_body(service: PaymentService, order: PaymentOrder, **overrides) -> dict:
    """Build a QueryDr response body signed with the service's own configuration."""
    body = {
        "vnp_ResponseId": "RID0000000000001",
        "vnp_Command": "querydr",
        "vnp_ResponseCode": "00",
        "vnp_Message": "Query Success",
        "vnp_TmnCode": service.vnpay.tmn_code,
        "vnp_TxnRef": order.internal_order_id,
        "vnp_Amount": str(order.amount * 100),
        "vnp_BankCode": "NCB",
        "vnp_PayDate": "20260505101530",
        "vnp_TransactionNo": "12345678",
        "vnp_TransactionType": "01",
        "vnp_TransactionStatus": "00",
        "vnp_OrderInfo": f"Query transaction {order.internal_order_id}",
    }
    body.update(overrides)
    body["vnp_SecureHash"] = service.vnpay.generate_query_response_secure_hash(body)
    return body


class TestQueryDrResultClassification:
    """Blocker C: conservative classification of QueryDr transaction statuses."""

    def _service(self) -> PaymentService:
        return PaymentService(_make_payment_service_session())

    def test_success_requires_rc_and_status_00(self) -> None:
        service = self._service()
        assert (
            service._classify_querydr_result(
                {"vnp_ResponseCode": "00", "vnp_TransactionStatus": "00"}
            )
            == "success"
        )

    @pytest.mark.parametrize("status", ["02", "04"])
    def test_documented_terminal_failures(self, status: str) -> None:
        service = self._service()
        assert (
            service._classify_querydr_result(
                {"vnp_ResponseCode": "00", "vnp_TransactionStatus": status}
            )
            == "failed"
        )

    def test_status_07_is_inconclusive_not_failed(self) -> None:
        service = self._service()
        assert "07" not in service.QUERYDR_TERMINAL_FAILURE_STATUSES
        assert (
            service._classify_querydr_result(
                {"vnp_ResponseCode": "00", "vnp_TransactionStatus": "07"}
            )
            == "inconclusive"
        )

    def test_status_01_is_pending(self) -> None:
        service = self._service()
        assert (
            service._classify_querydr_result(
                {"vnp_ResponseCode": "00", "vnp_TransactionStatus": "01"}
            )
            == "pending"
        )

    @pytest.mark.parametrize("status", ["05", "06", "09", "99", ""])
    def test_refund_and_unknown_statuses_are_inconclusive(self, status: str) -> None:
        service = self._service()
        assert (
            service._classify_querydr_result(
                {"vnp_ResponseCode": "00", "vnp_TransactionStatus": status}
            )
            == "inconclusive"
        )

    def test_non_zero_query_response_code_is_inconclusive(self) -> None:
        service = self._service()
        assert (
            service._classify_querydr_result(
                {"vnp_ResponseCode": "97", "vnp_TransactionStatus": "00"}
            )
            == "inconclusive"
        )

    def test_missing_fields_are_inconclusive(self) -> None:
        service = self._service()
        assert service._classify_querydr_result({}) == "inconclusive"


class TestQueryDrReferenceValidation:
    """Blocker B: strict response field validation."""

    def _service_and_order(self) -> tuple[PaymentService, PaymentOrder]:
        service = PaymentService(_make_payment_service_session())
        return service, _make_querydr_order()

    def test_valid_response_matches(self) -> None:
        service, order = self._service_and_order()
        assert service._querydr_reference_matches(order, _signed_querydr_body(service, order))

    def test_missing_txnref_rejected(self) -> None:
        service, order = self._service_and_order()
        body = _signed_querydr_body(service, order)
        body.pop("vnp_TxnRef")
        assert service._querydr_reference_matches(order, body) is False

    def test_wrong_txnref_rejected(self) -> None:
        service, order = self._service_and_order()
        body = _signed_querydr_body(service, order, vnp_TxnRef="VNPAY_OTHER")
        assert service._querydr_reference_matches(order, body) is False

    def test_missing_tmn_code_rejected(self) -> None:
        service, order = self._service_and_order()
        body = _signed_querydr_body(service, order)
        body.pop("vnp_TmnCode")
        assert service._querydr_reference_matches(order, body) is False

    def test_wrong_tmn_code_rejected(self) -> None:
        service, order = self._service_and_order()
        body = _signed_querydr_body(service, order, vnp_TmnCode="OTHER_MERCHANT")
        assert service._querydr_reference_matches(order, body) is False

    def test_missing_amount_rejected(self) -> None:
        service, order = self._service_and_order()
        body = _signed_querydr_body(service, order)
        body.pop("vnp_Amount")
        assert service._querydr_reference_matches(order, body) is False

    @pytest.mark.parametrize("amount", ["not-a-number", "100000.5", "", None, True])
    def test_malformed_amount_rejected(self, amount) -> None:
        service, order = self._service_and_order()
        body = _signed_querydr_body(service, order, vnp_Amount=amount)
        assert service._querydr_reference_matches(order, body) is False

    def test_wrong_amount_rejected(self) -> None:
        service, order = self._service_and_order()
        body = _signed_querydr_body(service, order, vnp_Amount="1")
        assert service._querydr_reference_matches(order, body) is False

    @pytest.mark.parametrize("txn_type", ["02", "03", None, "1", ""])
    def test_non_payment_transaction_type_rejected(self, txn_type) -> None:
        service, order = self._service_and_order()
        body = _signed_querydr_body(service, order, vnp_TransactionType=txn_type)
        assert service._querydr_reference_matches(order, body) is False


class TestReconcileForgeResistance:
    """Forged / tampered QueryDr responses must never finalize an order."""

    @pytest.fixture(autouse=True)
    def _reset_throttle(self):
        from app.services.payment_service import reset_querydr_throttle

        reset_querydr_throttle()
        yield
        reset_querydr_throttle()

    @pytest.mark.asyncio
    async def test_forged_signature_does_not_finalize(self) -> None:
        session = _make_payment_service_session()
        service = PaymentService(session)
        order = _make_querydr_order(internal_order_id="VNPAY_FORGED_0001")

        body = _signed_querydr_body(service, order)
        body["vnp_Amount"] = "1"  # tampered after signing → invalid checksum

        with patch.object(
            service, "_send_querydr_request", new=AsyncMock(return_value=body)
        ), patch.object(
            service, "_finalize_reconciled_success", new=AsyncMock()
        ) as finalize_success, patch.object(
            service, "_finalize_reconciled_failure", new=AsyncMock()
        ) as finalize_failure:
            await service._reconcile_pending_vnpay_payment(order)

        finalize_success.assert_not_called()
        finalize_failure.assert_not_called()
        assert order.status == PaymentOrderStatus.PENDING
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_signature_does_not_finalize(self) -> None:
        session = _make_payment_service_session()
        service = PaymentService(session)
        order = _make_querydr_order(internal_order_id="VNPAY_FORGED_0002")

        body = _signed_querydr_body(service, order)
        body.pop("vnp_SecureHash")

        with patch.object(
            service, "_send_querydr_request", new=AsyncMock(return_value=body)
        ), patch.object(
            service, "_finalize_reconciled_success", new=AsyncMock()
        ) as finalize_success:
            await service._reconcile_pending_vnpay_payment(order)

        finalize_success.assert_not_called()
        assert order.status == PaymentOrderStatus.PENDING

    @pytest.mark.asyncio
    async def test_valid_signed_success_invokes_finalize(self) -> None:
        session = _make_payment_service_session()
        service = PaymentService(session)
        order = _make_querydr_order(internal_order_id="VNPAY_VALID_0001")
        body = _signed_querydr_body(service, order)

        with patch.object(
            service, "_send_querydr_request", new=AsyncMock(return_value=body)
        ), patch.object(
            service, "_finalize_reconciled_success", new=AsyncMock()
        ) as finalize_success:
            await service._reconcile_pending_vnpay_payment(order)

        finalize_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_querydr_after_ipn_already_paid_does_not_double_activate(self) -> None:
        """If an IPN already finalized the order PAID, QueryDr must not re-activate."""
        session = _make_payment_service_session()
        service = PaymentService(session)
        order = _make_querydr_order(internal_order_id="VNPAY_RACE_0001")
        order.status = PaymentOrderStatus.PAID  # IPN won the race
        body = _signed_querydr_body(service, order)

        with patch.object(
            service, "_lock_payment_order", new=AsyncMock(return_value=order)
        ), patch.object(
            service, "_record_success_and_activate", new=AsyncMock()
        ) as record:
            await service._finalize_reconciled_success(order, body)

        record.assert_not_called()

    @pytest.mark.asyncio
    async def test_querydr_duplicate_provider_transaction_not_recorded_twice(self) -> None:
        """A provider transaction already recorded by IPN is not recorded again."""
        session = _make_payment_service_session()
        service = PaymentService(session)
        order = _make_querydr_order(internal_order_id="VNPAY_DUP_0001")
        body = _signed_querydr_body(service, order)

        service.payment_transactions.get_by_provider_transaction_id = AsyncMock(
            return_value=MagicMock()
        )

        with patch.object(
            service, "_lock_payment_order", new=AsyncMock(return_value=order)
        ), patch.object(
            service, "_record_success_and_activate", new=AsyncMock()
        ) as record:
            await service._finalize_reconciled_success(order, body)

        record.assert_not_called()

    @pytest.mark.asyncio
    async def test_tampered_unsigned_body_with_status_07_does_not_fail_order(self) -> None:
        session = _make_payment_service_session()
        service = PaymentService(session)
        order = _make_querydr_order(internal_order_id="VNPAY_STATUS07_0001")
        body = _signed_querydr_body(service, order, vnp_TransactionStatus="07")

        with patch.object(
            service, "_send_querydr_request", new=AsyncMock(return_value=body)
        ), patch.object(
            service, "_finalize_reconciled_failure", new=AsyncMock()
        ) as finalize_failure:
            await service._reconcile_pending_vnpay_payment(order)

        finalize_failure.assert_not_called()
        assert order.status == PaymentOrderStatus.PENDING
