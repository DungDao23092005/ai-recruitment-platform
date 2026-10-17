from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    InvalidTransitionException,
    ValidationError,
)
from app.domain.enums import PaymentOrderStatus, PaymentProvider, PaymentTransactionStatus, SubscriptionStatus, UserRole
from app.domain.models.base import utc_now
from app.models import PaymentOrder, PaymentTransaction, RecruitmentPlan, RecruiterProfile, Subscription, User
from app.repositories import (
    PaymentOrderRepository,
    PaymentTransactionRepository,
    RecruitmentPlanRepository,
    SubscriptionRepository,
)
from app.services.payment_providers import VNPAYProvider
from app.services.payment_providers.vnpay import VIETNAM_TZ
from app.services.recruiter_access import ensure_recruiter_access


# Lightweight, in-process throttle for server-to-server QueryDr reconciliation.
# It prevents repeated client status polls from generating unbounded outbound
# QueryDr calls. Keyed by the VNPAY merchant reference (internal_order_id).
# This is intentionally process-local and best-effort; it is not a substitute
# for infrastructure rate limiting.
_QUERYDR_LAST_ATTEMPT: dict[str, float] = {}
QUERYDR_MIN_INTERVAL_SECONDS = 5.0


def reset_querydr_throttle() -> None:
    """Clear the in-process QueryDr reconciliation throttle (used in tests)."""
    _QUERYDR_LAST_ATTEMPT.clear()


