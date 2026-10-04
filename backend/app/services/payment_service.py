from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    InvalidTransitionException,
    ValidationError,
)
from app.domain.enums import PaymentOrderStatus, PaymentProvider, PaymentTransactionStatus, SubscriptionStatus
from app.domain.models.base import utc_now
from app.models import PaymentOrder, PaymentTransaction, RecruitmentPlan, Subscription, User
from app.repositories import (
    PaymentOrderRepository,
    PaymentTransactionRepository,
    RecruitmentPlanRepository,
    SubscriptionRepository,
)
from app.services.payment_providers import VNPAYProvider


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
    """

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

        payment_order = PaymentOrder(
            user_id=user_id,
            plan_id=plan_id,
            subscription_id=subscription.id,
            amount=amount,
            currency="VND",
            provider=PaymentProvider.VNPAY,
            internal_order_id=internal_order_id,
            status=PaymentOrderStatus.PENDING,
            expired_at=utc_now() + timedelta(minutes=15),  # Match VNPAY expire time
        )
        self.session.add(payment_order)
        await self.session.commit()
        await self.session.refresh(payment_order)
        await self.session.refresh(subscription)

        # 5. Build VNPAY parameters
        order_info = f"Thanh toan goi tuyen dung {plan.name}"
        params = self.vnpay.build_payment_params(
            amount=amount,
            order_id=internal_order_id,
            order_info=order_info,
            client_ip=client_ip,
            return_url=return_url,
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

        # Create transaction record
        transaction = PaymentTransaction(
            payment_order_id=payment_order.id,
            provider_transaction_id=vnp_transaction_no,
            provider_result_code=response_code,
            provider_message=response_msg if not is_successful else transaction_msg,
            provider_response_metadata=str(params),
            status=PaymentTransactionStatus.SUCCESS if is_successful else PaymentTransactionStatus.FAILED,
            responded_at=utc_now(),
        )
        self.session.add(transaction)

        # 8. Update PaymentOrder status
        if is_successful:
            payment_order.status = PaymentOrderStatus.PAID
            payment_order.paid_at = utc_now()
            payment_order.provider_order_id = vnp_transaction_no
            payment_order.provider_request_id = params.get("vnp_BankTranNo")

            # 9. Activate subscription
            if payment_order.subscription_id:
                try:
                    await self._activate_subscription_for_payment(payment_order.subscription_id)
                except ConflictException as exc:
                    # Payment successful but subscription activation failed due to existing active subscription
                    # PaymentOrder remains PAID, transaction recorded, subscription stays PENDING
                    # This is an explicit reconciliation state - log and return success to VNPAY
                    # The payment was successful, but entitlement activation needs manual reconciliation
                    await self.session.commit()
                    return {
                        "RspCode": "00",
                        "Message": "Confirm Success - Payment received but subscription activation requires reconciliation"
                    }
        else:
            payment_order.status = PaymentOrderStatus.FAILED
            payment_order.provider_order_id = vnp_transaction_no

        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            return {"RspCode": "99", "Message": "Internal processing error"}

        return {"RspCode": "00", "Message": "Confirm Success"}

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

        Args:
            user_id: Authenticated user ID
            internal_order_id: Internal order ID (vnp_TxnRef)

        Returns:
            Payment status dict or None if not found/access denied
        """
        payment_order = await self.payment_orders.get_by_internal_order_id(internal_order_id)
        if payment_order is None:
            return None

        # Cross-user protection
        if payment_order.user_id != user_id:
            return None

        transaction = await self.payment_transactions.get_latest_by_payment_order_id(payment_order.id)

        return {
            "payment_order": payment_order,
            "transaction": transaction,
            "is_successful": payment_order.status == PaymentOrderStatus.PAID,
        }

    async def query_vnpay_transaction(
        self,
        internal_order_id: str,
    ) -> dict[str, Any] | None:
        """Query VNPAY for transaction status (reconciliation).

        Uses VNPAY querydr API.

        Args:
            internal_order_id: Internal order ID (vnp_TxnRef)

        Returns:
            VNPAY query response or None if not found
        """
        payment_order = await self.payment_orders.get_by_internal_order_id(internal_order_id)
        if payment_order is None:
            return None

        transaction_date = payment_order.created_at.strftime("%Y%m%d%H%M%S")
        params = self.vnpay.build_query_params(
            txn_ref=internal_order_id,
            transaction_date=transaction_date,
        )
        query_url = self.vnpay.build_query_url(params)

        # Note: Actual HTTP call would be made here using async HTTP client
        # For now, return the query URL for external calling
        return {
            "query_url": query_url,
            "params": params,
        }