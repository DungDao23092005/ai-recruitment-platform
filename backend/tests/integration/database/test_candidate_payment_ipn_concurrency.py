"""Candidate VNPAY duplicate/concurrent IPN integration test."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.database.session import async_session_factory
from app.domain.enums import (
    PaymentOrderStatus,
    PaymentProvider,
    PlanAudience,
    SubscriptionScope,
    SubscriptionStatus,
    UserRole,
)
from app.models import (
    EmailOutbox,
    PaymentOrder,
    PaymentTransaction,
    RecruitmentPlan,
    RecruiterProfile,
    Subscription,
    User,
)
from app.services.payment_providers.vnpay import VNPAYProvider
from app.services.payment_service import PaymentService
from app.services.subscription_email_service import EVENT_PAYMENT_RECEIPT
from tests.integration.conftest import run

pytestmark = pytest.mark.integration

settings.VNPAY_TMN_CODE = "TESTTMN"
settings.VNPAY_HASH_SECRET = "testhashsecret123"


def test_concurrent_duplicate_candidate_ipn_activates_once():
    async def _run():
        async with async_session_factory() as setup:
            now = datetime.now(timezone.utc)
            paid_plan = RecruitmentPlan(
                name=f"Candidate Paid {uuid.uuid4().hex[:8]}",
                description="candidate concurrency paid",
                price=99_000,
                currency="VND",
                duration_days=30,
                max_job_posts=0,
                max_candidate_searches=10,
                max_ai_features=25,
                plan_audience=PlanAudience.CANDIDATE,
                is_free=False,
                is_active=True,
                display_order=1,
            )
            free_plan = await setup.scalar(
                select(RecruitmentPlan).where(
                    RecruitmentPlan.plan_audience == PlanAudience.CANDIDATE,
                    RecruitmentPlan.is_free == True,  # noqa: E712 - MSSQL boolean
                    RecruitmentPlan.is_active == True,  # noqa: E712
                    RecruitmentPlan.is_deleted == False,  # noqa: E712
                )
            )
            if free_plan is None:
                free_plan = RecruitmentPlan(
                    name=f"Candidate Free {uuid.uuid4().hex[:8]}",
                    description="candidate concurrency free",
                    price=0,
                    currency="VND",
                    duration_days=30,
                    max_job_posts=0,
                    max_candidate_searches=0,
                    max_ai_features=3,
                    plan_audience=PlanAudience.CANDIDATE,
                    is_free=True,
                    is_active=True,
                    display_order=0,
                )
                setup.add(free_plan)
            setup.add(paid_plan)
            await setup.flush()

            user_email = (
                f"candidate-concurrent-{uuid.uuid4().hex[:8]}@example.com"
            )
            user = User(
                email=user_email,
                password_hash="hashed",
                role=UserRole.CANDIDATE,
            )
            setup.add(user)
            await setup.flush()

            free_subscription = Subscription(
                user_id=user.id,
                plan_id=free_plan.id,
                scope=SubscriptionScope.CANDIDATE_PERSONAL,
                is_free=True,
                status=SubscriptionStatus.ACTIVE,
                max_job_posts=0,
                max_candidate_searches=0,
                max_ai_features=3,
                ai_features_used=1,
                current_period_key="2026-11",
            )
            pending_subscription = Subscription(
                user_id=user.id,
                plan_id=paid_plan.id,
                scope=SubscriptionScope.CANDIDATE_PERSONAL,
                is_free=False,
                status=SubscriptionStatus.PENDING,
            )
            setup.add_all([free_subscription, pending_subscription])
            await setup.flush()

            internal_order_id = f"VNPAY_CAND_RACE_{uuid.uuid4().hex[:8]}"
            order = PaymentOrder(
                user_id=user.id,
                plan_id=paid_plan.id,
                subscription_id=pending_subscription.id,
                scope=SubscriptionScope.CANDIDATE_PERSONAL,
                amount=paid_plan.price,
                currency=paid_plan.currency,
                provider=PaymentProvider.VNPAY,
                internal_order_id=internal_order_id,
                status=PaymentOrderStatus.PENDING,
                created_at=now,
                expired_at=now + timedelta(minutes=15),
            )
            setup.add(order)
            await setup.commit()
            user_id = user.id
            user_email = user.email
            free_id = free_subscription.id
            pending_id = pending_subscription.id
            order_id = order.id

        provider = VNPAYProvider()
        ipn_params = {
            "vnp_TmnCode": settings.VNPAY_TMN_CODE,
            "vnp_Amount": str(paid_plan.price * 100),
            "vnp_BankCode": "NCB",
            "vnp_BankTranNo": "VNP123456",
            "vnp_CardType": "ATM",
            "vnp_PayDate": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
            "vnp_OrderInfo": "Candidate concurrent IPN",
            "vnp_TransactionNo": "CAND13524458",
            "vnp_ResponseCode": "00",
            "vnp_TransactionStatus": "00",
            "vnp_TxnRef": internal_order_id,
        }
        ipn_params["vnp_SecureHash"] = provider.generate_secure_hash(ipn_params)

        async with async_session_factory() as session_a:
            async with async_session_factory() as session_b:
                result_a, result_b = await asyncio.gather(
                    PaymentService(session_a).process_vnpay_ipn(
                        ipn_params, "127.0.0.1"
                    ),
                    PaymentService(session_b).process_vnpay_ipn(
                        ipn_params, "127.0.0.1"
                    ),
                )

        async with async_session_factory() as check:
            order = await check.get(PaymentOrder, order_id)
            paid_subscription = await check.get(Subscription, pending_id)
            free_subscription = await check.get(Subscription, free_id)
            user = await check.get(User, user_id)
            profile = await check.scalar(
                select(RecruiterProfile).where(
                    RecruiterProfile.user_id == user_id
                )
            )
            transaction_count = await check.scalar(
                select(func.count())
                .select_from(PaymentTransaction)
                .where(PaymentTransaction.payment_order_id == order_id)
            )
            receipt_count = await check.scalar(
                select(func.count())
                .select_from(EmailOutbox)
                .where(
                    EmailOutbox.event_type == EVENT_PAYMENT_RECEIPT,
                    EmailOutbox.to_email == user_email,
                )
            )

        return (
            result_a,
            result_b,
            order,
            paid_subscription,
            free_subscription,
            user,
            profile,
            transaction_count,
            receipt_count,
        )

    (
        result_a,
        result_b,
        order,
        paid_subscription,
        free_subscription,
        user,
        profile,
        transaction_count,
        receipt_count,
    ) = run(_run())

    assert result_a["RspCode"] == "00"
    assert result_b["RspCode"] == "00"
    assert order.status == PaymentOrderStatus.PAID
    assert paid_subscription.status == SubscriptionStatus.ACTIVE
    assert paid_subscription.scope == SubscriptionScope.CANDIDATE_PERSONAL
    assert paid_subscription.is_free is False
    assert paid_subscription.company_id is None
    assert paid_subscription.current_period_key is None
    assert paid_subscription.ai_features_used == 0
    assert user.role == UserRole.CANDIDATE
    assert profile is None
    assert free_subscription.status == SubscriptionStatus.ACTIVE
    assert free_subscription.ai_features_used == 1
    assert free_subscription.current_period_key == "2026-11"
    assert transaction_count == 1
    assert receipt_count == 1
