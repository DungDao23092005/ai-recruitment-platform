"""Candidate VNPAY checkout and IPN activation integration tests."""

from __future__ import annotations

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
from app.domain.models.base import utc_now
from app.models import (
    CompanyMembership,
    EmailOutbox,
    PaymentOrder,
    PaymentTransaction,
    RecruitmentPlan,
    RecruiterProfile,
    Subscription,
    User,
)
from app.services.payment_providers.vnpay import VNPAYProvider
from app.services.subscription_email_service import EVENT_PAYMENT_RECEIPT
from app.services.subscription_service import SubscriptionService
from tests.integration.api.conftest import API_V1
from tests.integration.conftest import run

settings.VNPAY_TMN_CODE = "TESTTMN"
settings.VNPAY_HASH_SECRET = "testhashsecret123"


def _create_plan(
    *,
    price: int = 99_000,
    audience: PlanAudience = PlanAudience.CANDIDATE,
    is_free: bool = False,
    duration_days: int = 30,
    max_ai_features: int = 25,
    is_active: bool = True,
) -> RecruitmentPlan:
    async def _run():
        async with async_session_factory() as session:
            plan = RecruitmentPlan(
                name=f"Candidate Test Plan {uuid.uuid4().hex[:8]}",
                description="candidate payment test plan",
                price=price,
                currency="VND",
                duration_days=duration_days,
                max_job_posts=0,
                max_candidate_searches=10,
                max_ai_features=max_ai_features,
                plan_audience=audience,
                is_free=is_free,
                is_active=is_active,
                display_order=1,
            )
            session.add(plan)
            await session.commit()
            await session.refresh(plan)
            return plan

    return run(_run())


async def _load_candidate_user() -> User:
    async with async_session_factory() as session:
        user = await session.scalar(
            select(User).where(User.role == UserRole.CANDIDATE)
        )
        assert user is not None
        return user


def _candidate_user() -> User:
    return run(_load_candidate_user())


def _checkout(client, plan_id):
    return run(
        client.post(
            f"{API_V1}/payments/vnpay/create",
            json={"plan_id": str(plan_id)},
        )
    )


def _signed_ipn(
    *,
    internal_order_id: str,
    amount: int,
    response_code: str = "00",
    transaction_status: str = "00",
    transaction_no: str | None = None,
) -> dict[str, str]:
    provider = VNPAYProvider()
    params = {
        "vnp_TmnCode": settings.VNPAY_TMN_CODE,
        "vnp_Amount": str(amount * 100),
        "vnp_BankCode": "NCB",
        "vnp_BankTranNo": f"BANK{uuid.uuid4().hex[:8].upper()}",
        "vnp_CardType": "ATM",
        "vnp_PayDate": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        "vnp_OrderInfo": f"Thanh toan {internal_order_id}",
        "vnp_TransactionNo": transaction_no or uuid.uuid4().hex[:10],
        "vnp_ResponseCode": response_code,
        "vnp_TransactionStatus": transaction_status,
        "vnp_TxnRef": internal_order_id,
    }
    params["vnp_SecureHash"] = provider.generate_secure_hash(params)
    return params


def _send_ipn(client, params):
    return run(client.get(f"{API_V1}/payments/vnpay/ipn", params=params))


async def _load_payment_state(internal_order_id: str):
    async with async_session_factory() as session:
        order = await session.scalar(
            select(PaymentOrder).where(
                PaymentOrder.internal_order_id == internal_order_id
            )
        )
        assert order is not None
        subscription = await session.get(Subscription, order.subscription_id)
        user = await session.get(User, order.user_id)
        free = await session.scalar(
            select(Subscription).where(
                Subscription.user_id == order.user_id,
                Subscription.scope == SubscriptionScope.CANDIDATE_PERSONAL,
                Subscription.is_free == True,  # noqa: E712
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )
        profile = await session.scalar(
            select(RecruiterProfile).where(
                RecruiterProfile.user_id == order.user_id
            )
        )
        membership = await session.scalar(
            select(CompanyMembership).where(
                CompanyMembership.user_id == order.user_id
            )
        )
        company_sub_count = await session.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(
                Subscription.user_id == order.user_id,
                Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
            )
        )
        transaction_count = await session.scalar(
            select(func.count())
            .select_from(PaymentTransaction)
            .where(PaymentTransaction.payment_order_id == order.id)
        )
        receipt_count = await session.scalar(
            select(func.count())
            .select_from(EmailOutbox)
            .where(EmailOutbox.event_type == EVENT_PAYMENT_RECEIPT)
        )
        return (
            order,
            subscription,
            user,
            free,
            profile,
            membership,
            company_sub_count,
            transaction_count,
            receipt_count,
        )


def _load_payment_state_for(internal_order_id: str):
    return run(_load_payment_state(internal_order_id))


