"""Candidate personal entitlement and usage API tests.

The critical invariant is that an active Paid entitlement always wins and its
read path never mutates the preserved Free row, even when the Free period is
stale. Free projection and lazy provisioning are covered explicitly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

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
from app.models import RecruitmentPlan, Subscription, SubscriptionUsage, User
from tests.integration.api.conftest import API_V1

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _auth_user_id(client, run_async) -> uuid.UUID:
    response = run_async(client.get(f"{API_V1}/auth/me"))
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["id"])


async def _create_candidate_paid_plan(max_ai_features: int = 25) -> uuid.UUID:
    async with async_session_factory() as session:
        plan = RecruitmentPlan(
            name=f"Candidate Paid API Plan {uuid.uuid4().hex[:8]}",
            description="Test-only candidate paid tier",
            price=99000,
            currency="VND",
            duration_days=30,
            max_job_posts=0,
            max_candidate_searches=0,
            max_ai_features=max_ai_features,
            plan_audience=PlanAudience.CANDIDATE,
            is_free=False,
            is_active=True,
            display_order=1,
        )
        session.add(plan)
        await session.commit()
        await session.refresh(plan)
        return plan.id


async def _seed_paid(
    user_id: uuid.UUID,
    *,
    used: int = 0,
    max_ai_features: int = 25,
    expires_delta_days: int = 30,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
) -> uuid.UUID:
    plan_id = await _create_candidate_paid_plan(max_ai_features)
    async with async_session_factory() as session:
        now = utc_now()
        subscription = Subscription(
            user_id=user_id,
            company_id=None,
            plan_id=plan_id,
            scope=SubscriptionScope.CANDIDATE_PERSONAL,
            is_free=False,
            status=status,
            started_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=expires_delta_days),
            max_ai_features=max_ai_features,
            ai_features_used=used,
        )
        session.add(subscription)
        await session.commit()
        await session.refresh(subscription)
        return subscription.id


async def _set_free(
    user_id: uuid.UUID,
    *,
    used: int | None = None,
    period_key: str | None = None,
    status: SubscriptionStatus | None = None,
) -> None:
    async with async_session_factory() as session:
        free = await session.scalar(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.scope == SubscriptionScope.CANDIDATE_PERSONAL,
                Subscription.is_free == True,  # noqa: E712
            )
        )
        assert free is not None
        if used is not None:
            free.ai_features_used = used
        if period_key is not None:
            free.current_period_key = period_key
        if status is not None:
            free.status = status
        await session.commit()


async def _load_free_state(user_id: uuid.UUID) -> dict | None:
    async with async_session_factory() as session:
        free = await session.scalar(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.scope == SubscriptionScope.CANDIDATE_PERSONAL,
                Subscription.is_free == True,  # noqa: E712
            )
        )
        if free is None:
            return None
        return {
            "used": free.ai_features_used,
            "period_key": free.current_period_key,
            "status": free.status.value,
        }


async def _delete_free_rows(user_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        await session.execute(
            delete(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.scope == SubscriptionScope.CANDIDATE_PERSONAL,
                Subscription.is_free == True,  # noqa: E712
            )
        )
        await session.commit()


async def _count_free_rows(user_id: uuid.UUID) -> int:
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(Subscription).where(
                    Subscription.user_id == user_id,
                    Subscription.scope
                    == SubscriptionScope.CANDIDATE_PERSONAL,
                    Subscription.is_free == True,  # noqa: E712
                )
            )
        ).scalars().all()
        return len(list(rows))


def _free_plan_max(run_async) -> int:
    async def _load() -> int:
        async with async_session_factory() as session:
            plan = await session.scalar(
                select(RecruitmentPlan).where(
                    RecruitmentPlan.plan_audience
                    == PlanAudience.CANDIDATE,
                    RecruitmentPlan.is_free == True,  # noqa: E712
                    RecruitmentPlan.is_active == True,  # noqa: E712
                )
            )
            assert plan is not None
            return plan.max_ai_features or 0

    return run_async(_load())


def _previous_period_key() -> str:
    now = utc_now().astimezone(VN_TZ)
    first = now.replace(day=1)
    previous = first - timedelta(days=1)
    return previous.strftime("%Y-%m")


class TestCandidateEntitlementSummary:
    def test_free_entitlement_summary(self, candidate_client, run_async):
        response = run_async(
            candidate_client.get(f"{API_V1}/subscriptions/candidate/me")
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["effective_tier"] == "free"
        assert body["paid_subscription"] is None
        assert body["is_paid_exhausted"] is False
        assert body["is_projected"] is False
        free = body["free_subscription"]
        assert free["is_free"] is True
        assert free["ai_features_used"] == 0
        assert free["max_ai_features"] == _free_plan_max(run_async)
        assert free["ai_features_remaining"] == free["max_ai_features"]
        assert body["effective_subscription"]["id"] == free["id"]
        assert body["next_free_reset_at"] is not None

    def test_paid_takes_precedence_and_preserves_free(
        self, candidate_client, run_async
    ):
        user_id = _auth_user_id(candidate_client, run_async)
        run_async(_set_free(user_id, used=2))
        run_async(_seed_paid(user_id, used=4))
        before = run_async(_load_free_state(user_id))

        response = run_async(
            candidate_client.get(f"{API_V1}/subscriptions/candidate/me")
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["effective_tier"] == "paid"
        assert body["effective_subscription"]["is_free"] is False
        assert body["effective_subscription"]["ai_features_used"] == 4
        assert body["paid_subscription"]["ai_features_used"] == 4
        assert body["free_subscription"]["ai_features_used"] == 2
        assert run_async(_load_free_state(user_id)) == before

    def test_paid_active_with_stale_free_does_not_mutate_free(
        self, candidate_client, run_async
    ):
        user_id = _auth_user_id(candidate_client, run_async)
        stale_key = _previous_period_key()
        run_async(_set_free(user_id, used=3, period_key=stale_key))
        run_async(_seed_paid(user_id, used=1))
        before = run_async(_load_free_state(user_id))

        response = run_async(
            candidate_client.get(f"{API_V1}/subscriptions/candidate/me")
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["effective_tier"] == "paid"
        free = body["free_subscription"]
        assert free["current_period_key"] == stale_key
        assert free["ai_features_used"] == 3
        assert free["is_projected"] is False
        assert run_async(_load_free_state(user_id)) == before

    def test_paid_exhausted_does_not_fall_back_to_free(
        self, candidate_client, run_async
    ):
        user_id = _auth_user_id(candidate_client, run_async)
        run_async(_seed_paid(user_id, used=25, max_ai_features=25))

        response = run_async(
            candidate_client.get(f"{API_V1}/subscriptions/candidate/me")
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["effective_tier"] == "paid"
        assert body["is_paid_exhausted"] is True
        assert body["effective_subscription"]["ai_features_remaining"] == 0
        assert body["free_subscription"] is not None

    def test_expired_paid_resumes_free(self, candidate_client, run_async):
        user_id = _auth_user_id(candidate_client, run_async)
        run_async(
            _seed_paid(
                user_id,
                used=25,
                max_ai_features=25,
                expires_delta_days=-1,
            )
        )

        response = run_async(
            candidate_client.get(f"{API_V1}/subscriptions/candidate/me")
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["effective_tier"] == "free"
        assert body["paid_subscription"] is None
        assert body["is_paid_exhausted"] is False
        assert body["effective_subscription"]["is_free"] is True

    def test_stale_free_is_projected_without_writing(
        self, candidate_client, run_async
    ):
        user_id = _auth_user_id(candidate_client, run_async)
        stale_key = _previous_period_key()
        run_async(_set_free(user_id, used=3, period_key=stale_key))
        before = run_async(_load_free_state(user_id))

        response = run_async(
            candidate_client.get(f"{API_V1}/subscriptions/candidate/me")
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["effective_tier"] == "free"
        assert body["is_projected"] is True
        effective = body["effective_subscription"]
        assert effective["is_projected"] is True
        assert effective["ai_features_used"] == 0
        assert effective["ai_features_remaining"] == effective["max_ai_features"]
        assert run_async(_load_free_state(user_id)) == before

    def test_paid_active_missing_free_reports_null_without_creating(
        self, candidate_client, run_async
    ):
        user_id = _auth_user_id(candidate_client, run_async)
        run_async(_delete_free_rows(user_id))
        run_async(_seed_paid(user_id, used=0))

        response = run_async(
            candidate_client.get(f"{API_V1}/subscriptions/candidate/me")
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["effective_tier"] == "paid"
        assert body["free_subscription"] is None
        assert run_async(_count_free_rows(user_id)) == 0

    def test_missing_free_without_paid_is_lazily_provisioned(
        self, candidate_client, run_async
    ):
        user_id = _auth_user_id(candidate_client, run_async)
        run_async(_delete_free_rows(user_id))

        response = run_async(
            candidate_client.get(f"{API_V1}/subscriptions/candidate/me")
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["effective_tier"] == "free"
        assert body["is_projected"] is False
        assert run_async(_count_free_rows(user_id)) == 1

    def test_recruiter_cannot_read_candidate_entitlement(
        self, recruiter_client, run_async
    ):
        response = run_async(
            recruiter_client.get(f"{API_V1}/subscriptions/candidate/me")
        )
        assert response.status_code == 403

    def test_admin_cannot_read_candidate_entitlement(
        self, admin_client, run_async
    ):
        response = run_async(
            admin_client.get(f"{API_V1}/subscriptions/candidate/me")
        )
        assert response.status_code == 403


async def _seed_usage(
    *,
    user_id: uuid.UUID,
    subscription_id: uuid.UUID,
    feature_type: SubscriptionUsageFeatureType,
    status: SubscriptionUsageStatus = SubscriptionUsageStatus.COMPLETED,
    amount: int = 1,
    created_at: datetime | None = None,
    scope: SubscriptionScope = SubscriptionScope.CANDIDATE_PERSONAL,
) -> uuid.UUID:
    async with async_session_factory() as session:
        usage = SubscriptionUsage(
            subscription_id=subscription_id,
            user_id=user_id,
            company_id=None,
            scope=scope,
            feature_type=feature_type,
            status=status,
            amount=amount,
            created_at=created_at or utc_now(),
        )
        session.add(usage)
        await session.commit()
        await session.refresh(usage)
        return usage.id


def _free_subscription_id(run_async, user_id: uuid.UUID) -> uuid.UUID:
    async def _load() -> uuid.UUID:
        async with async_session_factory() as session:
            free = await session.scalar(
                select(Subscription).where(
                    Subscription.user_id == user_id,
                    Subscription.scope
                    == SubscriptionScope.CANDIDATE_PERSONAL,
                    Subscription.is_free == True,  # noqa: E712
                )
            )
            assert free is not None
            return free.id

    return run_async(_load())


class TestCandidateUsageHistory:
    def test_returns_only_own_candidate_rows(
        self, candidate_client, candidate_b_client, run_async
    ):
        user_id = _auth_user_id(candidate_client, run_async)
        other_id = _auth_user_id(candidate_b_client, run_async)
        free_id = _free_subscription_id(run_async, user_id)
        other_free_id = _free_subscription_id(run_async, other_id)

        run_async(
            _seed_usage(
                user_id=user_id,
                subscription_id=free_id,
                feature_type=SubscriptionUsageFeatureType.CANDIDATE_PARSE_RESUME,
                amount=2,
            )
        )
        run_async(
            _seed_usage(
                user_id=user_id,
                subscription_id=free_id,
                feature_type=SubscriptionUsageFeatureType.CANDIDATE_CHAT,
                status=SubscriptionUsageStatus.FAILED,
            )
        )
        run_async(
            _seed_usage(
                user_id=user_id,
                subscription_id=free_id,
                feature_type=SubscriptionUsageFeatureType.CANDIDATE_JOB_RECOMMENDATIONS,
                scope=SubscriptionScope.LEGACY_RECRUITER_PERSONAL,
            )
        )
        run_async(
            _seed_usage(
                user_id=other_id,
                subscription_id=other_free_id,
                feature_type=SubscriptionUsageFeatureType.CANDIDATE_CHAT,
            )
        )

        response = run_async(
            candidate_client.get(f"{API_V1}/subscriptions/candidate/usages")
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["total"] == 2
        assert body["page"] == 1
        assert body["page_size"] == 10
        assert len(body["items"]) == 2
        by_feature = {item["feature_type"]: item for item in body["items"]}
        assert by_feature["candidate_parse_resume"]["feature_label"] == (
            "Phân tích CV"
        )
        assert by_feature["candidate_parse_resume"]["amount"] == 2
        assert by_feature["candidate_chat"]["status_label"] == "Thất bại"

    def test_filters_and_pagination(
        self, candidate_client, run_async
    ):
        user_id = _auth_user_id(candidate_client, run_async)
        free_id = _free_subscription_id(run_async, user_id)
        base = utc_now() - timedelta(minutes=5)
        for index in range(3):
            run_async(
                _seed_usage(
                    user_id=user_id,
                    subscription_id=free_id,
                    feature_type=(
                        SubscriptionUsageFeatureType.CANDIDATE_CHAT
                        if index < 2
                        else SubscriptionUsageFeatureType.CANDIDATE_PARSE_RESUME
                    ),
                    status=(
                        SubscriptionUsageStatus.COMPLETED
                        if index < 2
                        else SubscriptionUsageStatus.FAILED
                    ),
                    created_at=base + timedelta(minutes=index),
                )
            )

        filtered = run_async(
            candidate_client.get(
                f"{API_V1}/subscriptions/candidate/usages",
                params={"feature_type": "candidate_chat"},
            )
        )
        assert filtered.status_code == 200, filtered.text
        assert filtered.json()["total"] == 2

        by_status = run_async(
            candidate_client.get(
                f"{API_V1}/subscriptions/candidate/usages",
                params={"status": "failed"},
            )
        )
        assert by_status.status_code == 200, by_status.text
        assert by_status.json()["total"] == 1

        page_two = run_async(
            candidate_client.get(
                f"{API_V1}/subscriptions/candidate/usages",
                params={"page": 2, "page_size": 1},
            )
        )
        assert page_two.status_code == 200, page_two.text
        assert page_two.json()["page"] == 2
        assert page_two.json()["total_pages"] == 3
        assert len(page_two.json()["items"]) == 1

    def test_rejects_oversized_page_and_invalid_windows(
        self, candidate_client, run_async
    ):
        oversized = run_async(
            candidate_client.get(
                f"{API_V1}/subscriptions/candidate/usages",
                params={"page_size": 51},
            )
        )
        assert oversized.status_code == 422

        inverted = run_async(
            candidate_client.get(
                f"{API_V1}/subscriptions/candidate/usages",
                params={
                    "start_date": "2026-02-10",
                    "end_date": "2026-02-01",
                },
            )
        )
        assert inverted.status_code == 422

        too_long = run_async(
            candidate_client.get(
                f"{API_V1}/subscriptions/candidate/usages",
                params={
                    "start_date": "2024-01-01",
                    "end_date": "2026-01-02",
                },
            )
        )
        assert too_long.status_code == 422

    def test_recruiter_cannot_read_candidate_usages(
        self, recruiter_client, run_async
    ):
        response = run_async(
            recruiter_client.get(f"{API_V1}/subscriptions/candidate/usages")
        )
        assert response.status_code == 403
