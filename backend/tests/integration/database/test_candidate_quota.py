"""Candidate AI quota priority, lazy reset and period-boundary release."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.core.exceptions import CandidateQuotaExhaustedException
from app.database.session import async_session_factory
from app.domain.enums import (
    PlanAudience,
    SubscriptionScope,
    SubscriptionStatus,
    SubscriptionUsageFeatureType,
    SubscriptionUsageStatus,
    UserRole,
)
from app.domain.models.base import utc_now
from app.models import Notification, Subscription, SubscriptionUsage
from app.services.candidate_entitlement_service import CandidateEntitlementService
from app.services.quota_enforcement_service import QuotaEnforcementService
from app.services.subscription_service import SubscriptionService
from tests.integration.company_billing_helpers import (
    _create_plan,
    _create_user,
)

pytestmark = pytest.mark.integration


async def _create_candidate_free_subscription(
    session,
    *,
    user_id: uuid.UUID,
    plan_id: uuid.UUID,
    max_ai_features: int,
    used: int = 0,
    period_key: str | None = None,
) -> Subscription:
    now = utc_now()
    subscription = Subscription(
        user_id=user_id,
        company_id=None,
        plan_id=plan_id,
        scope=SubscriptionScope.CANDIDATE_PERSONAL,
        is_free=True,
        current_period_key=period_key
        or CandidateEntitlementService.candidate_period_key(now),
        status=SubscriptionStatus.ACTIVE,
        started_at=now,
        expires_at=None,
        max_job_posts=0,
        max_candidate_searches=0,
        max_ai_features=max_ai_features,
        job_posts_used=0,
        candidate_searches_used=0,
        ai_features_used=used,
    )
    session.add(subscription)
    await session.flush()
    return subscription


async def _create_candidate_paid_subscription(
    session,
    *,
    user_id: uuid.UUID,
    plan_id: uuid.UUID,
    max_ai_features: int,
    used: int = 0,
    expires_at=None,
) -> Subscription:
    now = utc_now()
    subscription = Subscription(
        user_id=user_id,
        company_id=None,
        plan_id=plan_id,
        scope=SubscriptionScope.CANDIDATE_PERSONAL,
        is_free=False,
        current_period_key=None,
        status=SubscriptionStatus.ACTIVE,
        started_at=now,
        expires_at=expires_at or now + timedelta(days=30),
        max_job_posts=0,
        max_candidate_searches=0,
        max_ai_features=max_ai_features,
        job_posts_used=0,
        candidate_searches_used=0,
        ai_features_used=used,
    )
    session.add(subscription)
    await session.flush()
    return subscription


async def _create_candidate_free_plan(session, max_ai_features: int):
    return await _create_plan(
        session,
        audience=PlanAudience.CANDIDATE,
        is_free=True,
        max_job_posts=0,
        max_candidate_searches=0,
        max_ai_features=max_ai_features,
        duration_days=30,
    )


def test_free_reservation_uses_current_vietnam_period(run_async):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session, role=UserRole.CANDIDATE)
            plan = await _create_candidate_free_plan(session, max_ai_features=2)
            subscription = await _create_candidate_free_subscription(
                session,
                user_id=user.id,
                plan_id=plan.id,
                max_ai_features=2,
            )
            await session.commit()
            user_id, subscription_id = user.id, subscription.id

        async with async_session_factory() as session:
            quota = QuotaEnforcementService(session)
            result = await quota.reserve_candidate_ai_quota(
                candidate_id=user_id,
                feature_type=SubscriptionUsageFeatureType.CANDIDATE_PARSE_RESUME,
            )
            await session.commit()

        assert result.remaining == 1

        async with async_session_factory() as session:
            subscription = await session.get(Subscription, subscription_id)
            usage = await session.scalar(
                select(SubscriptionUsage).where(
                    SubscriptionUsage.subscription_id == subscription_id
                )
            )
            assert subscription.ai_features_used == 1
            assert usage is not None
            assert usage.period_key == subscription.current_period_key
            assert usage.scope == SubscriptionScope.CANDIDATE_PERSONAL
            assert usage.company_id is None
            assert usage.status == SubscriptionUsageStatus.RESERVED

    run_async(_run())


def test_active_paid_is_used_first_and_exhaustion_never_falls_back_to_free(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session, role=UserRole.CANDIDATE)
            free_plan = await _create_candidate_free_plan(
                session, max_ai_features=10
            )
            paid_plan = await _create_plan(
                session,
                audience=PlanAudience.CANDIDATE,
                is_free=False,
                max_job_posts=0,
                max_candidate_searches=0,
                max_ai_features=1,
            )
            free = await _create_candidate_free_subscription(
                session,
                user_id=user.id,
                plan_id=free_plan.id,
                max_ai_features=10,
            )
            paid = await _create_candidate_paid_subscription(
                session,
                user_id=user.id,
                plan_id=paid_plan.id,
                max_ai_features=1,
                used=1,
            )
            await session.commit()
            user_id, free_id, paid_id = user.id, free.id, paid.id

        async with async_session_factory() as session:
            quota = QuotaEnforcementService(session)
            with pytest.raises(CandidateQuotaExhaustedException) as raised:
                await quota.reserve_candidate_ai_quota(
                    candidate_id=user_id,
                    feature_type=SubscriptionUsageFeatureType.CANDIDATE_CHAT,
                )

        assert raised.value.is_free is False
        assert raised.value.subscription_id == paid_id
        assert raised.value.plan_name is not None

        async with async_session_factory() as session:
            free = await session.get(Subscription, free_id)
            paid = await session.get(Subscription, paid_id)
            assert free.ai_features_used == 0
            assert paid.ai_features_used == 1
            count = await session.scalar(
                select(SubscriptionUsage.id).where(
                    SubscriptionUsage.subscription_id.in_(
                        [free_id, paid_id]
                    )
                )
            )
            assert count is None

    run_async(_run())


def test_free_entitlement_lazily_resets_stale_period_before_reserving(run_async):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session, role=UserRole.CANDIDATE)
            plan = await _create_candidate_free_plan(session, max_ai_features=2)
            subscription = await _create_candidate_free_subscription(
                session,
                user_id=user.id,
                plan_id=plan.id,
                max_ai_features=2,
                used=2,
                period_key="2000-01",
            )
            await session.commit()
            user_id, subscription_id = user.id, subscription.id

        async with async_session_factory() as session:
            quota = QuotaEnforcementService(session)
            result = await quota.reserve_candidate_ai_quota(
                candidate_id=user_id,
                feature_type=SubscriptionUsageFeatureType.CANDIDATE_JOB_RECOMMENDATIONS,
            )
            await session.commit()

        current_period = CandidateEntitlementService.candidate_period_key(
            utc_now()
        )
        assert result.remaining == 1

        async with async_session_factory() as session:
            subscription = await session.get(Subscription, subscription_id)
            assert subscription.ai_features_used == 1
            assert subscription.current_period_key == current_period

    run_async(_run())


def test_release_of_stale_period_does_not_decrement_new_month_counter(run_async):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session, role=UserRole.CANDIDATE)
            plan = await _create_candidate_free_plan(session, max_ai_features=2)
            subscription = await _create_candidate_free_subscription(
                session,
                user_id=user.id,
                plan_id=plan.id,
                max_ai_features=2,
            )
            await session.commit()
            user_id, subscription_id = user.id, subscription.id

        async with async_session_factory() as session:
            quota = QuotaEnforcementService(session)
            old_reservation = await quota.reserve_candidate_ai_quota(
                candidate_id=user_id,
                feature_type=SubscriptionUsageFeatureType.CANDIDATE_CHAT,
            )
            await session.commit()
            old_usage_id = old_reservation.usage_id

        # Simulate the monthly worker advancing the period and zeroing usage.
        async with async_session_factory() as session:
            await session.execute(
                update(Subscription)
                .where(Subscription.id == subscription_id)
                .values(
                    ai_features_used=0,
                    current_period_key="2999-12",
                )
            )
            await session.commit()

        async with async_session_factory() as session:
            quota = QuotaEnforcementService(session)
            released = await quota.release_reservation(old_usage_id)
            await session.commit()
        assert released is True

        async with async_session_factory() as session:
            subscription = await session.get(Subscription, subscription_id)
            old_usage = await session.get(SubscriptionUsage, old_usage_id)
            assert subscription.ai_features_used == 0
            assert old_usage.status == SubscriptionUsageStatus.FAILED

        # The artificially advanced period is still usable and starts at 1.
        async with async_session_factory() as session:
            quota = QuotaEnforcementService(session)
            result = await quota.reserve_candidate_ai_quota(
                candidate_id=user_id,
                feature_type=SubscriptionUsageFeatureType.CANDIDATE_CHAT,
            )
            await session.commit()
        assert result.remaining == 1

    run_async(_run())


def test_expired_candidate_paid_notifies_once_and_returns_to_existing_free(run_async):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session, role=UserRole.CANDIDATE)
            free_plan = await _create_candidate_free_plan(
                session, max_ai_features=3
            )
            paid_plan = await _create_plan(
                session,
                audience=PlanAudience.CANDIDATE,
                is_free=False,
                max_job_posts=0,
                max_candidate_searches=0,
                max_ai_features=5,
            )
            await _create_candidate_free_subscription(
                session,
                user_id=user.id,
                plan_id=free_plan.id,
                max_ai_features=3,
            )
            paid = await _create_candidate_paid_subscription(
                session,
                user_id=user.id,
                plan_id=paid_plan.id,
                max_ai_features=5,
                expires_at=utc_now() - timedelta(minutes=1),
            )
            await session.commit()
            user_id, paid_id = user.id, paid.id

        async with async_session_factory() as session:
            expired = await SubscriptionService(
                session
            ).check_and_expire_subscriptions(limit=10)

        assert expired == 1

        async with async_session_factory() as session:
            paid = await session.get(Subscription, paid_id)
            notifications = (
                await session.scalars(
                    select(Notification).where(
                        Notification.user_id == user_id,
                        Notification.notification_type
                        == "candidate_returned_to_free",
                        Notification.entity_id == paid_id,
                    )
                )
            ).all()
            assert paid.status == SubscriptionStatus.EXPIRED
            assert len(notifications) == 1

        # A second expiration pass must not duplicate the notification.
        async with async_session_factory() as session:
            await SubscriptionService(session).check_and_expire_subscriptions(
                limit=10
            )

        async with async_session_factory() as session:
            count = await session.scalar(
                select(Notification.id).where(
                    Notification.user_id == user_id,
                    Notification.notification_type
                    == "candidate_returned_to_free",
                    Notification.entity_id == paid_id,
                )
            )
            assert count is not None

        async with async_session_factory() as session:
            quota = QuotaEnforcementService(session)
            result = await quota.reserve_candidate_ai_quota(
                candidate_id=user_id,
                feature_type=SubscriptionUsageFeatureType.CANDIDATE_CHAT,
            )
            await session.commit()
        assert result.remaining == 2

    run_async(_run())


def test_cancel_candidate_paid_notifies_return_to_free(run_async):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session, role=UserRole.CANDIDATE)
            plan = await _create_plan(
                session,
                audience=PlanAudience.CANDIDATE,
                is_free=False,
                max_job_posts=0,
                max_candidate_searches=0,
                max_ai_features=5,
            )
            paid = await _create_candidate_paid_subscription(
                session,
                user_id=user.id,
                plan_id=plan.id,
                max_ai_features=5,
            )
            await session.commit()
            user_id, paid_id = user.id, paid.id

        async with async_session_factory() as session:
            cancelled = await SubscriptionService(
                session
            ).cancel_subscription(paid_id, user_id=user_id)

        assert cancelled.status == SubscriptionStatus.CANCELLED

        async with async_session_factory() as session:
            notification = await session.scalar(
                select(Notification).where(
                    Notification.user_id == user_id,
                    Notification.notification_type
                    == "candidate_returned_to_free",
                    Notification.entity_id == paid_id,
                )
            )
            assert notification is not None

    run_async(_run())


def test_reset_candidate_free_periods_only_resets_stale_free_rows(run_async):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session, role=UserRole.CANDIDATE)
            free_plan = await _create_candidate_free_plan(
                session, max_ai_features=3
            )
            paid_plan = await _create_plan(
                session,
                audience=PlanAudience.CANDIDATE,
                is_free=False,
                max_job_posts=0,
                max_candidate_searches=0,
                max_ai_features=5,
            )
            free = await _create_candidate_free_subscription(
                session,
                user_id=user.id,
                plan_id=free_plan.id,
                max_ai_features=3,
                used=3,
                period_key="2000-01",
            )
            paid = await _create_candidate_paid_subscription(
                session,
                user_id=user.id,
                plan_id=paid_plan.id,
                max_ai_features=5,
                used=2,
            )
            await session.commit()
            free_id, paid_id = free.id, paid.id

        current_period = CandidateEntitlementService.candidate_period_key(
            utc_now()
        )
        async with async_session_factory() as session:
            reset = await QuotaEnforcementService(
                session
            ).reset_candidate_free_periods(current_period, limit=10)
            await session.commit()
        assert reset == 1

        async with async_session_factory() as session:
            free = await session.get(Subscription, free_id)
            paid = await session.get(Subscription, paid_id)
            assert free.ai_features_used == 0
            assert free.current_period_key == current_period
            assert paid.ai_features_used == 2

        async with async_session_factory() as session:
            reset_again = await QuotaEnforcementService(
                session
            ).reset_candidate_free_periods(current_period, limit=10)
            await session.commit()
        assert reset_again == 0

    run_async(_run())


def test_candidate_idempotency_key_does_not_double_charge(run_async):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session, role=UserRole.CANDIDATE)
            plan = await _create_candidate_free_plan(session, max_ai_features=3)
            subscription = await _create_candidate_free_subscription(
                session,
                user_id=user.id,
                plan_id=plan.id,
                max_ai_features=3,
            )
            await session.commit()
            user_id, subscription_id = user.id, subscription.id

        key = f"idem-candidate-{uuid.uuid4().hex}"
        async with async_session_factory() as first:
            one = await QuotaEnforcementService(
                first
            ).reserve_candidate_ai_quota(
                candidate_id=user_id,
                feature_type=SubscriptionUsageFeatureType.CANDIDATE_CHAT,
                idempotency_key=key,
            )
            await first.commit()

        async with async_session_factory() as second:
            two = await QuotaEnforcementService(
                second
            ).reserve_candidate_ai_quota(
                candidate_id=user_id,
                feature_type=SubscriptionUsageFeatureType.CANDIDATE_CHAT,
                idempotency_key=key,
            )
            await second.commit()

        assert one.usage_id == two.usage_id

        async with async_session_factory() as session:
            subscription = await session.get(Subscription, subscription_id)
            count = await session.scalar(
                select(SubscriptionUsage.id).where(
                    SubscriptionUsage.idempotency_key == key
                )
            )
            assert subscription.ai_features_used == 1
            assert count == one.usage_id

    run_async(_run())
