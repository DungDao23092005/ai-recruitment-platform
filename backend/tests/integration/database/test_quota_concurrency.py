import asyncio
import uuid
from datetime import timedelta

import pyodbc
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.exceptions import ForbiddenException
from app.database.session import async_session_factory
from app.domain.enums import (
    SubscriptionStatus,
    SubscriptionUsageFeatureType,
    SubscriptionUsageStatus,
    UserRole,
)
from app.domain.models.base import utc_now
from app.models import RecruitmentPlan, Subscription, SubscriptionUsage, User
from app.services.quota_enforcement_service import QuotaEnforcementService


def _sql_server_available() -> bool:
    """Synchronously probe the configured SQL Server (no asyncio loop involved)."""
    try:
        conn_str = (
            f"DRIVER={{{settings.DATABASE_DRIVER}}};"
            f"SERVER={settings.DATABASE_HOST},{settings.DATABASE_PORT};"
            f"DATABASE={settings.DATABASE_NAME};"
        )
        if settings.DATABASE_USER:
            conn_str += f"UID={settings.DATABASE_USER};PWD={settings.DATABASE_PASSWORD};"
        conn_str += "TrustServerCertificate=yes;Connection Timeout=3;"
        conn = pyodbc.connect(conn_str)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _sql_server_available(),
    reason="SQL Server test database (localhost:1433 / ai_recruitment_platform_test) "
    "is not available in this environment. Live quota-concurrency test cannot run "
    "without a real SQL Server; race safety is therefore not claimed as proven here.",
)


async def _create_subscription_with_one_search(session) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a recruiter user + active subscription with exactly 1 search slot.

    Returns (user_id, subscription_id).
    """
    user = User(
        email=f"conc_{uuid.uuid4()}@example.com",
        password_hash="hash",
        role=UserRole.RECRUITER,
        is_active=True,
    )
    plan = RecruitmentPlan(
        name=f"Conc Plan {uuid.uuid4()}",
        price=1000,
        currency="VND",
        duration_days=30,
        max_job_posts=0,
        max_candidate_searches=1,
        max_ai_features=0,
        is_active=True,
        display_order=0,
    )
    session.add_all([user, plan])
    await session.commit()
    await session.refresh(user)
    await session.refresh(plan)

    now = utc_now()
    sub = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        started_at=now,
        expires_at=now + timedelta(days=30),
        max_job_posts=0,
        max_candidate_searches=1,
        max_ai_features=0,
        job_posts_used=0,
        candidate_searches_used=0,
        ai_features_used=0,
    )
    session.add(sub)
    await session.flush()
    return user.id, sub.id


async def _reserve_once(user_id: uuid.UUID, key: str):
    """Attempt to reserve one search slot in an independent session/transaction."""
    async with async_session_factory() as session:
        service = QuotaEnforcementService(session)
        try:
            reservation = await service.reserve_search_quota(
                user_id=user_id,
                idempotency_key=key,
                reference_id=None,
            )
            await session.commit()
            return ("ok", reservation.usage_id)
        except ForbiddenException:
            await session.rollback()
            return ("exhausted", None)


async def _count_usages(session, subscription_id: uuid.UUID) -> list:
    result = await session.execute(
        select(SubscriptionUsage).where(
            SubscriptionUsage.subscription_id == subscription_id,
            SubscriptionUsage.feature_type == SubscriptionUsageFeatureType.CANDIDATE_SEARCH,
        )
    )
    return result.scalars().all()


def test_concurrent_search_quota_atomicity(run_async):
    """Two concurrent sessions reserving the last search slot: exactly one wins.

    Uses two independent database sessions/transactions contending for the same
    final quota slot. The atomic conditional UPDATE in QuotaEnforcementService
    must serialize them so exactly one reservation succeeds and the counter ends
    at exactly 1 with exactly one COMPLETED usage record.
    """

    async def _test():
        user_id = None
        sub_id = None
        async with async_session_factory() as setup:
            user_id, sub_id = await _create_subscription_with_one_search(setup)
            await setup.commit()

        results = await asyncio.gather(
            _reserve_once(user_id, f"conc-{uuid.uuid4()}"),
            _reserve_once(user_id, f"conc-{uuid.uuid4()}"),
        )

        successes = [r for r in results if r[0] == "ok"]
        exhausted = [r for r in results if r[0] == "exhausted"]
        assert len(successes) == 1, f"expected exactly 1 success, got {results}"
        assert len(exhausted) == 1, f"expected exactly 1 exhaustion, got {results}"

        async with async_session_factory() as check:
            sub = await check.get(Subscription, sub_id)
            assert sub is not None
            assert sub.candidate_searches_used == 1, (
                f"counter must be exactly 1, got {sub.candidate_searches_used}"
            )
            rows = await _count_usages(check, sub_id)
            assert len(rows) == 1, f"exactly one usage record expected, got {len(rows)}"
            assert rows[0].status == SubscriptionUsageStatus.RESERVED

    run_async(_test())


async def _create_subscription_with_job_posts(
    session, max_job_posts: int = 5
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a recruiter user + active subscription with job-post quota.

    Returns (user_id, subscription_id).
    """
    user = User(
        email=f"conc_jp_{uuid.uuid4()}@example.com",
        password_hash="hash",
        role=UserRole.RECRUITER,
        is_active=True,
    )
    plan = RecruitmentPlan(
        name=f"Conc JP Plan {uuid.uuid4()}",
        price=1000,
        currency="VND",
        duration_days=30,
        max_job_posts=max_job_posts,
        max_candidate_searches=0,
        max_ai_features=0,
        is_active=True,
        display_order=0,
    )
    session.add_all([user, plan])
    await session.commit()
    await session.refresh(user)
    await session.refresh(plan)

    now = utc_now()
    sub = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        started_at=now,
        expires_at=now + timedelta(days=30),
        max_job_posts=max_job_posts,
        max_candidate_searches=0,
        max_ai_features=0,
        job_posts_used=0,
        candidate_searches_used=0,
        ai_features_used=0,
    )
    session.add(sub)
    await session.flush()
    return user.id, sub.id


