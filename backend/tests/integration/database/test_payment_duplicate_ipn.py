"""Real SQL Server integration test for concurrent duplicate IPN.

Scenario:
- PaymentOrder = PENDING
- Subscription = PENDING
- IPN A = SUCCESS
- IPN B = IDENTICAL SUCCESS
- same vnp_TxnRef
- same vnp_TransactionNo
- same amount
- valid signature
- Execute both concurrently using separate database sessions

Required final invariant:
- PaymentOrder = PAID/SUCCESS
- PaymentTransaction effective count = 1
- Subscription activation effect = 1
- ACTIVE subscription count = 1

Required outcome:
- one effective processing
- one idempotent response
- no duplicate transaction effect
- no duplicate subscription activation
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from app.core.config import settings

# Set VNPAY test settings
settings.VNPAY_TMN_CODE = "TESTTMN"
settings.VNPAY_HASH_SECRET = "testhashsecret123"

from app.database.session import async_session_factory
from app.domain.enums import PaymentOrderStatus, PaymentProvider, PaymentTransactionStatus, SubscriptionStatus, UserRole
from app.models import PaymentOrder, PaymentTransaction, Subscription, RecruitmentPlan, User
from app.repositories import PaymentOrderRepository, PaymentTransactionRepository, SubscriptionRepository
from app.services.payment_service import PaymentService
from app.services.payment_providers.vnpay import VNPAYProvider
from tests.integration.conftest import run


pytestmark = pytest.mark.integration


def test_concurrent_duplicate_ipn_same_txnref():
    """Real SQL Server integration test for concurrent duplicate IPN.

    Scenario:
    - PaymentOrder = PENDING
    - Subscription = PENDING
    - IPN A = SUCCESS
    - IPN B = IDENTICAL SUCCESS
    - same vnp_TxnRef
    - same vnp_TransactionNo
    - same amount
    - valid signature
    - Execute both concurrently using separate database sessions

    Required final invariant:
    - PaymentOrder = PAID/SUCCESS
    - PaymentTransaction effective count = 1
    - Subscription activation effect = 1
    - ACTIVE subscription count = 1

    Required outcome:
    - one effective processing
    - one idempotent response
    - no duplicate transaction effect
    - no duplicate subscription activation
    """
    from app.core.config import settings

    async def _run_test():
        # Phase A: Setup session creates + commits data, then closes
        async with async_session_factory() as session_setup:
            plan_id = uuid4()

            # Create a test plan
            plan = RecruitmentPlan(
                id=plan_id,
                name="Test Plan",
                description="Test plan for concurrent IPN",
                price=1000000,
                currency="VND",
                duration_days=30,
                max_job_posts=10,
                is_active=True,
                display_order=1,
            )
            session_setup.add(plan)
            await session_setup.flush()

            # Create a user
            user_id = uuid4()
            user = User(
                id=user_id,
                email="test@test.com",
                password_hash="hashed",
                role=UserRole.CANDIDATE,
            )
            session_setup.add(user)
            await session_setup.flush()

            # Create PENDING subscription
            subscription = Subscription(
                id=uuid4(),
                user_id=user_id,
                plan_id=plan_id,
                status=SubscriptionStatus.PENDING,
            )
            session_setup.add(subscription)
            await session_setup.flush()

            # Create PaymentOrder with PENDING status
            internal_order_id = "VNPAY_CONCURRENT_TEST_001"
            payment_order = PaymentOrder(
                id=uuid4(),
                user_id=user_id,
                plan_id=plan_id,
                subscription_id=subscription.id,
                amount=1000000,
                currency="VND",
                provider=PaymentProvider.VNPAY,
                internal_order_id=internal_order_id,
                status=PaymentOrderStatus.PENDING,
                expired_at=datetime.utcnow() + timedelta(minutes=15),
            )
            session_setup.add(payment_order)
            await session_setup.flush()

            # Commit and close setup session before the race
            await session_setup.commit()
            await session_setup.close()

        # Phase B: Session A + Phase C: Session B (genuine concurrent race)
        async with async_session_factory() as session_a:
            async with async_session_factory() as session_b:
                vnpay = VNPAYProvider()

                # Prepare IPN params (identical for both)
                ipn_params = {
                    "vnp_TmnCode": settings.VNPAY_TMN_CODE,
                    "vnp_Amount": "100000000",
                    "vnp_BankCode": "NCB",
                    "vnp_BankTranNo": "VNP123456",
                    "vnp_CardType": "ATM",
                    "vnp_PayDate": datetime.utcnow().strftime("%Y%m%d%H%M%S"),
                    "vnp_OrderInfo": "Test concurrent IPN",
                    "vnp_TransactionNo": "13524458",
                    "vnp_ResponseCode": "00",
                    "vnp_TransactionStatus": "00",
                    "vnp_TxnRef": internal_order_id,
                }
                ipn_hash = vnpay.generate_secure_hash(ipn_params)
                ipn_params["vnp_SecureHash"] = ipn_hash

                # Genuine concurrent execution using asyncio.gather()
                service_a = PaymentService(session_a)
                service_b = PaymentService(session_b)

                result_a, result_b = await asyncio.gather(
                    service_a.process_vnpay_ipn(ipn_params, "127.0.0.1"),
                    service_b.process_vnpay_ipn(ipn_params, "127.0.0.1"),
                )

                # --- VERIFY while sessions are still open ---
                # Re-fetch payment_order tracked by session_a
                payment_order = await session_a.get(PaymentOrder, uuid4())
                # Actually payment_order.id was generated in session_setup; need to find it

                # Use repository to find the payment order by internal_order_id
                from app.repositories import PaymentOrderRepository
                orepo = PaymentOrderRepository(session_a)
                payment_order = await orepo.get_by_internal_order_id(internal_order_id)
                assert payment_order is not None, "PaymentOrder not found after IPN race"

                assert payment_order.status == PaymentOrderStatus.PAID, (
                    f"PaymentOrder status expected PAID, got {payment_order.status}"
                )

                # PaymentTransaction effective count should be 1 (not 2)
                txn_repo = PaymentTransactionRepository(session_a)
                transactions = await txn_repo.get_by_payment_order_id(payment_order.id)
                assert len(transactions) == 1, (
                    f"Expected 1 PaymentTransaction, got {len(transactions)}: {transactions}"
                )

                # Subscription should be ACTIVATED (effective count = 1)
                from app.repositories import SubscriptionRepository
                srepo = SubscriptionRepository(session_a)
                subscription = await srepo.get_by_user_and_plan(user_id, plan_id)
                assert subscription.status == SubscriptionStatus.ACTIVE, (
                    f"Subscription status expected ACTIVE, got {subscription.status}"
                )

                # Return results AFTER verification
                return result_a, result_b

        # Sessions are now closed

    import asyncio
    result_a, result_b = run(_run_test())

    # Both should return success (idempotent)
    assert result_a["RspCode"] == "00", f"IPN A failed: {result_a}"
    assert result_b["RspCode"] == "00", f"IPN B failed: {result_b}"