def _seed_active_candidate_paid(plan: RecruitmentPlan) -> None:
    async def _run():
        async with async_session_factory() as session:
            user = await session.scalar(
                select(User).where(User.role == UserRole.CANDIDATE)
            )
            assert user is not None
            now = utc_now()
            session.add(
                Subscription(
                    user_id=user.id,
                    plan_id=plan.id,
                    scope=SubscriptionScope.CANDIDATE_PERSONAL,
                    is_free=False,
                    status=SubscriptionStatus.ACTIVE,
                    started_at=now,
                    expires_at=now + timedelta(days=plan.duration_days),
                    max_job_posts=plan.max_job_posts,
                    max_candidate_searches=plan.max_candidate_searches or 0,
                    max_ai_features=plan.max_ai_features or 0,
                )
            )
            await session.commit()

    run(_run())


def _set_free_usage() -> None:
    async def _run():
        async with async_session_factory() as session:
            free = await session.scalar(
                select(Subscription).where(
                    Subscription.scope == SubscriptionScope.CANDIDATE_PERSONAL,
                    Subscription.is_free == True,  # noqa: E712
                    Subscription.status == SubscriptionStatus.ACTIVE,
                )
            )
            assert free is not None
            free.ai_features_used = 2
            free.current_period_key = "2026-11"
            await session.commit()

    run(_run())


class TestCandidateCheckout:
    def test_checkout_creates_candidate_personal_order_and_preserves_free(
        self, candidate_client
    ):
        plan = _create_plan()
        response = _checkout(candidate_client, plan.id)

        assert response.status_code == 201, response.text
        data = response.json()
        order, subscription, user, free, *_ = _load_payment_state_for(
            data["internal_order_id"]
        )

        assert order.scope == SubscriptionScope.CANDIDATE_PERSONAL
        assert order.company_id is None
        assert order.user_id == user.id
        assert order.plan_id == plan.id
        assert order.amount == plan.price
        assert order.currency == plan.currency
        assert order.status == PaymentOrderStatus.PENDING
        assert order.subscription_id == subscription.id

        assert subscription.scope == SubscriptionScope.CANDIDATE_PERSONAL
        assert subscription.is_free is False
        assert subscription.company_id is None
        assert subscription.status == SubscriptionStatus.PENDING
        assert subscription.user_id == user.id

        assert free is not None
        assert free.status == SubscriptionStatus.ACTIVE
        assert free.id != subscription.id

    def test_candidate_free_plan_is_rejected(self, candidate_client):
        async def _free_plan():
            async with async_session_factory() as session:
                return await session.scalar(
                    select(RecruitmentPlan).where(
                        RecruitmentPlan.plan_audience == PlanAudience.CANDIDATE,
                        RecruitmentPlan.is_free == True,  # noqa: E712
                        RecruitmentPlan.is_active == True,  # noqa: E712
                    )
                )

        free_plan = run(_free_plan())
        assert free_plan is not None

        response = _checkout(candidate_client, free_plan.id)
        assert response.status_code == 400

    def test_candidate_company_plan_is_rejected(self, candidate_client):
        company_plan = _create_plan(audience=PlanAudience.COMPANY)
        response = _checkout(candidate_client, company_plan.id)
        assert response.status_code == 403

    def test_platform_admin_personal_checkout_is_rejected(self, admin_client):
        plan = _create_plan()
        response = _checkout(admin_client, plan.id)
        assert response.status_code == 403

    def test_recruiter_candidate_plan_is_rejected(self, recruiter_client):
        plan = _create_plan()
        response = _checkout(recruiter_client, plan.id)
        assert response.status_code == 403

    def test_active_candidate_paid_blocks_checkout(self, candidate_client):
        plan = _create_plan()
        _seed_active_candidate_paid(plan)

        response = _checkout(candidate_client, plan.id)
        assert response.status_code == 409


