from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.database.session import async_session_factory
from app.domain.enums import SubscriptionStatus, UserRole
from app.domain.models.base import utc_now
from app.models import RecruitmentPlan, Subscription, User
from app.repositories import SubscriptionRepository
from app.services.admin_subscription_service import AdminSubscriptionService
from app.services.subscription_service import SubscriptionService

pytestmark = pytest.mark.integration


async def _seed_user(session) -> User:
    user = User(
        email=f"exp-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="hash",
        role=UserRole.CANDIDATE,
    )
    session.add(user)
    await session.flush()
    return user


async def _seed_user_plan(session) -> tuple[User, RecruitmentPlan]:
    user = await _seed_user(session)
    plan = RecruitmentPlan(
        name=f"Expiration Plan {uuid.uuid4().hex[:6]}",
        price=1000,
        currency="VND",
        duration_days=30,
        max_job_posts=1,
        max_candidate_searches=1,
        max_ai_features=1,
        is_active=True,
        display_order=0,
    )
    session.add(plan)
    await session.flush()
    return user, plan


async def _add_subscription(
    session,
    *,
    user_id,
    plan_id,
    status: SubscriptionStatus,
    expires_at,
    is_deleted: bool = False,
) -> Subscription:
    sub = Subscription(
        user_id=user_id,
        plan_id=plan_id,
        status=status,
        started_at=utc_now() - timedelta(days=1),
        expires_at=expires_at,
        is_deleted=is_deleted,
    )
    session.add(sub)
    await session.flush()
    return sub


def test_expiration_predicates_limit_and_order_against_sql_server(run_async):
    async def _run():
        now = utc_now()
        async with async_session_factory() as setup:
            user, plan = await _seed_user_plan(setup)
            user_newer = await _seed_user(setup)
            user_third = await _seed_user(setup)
            user_future = await _seed_user(setup)
            user_no_expiry = await _seed_user(setup)
            oldest = await _add_subscription(
                setup,
                user_id=user.id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                expires_at=now - timedelta(hours=3),
            )
            newer = await _add_subscription(
                setup,
                user_id=user_newer.id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                expires_at=now - timedelta(hours=2),
            )
            third = await _add_subscription(
                setup,
                user_id=user_third.id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                expires_at=now - timedelta(seconds=1),
            )
            future = await _add_subscription(
                setup,
                user_id=user_future.id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                expires_at=now + timedelta(days=1),
            )
            no_expiry = await _add_subscription(
                setup,
                user_id=user_no_expiry.id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                expires_at=None,
            )
            cancelled = await _add_subscription(
                setup,
                user_id=user.id,
                plan_id=plan.id,
                status=SubscriptionStatus.CANCELLED,
                expires_at=now - timedelta(hours=4),
            )
            pending = await _add_subscription(
                setup,
                user_id=user.id,
                plan_id=plan.id,
                status=SubscriptionStatus.PENDING,
                expires_at=now - timedelta(hours=4),
            )
            deleted = await _add_subscription(
                setup,
                user_id=user.id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                expires_at=now - timedelta(hours=4),
                is_deleted=True,
            )
            await setup.commit()
            ids = {
                "oldest": oldest.id,
                "newer": newer.id,
                "third": third.id,
                "future": future.id,
                "no_expiry": no_expiry.id,
                "cancelled": cancelled.id,
                "pending": pending.id,
                "deleted": deleted.id,
            }

        async with async_session_factory() as session:
            first_count = await SubscriptionService(
                session
            ).check_and_expire_subscriptions(now=now, limit=2)

        async with async_session_factory() as session:
            second_count = await SubscriptionService(
                session
            ).check_and_expire_subscriptions(now=now, limit=2)

        async with async_session_factory() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.id.in_(ids.values()))
            )
            rows = {row.id: row for row in result.scalars().all()}

        assert first_count == 2
        assert second_count == 1
        assert rows[ids["oldest"]].status == SubscriptionStatus.EXPIRED
        assert rows[ids["newer"]].status == SubscriptionStatus.EXPIRED
        assert rows[ids["third"]].status == SubscriptionStatus.EXPIRED
        assert rows[ids["future"]].status == SubscriptionStatus.ACTIVE
        assert rows[ids["no_expiry"]].status == SubscriptionStatus.ACTIVE
        assert rows[ids["cancelled"]].status == SubscriptionStatus.CANCELLED
        assert rows[ids["pending"]].status == SubscriptionStatus.PENDING
        assert rows[ids["deleted"]].status == SubscriptionStatus.ACTIVE

    run_async(_run())


