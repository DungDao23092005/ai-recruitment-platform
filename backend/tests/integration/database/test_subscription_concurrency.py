import asyncio
import uuid

import pytest

from app.database.session import async_session_factory
from app.domain.enums import SubscriptionStatus, UserRole
from app.models import RecruitmentPlan, Subscription, User
from app.repositories import SubscriptionRepository
from app.services.subscription_service import SubscriptionService


def test_concurrent_activation_prevents_overlap(run_async):
    """Test that concurrent activation of pending subscriptions for the same user is prevented."""
    async def _test():
        # Setup: create user and plan in one session
        async with async_session_factory() as setup_session:
            user = User(email=f"test_{uuid.uuid4()}@example.com", password_hash="hash", role=UserRole.CANDIDATE)
            setup_session.add(user)
            plan = RecruitmentPlan(name="Test Plan", price=1000, currency="VND", duration_days=30, max_job_posts=1)
            setup_session.add(plan)
            await setup_session.commit()
            await setup_session.refresh(user)
            await setup_session.refresh(plan)
            user_id = user.id
            plan_id = plan.id

        # Create two pending subscriptions in separate transactions
        async with async_session_factory() as session1:
            pending1 = Subscription(user_id=user_id, plan_id=plan_id, status=SubscriptionStatus.PENDING)
            session1.add(pending1)
            await session1.commit()
            await session1.refresh(pending1)

        async with async_session_factory() as session2:
            pending2 = Subscription(user_id=user_id, plan_id=plan_id, status=SubscriptionStatus.PENDING)
            session2.add(pending2)
            await session2.commit()
            await session2.refresh(pending2)

        # Try to activate both concurrently using separate sessions
        async def activate_sub(pending_id):
            async with async_session_factory() as session:
                service = SubscriptionService(session)
                return await service.activate_subscription(pending_id)

        task1 = asyncio.create_task(activate_sub(pending1.id))
        task2 = asyncio.create_task(activate_sub(pending2.id))

        results = await asyncio.gather(task1, task2, return_exceptions=True)

        successes = [r for r in results if not isinstance(r, Exception)]
        exceptions = [r for r in results if isinstance(r, Exception)]

        # Exactly one should succeed, one should fail with ConflictException
        assert len(successes) == 1
        assert len(exceptions) == 1
        assert "already has an active subscription" in str(exceptions[0])

        # Verify only one active subscription exists
        async with async_session_factory() as check_session:
            subs = await SubscriptionRepository(check_session).get_by_user_id(user_id)
            active_subs = [s for s in subs if s.status == SubscriptionStatus.ACTIVE]
            assert len(active_subs) == 1

    run_async(_test())


def test_concurrent_admin_provisioning_prevents_overlap(run_async):
    """Test that concurrent admin provisioning for the same user is prevented."""
    async def _test():
        # Setup: create user and plans
        async with async_session_factory() as setup_session:
            user = User(email=f"test_{uuid.uuid4()}@example.com", password_hash="hash", role=UserRole.CANDIDATE)
            setup_session.add(user)
            plan1 = RecruitmentPlan(name="Plan A", price=1000, currency="VND", duration_days=30, max_job_posts=1)
            plan2 = RecruitmentPlan(name="Plan B", price=2000, currency="VND", duration_days=30, max_job_posts=2)
            setup_session.add_all([plan1, plan2])
            await setup_session.commit()
            await setup_session.refresh(user)
            await setup_session.refresh(plan1)
            await setup_session.refresh(plan2)
            user_id = user.id
            plan1_id = plan1.id
            plan2_id = plan2.id

        # Run two concurrent provisioning attempts using separate sessions
        async def admin_provision_sub(user_id, plan_id):
            async with async_session_factory() as session:
                service = SubscriptionService(session)
                sub = await service.create_pending_subscription(user_id, plan_id)
                return await service.activate_subscription(sub.id)

        taskA = asyncio.create_task(admin_provision_sub(user_id, plan1_id))
        taskB = asyncio.create_task(admin_provision_sub(user_id, plan2_id))

        results = await asyncio.gather(taskA, taskB, return_exceptions=True)

        successes = [r for r in results if not isinstance(r, Exception)]
        exceptions = [r for r in results if isinstance(r, Exception)]

        assert len(successes) == 1, "Expected exactly 1 provisioning to succeed"
        assert len(exceptions) == 1, "Expected exactly 1 provisioning to fail"
        from app.core.exceptions import ConflictException
        assert isinstance(exceptions[0], ConflictException), "Failure should be ConflictException"

        # Verify only one active subscription exists in the database
        async with async_session_factory() as check_session:
            subs = await SubscriptionRepository(check_session).get_by_user_id(user_id)
            active_subs = [s for s in subs if s.status == SubscriptionStatus.ACTIVE]
            assert len(active_subs) == 1

    run_async(_test())