class PaymentService:
    """Payment service handling VNPAY integration.

    Owns platform business logic:
    - PaymentOrder creation
    - State transitions
    - Idempotency
    - Ownership
    - Amount validation
    - PaymentTransaction
    - Subscription activation boundary
    - Server-to-server QueryDr reconciliation of pending VNPAY orders
    """

    # QueryDr v2.1.0 documented outcome classification.
    QUERYDR_SUCCESS_RESPONSE_CODE = "00"
    QUERYDR_SUCCESS_TRANSACTION_STATUS = "00"
    # Documented terminal (non-pending, non-success) transaction statuses that
    # may safely finalize an order as FAILED: 02 = transaction error,
    # 04 = reversed. Status 07 (fraud-suspected / cancelled) is deliberately
    # excluded here: it must stay inconclusive so it cannot close the IPN or
    # manual-investigation path.
    QUERYDR_TERMINAL_FAILURE_STATUSES = frozenset({"02", "04"})
    # The only documented status that means "still awaiting completion".
    # 05/06/09 are refund-related and must never be treated as an active
    # original payment.
    QUERYDR_PENDING_TRANSACTION_STATUSES = frozenset({"01"})

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.payment_orders = PaymentOrderRepository(session)
        self.payment_transactions = PaymentTransactionRepository(session)
        self.plans = RecruitmentPlanRepository(session)
        self.subscriptions = SubscriptionRepository(session)
        self.vnpay = VNPAYProvider()

    def _generate_internal_order_id(self) -> str:
        """Generate unique internal order ID for VNPAY vnp_TxnRef.

        Format: VNPAY_YYYYMMDD_HHMMSS_XXXX (where XXXX is random hex)
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        random_suffix = uuid.uuid4().hex[:8].upper()
        return f"VNPAY_{timestamp}_{random_suffix}"

    async def create_vnpay_payment(
        self,
        user_id: uuid.UUID,
        plan_id: uuid.UUID,
        client_ip: str,
        return_url: str | None = None,
    ) -> tuple[str, uuid.UUID, uuid.UUID]:
        """Create VNPAY payment for a recruitment plan.

        Flow:
        1. Load RecruitmentPlan and verify it's valid/active
        2. Read authoritative plan price
        3. Create PENDING Subscription
        4. Create PaymentOrder with provider=VNPAY
        5. Generate unique internal_order_id (vnp_TxnRef)
        6. Construct VNPAY parameters
        7. Calculate vnp_SecureHash
        8. Return payment URL

        Args:
            user_id: Authenticated candidate user ID
            plan_id: Recruitment plan ID
            client_ip: Client IP address for VNPAY
            return_url: Optional override for return URL

        Returns:
            Tuple of (payment_url, internal_order_id, subscription_id)
        """
        # 1. Load and verify plan
        plan = await self.plans.get_active_by_id(plan_id)
        if plan is None:
            raise EntityNotFoundException(f"Plan {plan_id} not found or inactive")

        # 2. Use authoritative plan price (do NOT accept from client)
        amount = plan.price

        # 3. Create PENDING subscription
        subscription = Subscription(
            user_id=user_id,
            plan_id=plan_id,
            status=SubscriptionStatus.PENDING,
        )
        self.session.add(subscription)
        await self.session.flush()  # Get subscription ID

        # 4. Create PaymentOrder
        internal_order_id = self._generate_internal_order_id()

        # Resolve the timeout once from the configured provider (VNPAY_TIMEOUT,
        # in minutes). The same value is used for both the application-level
        # expiration and the VNPAY gateway expiration so they represent the
        # same instant.
        timeout = self.vnpay.timeout

        # Capture ONE authoritative creation instant (UTC-aware) and reuse it
        # for the persisted order timestamp, the application expiration, and
        # the VNPAY PAY request. This prevents a cross-second clock read from
        # making the stored created_at differ from the original PAY
        # vnp_CreateDate, which QueryDr relies on to reference the transaction.
        now_utc = utc_now()

        payment_order = PaymentOrder(
            user_id=user_id,
            plan_id=plan_id,
            subscription_id=subscription.id,
            amount=amount,
            currency="VND",
            provider=PaymentProvider.VNPAY,
            internal_order_id=internal_order_id,
            status=PaymentOrderStatus.PENDING,
            created_at=now_utc,
            expired_at=now_utc + timedelta(minutes=timeout),
        )
        self.session.add(payment_order)
        try:
            await self.session.commit()
            await self.session.refresh(payment_order)
            await self.session.refresh(subscription)
        except Exception:
            await self.session.rollback()
            raise

        # 5. Build VNPAY parameters (same timeout AND same creation instant as
        # the persisted order, so PAY vnp_CreateDate == created_at).
        order_info = f"Thanh toan goi tuyen dung {plan.name}"
        params = self.vnpay.build_payment_params(
            amount=amount,
            order_id=internal_order_id,
            order_info=order_info,
            client_ip=client_ip,
            return_url=return_url,
            expire_minutes=timeout,
            create_time=now_utc,
        )

        # 6. Build payment URL with secure hash
        payment_url = self.vnpay.build_payment_url(params)

        return payment_url, internal_order_id, subscription.id

    async def process_vnpay_ipn(
        self,
        params: dict[str, str],
        client_ip: str,
    ) -> dict[str, str]:
        """Process VNPAY IPN (Instant Payment Notification).

        Flow:
        1. Verify signature
        2. Lookup PaymentOrder by vnp_TxnRef (internal_order_id)
        3. Validate merchant/order correlation
        4. Validate amount
        5. Read current backend payment state
        6. Idempotent processing
        7. Create PaymentTransaction
        8. Activate subscription when appropriate
        9. Return VNPAY IPN response

        Args:
            params: VNPAY callback parameters
            client_ip: Client IP address

        Returns:
            VNPAY IPN response dict with RspCode and Message
        """
        # 1. Verify signature
        if not self.vnpay.verify_signature(params):
            return {"RspCode": "97", "Message": "Invalid signature"}

        # 2. Lookup PaymentOrder by vnp_TxnRef with row-level locking for idempotency
        txn_ref = params.get("vnp_TxnRef")
        if not txn_ref:
            return {"RspCode": "01", "Message": "Missing transaction reference"}

        # Lock the PaymentOrder row to prevent concurrent IPN race conditions
        stmt = (
            select(PaymentOrder)
            .where(PaymentOrder.internal_order_id == txn_ref)
            .where(PaymentOrder.is_deleted == False)  # noqa: E712
            .with_hint(PaymentOrder, "WITH (UPDLOCK, ROWLOCK)")
        )
        result = await self.session.execute(stmt)
        payment_order = result.scalar_one_or_none()

        # 3. Validate merchant correlation (TNmnCode)
        tmn_code = params.get("vnp_TmnCode")
        if tmn_code != settings.VNPAY_TMN_CODE:
            return {"RspCode": "02", "Message": "Invalid merchant"}

        # 4. Validate amount
        vnp_amount_str = params.get("vnp_Amount", "0")
        try:
            vnp_amount = int(vnp_amount_str)
        except ValueError:
            return {"RspCode": "04", "Message": "Invalid amount"}

        expected_amount = payment_order.amount * 100
        if vnp_amount != expected_amount:
            return {"RspCode": "04", "Message": "Invalid amount"}

        # 5. Check payment state for idempotency
        if payment_order.status == PaymentOrderStatus.PAID:
            # Already processed successfully - return success (idempotent)
            return {"RspCode": "00", "Message": "Confirm Success"}

        if payment_order.status in (PaymentOrderStatus.FAILED, PaymentOrderStatus.CANCELLED, PaymentOrderStatus.EXPIRED):
            # Cannot process payment for failed/cancelled/expired order
            return {"RspCode": "02", "Message": "Order already failed or cancelled"}

        # 6. Determine payment success from VNPAY response
        response_code = params.get("vnp_ResponseCode", "")
        transaction_status = params.get("vnp_TransactionStatus", "")
        vnp_transaction_no = params.get("vnp_TransactionNo")

        response_success, response_msg = self.vnpay.parse_response_code(response_code)
        transaction_success, transaction_msg = self.vnpay.parse_transaction_status(transaction_status)

        is_successful = response_success and transaction_success

        # 7. Create PaymentTransaction (idempotent - check for duplicate provider transaction)
        if vnp_transaction_no and await self.payment_transactions.exists_by_provider_transaction_id(vnp_transaction_no):
            # Duplicate provider transaction - check if already linked to this order
            existing_txn = await self.payment_transactions.get_by_provider_transaction_id(vnp_transaction_no)
            if existing_txn and existing_txn.payment_order_id == payment_order.id:
                return {"RspCode": "00", "Message": "Confirm Success"}
            # Different order - potential issue
            return {"RspCode": "02", "Message": "Duplicate transaction for different order"}

        # 7b/8. Finalize through the single shared verified-success path so the
        # IPN path and QueryDr reconciliation cannot diverge or double-activate.
        if is_successful:
            activated = await self._record_success_and_activate(
                payment_order,
                provider_transaction_id=vnp_transaction_no,
                provider_result_code=response_code,
                provider_message=transaction_msg,
                provider_request_id=params.get("vnp_BankTranNo"),
                provider_response_metadata=str(params),
            )
            if not activated:
                # Payment successful but subscription activation failed due to
                # an existing active subscription. The PaymentOrder stays PAID
                # and the transaction is recorded; the subscription remains
                # PENDING pending manual reconciliation. Still acknowledge the
                # successful payment to VNPAY.
                return {
                    "RspCode": "00",
                    "Message": "Confirm Success - Payment received but subscription activation requires reconciliation",
                }
            return {"RspCode": "00", "Message": "Confirm Success"}

        # Failure branch: record the failed transaction and mark the order FAILED.
        transaction = PaymentTransaction(
            payment_order_id=payment_order.id,
            provider_transaction_id=vnp_transaction_no,
            provider_result_code=response_code,
            provider_message=response_msg,
            provider_response_metadata=str(params),
            status=PaymentTransactionStatus.FAILED,
            responded_at=utc_now(),
        )
        self.session.add(transaction)
        payment_order.status = PaymentOrderStatus.FAILED
        payment_order.provider_order_id = vnp_transaction_no

        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            return {"RspCode": "99", "Message": "Internal processing error"}

        return {"RspCode": "00", "Message": "Confirm Success"}

    async def _record_success_and_activate(
        self,
        payment_order: PaymentOrder,
        *,
        provider_transaction_id: str | None,
        provider_result_code: str,
        provider_message: str,
        provider_request_id: str | None,
        provider_response_metadata: str,
    ) -> bool:
        """Persist a verified successful payment and activate its subscription.

        Shared by the IPN path and QueryDr reconciliation so both record exactly
        one PaymentTransaction and activate through the same safe path. The
        caller must already hold the PaymentOrder row lock and have confirmed
        the order is still PENDING.

        Returns:
            True if the subscription was activated, False if the payment was
            recorded but activation requires manual reconciliation because the
            user already has an active subscription.
        """
        payment_order.status = PaymentOrderStatus.PAID
        payment_order.paid_at = utc_now()
        payment_order.provider_order_id = provider_transaction_id
        payment_order.provider_request_id = provider_request_id

        transaction = PaymentTransaction(
            payment_order_id=payment_order.id,
            provider_transaction_id=provider_transaction_id,
            provider_result_code=provider_result_code,
            provider_message=provider_message,
            provider_response_metadata=provider_response_metadata,
            status=PaymentTransactionStatus.SUCCESS,
            responded_at=utc_now(),
        )
        self.session.add(transaction)

        if payment_order.subscription_id:
            try:
                await self._activate_subscription_for_payment(payment_order.subscription_id)
            except ConflictException:
                await self.session.commit()
                return False
            return True

        await self.session.commit()
        return True

    async def _activate_subscription_for_payment(
        self,
        subscription_id: uuid.UUID,
    ) -> Subscription:
        """Activate subscription for successful payment.

        Uses the same locking and validation logic as SubscriptionService.activate_subscription.
        """
        sub = await self.subscriptions.get_by_id_including_deleted(subscription_id)
        if sub is None:
            raise EntityNotFoundException(f"Subscription {subscription_id} not found")

        if sub.status != SubscriptionStatus.PENDING:
            raise InvalidTransitionException(
                f"Cannot activate subscription in status {sub.status.value}"
            )

        # Lock user row to serialize activation for this user
        stmt = (
            select(User)
            .where(User.id == sub.user_id)
            .with_hint(User, "WITH (UPDLOCK, ROWLOCK)")
        )
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            raise EntityNotFoundException(f"User {sub.user_id} not found")

        # Ensure recruiter access (role transition + profile creation)
        await ensure_recruiter_access(self.session, user)

        now = utc_now()

        # Check for existing active subscription BEFORE activating
        existing_active = await self.subscriptions.get_active_by_user_id(sub.user_id, now)
        if existing_active is not None and existing_active.id != sub.id:
            raise ConflictException(
                f"User already has an active subscription (id: {existing_active.id})"
            )

        plan = await self.plans.get_active_by_id(sub.plan_id)
        if plan is None:
            raise EntityNotFoundException(f"Plan {sub.plan_id} not found or inactive")

        sub.status = SubscriptionStatus.ACTIVE
        sub.started_at = now
        sub.expires_at = now + timedelta(days=plan.duration_days)

        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def process_vnpay_return(
        self,
        params: dict[str, str],
    ) -> tuple[bool, str, str | None]:
        """Process VNPAY Return URL (browser redirect).

        This is informational only - authoritative processing happens via IPN.
        Returns: (is_successful, message, internal_order_id)
        """
        if not self.vnpay.verify_signature(params):
            return False, "Invalid signature", None

        txn_ref = params.get("vnp_TxnRef")
        if not txn_ref:
            return False, "Missing transaction reference", None

        payment_order = await self.payment_orders.get_by_internal_order_id(txn_ref)
        if payment_order is None:
            return False, "Order not found", None

        is_successful = self.vnpay.is_payment_successful(params)
        response_code = params.get("vnp_ResponseCode", "")
        response_success, response_msg = self.vnpay.parse_response_code(response_code)

        if is_successful:
            message = "Thanh toán thành công"
        else:
            message = f"Thanh toán thất bại: {response_msg}"

        return is_successful, message, txn_ref

    async def get_payment_status(
        self,
        user_id: uuid.UUID,
        internal_order_id: str,
    ) -> Optional[dict]:
        """Get payment status for a user's payment order.

        Ownership is enforced before any reconciliation. When the order is an
        authenticated user's own still-PENDING VNPAY order, a server-to-server
        QueryDr reconciliation is attempted so a payment whose IPN could not
        reach the backend (for example a localhost IPN URL) can still be
        finalized through the same verified path.

        Args:
            user_id: Authenticated user ID
            internal_order_id: Internal order ID (vnp_TxnRef)

        Returns:
            Payment status dict or None if not found/access denied
        """
        payment_order = await self.payment_orders.get_by_internal_order_id(internal_order_id)
        if payment_order is None:
            return None

        # Cross-user protection: never disclose or reconcile another user's order.
        if payment_order.user_id != user_id:
            return None

        if (
            payment_order.status == PaymentOrderStatus.PENDING
            and payment_order.provider == PaymentProvider.VNPAY
        ):
            await self._reconcile_pending_vnpay_payment(payment_order)
            # Reflect any state finalized during reconciliation.
            await self.session.refresh(payment_order)

        transaction = await self.payment_transactions.get_latest_by_payment_order_id(payment_order.id)

        return {
            "payment_order": payment_order,
            "transaction": transaction,
            "is_successful": payment_order.status == PaymentOrderStatus.PAID,
        }

    # ------------------------------------------------------------------
    # Server-to-server QueryDr reconciliation
    # ------------------------------------------------------------------

    def _querydr_throttle_allows(self, internal_order_id: str) -> bool:
        """Best-effort in-process throttle to bound outbound QueryDr calls.

        Returns True and records the attempt when the previous attempt for this
        order is older than ``QUERYDR_MIN_INTERVAL_SECONDS``.
        """
        now = time.monotonic()
        last = _QUERYDR_LAST_ATTEMPT.get(internal_order_id)
        if last is not None and (now - last) < QUERYDR_MIN_INTERVAL_SECONDS:
            return False
        _QUERYDR_LAST_ATTEMPT[internal_order_id] = now
        return True

    def _classify_querydr_result(self, body: dict[str, Any]) -> str:
        """Classify a QueryDr response as success/pending/failed/inconclusive.

        Only documented, verified outcomes are acted upon:
        - ``success``: response code 00 AND transaction status 00.
        - ``failed``: successful query (response code 00) with a documented
          terminal transaction status (02/04) for the original payment.
        - ``pending``: the documented not-yet-completed status (01).
        - ``inconclusive``: everything else, including fraud-suspected 07,
          refund-related 05/06/09, an unsupported status, a non-00 query
          response code, or missing fields. These never change order state.
        """
        response_code = body.get("vnp_ResponseCode")
        transaction_status = body.get("vnp_TransactionStatus")

        # A failed query request (anything other than 00) is never conclusive.
        if response_code != self.QUERYDR_SUCCESS_RESPONSE_CODE:
            return "inconclusive"

        if transaction_status == self.QUERYDR_SUCCESS_TRANSACTION_STATUS:
            return "success"

        if transaction_status in self.QUERYDR_TERMINAL_FAILURE_STATUSES:
            return "failed"

        if transaction_status in self.QUERYDR_PENDING_TRANSACTION_STATUSES:
            return "pending"

        return "inconclusive"

    def _querydr_reference_matches(
        self,
        payment_order: PaymentOrder,
        body: dict[str, Any],
    ) -> bool:
        """Strictly verify a QueryDr response refers to this exact payment.

        Every required field must be present, correctly typed, and match the
        order. A missing or malformed field is rejected (never treated as a
        wildcard). Only the original payment transaction type (``"01"``) is
        accepted; refunds or any other transaction type are rejected so they
        can never be mistaken for the original payment.
        """
        response_ref = body.get("vnp_TxnRef")
        if not isinstance(response_ref, str) or response_ref != payment_order.internal_order_id:
            return False

        response_tmn_code = body.get("vnp_TmnCode")
        if not isinstance(response_tmn_code, str) or response_tmn_code != self.vnpay.tmn_code:
            return False

        response_amount = body.get("vnp_Amount")
        if response_amount is None:
            return False
        try:
            amount_value = int(str(response_amount))
        except (TypeError, ValueError):
            return False
        if amount_value != payment_order.amount * 100:
            return False

        if body.get("vnp_TransactionType") != "01":
            return False

        return True

    async def _lock_payment_order(
        self,
        internal_order_id: str,
    ) -> PaymentOrder | None:
        """Re-load and lock the PaymentOrder row within the current transaction.

        Uses the same UPDLOCK/ROWLOCK hint as the IPN path and forces a
        populate_existing reload so the caller observes the current database
        state (a concurrent IPN may have finalized the order while the outbound
        QueryDr request was in flight).
        """
        stmt = (
            select(PaymentOrder)
            .where(PaymentOrder.internal_order_id == internal_order_id)
            .where(PaymentOrder.is_deleted == False)  # noqa: E712
            .with_hint(PaymentOrder, "WITH (UPDLOCK, ROWLOCK)")
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _reconcile_pending_vnpay_payment(self, payment_order: PaymentOrder) -> None:
        """Reconcile a pending VNPAY order via server-to-server QueryDr.

        No database row lock is held while the outbound HTTP request is in
        flight. When QueryDr returns a conclusive outcome the order is
        re-locked and re-checked inside a short transaction before any state
        transition, so a concurrent IPN cannot cause double activation.
        Inconclusive outcomes (timeout, network error, unknown codes, malformed
        or mismatched responses) preserve PENDING.
        """
        if not self._querydr_throttle_allows(payment_order.internal_order_id):
            return

        try:
            body = await self._send_querydr_request(payment_order)
        except Exception:
            # Timeout, network error, non-2xx, or malformed body: stay pending.
            return

        if not isinstance(body, dict):
            return

        # Never trust an unverified response: the VNPAY checksum must be valid
        # before any classification or state change is considered.
        if not self.vnpay.verify_query_response_hash(body):
            return

        if not self._querydr_reference_matches(payment_order, body):
            # Response does not correspond to this order/amount: stay pending.
            return

        outcome = self._classify_querydr_result(body)

        if outcome == "success":
            await self._finalize_reconciled_success(payment_order, body)
        elif outcome == "failed":
            await self._finalize_reconciled_failure(payment_order, body)
        # pending / inconclusive: preserve PENDING, do nothing.

    async def _finalize_reconciled_success(
        self,
        payment_order: PaymentOrder,
        body: dict[str, Any],
    ) -> None:
        """Finalize a QueryDr-verified success inside a short locked transaction."""
        locked = await self._lock_payment_order(payment_order.internal_order_id)
        if locked is None or locked.status != PaymentOrderStatus.PENDING:
            # Another request (e.g. a concurrent IPN) already finalized it.
            return

        # Re-validate the conclusive response against the freshly locked order.
        if not self._querydr_reference_matches(locked, body):
            return

        provider_transaction_id = body.get("vnp_TransactionNo")

        # Idempotency: never record a second transaction for the same provider id.
        if provider_transaction_id:
            existing = await self.payment_transactions.get_by_provider_transaction_id(
                provider_transaction_id
            )
            if existing is not None:
                # Already recorded (for this or another order): do not double-account.
                return

        try:
            await self._record_success_and_activate(
                locked,
                provider_transaction_id=provider_transaction_id,
                provider_result_code=str(body.get("vnp_ResponseCode", "")),
                provider_message="Reconciled via VNPAY QueryDr",
                provider_request_id=body.get("vnp_BankTranNo"),
                provider_response_metadata=str(body),
            )
        except Exception:
            await self.session.rollback()

    async def _finalize_reconciled_failure(
        self,
        payment_order: PaymentOrder,
        body: dict[str, Any],
    ) -> None:
        """Mark an order FAILED only for a documented, definitive terminal status."""
        locked = await self._lock_payment_order(payment_order.internal_order_id)
        if locked is None or locked.status != PaymentOrderStatus.PENDING:
            return

        if not self._querydr_reference_matches(locked, body):
            return

        if self._classify_querydr_result(body) != "failed":
            return

        provider_transaction_id = body.get("vnp_TransactionNo")

        # Idempotency: if a transaction already exists, do not create another.
        if (
            provider_transaction_id
            and await self.payment_transactions.exists_by_provider_transaction_id(
                provider_transaction_id
            )
        ):
            return

        transaction = PaymentTransaction(
            payment_order_id=locked.id,
            provider_transaction_id=provider_transaction_id,
            provider_result_code=str(body.get("vnp_ResponseCode", "")),
            provider_message="Reconciled via VNPAY QueryDr",
            provider_response_metadata=str(body),
            status=PaymentTransactionStatus.FAILED,
            responded_at=utc_now(),
        )
        self.session.add(transaction)
        locked.status = PaymentOrderStatus.FAILED
        locked.provider_order_id = provider_transaction_id

        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()

    async def _send_querydr_request(self, payment_order: PaymentOrder) -> Any:
        """Build and POST a QueryDr request for the given order.

        ``vnp_TransactionDate`` identifies the original payment's creation time
        in Vietnam time (GMT+7), matching the original PAY ``vnp_CreateDate``.
        ``created_at`` is stored UTC-aware and converted to Vietnam time rather
        than substituting the current time.
        """
        vietnam_created_at = payment_order.created_at.astimezone(VIETNAM_TZ)
        transaction_date = vietnam_created_at.strftime("%Y%m%d%H%M%S")
        params = self.vnpay.build_query_params(
            txn_ref=payment_order.internal_order_id,
            transaction_date=transaction_date,
        )
        request = self.vnpay.build_query_request(params)

        # QueryDr v2.1.0 is an HTTP POST with a JSON body.
        async with httpx.AsyncClient() as client:
            response = await client.post(
                request["url"],
                json=request["json"],
                headers=request["headers"],
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def query_vnpay_transaction(
        self,
        internal_order_id: str,
    ) -> dict[str, Any] | None:
        """Query VNPAY for transaction status (reconciliation).

        Uses the VNPAY querydr API. Returns the raw provider response or None
        if the order is not found. This low-level helper does not change any
        order state; state transitions go through the reconciliation path.

        Args:
            internal_order_id: Internal order ID (vnp_TxnRef)

        Returns:
            VNPAY query response or None if not found
        """
        payment_order = await self.payment_orders.get_by_internal_order_id(internal_order_id)
        if payment_order is None:
            return None

        return await self._send_querydr_request(payment_order)