def test_expiration_does_not_overwrite_concurrent_change_plan(run_async):
    """A renewal that wins the row lock must survive the worker's write.

    The real ``change_plan`` is paused after flushing its new future expiry
    while still holding the row lock. The worker's expiration UPDATE must block,
    then re-evaluate its predicates against the committed renewal and update
    zero rows.
    """

    async def _run():
        now = utc_now()
        async with async_session_factory() as setup:
            user, source_plan = await _seed_user_plan(setup)
            admin = User(
                email=f"exp-admin-{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hash",
                role=UserRole.ADMIN,
            )
            setup.add(admin)
            target_plan = RecruitmentPlan(
                name=f"Renewed Plan {uuid.uuid4().hex[:6]}",
                price=2000,
                currency="VND",
                duration_days=60,
                max_job_posts=2,
                max_candidate_searches=2,
                max_ai_features=2,
                is_active=True,
                display_order=1,
            )
            setup.add(target_plan)
            sub = await _add_subscription(
                setup,
                user_id=user.id,
                plan_id=source_plan.id,
                status=SubscriptionStatus.ACTIVE,
                expires_at=now + timedelta(minutes=5),
            )
            await setup.commit()
            sub_id = sub.id
            user_id = user.id
            target_plan_id = target_plan.id
            admin_id = admin.id

        renewal_flushed = asyncio.Event()
        release_renewal = asyncio.Event()
        original_commit = AdminSubscriptionService._commit_and_refresh

        async def _hold_then_commit(self, sub):
            await self.session.flush()
            renewal_flushed.set()
            await release_renewal.wait()
            await original_commit(self, sub)

        async def _change_plan():
            async with async_session_factory() as session:
                return await AdminSubscriptionService(session).change_plan(
                    admin_id=admin_id,
                    subscription_id=sub_id,
                    target_plan_id=target_plan_id,
                    reason="gia hạn đồng thời",
                )

        async def _expire():
            async with async_session_factory() as session:
                return await SubscriptionRepository(session).expire_stale_active(
                    now + timedelta(minutes=10), limit=10
                )

        with patch.object(
            AdminSubscriptionService,
            "_commit_and_refresh",
            new=_hold_then_commit,
        ):
            renewal = None
            expiration = None
            try:
                renewal = asyncio.create_task(
                    _change_plan(), name="expiration-renewal"
                )
                await asyncio.wait_for(renewal_flushed.wait(), timeout=5)
                expiration = asyncio.create_task(
                    _expire(), name="expiration-worker"
                )
                await asyncio.sleep(0.2)
                assert not expiration.done()
                release_renewal.set()
                renewed = await asyncio.wait_for(renewal, timeout=10)
                expired = await asyncio.wait_for(expiration, timeout=10)
            finally:
                # Always release the renewal gate and reap both workers so a
                # failed assertion cannot leave a transaction holding locks
                # while the schema is dropped.
                release_renewal.set()
                workers = [
                    task
                    for task in (renewal, expiration)
                    if task is not None
                ]
                for task in workers:
                    if not task.done():
                        task.cancel()
                if workers:
                    await asyncio.gather(*workers, return_exceptions=True)

        assert renewed.status == SubscriptionStatus.ACTIVE
        assert renewed.plan_id == target_plan_id
        assert expired == 0

        async with async_session_factory() as check:
            stored = await check.get(Subscription, sub_id)
            assert stored.status == SubscriptionStatus.ACTIVE
            assert stored.plan_id == target_plan_id
            active = await SubscriptionService(
                check
            ).get_current_active_subscription(
                user_id, now=now + timedelta(minutes=10)
            )
            assert active is not None
            assert active.id == sub_id

    run_async(_run())
