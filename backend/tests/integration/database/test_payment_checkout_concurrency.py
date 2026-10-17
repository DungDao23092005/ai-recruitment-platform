"""Real SQL Server concurrency tests for VNPAY checkout creation.

These exercise the per-user serialization invariant against a genuine
database (not mocks):

1. Two concurrent checkouts for the same user and plan must not create two
   independently payable orders.
2. Two concurrent checkouts for two different plans while a pending checkout
   exists must not both create a payable order.
3. A concurrent checkout and IPN for the same user must not deadlock and must
   leave a single, consistent final state.

The lock hierarchy implemented by PaymentService is ``User -> PaymentOrder`` on
every write path (checkout, IPN, QueryDr finalize); these tests would surface a
deadlock as a non-Conflict database exception.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import settings

# Ensure the VNPAY provider can build/sign links in the test environment.
settings.VNPAY_TMN_CODE = "TESTTMN"
settings.VNPAY_HASH_SECRET = "testhashsecret123"

from app.core.exceptions import ConflictException
from app.database.session import async_session_factory
from app.domain.enums import (
    PaymentOrderStatus,
    PaymentProvider,
    SubscriptionStatus,
    UserRole,
)
from app.models import PaymentOrder, RecruitmentPlan, Subscription, User
from app.services.payment_providers.vnpay import VNPAYProvider
from app.services.payment_service import PaymentService
from tests.integration.conftest import run


pytestmark = pytest.mark.integration


async def _make_plan(session, *, price: int = 299_000, name: str = "Plan") -> RecruitmentPlan:
    plan = RecruitmentPlan(
        id=uuid4(),
        name=name,
        description="concurrency plan",
        price=price,
        currency="VND",
        duration_days=30,
        max_job_posts=5,
        is_active=True,
        display_order=0,
    )
    session.add(plan)
    await session.flush()
    return plan


async def _make_user(session, *, email: str) -> User:
    user = User(
        id=uuid4(),
        email=email,
        password_hash="hashed",
        role=UserRole.CANDIDATE,
    )
    session.add(user)
    await session.flush()
    return user


async def _counts(user_id) -> tuple[int, int, int]:
    async with async_session_factory() as session:
        order_count = await session.scalar(
            select(func.count())
            .select_from(PaymentOrder)
            .where(PaymentOrder.user_id == user_id)
        )
        sub_count = await session.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.user_id == user_id)
        )
        active_count = await session.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )
        return order_count, sub_count, active_count


def test_concurrent_same_plan_checkout_creates_one_order():
    """Invariant 1: two concurrent same-plan checkouts create one payable order."""

    async def _run():
        async with async_session_factory() as setup:
            plan = await _make_plan(setup, name="Same Plan")
            user = await _make_user(setup, email=f"same-{uuid4().hex[:8]}@example.com")
            await setup.commit()
            plan_id, user_id = plan.id, user.id

        async def checkout():
            async with async_session_factory() as session:
                return await PaymentService(session).create_vnpay_payment(
                    user_id, plan_id, "127.0.0.1"
                )

        result_a, result_b = await asyncio.gather(checkout(), checkout())

        order_count, sub_count, _ = await _counts(user_id)
        return result_a, result_b, order_count, sub_count

    result_a, result_b, order_count, sub_count = run(_run())

    # Exactly one payable order and one subscription exist.
    assert order_count == 1, f"expected 1 PaymentOrder, got {order_count}"
    assert sub_count == 1, f"expected 1 Subscription, got {sub_count}"
    # Both callers converge on the same order (the second reuses the first).
    assert result_a[1] == result_b[1]
    assert result_a[2] == result_b[2]


def test_concurrent_different_plan_checkout_cannot_both_create():
    """Invariant 2: with a pending checkout, two different-plan requests can
    never both create a payable checkout."""

    async def _run():
        async with async_session_factory() as setup:
            pending_plan = await _make_plan(setup, name="Pending Plan")
            plan_b = await _make_plan(setup, price=500_000, name="Plan B")
            plan_c = await _make_plan(setup, price=700_000, name="Plan C")
            user = await _make_user(setup, email=f"multi-{uuid4().hex[:8]}@example.com")

            subscription = Subscription(
                id=uuid4(),
                user_id=user.id,
                plan_id=pending_plan.id,
                status=SubscriptionStatus.PENDING,
            )
            setup.add(subscription)
            await setup.flush()
            order = PaymentOrder(
                id=uuid4(),
                user_id=user.id,
                plan_id=pending_plan.id,
                subscription_id=subscription.id,
                amount=pending_plan.price,
                currency="VND",
                provider=PaymentProvider.VNPAY,
                internal_order_id=f"VNPAY_PENDING_{uuid4().hex[:8].upper()}",
                status=PaymentOrderStatus.PENDING,
                created_at=datetime.now(timezone.utc),
                expired_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            )
            setup.add(order)
            await setup.commit()
            user_id = user.id
            plan_b_id, plan_c_id = plan_b.id, plan_c.id

        async def checkout(plan_id):
            async with async_session_factory() as session:
                return await PaymentService(session).create_vnpay_payment(
                    user_id, plan_id, "127.0.0.1"
                )

        results = await asyncio.gather(
            checkout(plan_b_id),
            checkout(plan_c_id),
            return_exceptions=True,
        )
        order_count, _, _ = await _counts(user_id)
        return results, order_count

    results, order_count = run(_run())

    for result in results:
        assert isinstance(result, ConflictException), result
    # The original pending order is the only one; neither request added another.
    assert order_count == 1, f"expected 1 PaymentOrder, got {order_count}"


def test_concurrent_checkout_and_ipn_no_deadlock_consistent_state():
    """Invariant 3 & 4: a checkout racing the IPN of the same user serializes on
    the user lock (no deadlock) and leaves exactly one active subscription."""

    async def _run():
        async with async_session_factory() as setup:
            plan = await _make_plan(setup, name="Race Plan")
            user = await _make_user(setup, email=f"race-{uuid4().hex[:8]}@example.com")

            subscription = Subscription(
                id=uuid4(),
                user_id=user.id,
                plan_id=plan.id,
                status=SubscriptionStatus.PENDING,
            )
            setup.add(subscription)
            await setup.flush()
            internal_order_id = f"VNPAY_RACE_{uuid4().hex[:8].upper()}"
            order = PaymentOrder(
                id=uuid4(),
                user_id=user.id,
                plan_id=plan.id,
                subscription_id=subscription.id,
                amount=plan.price,
                currency="VND",
                provider=PaymentProvider.VNPAY,
                internal_order_id=internal_order_id,
                status=PaymentOrderStatus.PENDING,
                created_at=datetime.now(timezone.utc),
                expired_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            )
            setup.add(order)
            await setup.commit()
            user_id, plan_id = user.id, plan.id

        provider = VNPAYProvider()
        ipn_params = {
            "vnp_TmnCode": settings.VNPAY_TMN_CODE,
            "vnp_Amount": str(plan.price * 100),
            "vnp_BankCode": "NCB",
            "vnp_BankTranNo": "RACEBANK1",
            "vnp_CardType": "ATM",
            "vnp_PayDate": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
            "vnp_OrderInfo": "Race IPN",
            "vnp_TransactionNo": f"RACE{uuid4().int % 10**10}",
            "vnp_ResponseCode": "00",
            "vnp_TransactionStatus": "00",
            "vnp_TxnRef": internal_order_id,
        }
        ipn_params["vnp_SecureHash"] = provider.generate_secure_hash(ipn_params)

        async def checkout():
            async with async_session_factory() as session:
                return await PaymentService(session).create_vnpay_payment(
                    user_id, plan_id, "127.0.0.1"
                )

        async def ipn():
            async with async_session_factory() as session:
                return await PaymentService(session).process_vnpay_ipn(
                    ipn_params, "127.0.0.1"
                )

        checkout_result, ipn_result = await asyncio.gather(
            checkout(), ipn(), return_exceptions=True
        )

        async with async_session_factory() as session:
            final_order = await session.scalar(
                select(PaymentOrder).where(
                    PaymentOrder.internal_order_id == internal_order_id
                )
            )
            final_sub = await session.get(Subscription, subscription.id)
            order_status = final_order.status
            sub_status = final_sub.status

        order_count, _, active_count = await _counts(user_id)
        return (
            checkout_result,
            ipn_result,
            order_status,
            sub_status,
            order_count,
            active_count,
        )

    (
        checkout_result,
        ipn_result,
        order_status,
        sub_status,
        order_count,
        active_count,
    ) = run(_run())

    # The IPN must succeed; a database deadlock would surface as a non-Conflict
    # exception here.
    assert isinstance(ipn_result, dict), ipn_result
    assert ipn_result["RspCode"] == "00", ipn_result

    # The checkout either reused the pending order or was refused as a renewal.
    if isinstance(checkout_result, Exception):
        assert isinstance(checkout_result, ConflictException), checkout_result

    assert order_status == PaymentOrderStatus.PAID
    assert sub_status == SubscriptionStatus.ACTIVE
    assert order_count == 1, f"expected 1 PaymentOrder, got {order_count}"
    assert active_count == 1, f"expected 1 ACTIVE Subscription, got {active_count}"
