"""Real SQL Server integration tests for subscription activation notifications.

Proves that the one-time ``subscription_activated`` notification is created
exactly once for each genuine PENDING -> ACTIVE transition, in the same
transaction as the activation, across the supported activation pathways:

- VNPAY IPN success
- VNPAY QueryDr reconciliation (shared finalize path)
- Direct / admin provisioning (SubscriptionService.activate_subscription)

and that it is NOT created when the payment is PAID but the subscription stays
PENDING (activation refused), nor when Redis publishing fails.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.core.config import settings

# Configure VNPAY test settings BEFORE importing the provider/service.
settings.VNPAY_TMN_CODE = "TESTTMN"
settings.VNPAY_HASH_SECRET = "testhashsecret123"

from app.core.exceptions import InvalidTransitionException  # noqa: E402
from app.database.session import async_session_factory  # noqa: E402
from app.domain.enums import (  # noqa: E402
    PaymentOrderStatus,
    PaymentProvider,
    SubscriptionStatus,
    UserRole,
)
from app.models import (  # noqa: E402
    Notification,
    PaymentOrder,
    RecruitmentPlan,
    Subscription,
    User,
)
from app.services.notification_service import VIETNAM_TZ  # noqa: E402
from app.services.payment_providers.vnpay import VNPAYProvider  # noqa: E402
from app.services.payment_service import PaymentService  # noqa: E402
from app.services.subscription_service import SubscriptionService  # noqa: E402


pytestmark = pytest.mark.integration

ACTIVATION_TYPE = "subscription_activated"


async def _count_activation_notifications(session, user_id: uuid.UUID) -> int:
    stmt = select(func.count(Notification.id)).where(
        Notification.user_id == user_id,
        Notification.notification_type == ACTIVATION_TYPE,
        Notification.is_deleted == False,  # noqa: E712
    )
    return (await session.execute(stmt)).scalar_one()


async def _get_activation_notification(session, user_id: uuid.UUID) -> Notification | None:
    stmt = select(Notification).where(
        Notification.user_id == user_id,
        Notification.notification_type == ACTIVATION_TYPE,
        Notification.is_deleted == False,  # noqa: E712
    )
    return (await session.execute(stmt)).scalars().first()


async def _seed(session, *, plan_name="Professional", price=299_000, duration_days=30):
    plan = RecruitmentPlan(
        name=plan_name,
        price=price,
        currency="VND",
        duration_days=duration_days,
        max_job_posts=10,
        max_candidate_searches=10,
        max_ai_features=10,
        is_active=True,
        display_order=1,
    )
    user = User(
        email=f"notif-{uuid.uuid4()}@example.com",
        password_hash="hash",
        role=UserRole.CANDIDATE,
    )
    session.add_all([plan, user])
    await session.flush()
    return plan, user


async def _seed_pending_subscription(session, user, plan):
    sub = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.PENDING,
    )
    session.add(sub)
    await session.flush()
    return sub


async def _seed_pending_order(session, user, plan, sub, internal_order_id: str):
    order = PaymentOrder(
        user_id=user.id,
        plan_id=plan.id,
        subscription_id=sub.id,
        amount=plan.price,
        currency="VND",
        provider=PaymentProvider.VNPAY,
        internal_order_id=internal_order_id,
        status=PaymentOrderStatus.PENDING,
        expired_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    session.add(order)
    await session.flush()
    return order


def _ipn_params(order: PaymentOrder, provider: VNPAYProvider, txn_no: str = "13524458") -> dict:
    params = {
        "vnp_TmnCode": settings.VNPAY_TMN_CODE,
        "vnp_Amount": str(order.amount * 100),
        "vnp_BankCode": "NCB",
        "vnp_BankTranNo": "VNP123456",
        "vnp_CardType": "ATM",
        "vnp_PayDate": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        "vnp_OrderInfo": "Test activation",
        "vnp_TransactionNo": txn_no,
        "vnp_ResponseCode": "00",
        "vnp_TransactionStatus": "00",
        "vnp_TxnRef": order.internal_order_id,
    }
    params["vnp_SecureHash"] = provider.generate_secure_hash(params)
    return params


def test_ipn_activation_creates_exactly_one_notification(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan, user = await _seed(setup)
            sub = await _seed_pending_subscription(setup, user, plan)
            order = await _seed_pending_order(
                setup, user, plan, sub, "VNPAY_NOTIF_IPN_001"
            )
            await setup.commit()
            user_id, sub_id, plan_name = user.id, sub.id, plan.name

        provider = VNPAYProvider()
        async with async_session_factory() as session:
            params = _ipn_params(order, provider)
            result = await PaymentService(session).process_vnpay_ipn(params, "127.0.0.1")
            assert result["RspCode"] == "00", result

        async with async_session_factory() as check:
            count = await _count_activation_notifications(check, user_id)
            assert count == 1, f"expected exactly 1 activation notification, got {count}"
            notif = await _get_activation_notification(check, user_id)
            assert notif is not None
            assert notif.title == "Kích hoạt gói dịch vụ thành công"
            assert notif.entity_type == "subscription"
            assert notif.entity_id == sub_id
            assert plan_name in notif.content

    run_async(_run())


def test_duplicate_ipn_does_not_duplicate_notification(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan, user = await _seed(setup)
            sub = await _seed_pending_subscription(setup, user, plan)
            order = await _seed_pending_order(
                setup, user, plan, sub, "VNPAY_NOTIF_IPN_002"
            )
            await setup.commit()
            user_id = user.id

        provider = VNPAYProvider()
        params = _ipn_params(order, provider)
        async with async_session_factory() as session:
            svc = PaymentService(session)
            first = await svc.process_vnpay_ipn(params, "127.0.0.1")
            second = await svc.process_vnpay_ipn(params, "127.0.0.1")
            assert first["RspCode"] == "00"
            assert second["RspCode"] == "00"

        async with async_session_factory() as check:
            count = await _count_activation_notifications(check, user_id)
            assert count == 1, f"duplicate IPN produced {count} notifications"

    run_async(_run())


def test_concurrent_duplicate_ipn_creates_single_notification(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan, user = await _seed(setup)
            sub = await _seed_pending_subscription(setup, user, plan)
            order = await _seed_pending_order(
                setup, user, plan, sub, "VNPAY_NOTIF_IPN_003"
            )
            await setup.commit()
            user_id = user.id

        provider = VNPAYProvider()
        params = _ipn_params(order, provider)

        async with async_session_factory() as session_a, async_session_factory() as session_b:
            service_a = PaymentService(session_a)
            service_b = PaymentService(session_b)
            result_a, result_b = await asyncio.gather(
                service_a.process_vnpay_ipn(params, "127.0.0.1"),
                service_b.process_vnpay_ipn(params, "127.0.0.1"),
            )
            assert result_a["RspCode"] == "00", result_a
            assert result_b["RspCode"] == "00", result_b

        async with async_session_factory() as check:
            count = await _count_activation_notifications(check, user_id)
            assert count == 1, f"concurrent duplicate IPN produced {count} notifications"

    run_async(_run())


def test_querydr_finalize_after_ipn_does_not_duplicate_notification(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan, user = await _seed(setup)
            sub = await _seed_pending_subscription(setup, user, plan)
            order = await _seed_pending_order(
                setup, user, plan, sub, "VNPAY_NOTIF_IPN_004"
            )
            await setup.commit()
            user_id, order_id = user.id, order.id

        provider = VNPAYProvider()
        async with async_session_factory() as session:
            svc = PaymentService(session)
            ipn = await svc.process_vnpay_ipn(_ipn_params(order, provider), "127.0.0.1")
            assert ipn["RspCode"] == "00"

        # Simulate the QueryDr reconciliation finalize on the now-PAID order. It
        # must observe PAID under the order lock and bail out without notifying.
        async with async_session_factory() as session:
            svc = PaymentService(session)
            locked = await svc.payment_orders.get_by_internal_order_id(
                "VNPAY_NOTIF_IPN_004"
            )
            assert locked is not None and locked.id == order_id
            await svc._finalize_reconciled_success(locked, {})

        async with async_session_factory() as check:
            count = await _count_activation_notifications(check, user_id)
            assert count == 1, f"QueryDr after IPN produced {count} notifications"

    run_async(_run())


def test_paid_order_without_activation_creates_no_success_notification(run_async):
    """PAID order + PENDING subscription (activation refused) => no success notification."""

    async def _run():
        async with async_session_factory() as setup:
            high_plan, user = await _seed(setup, plan_name="Enterprise", price=999_000)
            # Existing ACTIVE subscription on the high-tier plan.
            active = Subscription(
                user_id=user.id,
                plan_id=high_plan.id,
                status=SubscriptionStatus.ACTIVE,
                started_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                max_job_posts=10,
            )
            setup.add(active)
            # A cheaper plan checkout: activation would be a downgrade -> refused.
            low_plan = RecruitmentPlan(
                name="Starter",
                price=99_000,
                currency="VND",
                duration_days=30,
                max_job_posts=1,
                is_active=True,
                display_order=2,
            )
            setup.add(low_plan)
            await setup.flush()
            sub = await _seed_pending_subscription(setup, user, low_plan)
            order = await _seed_pending_order(
                setup, user, low_plan, sub, "VNPAY_NOTIF_IPN_005"
            )
            await setup.commit()
            user_id, sub_id = user.id, sub.id

        provider = VNPAYProvider()
        async with async_session_factory() as session:
            result = await PaymentService(session).process_vnpay_ipn(
                _ipn_params(order, provider), "127.0.0.1"
            )
            assert result["RspCode"] == "00", result

        async with async_session_factory() as check:
            # Payment recorded as PAID...
            order_row = await check.get(PaymentOrder, order.id)
            assert order_row.status == PaymentOrderStatus.PAID
            # ...but the subscription stayed PENDING...
            sub_row = await check.get(Subscription, sub_id)
            assert sub_row.status == SubscriptionStatus.PENDING
            # ...and no activation success notification was emitted.
            count = await _count_activation_notifications(check, user_id)
            assert count == 0, f"expected no activation notification, got {count}"

    run_async(_run())


def test_direct_activation_creates_one_notification_and_repeat_is_idempotent(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan, user = await _seed(setup)
            sub = await _seed_pending_subscription(setup, user, plan)
            await setup.commit()
            user_id, sub_id, plan_name = user.id, sub.id, plan.name

        async with async_session_factory() as session:
            await SubscriptionService(session).activate_subscription(sub_id)

        async with async_session_factory() as check:
            count = await _count_activation_notifications(check, user_id)
            assert count == 1, f"direct activation produced {count} notifications"
            notif = await _get_activation_notification(check, user_id)
            assert notif is not None
            assert notif.title == "Kích hoạt gói dịch vụ thành công"
            assert notif.entity_type == "subscription"
            assert notif.entity_id == sub_id
            assert plan_name in notif.content
            sub_row = await check.get(Subscription, sub_id)
            assert sub_row.status == SubscriptionStatus.ACTIVE

        # A repeat activation must raise and must not create a second notification.
        async with async_session_factory() as session:
            with pytest.raises(InvalidTransitionException):
                await SubscriptionService(session).activate_subscription(sub_id)

        async with async_session_factory() as check:
            count = await _count_activation_notifications(check, user_id)
            assert count == 1, f"repeat activation produced {count} notifications"

    run_async(_run())


def test_concurrent_direct_activation_creates_single_notification(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan, user = await _seed(setup)
            sub = await _seed_pending_subscription(setup, user, plan)
            await setup.commit()
            user_id, sub_id = user.id, sub.id

        async def _activate():
            async with async_session_factory() as session:
                return await SubscriptionService(session).activate_subscription(sub_id)

        results = await asyncio.gather(_activate(), _activate(), return_exceptions=True)
        successes = [r for r in results if not isinstance(r, Exception)]
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(successes) == 1, f"expected 1 success, got {results}"
        assert len(exceptions) == 1, f"expected 1 failure, got {results}"
        assert isinstance(exceptions[0], InvalidTransitionException)

        async with async_session_factory() as check:
            count = await _count_activation_notifications(check, user_id)
            assert count == 1, f"concurrent direct activation produced {count} notifications"

    run_async(_run())


def test_activation_rollback_leaves_no_notification(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan, user = await _seed(setup)
            sub = await _seed_pending_subscription(setup, user, plan)
            await setup.commit()
            user_id, sub_id = user.id, sub.id

        async with async_session_factory() as session:
            service = SubscriptionService(session)
            with patch.object(
                session, "commit", new=AsyncMock(side_effect=RuntimeError("db down"))
            ):
                with pytest.raises(RuntimeError):
                    await service.activate_subscription(sub_id)

        async with async_session_factory() as check:
            count = await _count_activation_notifications(check, user_id)
            assert count == 0, f"rolled-back activation left {count} notifications"
            sub_row = await check.get(Subscription, sub_id)
            assert sub_row.status == SubscriptionStatus.PENDING

    run_async(_run())


def test_redis_publish_failure_does_not_break_activation(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan, user = await _seed(setup)
            sub = await _seed_pending_subscription(setup, user, plan)
            await setup.commit()
            user_id, sub_id = user.id, sub.id

        from app.core.pubsub import pubsub_manager

        with patch.object(
            pubsub_manager,
            "publish",
            new=AsyncMock(side_effect=RuntimeError("redis down")),
        ):
            async with async_session_factory() as session:
                await SubscriptionService(session).activate_subscription(sub_id)

        async with async_session_factory() as check:
            sub_row = await check.get(Subscription, sub_id)
            assert sub_row.status == SubscriptionStatus.ACTIVE
            count = await _count_activation_notifications(check, user_id)
            assert count == 1, f"expected notification to persist despite Redis failure, got {count}"

    run_async(_run())
