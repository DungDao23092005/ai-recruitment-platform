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
    PlanAudience,
    SubscriptionScope,
    SubscriptionStatus,
    UserRole,
)
from app.models import PaymentOrder, RecruitmentPlan, Subscription, User
from app.services.payment_providers.vnpay import VNPAYProvider
from app.services.payment_service import PaymentService
from tests.integration.conftest import run


pytestmark = pytest.mark.integration


async def _make_plan(
    session,
    *,
    price: int = 299_000,
    name: str = "Plan",
    plan_audience: PlanAudience = PlanAudience.CANDIDATE,
    is_free: bool = False,
) -> RecruitmentPlan:
    plan = RecruitmentPlan(
        id=uuid4(),
        name=name,
        description="concurrency plan",
        price=price,
        currency="VND",
        duration_days=30,
        max_job_posts=5,
        plan_audience=plan_audience,
        is_free=is_free,
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
                scope=SubscriptionScope.CANDIDATE_PERSONAL,
                is_free=False,
                status=SubscriptionStatus.PENDING,
            )
            setup.add(subscription)
            await setup.flush()
            order = PaymentOrder(
                id=uuid4(),
                user_id=user.id,
                plan_id=pending_plan.id,
                subscription_id=subscription.id,
                scope=SubscriptionScope.CANDIDATE_PERSONAL,
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
                scope=SubscriptionScope.CANDIDATE_PERSONAL,
                is_free=False,
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
                scope=SubscriptionScope.CANDIDATE_PERSONAL,
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


# ============================================================================
# Wave 1.4 Phase 2: Company Checkout Concurrency & Locking (P23-P28, P40)
# ============================================================================

from unittest.mock import patch
from app.domain.enums import MembershipRole
from app.domain.models.base import utc_now
from tests.integration.company_billing_helpers import (
    _build_signed_ipn,
    _create_company,
    _create_company_subscription,
    _create_membership,
    _create_plan,
    _create_user,
)


def test_p23_stale_cleanup_commits_and_releases_lock_before_tx2_reacquires(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan_old = await _create_plan(session, price=300_000)
            plan_new = await _create_plan(session, price=600_000)
            now = utc_now()
            stale_sub = await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan_old.id,
                status=SubscriptionStatus.PENDING,
            )
            stale_order = PaymentOrder(
                user_id=user.id,
                company_id=company.id,
                scope=SubscriptionScope.COMPANY_RECRUITING,
                plan_id=plan_old.id,
                subscription_id=stale_sub.id,
                amount=plan_old.price,
                currency="VND",
                provider=PaymentProvider.VNPAY,
                internal_order_id=f"STALE-{uuid4().hex[:8]}",
                status=PaymentOrderStatus.PENDING,
                created_at=now - timedelta(minutes=30),
                expired_at=now - timedelta(minutes=15),
            )
            session.add(stale_order)
            await session.commit()
            user_id, company_id, plan_new_id = user.id, company.id, plan_new.id
            stale_order_id, stale_sub_id = stale_order.id, stale_sub.id

        async with async_session_factory() as session:
            _, ref_new, sub_new_id = await PaymentService(
                session
            ).create_company_vnpay_payment(
                user_id=user_id,
                company_id=company_id,
                plan_id=plan_new_id,
                client_ip="127.0.0.1",
            )

        async with async_session_factory() as check:
            so = await check.get(PaymentOrder, stale_order_id)
            ss = await check.get(Subscription, stale_sub_id)
            no = await check.scalar(
                select(PaymentOrder).where(
                    PaymentOrder.internal_order_id == ref_new
                )
            )
            assert so.status == PaymentOrderStatus.EXPIRED
            assert ss.status == SubscriptionStatus.CANCELLED
            assert no.status == PaymentOrderStatus.PENDING

    run_async(_run())


def test_p24_concurrent_company_checkout_interleaving_creates_single_order(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session)
            await session.commit()
            user_id, company_id, plan_id = user.id, company.id, plan.id

        async def _checkout():
            async with async_session_factory() as s:
                return await PaymentService(s).create_company_vnpay_payment(
                    user_id=user_id,
                    company_id=company_id,
                    plan_id=plan_id,
                    client_ip="127.0.0.1",
                )

        res_a, res_b = await asyncio.gather(_checkout(), _checkout())
        assert res_a[1] == res_b[1]
        assert res_a[2] == res_b[2]

        async with async_session_factory() as check:
            count = await check.scalar(
                select(func.count())
                .select_from(PaymentOrder)
                .where(PaymentOrder.company_id == company_id)
            )
            assert count == 1

    run_async(_run())


def test_p25_concurrent_ipn_activation_conflict_returns_409_or_serializes(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session)
            await session.commit()
            user_id, company_id, plan_id = user.id, company.id, plan.id

        async with async_session_factory() as session:
            _, internal_order_id, _ = await PaymentService(
                session
            ).create_company_vnpay_payment(
                user_id=user_id,
                company_id=company_id,
                plan_id=plan_id,
                client_ip="127.0.0.1",
            )

        # Now seed an already-ACTIVE subscription for the same company to force a conflict on activation
        async with async_session_factory() as session:
            await _create_company_subscription(
                session,
                company_id=company_id,
                user_id=user_id,
                plan_id=plan_id,
                status=SubscriptionStatus.ACTIVE,
            )
            await session.commit()

        ipn_params = _build_signed_ipn(
            internal_order_id=internal_order_id, amount_vnd=500_000
        )
        async with async_session_factory() as s_ipn:
            with pytest.raises(ConflictException):
                await PaymentService(s_ipn).process_vnpay_ipn(
                    ipn_params, "127.0.0.1"
                )

    run_async(_run())


def test_p26_same_company_same_plan_reuses_single_unexpired_pending_order(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session)
            await session.commit()
            user_id, company_id, plan_id = user.id, company.id, plan.id

        async with async_session_factory() as s1:
            _, ref1, id1 = await PaymentService(
                s1
            ).create_company_vnpay_payment(
                user_id=user_id,
                company_id=company_id,
                plan_id=plan_id,
                client_ip="127.0.0.1",
            )
        async with async_session_factory() as s2:
            _, ref2, id2 = await PaymentService(
                s2
            ).create_company_vnpay_payment(
                user_id=user_id,
                company_id=company_id,
                plan_id=plan_id,
                client_ip="127.0.0.1",
            )
        assert ref1 == ref2
        assert id1 == id2

    run_async(_run())


def test_p27_same_company_different_plan_rejects_with_409_conflict(run_async):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan_a = await _create_plan(session, price=300_000)
            plan_b = await _create_plan(session, price=600_000)
            await session.commit()
            user_id, company_id = user.id, company.id
            plan_a_id, plan_b_id = plan_a.id, plan_b.id

        async with async_session_factory() as s1:
            await PaymentService(s1).create_company_vnpay_payment(
                user_id=user_id,
                company_id=company_id,
                plan_id=plan_a_id,
                client_ip="127.0.0.1",
            )
        async with async_session_factory() as s2:
            with pytest.raises(ConflictException):
                await PaymentService(s2).create_company_vnpay_payment(
                    user_id=user_id,
                    company_id=company_id,
                    plan_id=plan_b_id,
                    client_ip="127.0.0.1",
                )

    run_async(_run())


def test_p28_multiple_unexpired_pending_orders_trigger_integrity_error(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session)
            now = utc_now()
            sub1 = await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
                status=SubscriptionStatus.PENDING,
            )
            sub2 = await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
                status=SubscriptionStatus.PENDING,
            )
            for idx, s in enumerate((sub1, sub2)):
                session.add(
                    PaymentOrder(
                        user_id=user.id,
                        company_id=company.id,
                        scope=SubscriptionScope.COMPANY_RECRUITING,
                        plan_id=plan.id,
                        subscription_id=s.id,
                        amount=plan.price,
                        currency="VND",
                        provider=PaymentProvider.VNPAY,
                        internal_order_id=f"DUP-{idx}-{uuid4().hex[:6]}",
                        status=PaymentOrderStatus.PENDING,
                        created_at=now,
                        expired_at=now + timedelta(minutes=15),
                    )
                )
            await session.commit()
            user_id, company_id, plan_id = user.id, company.id, plan.id

        async with async_session_factory() as s:
            with pytest.raises(RuntimeError, match="Integrity error"):
                await PaymentService(s).create_company_vnpay_payment(
                    user_id=user_id,
                    company_id=company_id,
                    plan_id=plan_id,
                    client_ip="127.0.0.1",
                )

    run_async(_run())


def test_p40_company_checkout_uses_applock_and_legacy_checkout_preserves_user_lock(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session, price=500_000)
            await session.commit()
            user_id, company_id, plan_id = user.id, company.id, plan.id

        async with async_session_factory() as s_co:
            svc_co = PaymentService(s_co)
            with patch.object(
                svc_co,
                "_acquire_company_applock",
                wraps=svc_co._acquire_company_applock,
            ) as spy_applock:
                await svc_co.create_company_vnpay_payment(
                    user_id=user_id,
                    company_id=company_id,
                    plan_id=plan_id,
                    client_ip="127.0.0.1",
                )
                assert spy_applock.await_count >= 1

        async with async_session_factory() as s_leg:
            svc_leg = PaymentService(s_leg)
            with patch.object(
                svc_leg, "_lock_user", wraps=svc_leg._lock_user
            ) as spy_user_lock:
                await svc_leg.create_vnpay_payment(
                    user_id=user_id,
                    plan_id=plan_id,
                    client_ip="127.0.0.1",
                )
                assert spy_user_lock.await_count >= 1

    run_async(_run())
