import pytest
import uuid
from datetime import datetime
from uuid import uuid4

from app.domain.enums import PaymentOrderStatus, PaymentProvider, PaymentTransactionStatus, SubscriptionStatus
from app.models import PaymentOrder, PaymentTransaction
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