class TestCandidateIPN:
    def test_ipn_activates_once_and_preserves_candidate_free(self, candidate_client):
        plan = _create_plan(duration_days=30, max_ai_features=25)
        _set_free_usage()
        checkout = _checkout(candidate_client, plan.id)
        assert checkout.status_code == 201, checkout.text
        data = checkout.json()

        params = _signed_ipn(
            internal_order_id=data["internal_order_id"],
            amount=plan.price,
        )
        first = _send_ipn(candidate_client, params)
        assert first.json()["RspCode"] == "00", first.text

        (
            order,
            subscription,
            user,
            free,
            profile,
            membership,
            company_sub_count,
            transaction_count,
            receipt_count,
        ) = _load_payment_state_for(data["internal_order_id"])

        assert order.status == PaymentOrderStatus.PAID
        assert subscription.status == SubscriptionStatus.ACTIVE
        assert subscription.scope == SubscriptionScope.CANDIDATE_PERSONAL
        assert subscription.is_free is False
        assert subscription.company_id is None
        assert subscription.current_period_key is None
        assert subscription.max_job_posts == plan.max_job_posts
        assert subscription.max_candidate_searches == (
            plan.max_candidate_searches or 0
        )
        assert subscription.max_ai_features == (plan.max_ai_features or 0)
        assert subscription.job_posts_used == 0
        assert subscription.candidate_searches_used == 0
        assert subscription.ai_features_used == 0
        assert subscription.started_at is not None
        assert subscription.expires_at is not None
        assert subscription.expires_at >= subscription.started_at + timedelta(
            days=29
        )
        assert subscription.expires_at <= subscription.started_at + timedelta(
            days=31
        )

        assert user.role == UserRole.CANDIDATE
        assert profile is None
        assert membership is None
        assert company_sub_count == 0

        assert free is not None
        assert free.status == SubscriptionStatus.ACTIVE
        assert free.ai_features_used == 2
        assert free.current_period_key == "2026-11"

        assert transaction_count == 1
        assert receipt_count == 1

        second = _send_ipn(candidate_client, params)
        assert second.json() == {"RspCode": "00", "Message": "Confirm Success"}
        (
            _,
            subscription,
            _,
            _,
            _,
            _,
            _,
            transaction_count,
            receipt_count,
        ) = _load_payment_state_for(data["internal_order_id"])
        assert subscription.ai_features_used == 0
        assert transaction_count == 1
        assert receipt_count == 1

    def test_wrong_amount_does_not_activate(self, candidate_client):
        plan = _create_plan()
        checkout = _checkout(candidate_client, plan.id)
        assert checkout.status_code == 201, checkout.text
        data = checkout.json()

        result = _send_ipn(
            candidate_client,
            _signed_ipn(
                internal_order_id=data["internal_order_id"],
                amount=plan.price + 1,
            ),
        )
        assert result.json()["RspCode"] == "04"

        order, subscription, *_ = _load_payment_state_for(
            data["internal_order_id"]
        )
        assert order.status == PaymentOrderStatus.PENDING
        assert subscription.status == SubscriptionStatus.PENDING

    def test_active_paid_conflict_records_payment_without_activation(
        self, candidate_client
    ):
        plan = _create_plan()
        _seed_active_candidate_paid(plan)
        user = _candidate_user()

        async def _create_pending_order():
            async with async_session_factory() as session:
                subscription = Subscription(
                    user_id=user.id,
                    plan_id=plan.id,
                    scope=SubscriptionScope.CANDIDATE_PERSONAL,
                    is_free=False,
                    status=SubscriptionStatus.PENDING,
                )
                session.add(subscription)
                await session.flush()
                order = PaymentOrder(
                    user_id=user.id,
                    plan_id=plan.id,
                    subscription_id=subscription.id,
                    scope=SubscriptionScope.CANDIDATE_PERSONAL,
                    amount=plan.price,
                    currency=plan.currency,
                    provider=PaymentProvider.VNPAY,
                    internal_order_id=f"VNPAY_CAND_CONFLICT_{uuid.uuid4().hex[:8]}",
                    status=PaymentOrderStatus.PENDING,
                    expired_at=utc_now() + timedelta(minutes=15),
                )
                session.add(order)
                await session.commit()
                await session.refresh(order)
                return order

        order = run(_create_pending_order())
        result = _send_ipn(
            candidate_client,
            _signed_ipn(
                internal_order_id=order.internal_order_id,
                amount=plan.price,
            ),
        )
        assert result.json()["RspCode"] == "00"
        assert "requires reconciliation" in result.json()["Message"]

        (
            paid_order,
            subscription,
            user,
            _,
            profile,
            membership,
            company_sub_count,
            transaction_count,
            receipt_count,
        ) = _load_payment_state_for(order.internal_order_id)
        assert paid_order.status == PaymentOrderStatus.PAID
        assert subscription.status == SubscriptionStatus.PENDING
        assert user.role == UserRole.CANDIDATE
        assert profile is None
        assert membership is None
        assert company_sub_count == 0
        assert transaction_count == 1
        assert receipt_count == 0


class TestCandidateSecondaryActivation:
    def test_subscription_service_does_not_promote_candidate(
        self, candidate_client
    ):
        plan = _create_plan()
        user = _candidate_user()

        async def _activate():
            async with async_session_factory() as session:
                subscription = Subscription(
                    user_id=user.id,
                    plan_id=plan.id,
                    scope=SubscriptionScope.CANDIDATE_PERSONAL,
                    is_free=False,
                    status=SubscriptionStatus.PENDING,
                )
                session.add(subscription)
                await session.commit()
                await session.refresh(subscription)
                subscription_id = subscription.id
                await SubscriptionService(session).activate_subscription(
                    subscription_id
                )
                return subscription_id

        subscription_id = run(_activate())

        async def _load():
            async with async_session_factory() as session:
                subscription = await session.get(Subscription, subscription_id)
                user_row = await session.get(User, user.id)
                profile = await session.scalar(
                    select(RecruiterProfile).where(
                        RecruiterProfile.user_id == user.id
                    )
                )
                assert subscription is not None
                assert user_row is not None
                return subscription, user_row, profile

        subscription, user_row, profile = run(_load())
        assert subscription.status == SubscriptionStatus.ACTIVE
        assert subscription.current_period_key is None
        assert user_row.role == UserRole.CANDIDATE
        assert profile is None
