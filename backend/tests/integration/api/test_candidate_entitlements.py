"""Candidate entitlement foundation tests.

Covers registration provisioning, idempotent lazy provisioning, dual
Free/Paid coexistence, duplicate rejection, fail-closed configuration, and
role preservation. Candidate registration requires an active Free plan; the
API conftest seeds one per test unless a test removes it deliberately.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConfigurationError
from app.main import app
from app.core.security import get_password_hash
from app.database.session import async_session_factory
from app.domain.enums import (
    PlanAudience,
    SubscriptionScope,
    SubscriptionStatus,
    UserRole,
)
from app.domain.models.base import utc_now
from app.models import RecruitmentPlan, Subscription, User
from app.repositories import RecruitmentPlanRepository, SubscriptionRepository
from app.services.candidate_entitlement_service import CandidateEntitlementService
from app.services.subscription_service import SubscriptionService
from tests.integration.api.conftest import API_V1, PASSWORD


async def _create_candidate_user(
    role: UserRole = UserRole.CANDIDATE,
) -> uuid.UUID:
    async with async_session_factory() as session:
        user = User(
            email=f"entitlement-{uuid.uuid4()}@example.com",
            password_hash=get_password_hash(PASSWORD),
            role=role,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id


async def _create_candidate_paid_plan() -> uuid.UUID:
    async with async_session_factory() as session:
        plan = RecruitmentPlan(
            name=f"Candidate Paid Test Plan {uuid.uuid4().hex[:8]}",
            description="Test-only candidate paid tier",
            price=99000,
            currency="VND",
            duration_days=30,
            max_job_posts=0,
            max_candidate_searches=0,
            max_ai_features=25,
            plan_audience=PlanAudience.CANDIDATE,
            is_free=False,
            is_active=True,
            display_order=1,
        )
        session.add(plan)
        await session.commit()
        await session.refresh(plan)
        return plan.id


def _register(client, run_async, role: str) -> dict:
    email = f"entitlement-{uuid.uuid4()}@example.com"
    response = run_async(
        client.post(
            f"{API_V1}/auth/register",
            json={"email": email, "password": PASSWORD, "role": role},
        )
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestRegistrationProvisioning:
    def test_candidate_registration_provisions_free_entitlement(
        self, client, run_async
    ):
        body = _register(client, run_async, "candidate")
        user_id = uuid.UUID(body["id"])

        async def _load():
            async with async_session_factory() as session:
                plan = await RecruitmentPlanRepository(
                    session
                ).get_active_candidate_free_plan()
                subscriptions = await SubscriptionRepository(
                    session
                ).get_by_user_id(user_id)
                return plan, subscriptions

        plan, subscriptions = run_async(_load())
        assert plan is not None
        candidate_subscriptions = [
            sub
            for sub in subscriptions
            if sub.scope == SubscriptionScope.CANDIDATE_PERSONAL
        ]
        assert len(candidate_subscriptions) == 1

        subscription = candidate_subscriptions[0]
        assert subscription.is_free is True
        assert subscription.company_id is None
        assert subscription.status == SubscriptionStatus.ACTIVE
        assert subscription.plan_id == plan.id
        assert subscription.expires_at is None
        assert subscription.max_ai_features == plan.max_ai_features
        assert subscription.ai_features_used == 0
        assert subscription.candidate_searches_used == 0
        assert subscription.job_posts_used == 0
        expected_period = utc_now().astimezone(
            ZoneInfo("Asia/Ho_Chi_Minh")
        ).strftime("%Y-%m")
        assert subscription.current_period_key == expected_period

    def test_recruiter_registration_does_not_provision_candidate_free(
        self, client, run_async
    ):
        body = _register(client, run_async, "recruiter")
        user_id = uuid.UUID(body["id"])

        async def _count():
            async with async_session_factory() as session:
                rows = (
                    await session.execute(
                        select(Subscription).where(
                            Subscription.user_id == user_id,
                            Subscription.scope
                            == SubscriptionScope.CANDIDATE_PERSONAL,
                        )
                    )
                ).scalars().all()
                return list(rows)

        assert run_async(_count()) == []

    def test_candidate_registration_preserves_candidate_role(
        self, client, run_async
    ):
        body = _register(client, run_async, "candidate")

        async def _load_user():
            async with async_session_factory() as session:
                return await session.get(User, uuid.UUID(body["id"]))

        user = run_async(_load_user())
        assert user.role == UserRole.CANDIDATE

    def test_registration_without_free_plan_fails_without_orphan_user(
        self, client, run_async
    ):
        async def _deactivate():
            async with async_session_factory() as session:
                plan = await RecruitmentPlanRepository(
                    session
                ).get_active_candidate_free_plan()
                assert plan is not None
                plan.is_active = False
                await session.commit()

        run_async(_deactivate())
        email = f"missing-free-plan-{uuid.uuid4()}@example.com"

        async def _post():
            transport = httpx.ASGITransport(
                app=app,
                raise_app_exceptions=False,
            )
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as failing_client:
                return await failing_client.post(
                    f"{API_V1}/auth/register",
                    json={
                        "email": email,
                        "password": PASSWORD,
                        "role": "candidate",
                    },
                )

        response = run_async(_post())

        assert response.status_code == 500

        async def _load_user():
            async with async_session_factory() as session:
                return await session.scalar(
                    select(User).where(User.email == email)
                )

        assert run_async(_load_user()) is None


class TestLazyProvisioning:
    def test_existing_candidate_without_free_entitlement_is_lazily_provisioned(
        self, run_async
    ):
        user_id = run_async(_create_candidate_user())

        async def _provision():
            async with async_session_factory() as session:
                subscription = await CandidateEntitlementService(
                    session
                ).provision_free_entitlement(user_id)
                subscription_id = subscription.id
                await session.commit()
                return subscription_id

        subscription_id = run_async(_provision())

        async def _load():
            async with async_session_factory() as session:
                subscription = await session.get(Subscription, subscription_id)
                user = await session.get(User, user_id)
                return subscription, user

        subscription, user = run_async(_load())
        assert subscription.scope == SubscriptionScope.CANDIDATE_PERSONAL
        assert subscription.is_free is True
        assert subscription.company_id is None
        assert subscription.status == SubscriptionStatus.ACTIVE
        assert user.role == UserRole.CANDIDATE

    def test_repeated_lazy_provisioning_does_not_create_duplicates(
        self, run_async
    ):
        user_id = run_async(_create_candidate_user())

        async def _provision_twice():
            async with async_session_factory() as session:
                first = await CandidateEntitlementService(
                    session
                ).provision_free_entitlement(user_id)
                first_id = first.id
                await session.commit()

            async with async_session_factory() as session:
                second = await CandidateEntitlementService(
                    session
                ).provision_free_entitlement(user_id)
                second_id = second.id
                await session.commit()
            return first_id, second_id

        first_id, second_id = run_async(_provision_twice())
        assert first_id == second_id

        async def _count():
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

        assert run_async(_count()) == 1

    def test_missing_active_candidate_free_plan_raises_configuration_error(
        self, run_async
    ):
        async def _deactivate():
            async with async_session_factory() as session:
                plan = await RecruitmentPlanRepository(
                    session
                ).get_active_candidate_free_plan()
                assert plan is not None
                plan.is_active = False
                await session.commit()

        run_async(_deactivate())
        user_id = run_async(_create_candidate_user())

        async def _provision():
            async with async_session_factory() as session:
                with pytest.raises(
                    ConfigurationError,
                    match="No active Candidate Free Plan configured",
                ):
                    await CandidateEntitlementService(
                        session
                    ).provision_free_entitlement(user_id)

        run_async(_provision())


class TestDualEntitlementValidation:
    def test_candidate_free_and_paid_can_coexist(self, run_async):
        user_id = run_async(_create_candidate_user())
        paid_plan_id = run_async(_create_candidate_paid_plan())

        async def _seed():
            async with async_session_factory() as session:
                free_subscription = await CandidateEntitlementService(
                    session
                ).provision_free_entitlement(user_id)
                free_plan_id = free_subscription.plan_id
                now = utc_now()
                session.add(
                    Subscription(
                        user_id=user_id,
                        company_id=None,
                        plan_id=paid_plan_id,
                        scope=SubscriptionScope.CANDIDATE_PERSONAL,
                        is_free=False,
                        status=SubscriptionStatus.ACTIVE,
                        started_at=now,
                        expires_at=now + timedelta(days=30),
                        max_ai_features=25,
                        ai_features_used=0,
                    )
                )
                await session.commit()
                return free_plan_id

        free_plan_id = run_async(_seed())

        async def _check():
            async with async_session_factory() as session:
                plans = RecruitmentPlanRepository(session)
                free_plan = await plans.get_active_by_id(free_plan_id)
                paid_plan = await plans.get_active_by_id(paid_plan_id)
                service = SubscriptionService(session)
                now = utc_now()
                free_overlap = await service._check_active_overlap(
                    user_id, now, plan=free_plan
                )
                paid_overlap = await service._check_active_overlap(
                    user_id, now, plan=paid_plan
                )
                rows = (
                    await session.execute(
                        select(Subscription).where(
                            Subscription.user_id == user_id,
                            Subscription.scope
                            == SubscriptionScope.CANDIDATE_PERSONAL,
                        )
                    )
                ).scalars().all()
                return free_overlap, paid_overlap, list(rows)

        free_overlap, paid_overlap, rows = run_async(_check())
        assert free_overlap is not None and free_overlap.is_free is True
        assert paid_overlap is not None and paid_overlap.is_free is False
        assert len(rows) == 2

    def test_duplicate_candidate_free_and_paid_entitlements_are_rejected(
        self, run_async
    ):
        user_id = run_async(_create_candidate_user())
        paid_plan_id = run_async(_create_candidate_paid_plan())

        async def _seed():
            async with async_session_factory() as session:
                free_subscription = await CandidateEntitlementService(
                    session
                ).provision_free_entitlement(user_id)
                free_plan_id = free_subscription.plan_id
                now = utc_now()
                session.add(
                    Subscription(
                        user_id=user_id,
                        company_id=None,
                        plan_id=paid_plan_id,
                        scope=SubscriptionScope.CANDIDATE_PERSONAL,
                        is_free=False,
                        status=SubscriptionStatus.ACTIVE,
                        started_at=now,
                        expires_at=now + timedelta(days=30),
                        max_ai_features=25,
                        ai_features_used=0,
                    )
                )
                await session.commit()
                return free_plan_id

        free_plan_id = run_async(_seed())

        async def _read_overlaps():
            async with async_session_factory() as session:
                plans = RecruitmentPlanRepository(session)
                service = SubscriptionService(session)
                now = utc_now()
                return (
                    await service._check_active_overlap(
                        user_id, now, plan=await plans.get_active_by_id(free_plan_id)
                    ),
                    await service._check_active_overlap(
                        user_id, now, plan=await plans.get_active_by_id(paid_plan_id)
                    ),
                )

        free_overlap, paid_overlap = run_async(_read_overlaps())
        assert free_overlap is not None
        assert paid_overlap is not None

        async def _insert_duplicate(is_free: bool) -> None:
            async with async_session_factory() as session:
                now = utc_now()
                session.add(
                    Subscription(
                        user_id=user_id,
                        company_id=None,
                        plan_id=paid_plan_id if not is_free else free_plan_id,
                        scope=SubscriptionScope.CANDIDATE_PERSONAL,
                        is_free=is_free,
                        status=SubscriptionStatus.ACTIVE,
                        started_at=now,
                        expires_at=None if is_free else now + timedelta(days=30),
                        max_ai_features=25,
                        ai_features_used=0,
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.flush()
                await session.rollback()

        run_async(_insert_duplicate(True))
        run_async(_insert_duplicate(False))