async def _consume_job_post_once(user_id: uuid.UUID, job_id: uuid.UUID):
    """Attempt to consume one job-post quota in an independent session."""
    async with async_session_factory() as session:
        service = QuotaEnforcementService(session)
        try:
            result = await service.consume_job_post_quota_idempotent(
                user_id=user_id, job_id=job_id
            )
            await session.commit()
            return ("ok", result.used)
        except ForbiddenException:
            await session.rollback()
            return ("exhausted", None)
        except IntegrityError:
            await session.rollback()
            return ("integrity_error", None)


async def _count_job_post_usages(session, subscription_id: uuid.UUID) -> list:
    result = await session.execute(
        select(SubscriptionUsage).where(
            SubscriptionUsage.subscription_id == subscription_id,
            SubscriptionUsage.feature_type == SubscriptionUsageFeatureType.JOB_POST,
        )
    )
    return result.scalars().all()


def test_concurrent_job_post_quota_same_job_id(run_async):
    """Two concurrent sessions consuming job-post quota for the same job ID.

    Both tasks use independent AsyncSession instances and the same
    (user_id, job_id). Exactly one must charge the counter; the concurrent
    loser must detect the winner's committed idempotency record and not
    double-charge.

    Expected:
      - Both tasks report allowed (winner charged; loser idempotent).
      - job_posts_used == 1.
      - Exactly one usage row for (subscription, JOB_POST, job_post_{job_id}).
      - The row carries the deterministic idempotency key and reference_id.
      - Reopening the same job under the same subscription does not increase usage.
      - Publishing the same job under a second subscription consumes that
        subscription's quota once.
    """

    async def _test():
        user_id = None
        sub_id = None
        job_id = uuid.uuid4()
        async with async_session_factory() as setup:
            user_id, sub_id = await _create_subscription_with_job_posts(
                setup, max_job_posts=5
            )
            await setup.commit()

        results = await asyncio.gather(
            _consume_job_post_once(user_id, job_id),
            _consume_job_post_once(user_id, job_id),
        )

        assert all(r[0] == "ok" for r in results), f"unexpected results: {results}"

        async with async_session_factory() as check:
            sub = await check.get(Subscription, sub_id)
            assert sub is not None
            assert sub.job_posts_used == 1, (
                f"counter must be exactly 1, got {sub.job_posts_used}"
            )
            rows = await _count_job_post_usages(check, sub_id)
            assert len(rows) == 1, f"exactly one usage row expected, got {len(rows)}"
            row = rows[0]
            assert row.status == SubscriptionUsageStatus.COMPLETED
            assert row.reference_id == job_id
            assert row.idempotency_key == f"job_post_{job_id}"

        # Reopen the same job under the same subscription: no additional charge.
        async with async_session_factory() as session:
            service = QuotaEnforcementService(session)
            result = await service.consume_job_post_quota_idempotent(
                user_id=user_id, job_id=job_id
            )
            await session.commit()
            assert result.allowed is True

        async with async_session_factory() as check:
            sub = await check.get(Subscription, sub_id)
            assert sub.job_posts_used == 1, (
                f"counter must remain 1 after reopen, got {sub.job_posts_used}"
            )

        # Same job under a second subscription: consumes that subscription's quota once.
        async with async_session_factory() as setup2:
            user_id2, sub_id2 = await _create_subscription_with_job_posts(
                setup2, max_job_posts=5
            )
            await setup2.commit()
        async with async_session_factory() as session:
            service = QuotaEnforcementService(session)
            result = await service.consume_job_post_quota_idempotent(
                user_id=user_id2, job_id=job_id
            )
            await session.commit()
            assert result.allowed is True
        async with async_session_factory() as check:
            sub2 = await check.get(Subscription, sub_id2)
            assert sub2.job_posts_used == 1, (
                f"new subscription counter must be 1, got {sub2.job_posts_used}"
            )

    run_async(_test())
