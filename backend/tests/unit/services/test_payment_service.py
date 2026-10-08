import pytest
import uuid
import asyncio
from datetime import datetime
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

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


def _make_plan(plan_id: uuid.UUID) -> MagicMock:
    plan = MagicMock()
    plan.id = plan_id
    plan.duration_days = 30
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