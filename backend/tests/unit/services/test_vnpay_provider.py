from __future__ import annotations

import hmac
import hashlib
import urllib.parse
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from app.services.payment_providers.vnpay import VNPAYProvider, VIETNAM_TZ


class TestVNPAYProvider:
    """Unit tests for VNPAY provider adapter."""

    @pytest.fixture
    def provider(self) -> VNPAYProvider:
        """Create VNPAY provider with test configuration."""
        with patch("app.services.payment_providers.vnpay.settings") as mock_settings:
            mock_settings.VNPAY_TMN_CODE = "TEST_TMN_CODE"
            mock_settings.VNPAY_HASH_SECRET = "TEST_HASH_SECRET"
            mock_settings.VNPAY_PAYMENT_URL = "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html"
            mock_settings.VNPAY_QUERY_URL = "https://sandbox.vnpayment.vn/merchant_webapi/api/transaction"
            mock_settings.VNPAY_RETURN_URL = "http://localhost:5173/payment-result"
            mock_settings.VNPAY_IPN_URL = "http://localhost:8000/api/v1/payments/vnpay/ipn"
            mock_settings.VNPAY_TIMEOUT = 15
            provider = VNPAYProvider()
        return provider

    def test_build_payment_params_basic(self, provider: VNPAYProvider) -> None:
        """Test basic payment parameter construction."""
        params = provider.build_payment_params(
            amount=100000,
            order_id="VNPAY_20240101_120000_ABCD1234",
            order_info="Test payment",
            client_ip="192.168.1.1",
        )

        assert params["vnp_Version"] == "2.1.0"
        assert params["vnp_Command"] == "pay"
        assert params["vnp_TmnCode"] == "TEST_TMN_CODE"
        assert params["vnp_Amount"] == "10000000"  # 100000 * 100
        assert params["vnp_CurrCode"] == "VND"
        assert params["vnp_IpAddr"] == "192.168.1.1"
        assert params["vnp_Locale"] == "vn"
        assert params["vnp_OrderInfo"] == "Test payment"
        assert params["vnp_OrderType"] == "other"
        assert params["vnp_ReturnUrl"] == "http://localhost:5173/payment-result"
        assert params["vnp_TxnRef"] == "VNPAY_20240101_120000_ABCD1234"
        assert "vnp_CreateDate" in params
        assert "vnp_ExpireDate" in params

    def test_amount_conversion_x100(self, provider: VNPAYProvider) -> None:
        """Test amount is multiplied by 100 for VNPAY."""
        params = provider.build_payment_params(
            amount=50000,
            order_id="TEST_123",
            order_info="Test",
        )
        assert params["vnp_Amount"] == "5000000"

        params = provider.build_payment_params(
            amount=1,
            order_id="TEST_123",
            order_info="Test",
        )
        assert params["vnp_Amount"] == "100"

    def test_sort_params_alphabetical(self, provider: VNPAYProvider) -> None:
        """Test parameters are sorted alphabetically by key."""
        params = {
            "vnp_Z": "z",
            "vnp_A": "a",
            "vnp_M": "m",
        }
        sorted_params = provider._sort_params(params)
        keys = [k for k, _ in sorted_params]
        assert keys == ["vnp_A", "vnp_M", "vnp_Z"]

    def test_generate_secure_hash_deterministic(self, provider: VNPAYProvider) -> None:
        """Test HMAC-SHA512 signature generation is deterministic."""
        params = {
            "vnp_Amount": "10000000",
            "vnp_Command": "pay",
            "vnp_CreateDate": "20240101120000",
            "vnp_CurrCode": "VND",
            "vnp_IpAddr": "192.168.1.1",
            "vnp_Locale": "vn",
            "vnp_OrderInfo": "Test payment",
            "vnp_OrderType": "other",
            "vnp_ReturnUrl": "http://localhost:5173/payment-result",
            "vnp_TmnCode": "TEST_TMN_CODE",
            "vnp_TxnRef": "VNPAY_20240101_120000_ABCD1234",
            "vnp_Version": "2.1.0",
        }

        hash1 = provider.generate_secure_hash(params)
        hash2 = provider.generate_secure_hash(params)

        assert hash1 == hash2
        assert len(hash1) == 128  # SHA512 hex = 128 chars

    def test_generate_secure_hash_matches_manual(self, provider: VNPAYProvider) -> None:
        """Test hash matches manual HMAC-SHA512 calculation."""
        params = {
            "vnp_Amount": "10000000",
            "vnp_Command": "pay",
            "vnp_TmnCode": "TEST_TMN_CODE",
        }

        sorted_params = provider._sort_params(params)
        query_string = "&".join(f"{k}={urllib.parse.quote_plus(str(v))}" for k, v in sorted_params)

        expected = hmac.new(
            b"TEST_HASH_SECRET",
            query_string.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()

        actual = provider.generate_secure_hash(params)
        assert actual == expected

    def test_verify_signature_valid(self, provider: VNPAYProvider) -> None:
        """Test signature verification with valid signature."""
        params = {
            "vnp_Amount": "10000000",
            "vnp_Command": "pay",
            "vnp_TmnCode": "TEST_TMN_CODE",
        }
        secure_hash = provider.generate_secure_hash(params)
        params_with_hash = {**params, "vnp_SecureHash": secure_hash}

        assert provider.verify_signature(params_with_hash) is True

    def test_verify_signature_invalid(self, provider: VNPAYProvider) -> None:
        """Test signature verification fails with invalid signature."""
        params = {
            "vnp_Amount": "10000000",
            "vnp_Command": "pay",
            "vnp_TmnCode": "TEST_TMN_CODE",
            "vnp_SecureHash": "invalid_hash",
        }

        assert provider.verify_signature(params) is False

    def test_verify_signature_missing_hash(self, provider: VNPAYProvider) -> None:
        """Test signature verification fails when hash is missing."""
        params = {
            "vnp_Amount": "10000000",
            "vnp_Command": "pay",
            "vnp_TmnCode": "TEST_TMN_CODE",
        }

        assert provider.verify_signature(params) is False

    def test_verify_signature_excludes_hash_fields(self, provider: VNPAYProvider) -> None:
        """Test that vnp_SecureHash and vnp_SecureHashType are excluded from verification."""
        params = {
            "vnp_Amount": "10000000",
            "vnp_Command": "pay",
            "vnp_TmnCode": "TEST_TMN_CODE",
        }
        secure_hash = provider.generate_secure_hash(params)

        # Add both hash fields
        params_with_hash = {
            **params,
            "vnp_SecureHash": secure_hash,
            "vnp_SecureHashType": "HMACSHA512",
        }

        # Should still verify correctly (excludes both fields)
        assert provider.verify_signature(params_with_hash) is True

    def test_verify_signature_tampered_amount(self, provider: VNPAYProvider) -> None:
        """Test signature verification fails when amount is tampered."""
        params = {
            "vnp_Amount": "10000000",
            "vnp_Command": "pay",
            "vnp_TmnCode": "TEST_TMN_CODE",
        }
        secure_hash = provider.generate_secure_hash(params)

        # Tamper with amount
        params_tampered = {
            **params,
            "vnp_Amount": "20000000",  # Changed amount
            "vnp_SecureHash": secure_hash,
        }

        assert provider.verify_signature(params_tampered) is False

    def test_is_payment_successful_both_zero(self, provider: VNPAYProvider) -> None:
        """Test payment successful when both response code and transaction status are 00."""
        params = {
            "vnp_ResponseCode": "00",
            "vnp_TransactionStatus": "00",
        }
        assert provider.is_payment_successful(params) is True

    def test_is_payment_successful_response_not_zero(self, provider: VNPAYProvider) -> None:
        """Test payment not successful when response code is not 00."""
        params = {
            "vnp_ResponseCode": "24",  # User cancelled
            "vnp_TransactionStatus": "00",
        }
        assert provider.is_payment_successful(params) is False

    def test_is_payment_successful_transaction_not_zero(self, provider: VNPAYProvider) -> None:
        """Test payment not successful when transaction status is not 00."""
        params = {
            "vnp_ResponseCode": "00",
            "vnp_TransactionStatus": "02",  # Error
        }
        assert provider.is_payment_successful(params) is False

    def test_parse_response_code_known_codes(self, provider: VNPAYProvider) -> None:
        """Test parsing known VNPAY response codes."""
        success, msg = provider.parse_response_code("00")
        assert success is True
        assert "thành công" in msg.lower()

        success, msg = provider.parse_response_code("24")
        assert success is False
        assert "hủy" in msg.lower()

        success, msg = provider.parse_response_code("51")
        assert success is False
        assert "số dư" in msg.lower()

    def test_parse_response_code_unknown(self, provider: VNPAYProvider) -> None:
        """Test parsing unknown response code."""
        success, msg = provider.parse_response_code("999")
        assert success is False
        assert "không xác định" in msg.lower()

    def test_parse_transaction_status_known(self, provider: VNPAYProvider) -> None:
        """Test parsing known VNPAY transaction statuses."""
        success, msg = provider.parse_transaction_status("00")
        assert success is True
        assert "thành công" in msg.lower()

        success, msg = provider.parse_transaction_status("02")
        assert success is False
        assert "lỗi" in msg.lower()

    def test_build_payment_url_contains_hash(self, provider: VNPAYProvider) -> None:
        """Test payment URL contains secure hash."""
        params = provider.build_payment_params(
            amount=100000,
            order_id="TEST_123",
            order_info="Test",
        )
        url = provider.build_payment_url(params)

        assert "vnp_SecureHash=" in url
        assert url.startswith("https://sandbox.vnpayment.vn/paymentv2/vpcpay.html?")

    def test_query_params_construction(self, provider: VNPAYProvider) -> None:
        """Test querydr parameter construction uses official v2.1.0 field names."""
        params = provider.build_query_params(
            txn_ref="VNPAY_TEST_123",
            transaction_date="20240101120000",
            client_ip="192.168.1.1",
        )

        # Required official fields present
        assert params["vnp_Version"] == "2.1.0"
        assert params["vnp_Command"] == "querydr"
        assert params["vnp_TmnCode"] == "TEST_TMN_CODE"
        assert params["vnp_TxnRef"] == "VNPAY_TEST_123"
        assert params["vnp_TransactionDate"] == "20240101120000"
        assert params["vnp_IpAddr"] == "192.168.1.1"
        assert params["vnp_OrderInfo"] == "Query transaction VNPAY_TEST_123"
        assert "vnp_CreateDate" in params
        assert "vnp_RequestId" in params

        # Obsolete wire alias must be absent
        assert "vnp_TransDate" not in params

    def test_build_query_request(self, provider: VNPAYProvider) -> None:
        """Test querydr request is HTTP POST JSON with secure hash."""
        params = provider.build_query_params(
            txn_ref="VNPAY_TEST_123",
            transaction_date="20240101120000",
        )
        request = provider.build_query_request(params)

        assert request["url"] == (
            "https://sandbox.vnpayment.vn/merchant_webapi/api/transaction"
        )
        assert request["headers"]["Content-Type"] == "application/json"

        body = request["json"]
        assert "vnp_SecureHash" in body
        assert len(body["vnp_SecureHash"]) == 128  # SHA-512 hex length
        assert body["vnp_Command"] == "querydr"
        assert body["vnp_TxnRef"] == "VNPAY_TEST_123"

        # Hash matches manual pipe-delimited canonical computation
        canonical = "|".join(body[field] for field in provider.QUERYDR_SIGN_FIELDS)
        expected = hmac.new(
            b"TEST_HASH_SECRET",
            canonical.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()
        assert body["vnp_SecureHash"] == expected

    def test_query_request_id_unique(self, provider: VNPAYProvider) -> None:
        """Each QueryDr request must carry a unique vnp_RequestId."""
        params_a = provider.build_query_params(
            txn_ref="VNPAY_TEST_123", transaction_date="20240101120000"
        )
        params_b = provider.build_query_params(
            txn_ref="VNPAY_TEST_123", transaction_date="20240101120000"
        )
        assert params_a["vnp_RequestId"] != params_b["vnp_RequestId"]

    def test_query_secure_hash_pipe_delimited_order(self, provider: VNPAYProvider) -> None:
        """QueryDr signature uses the documented pipe-delimited field order."""
        params = provider.build_query_params(
            txn_ref="VNPAY_TEST_123",
            transaction_date="20240101120000",
            client_ip="192.168.1.1",
        )
        request = provider.build_query_request(params)
        body = request["json"]

        canonical = "|".join(
            body[field]
            for field in provider.QUERYDR_SIGN_FIELDS
        )
        expected = hmac.new(
            b"TEST_HASH_SECRET",
            canonical.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()
        assert body["vnp_SecureHash"] == expected

    def test_query_create_date_uses_vietnam_time(self, provider: VNPAYProvider) -> None:
        """QueryDr vnp_CreateDate must use Vietnam time."""
        fixed = self._fixed_vietnam_now()
        with patch("app.services.payment_providers.vnpay._vietnam_now", return_value=fixed):
            params = provider.build_query_params(
                txn_ref="VNPAY_TEST_123", transaction_date="20240101120000"
            )
        create_dt = datetime.strptime(params["vnp_CreateDate"], "%Y%m%d%H%M%S").replace(
            tzinfo=VIETNAM_TZ
        )
        assert create_dt == fixed
        assert create_dt.utcoffset() == timedelta(hours=7)

    def test_query_transaction_date_preserves_original(self, provider: VNPAYProvider) -> None:
        """QueryDr vnp_TransactionDate must be the original payment creation time, not now."""
        params = provider.build_query_params(
            txn_ref="VNPAY_TEST_123", transaction_date="20240101120000"
        )
        assert params["vnp_TransactionDate"] == "20240101120000"

    def _fixed_vietnam_now(self) -> datetime:
        """Fixed Vietnam (GMT+7) instant near a day boundary for deterministic tests."""
        return datetime(2026, 1, 31, 23, 50, 0, tzinfo=VIETNAM_TZ)

    def test_signature_valid_after_timestamp_change(self, provider: VNPAYProvider) -> None:
        """Signature generation/verification must remain valid with Vietnam timestamps."""
        fixed = self._fixed_vietnam_now()
        with patch("app.services.payment_providers.vnpay._vietnam_now", return_value=fixed):
            params = provider.build_payment_params(
                amount=100000, order_id="X", order_info="T", client_ip="127.0.0.1"
            )
        secure_hash = provider.generate_secure_hash(params)
        assert provider.verify_signature({**params, "vnp_SecureHash": secure_hash}) is True

    # ------------------------------------------------------------------
    # Restored regression tests (removed during the QueryDr edits).
    # Tests 1-7 below are restored verbatim from the committed base version.
    # Tests 8-14 were not recoverable from git history and are reconstructed
    # equivalents with meaningful assertions.
    # ------------------------------------------------------------------

    def _make_provider(
        self, *, timeout: int = 15, secret: str = "TEST_HASH_SECRET"
    ) -> VNPAYProvider:
        """Build a provider with an explicit configured timeout/secret."""
        with patch("app.services.payment_providers.vnpay.settings") as mock_settings:
            mock_settings.VNPAY_TMN_CODE = "TEST_TMN_CODE"
            mock_settings.VNPAY_HASH_SECRET = secret
            mock_settings.VNPAY_PAYMENT_URL = "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html"
            mock_settings.VNPAY_QUERY_URL = "https://sandbox.vnpayment.vn/merchant_webapi/api/transaction"
            mock_settings.VNPAY_RETURN_URL = "http://localhost:5173/payment-result"
            mock_settings.VNPAY_IPN_URL = "http://localhost:8000/api/v1/payments/vnpay/ipn"
            mock_settings.VNPAY_TIMEOUT = timeout
            return VNPAYProvider()

    @staticmethod
    def _parse_vietnam(value: str) -> datetime:
        """Parse a ``YYYYMMDDHHMMSS`` VNPAY date string as Vietnam time."""
        return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=VIETNAM_TZ)

    def test_verify_signature_tampered_order_info(self, provider: VNPAYProvider) -> None:
        """Test signature verification fails when order info is tampered."""
        params = {
            "vnp_Amount": "10000000",
            "vnp_Command": "pay",
            "vnp_TmnCode": "TEST_TMN_CODE",
            "vnp_OrderInfo": "Original order info",
        }
        secure_hash = provider.generate_secure_hash(params)

        # Tamper with order info
        params_tampered = {
            **params,
            "vnp_OrderInfo": "Tampered order info",
            "vnp_SecureHash": secure_hash,
        }

        assert provider.verify_signature(params_tampered) is False

    def test_verify_signature_malformed_hash(self, provider: VNPAYProvider) -> None:
        """Test signature verification fails with malformed hash."""
        params = {
            "vnp_Amount": "10000000",
            "vnp_Command": "pay",
            "vnp_TmnCode": "TEST_TMN_CODE",
            "vnp_SecureHash": "not_a_valid_hex_string_!!!",
        }

        assert provider.verify_signature(params) is False

    def test_verify_signature_empty_hash(self, provider: VNPAYProvider) -> None:
        """Test signature verification fails with empty hash."""
        params = {
            "vnp_Amount": "10000000",
            "vnp_Command": "pay",
            "vnp_TmnCode": "TEST_TMN_CODE",
            "vnp_SecureHash": "",
        }

        assert provider.verify_signature(params) is False

    def test_deterministic_test_vectors(self, provider: VNPAYProvider) -> None:
        """Test deterministic test vectors for signature verification.

        These are fixed input/output pairs that should never change.
        If they change, it indicates a breaking change in signature generation.
        """
        # Test vector 1: Minimal params
        params1 = {
            "vnp_Amount": "10000000",
            "vnp_Command": "pay",
            "vnp_TmnCode": "TEST_TMN_CODE",
        }
        hash1 = provider.generate_secure_hash(params1)
        assert provider.verify_signature({**params1, "vnp_SecureHash": hash1}) is True

        # Test vector 2: Full params
        params2 = {
            "vnp_Amount": "5000000",
            "vnp_Command": "pay",
            "vnp_CreateDate": "20240101120000",
            "vnp_CurrCode": "VND",
            "vnp_IpAddr": "192.168.1.1",
            "vnp_Locale": "vn",
            "vnp_OrderInfo": "Thanh toan goi tuyen dung Test Plan",
            "vnp_OrderType": "other",
            "vnp_ReturnUrl": "http://localhost:5173/payment-result",
            "vnp_TmnCode": "TEST_TMN_CODE",
            "vnp_TxnRef": "VNPAY_20240101_120000_ABCD1234",
            "vnp_Version": "2.1.0",
        }
        hash2 = provider.generate_secure_hash(params2)
        assert provider.verify_signature({**params2, "vnp_SecureHash": hash2}) is True

        # Test vector 3: Different secret produces different hash
        provider2 = self._make_provider(secret="DIFFERENT_SECRET")
        hash2_diff = provider2.generate_secure_hash(params1)
        assert hash2_diff != hash1

    def test_all_vnpay_response_codes_mapped(self, provider: VNPAYProvider) -> None:
        """Test that all documented VNPAY response codes are handled."""
        # Success codes
        assert provider.parse_response_code("00")[0] is True

        # Failure codes - all should return False
        failure_codes = ["07", "09", "10", "11", "12", "13", "24", "51", "65", "75", "79", "99"]
        for code in failure_codes:
            success, _ = provider.parse_response_code(code)
            assert success is False, f"Code {code} should be failure"

        # Unknown code
        success, msg = provider.parse_response_code("999")
        assert success is False
        assert "không xác định" in msg.lower()

    def test_all_vnpay_transaction_statuses_mapped(self, provider: VNPAYProvider) -> None:
        """Test that all documented VNPAY transaction statuses are handled."""
        # Success status
        assert provider.parse_transaction_status("00")[0] is True

        # Failure statuses
        failure_statuses = ["01", "02", "04", "05", "06", "07"]
        for status in failure_statuses:
            success, _ = provider.parse_transaction_status(status)
            assert success is False, f"Status {status} should be failure"

        # Unknown status
        success, msg = provider.parse_transaction_status("99")
        assert success is False
        assert "không xác định" in msg.lower()

    def test_is_payment_successful_requires_both_zero(self, provider: VNPAYProvider) -> None:
        """Test payment is only successful when BOTH response code AND transaction status are 00."""
        # Response 00 + Status 00 = Success
        assert provider.is_payment_successful({"vnp_ResponseCode": "00", "vnp_TransactionStatus": "00"}) is True

        # Response 00 + Status 01 = Fail (not completed)
        assert provider.is_payment_successful({"vnp_ResponseCode": "00", "vnp_TransactionStatus": "01"}) is False

        # Response 00 + Status 02 = Fail (error)
        assert provider.is_payment_successful({"vnp_ResponseCode": "00", "vnp_TransactionStatus": "02"}) is False

        # Response 00 + Status 04 = Fail (reversal)
        assert provider.is_payment_successful({"vnp_ResponseCode": "00", "vnp_TransactionStatus": "04"}) is False

        # Response 07 (suspected fraud) + Status 00 = Fail
        assert provider.is_payment_successful({"vnp_ResponseCode": "07", "vnp_TransactionStatus": "00"}) is False

        # Response 24 (user cancelled) + Status 00 = Fail
        assert provider.is_payment_successful({"vnp_ResponseCode": "24", "vnp_TransactionStatus": "00"}) is False

    # --- Reconstructed tests (8-14): not recoverable from git history ---

    def test_create_date_uses_vietnam_time(self, provider: VNPAYProvider) -> None:
        """PAY vnp_CreateDate must be rendered from Vietnam (GMT+7) time."""
        fixed = self._fixed_vietnam_now()
        with patch("app.services.payment_providers.vnpay._vietnam_now", return_value=fixed):
            params = provider.build_payment_params(
                amount=100000, order_id="TEST_123", order_info="Test"
            )
        create_dt = self._parse_vietnam(params["vnp_CreateDate"])
        assert create_dt == fixed
        assert create_dt.utcoffset() == timedelta(hours=7)

    def test_expire_date_uses_vietnam_time(self, provider: VNPAYProvider) -> None:
        """PAY vnp_ExpireDate must be rendered from Vietnam time plus the timeout."""
        fixed = self._fixed_vietnam_now()
        with patch("app.services.payment_providers.vnpay._vietnam_now", return_value=fixed):
            params = provider.build_payment_params(
                amount=100000, order_id="TEST_123", order_info="Test", expire_minutes=15
            )
        expire_dt = self._parse_vietnam(params["vnp_ExpireDate"])
        assert expire_dt == fixed + timedelta(minutes=15)
        assert expire_dt.utcoffset() == timedelta(hours=7)

    def test_configured_timeout_thirty_minutes(self) -> None:
        """A configured 30-minute timeout is honoured by the PAY request."""
        provider = self._make_provider(timeout=30)
        fixed = self._fixed_vietnam_now()
        with patch("app.services.payment_providers.vnpay._vietnam_now", return_value=fixed):
            params = provider.build_payment_params(
                amount=100000, order_id="TEST_123", order_info="Test"
            )
        create_dt = self._parse_vietnam(params["vnp_CreateDate"])
        expire_dt = self._parse_vietnam(params["vnp_ExpireDate"])
        assert expire_dt - create_dt == timedelta(minutes=30)

    def test_omitting_timeout_uses_provider_timeout(self, provider: VNPAYProvider) -> None:
        """Omitting expire_minutes falls back to the configured provider timeout."""
        fixed = self._fixed_vietnam_now()
        with patch("app.services.payment_providers.vnpay._vietnam_now", return_value=fixed):
            params = provider.build_payment_params(
                amount=100000, order_id="TEST_123", order_info="Test"
            )
        create_dt = self._parse_vietnam(params["vnp_CreateDate"])
        expire_dt = self._parse_vietnam(params["vnp_ExpireDate"])
        assert expire_dt - create_dt == timedelta(minutes=provider.timeout)

    def test_explicit_timeout_overrides_configured(self, provider: VNPAYProvider) -> None:
        """An explicit expire_minutes overrides the configured timeout."""
        fixed = self._fixed_vietnam_now()
        with patch("app.services.payment_providers.vnpay._vietnam_now", return_value=fixed):
            params = provider.build_payment_params(
                amount=100000, order_id="TEST_123", order_info="Test", expire_minutes=45
            )
        create_dt = self._parse_vietnam(params["vnp_CreateDate"])
        expire_dt = self._parse_vietnam(params["vnp_ExpireDate"])
        assert expire_dt - create_dt == timedelta(minutes=45)

    def test_invalid_timeout_rejected(self, provider: VNPAYProvider) -> None:
        """Zero or negative timeouts must be rejected."""
        for invalid in (0, -1, -15):
            with pytest.raises(ValueError):
                provider.build_payment_params(
                    amount=100000,
                    order_id="TEST_123",
                    order_info="Test",
                    expire_minutes=invalid,
                )

    def test_day_rollover(self, provider: VNPAYProvider) -> None:
        """Expiration crossing midnight must roll to the next day correctly."""
        fixed = datetime(2026, 1, 31, 23, 50, 0, tzinfo=VIETNAM_TZ)
        with patch("app.services.payment_providers.vnpay._vietnam_now", return_value=fixed):
            params = provider.build_payment_params(
                amount=100000, order_id="TEST_123", order_info="Test", expire_minutes=15
            )
        assert params["vnp_CreateDate"] == "20260131235000"
        assert params["vnp_ExpireDate"] == "20260201000500"


def _querydr_response(**overrides):
    """A documented QueryDr v2.1.0 response body (unsigned)."""
    body = {
        "vnp_ResponseId": "RID0000000000001",
        "vnp_Command": "querydr",
        "vnp_ResponseCode": "00",
        "vnp_Message": "Query Success",
        "vnp_TmnCode": "TEST_TMN_CODE",
        "vnp_TxnRef": "VNPAY_20240101_120000_ABCD1234",
        "vnp_Amount": "10000000",
        "vnp_BankCode": "NCB",
        "vnp_PayDate": "20240101120030",
        "vnp_TransactionNo": "12345678",
        "vnp_TransactionType": "01",
        "vnp_TransactionStatus": "00",
        "vnp_OrderInfo": "Query transaction VNPAY_20240101_120000_ABCD1234",
    }
    body.update(overrides)
    return body


class TestVNPAYQueryDrResponseHash:
    """Unit tests for QueryDr response checksum generation/verification."""

    @pytest.fixture
    def provider(self) -> VNPAYProvider:
        with patch("app.services.payment_providers.vnpay.settings") as mock_settings:
            mock_settings.VNPAY_TMN_CODE = "TEST_TMN_CODE"
            mock_settings.VNPAY_HASH_SECRET = "TEST_HASH_SECRET"
            mock_settings.VNPAY_PAYMENT_URL = "https://example.test/pay"
            mock_settings.VNPAY_QUERY_URL = "https://example.test/query"
            mock_settings.VNPAY_RETURN_URL = "http://localhost:5173/payment-result"
            mock_settings.VNPAY_IPN_URL = "http://localhost:8000/ipn"
            mock_settings.VNPAY_TIMEOUT = 15
            return VNPAYProvider()

    def test_valid_response_signature_verifies(self, provider: VNPAYProvider) -> None:
        body = _querydr_response()
        body["vnp_SecureHash"] = provider.generate_query_response_secure_hash(body)
        assert provider.verify_query_response_hash(body) is True

    def test_optional_promotion_fields_contribute_empty_segments(
        self, provider: VNPAYProvider
    ) -> None:
        """The documented canonical string keeps empty segments for absent fields."""
        body = _querydr_response()  # no vnp_PromotionCode / vnp_PromotionAmount
        expected_canonical = "|".join(
            [
                body["vnp_ResponseId"],
                body["vnp_Command"],
                body["vnp_ResponseCode"],
                body["vnp_Message"],
                body["vnp_TmnCode"],
                body["vnp_TxnRef"],
                body["vnp_Amount"],
                body["vnp_BankCode"],
                body["vnp_PayDate"],
                body["vnp_TransactionNo"],
                body["vnp_TransactionType"],
                body["vnp_TransactionStatus"],
                body["vnp_OrderInfo"],
                "",
                "",
            ]
        )
        expected = hmac.new(
            b"TEST_HASH_SECRET", expected_canonical.encode("utf-8"), hashlib.sha512
        ).hexdigest()
        assert provider.generate_query_response_secure_hash(body) == expected

    def test_promotion_fields_change_signature(self, provider: VNPAYProvider) -> None:
        without = provider.generate_query_response_secure_hash(_querydr_response())
        with_promo = provider.generate_query_response_secure_hash(
            _querydr_response(vnp_PromotionCode="PROMO1", vnp_PromotionAmount="1000")
        )
        assert without != with_promo

    def test_tampered_field_fails_verification(self, provider: VNPAYProvider) -> None:
        body = _querydr_response()
        body["vnp_SecureHash"] = provider.generate_query_response_secure_hash(body)
        body["vnp_Amount"] = "1"  # tamper after signing
        assert provider.verify_query_response_hash(body) is False

    def test_missing_signature_fails_verification(self, provider: VNPAYProvider) -> None:
        assert provider.verify_query_response_hash(_querydr_response()) is False

    def test_empty_signature_fails_verification(self, provider: VNPAYProvider) -> None:
        body = _querydr_response(vnp_SecureHash="")
        assert provider.verify_query_response_hash(body) is False

    def test_malformed_signature_fails_verification(self, provider: VNPAYProvider) -> None:
        for bad in ("nothex" * 21, "abc", "z" * 128, "0" * 127):
            assert provider.verify_query_response_hash(
                _querydr_response(vnp_SecureHash=bad)
            ) is False

    def test_uppercase_signature_is_accepted(self, provider: VNPAYProvider) -> None:
        body = _querydr_response()
        digest = provider.generate_query_response_secure_hash(body)
        body["vnp_SecureHash"] = digest.upper()
        assert provider.verify_query_response_hash(body) is True

    def test_wrong_secret_fails_verification(self) -> None:
        with patch("app.services.payment_providers.vnpay.settings") as mock_settings:
            mock_settings.VNPAY_TMN_CODE = "TEST_TMN_CODE"
            mock_settings.VNPAY_HASH_SECRET = "WRONG_SECRET"
            mock_settings.VNPAY_PAYMENT_URL = "https://example.test/pay"
            mock_settings.VNPAY_QUERY_URL = "https://example.test/query"
            mock_settings.VNPAY_RETURN_URL = "http://localhost:5173/payment-result"
            mock_settings.VNPAY_IPN_URL = "http://localhost:8000/ipn"
            mock_settings.VNPAY_TIMEOUT = 15
            wrong_provider = VNPAYProvider()

        body = _querydr_response()
        body["vnp_SecureHash"] = wrong_provider.generate_query_response_secure_hash(body)
        with patch("app.services.payment_providers.vnpay.settings") as mock_settings:
            mock_settings.VNPAY_TMN_CODE = "TEST_TMN_CODE"
            mock_settings.VNPAY_HASH_SECRET = "TEST_HASH_SECRET"
            mock_settings.VNPAY_PAYMENT_URL = "https://example.test/pay"
            mock_settings.VNPAY_QUERY_URL = "https://example.test/query"
            mock_settings.VNPAY_RETURN_URL = "http://localhost:5173/payment-result"
            mock_settings.VNPAY_IPN_URL = "http://localhost:8000/ipn"
            mock_settings.VNPAY_TIMEOUT = 15
            real_provider = VNPAYProvider()
        assert real_provider.verify_query_response_hash(body) is False
