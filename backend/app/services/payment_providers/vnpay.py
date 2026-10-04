from __future__ import annotations

import hmac
import hashlib
import urllib.parse
from datetime import datetime
from typing import Any

from app.core.config import settings


class VNPAYProvider:
    """VNPAY Payment Provider Adapter.

    Handles VNPAY-specific concerns:
    - Parameter construction
    - Checksum generation and verification
    - Payment URL creation
    - Provider-specific mapping
    """

    def __init__(self) -> None:
        self.tmn_code = settings.VNPAY_TMN_CODE
        self.hash_secret = settings.VNPAY_HASH_SECRET
        self.payment_url = settings.VNPAY_PAYMENT_URL
        self.query_url = settings.VNPAY_QUERY_URL
        self.return_url = settings.VNPAY_RETURN_URL
        self.ipn_url = settings.VNPAY_IPN_URL
        self.timeout = settings.VNPAY_TIMEOUT

    def _get_client_ip(self, request_headers: dict[str, str] | None = None) -> str:
        """Extract client IP from request headers or use a default."""
        if request_headers:
            x_forwarded_for = request_headers.get("x-forwarded-for")
            if x_forwarded_for:
                return x_forwarded_for.split(",")[0].strip()
            x_real_ip = request_headers.get("x-real-ip")
            if x_real_ip:
                return x_real_ip
        return "127.0.0.1"

    def build_payment_params(
        self,
        *,
        amount: int,
        order_id: str,
        order_info: str,
        client_ip: str | None = None,
        locale: str = "vn",
        order_type: str = "other",
        return_url: str | None = None,
        ipn_url: str | None = None,
        expire_minutes: int = 15,
    ) -> dict[str, str]:
        """Build VNPAY payment parameters according to current specification.

        Args:
            amount: Amount in VND (smallest unit, will be multiplied by 100)
            order_id: Merchant transaction reference (vnp_TxnRef)
            order_info: Order description
            client_ip: Client IP address
            locale: Language locale (vn/en)
            order_type: Order type code
            return_url: Override return URL
            ipn_url: Override IPN URL
            expire_minutes: Payment expiration in minutes

        Returns:
            Dictionary of VNPAY parameters (without vnp_SecureHash)
        """
        now = datetime.utcnow()
        create_date = now.strftime("%Y%m%d%H%M%S")
        from datetime import timedelta
        expire_date = (now + timedelta(minutes=expire_minutes)).strftime("%Y%m%d%H%M%S")

        params = {
            "vnp_Version": "2.1.0",
            "vnp_Command": "pay",
            "vnp_TmnCode": self.tmn_code,
            "vnp_Amount": str(amount * 100),
            "vnp_CreateDate": create_date,
            "vnp_CurrCode": "VND",
            "vnp_IpAddr": client_ip or "127.0.0.1",
            "vnp_Locale": locale,
            "vnp_OrderInfo": order_info,
            "vnp_OrderType": order_type,
            "vnp_ReturnUrl": return_url or self.return_url,
            "vnp_TxnRef": order_id,
            "vnp_ExpireDate": expire_date,
        }

        return params

    def _sort_params(self, params: dict[str, str]) -> list[tuple[str, str]]:
        """Sort parameters alphabetically by key for canonicalization."""
        return sorted(params.items(), key=lambda x: x[0])

    def _build_query_string(self, params: list[tuple[str, str]]) -> str:
        """Build query string from sorted parameters using VNPAY encoding."""
        return "&".join(f"{k}={urllib.parse.quote_plus(str(v))}" for k, v in params)

    def generate_secure_hash(self, params: dict[str, str]) -> str:
        """Generate HMAC-SHA512 secure hash for VNPAY request.

        Args:
            params: Payment parameters (without vnp_SecureHash and vnp_SecureHashType)

        Returns:
            Hex-encoded HMAC-SHA512 hash
        """
        sorted_params = self._sort_params(params)
        query_string = self._build_query_string(sorted_params)
        hash_value = hmac.new(
            self.hash_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()
        return hash_value

    def build_payment_url(self, params: dict[str, str]) -> str:
        """Build complete VNPAY payment URL with secure hash.

        Args:
            params: Payment parameters (without vnp_SecureHash)

        Returns:
            Complete payment URL for redirect
        """
        secure_hash = self.generate_secure_hash(params)
        params_with_hash = {**params, "vnp_SecureHash": secure_hash}
        sorted_params = self._sort_params(params_with_hash)
        query_string = self._build_query_string(sorted_params)
        return f"{self.payment_url}?{query_string}"

    def verify_signature(self, params: dict[str, str]) -> bool:
        """Verify VNPAY callback signature.

        Args:
            params: Callback parameters including vnp_SecureHash

        Returns:
            True if signature is valid
        """
        received_hash = params.get("vnp_SecureHash", "")
        if not received_hash:
            return False

        # Exclude signature fields from verification
        verify_params = {
            k: v for k, v in params.items()
            if k not in ("vnp_SecureHash", "vnp_SecureHashType")
        }

        expected_hash = self.generate_secure_hash(verify_params)
        return hmac.compare_digest(expected_hash, received_hash)

    def build_query_params(
        self,
        *,
        txn_ref: str,
        transaction_date: str,
        client_ip: str | None = None,
    ) -> dict[str, str]:
        """Build VNPAY querydr (transaction query) parameters.

        Args:
            txn_ref: Merchant transaction reference
            transaction_date: Transaction date in YYYYMMDDHHMMSS format
            client_ip: Client IP address

        Returns:
            Dictionary of query parameters (without vnp_SecureHash)
        """
        params = {
            "vnp_Version": "2.1.0",
            "vnp_Command": "querydr",
            "vnp_TmnCode": self.tmn_code,
            "vnp_TxnRef": txn_ref,
            "vnp_OrderInfo": f"Query transaction {txn_ref}",
            "vnp_TransDate": transaction_date,
            "vnp_CreateDate": datetime.utcnow().strftime("%Y%m%d%H%M%S"),
            "vnp_IpAddr": client_ip or "127.0.0.1",
        }
        return params

    def build_query_url(self, params: dict[str, str]) -> str:
        """Build VNPAY query API URL with secure hash.

        Args:
            params: Query parameters (without vnp_SecureHash)

        Returns:
            Complete query URL
        """
        secure_hash = self.generate_secure_hash(params)
        params_with_hash = {**params, "vnp_SecureHash": secure_hash}
        sorted_params = self._sort_params(params_with_hash)
        query_string = self._build_query_string(sorted_params)
        return f"{self.query_url}?{query_string}"

    def parse_response_code(self, response_code: str) -> tuple[bool, str]:
        """Parse VNPAY response code into success status and message.

        Args:
            response_code: VNPAY response code (vnp_ResponseCode)

        Returns:
            Tuple of (is_success, message)
        """
        response_codes = {
            "00": (True, "Giao dịch thành công"),
            "07": (False, "Trừ tiền thành công. Giao dịch bị nghi ngờ (liên quan tới gian lột, bất thường)"),
            "09": (False, "Giao dịch không thành công do: Thẻ/Tài khoản của khách hàng chưa đăng ký dịch vụ InternetBanking tại ngân hàng"),
            "10": (False, "Giao dịch không thành công do: Khách hàng xác thực thông tin thẻ/tài khoản không đúng quá 3 lần"),
            "11": (False, "Giao dịch không thành công do: Đã hết hạn chờ thanh toán. Xin quý khách vui lòng thực hiện lại giao dịch"),
            "12": (False, "Giao dịch không thành công do: Thẻ/Tài khoản của khách hàng bị khóa"),
            "13": (False, "Giao dịch không thành công do Quý khách nhập sai mật khẩu xác thực giao dịch (OTP). Xin quý khách vui lòng thực hiện lại giao dịch"),
            "24": (False, "Giao dịch không thành công do: Khách hàng hủy giao dịch"),
            "51": (False, "Giao dịch không thành công do: Tài khoản của quý khách không đủ số dư để thực hiện giao dịch"),
            "65": (False, "Giao dịch không thành công do: Tài khoản của Quý khách đã vượt quá hạn mức giao dịch trong ngày"),
            "75": (False, "Ngân hàng thanh toán đang bảo trì"),
            "79": (False, "Giao dịch không thành công do: KH nhập sai mật khẩu thanh toán quá số lần quy định"),
            "99": (False, "Các lỗi khác (lỗi còn lại, không có trong danh sách mã lỗi đã liệt kê)"),
        }
        return response_codes.get(response_code, (False, f"Mã phản hồi không xác định: {response_code}"))

    def parse_transaction_status(self, transaction_status: str) -> tuple[bool, str]:
        """Parse VNPAY transaction status.

        Args:
            transaction_status: VNPAY transaction status (vnp_TransactionStatus)

        Returns:
            Tuple of (is_success, message)
        """
        statuses = {
            "00": (True, "Giao dịch thành công"),
            "01": (False, "Giao dịch chưa hoàn tất"),
            "02": (False, "Giao dịch lỗi"),
            "04": (False, "Giao dịch đảo (Khách hàng đã bị trừ tiền tại Ngân hàng nhưng GSN tại VNPAY không thành công)"),
            "05": (False, "VNPAY đang xử lý giao dịch này (Giao dịch hoàn tiền một phần)"),
            "06": (False, "VNPAY đã gửi yêu cầu hoàn tiền sang Ngân hàng (Giao dịch hoàn tiền một phần)"),
            "07": (False, "Giao dịch bị hủy"),
        }
        return statuses.get(transaction_status, (False, f"Trạng thái giao dịch không xác định: {transaction_status}"))

    def is_payment_successful(self, params: dict[str, str]) -> bool:
        """Determine if payment was successful based on VNPAY callback parameters.

        Args:
            params: Callback parameters from VNPAY

        Returns:
            True if both response code and transaction status indicate success
        """
        response_code = params.get("vnp_ResponseCode", "")
        transaction_status = params.get("vnp_TransactionStatus", "")

        response_success, _ = self.parse_response_code(response_code)
        transaction_success, _ = self.parse_transaction_status(transaction_status)

        return response_success and transaction_success