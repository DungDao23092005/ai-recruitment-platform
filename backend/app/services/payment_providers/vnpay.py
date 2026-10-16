from __future__ import annotations

import hmac
import hashlib
import urllib.parse
import uuid
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import settings

VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _vietnam_now() -> datetime:
    """Current time in Vietnam (GMT+7), timezone-aware."""
    return datetime.now(VIETNAM_TZ)


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
        expire_minutes: int | None = None,
        create_time: datetime | None = None,
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
            expire_minutes: Payment expiration in minutes. When omitted, the
                provider's configured ``self.timeout`` (from ``VNPAY_TIMEOUT``)
                is used. Must be a positive integer.
            create_time: Authoritative timezone-aware creation instant. When
                supplied, it is used (converted to Vietnam time) for both
                ``vnp_CreateDate`` and ``vnp_ExpireDate`` so that the PAY
                request timestamp matches the persisted
                ``PaymentOrder.created_at`` exactly. When omitted, the
                provider reads the current Vietnam time instead. Naive
                datetimes are rejected because interpreting them would depend
                on the host machine's timezone.

        Returns:
            Dictionary of VNPAY parameters (without vnp_SecureHash)

        Raises:
            ValueError: If ``expire_minutes`` is not a positive integer, or if
                ``create_time`` is a naive (timezone-unaware) datetime.
        """
        effective_timeout = expire_minutes if expire_minutes is not None else self.timeout
        if not isinstance(effective_timeout, int) or isinstance(effective_timeout, bool) or effective_timeout <= 0:
            raise ValueError("expire_minutes must be a positive integer")

        # All VNPAY date fields must use Vietnam time (GMT+7), never naive UTC.
        # Use the caller-supplied authoritative instant when provided so that
        # the PAY vnp_CreateDate cannot drift from the persisted
        # PaymentOrder.created_at across a second boundary.
        if create_time is not None:
            if create_time.tzinfo is None or create_time.utcoffset() is None:
                raise ValueError("create_time must be a timezone-aware datetime")
            create_dt = create_time.astimezone(VIETNAM_TZ)
        else:
            create_dt = _vietnam_now()

        create_date = create_dt.strftime("%Y%m%d%H%M%S")
        expire_date = (create_dt + timedelta(minutes=effective_timeout)).strftime("%Y%m%d%H%M%S")

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

        Uses the official QueryDr v2.1.0 wire field names:
        - ``vnp_TransactionDate``: the original payment creation time in
          Vietnam time (GMT+7), matching that payment's original
          ``vnp_CreateDate``.
        - ``vnp_CreateDate``: the current QueryDr request creation time in
          Vietnam time (GMT+7).
        - ``vnp_RequestId``: a unique identifier for this QueryDr request.

        Args:
            txn_ref: Merchant transaction reference
            transaction_date: Original payment creation time in
                ``YYYYMMDDHHMMSS`` format (Vietnam time)
            client_ip: Client IP address

        Returns:
            Dictionary of query parameters (without ``vnp_SecureHash``)
        """
        params = {
            "vnp_Version": "2.1.0",
            "vnp_Command": "querydr",
            "vnp_TmnCode": self.tmn_code,
            "vnp_TxnRef": txn_ref,
            "vnp_OrderInfo": f"Query transaction {txn_ref}",
            "vnp_TransactionDate": transaction_date,
            "vnp_RequestId": uuid.uuid4().hex,
            "vnp_CreateDate": _vietnam_now().strftime("%Y%m%d%H%M%S"),
            "vnp_IpAddr": client_ip or "127.0.0.1",
        }
        return params

    # Fields that form the QueryDr v2.1.0 canonical signing string, in the
    # exact order required by the VNPAY specification.
    QUERYDR_SIGN_FIELDS = (
        "vnp_RequestId",
        "vnp_Version",
        "vnp_Command",
        "vnp_TmnCode",
        "vnp_TxnRef",
        "vnp_TransactionDate",
        "vnp_CreateDate",
        "vnp_IpAddr",
        "vnp_OrderInfo",
    )

    def generate_query_secure_hash(self, params: dict[str, str]) -> str:
        """Generate HMAC-SHA512 secure hash for a QueryDr request.

        The canonical signing string is the pipe-delimited concatenation of
        the documented fields in exactly this order::

            vnp_RequestId|vnp_Version|vnp_Command|vnp_TmnCode|vnp_TxnRef|
            vnp_TransactionDate|vnp_CreateDate|vnp_IpAddr|vnp_OrderInfo

        Args:
            params: QueryDr parameters (without ``vnp_SecureHash``)

        Returns:
            Hex-encoded HMAC-SHA512 hash
        """
        canonical = "|".join(params[field] for field in self.QUERYDR_SIGN_FIELDS)
        return hmac.new(
            self.hash_secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()

    def build_query_request(self, params: dict[str, str]) -> dict[str, object]:
        """Build a complete QueryDr HTTP POST request.

        VNPAY QueryDr v2.1.0 is invoked as an HTTP POST with a JSON body,
        not a GET URL with a sorted query string.

        Args:
            params: QueryDr parameters (without ``vnp_SecureHash``)

        Returns:
            A dict with ``url``, ``json`` (body including
            ``vnp_SecureHash``), and ``headers`` suitable for passing to an
            HTTP client.
        """
        secure_hash = self.generate_query_secure_hash(params)
        body = {**params, "vnp_SecureHash": secure_hash}
        return {
            "url": self.query_url,
            "json": body,
            "headers": {"Content-Type": "application/json"},
        }

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