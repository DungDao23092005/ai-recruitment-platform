import pytest
import asyncio
import uuid
from app.domain.enums import UserRole, SubscriptionStatus
from app.models import User, RecruitmentPlan, Subscription

def test_sql_server_empty_result_race_condition(session, run_async):
    async def _test():
        # Setup
        user = User(email=f"test_{uuid.uuid4()}@example.com", password_hash="hash", role=UserRole.CANDIDATE)
        session.add(user)
        plan = RecruitmentPlan(name="Plan", price=1000, currency="VND", duration_days=30, max_job_posts=1)
        session.add(plan)
        await session.commit()
        from app.services.subscription_service import SubscriptionService
        from app.database.session import async_session_factory
            # Test 1: Concurrently creating pending subscriptions for DIFFERENT plans
        plan2 = RecruitmentPlan(name="Plan 2", price=2000, currency="VND", duration_days=30, max_job_posts=2)
        session.add(plan2)
        await session.commit()

        async with async_session_factory() as sessionA, async_session_factory() as sessionB:
            serviceA = SubscriptionService(sessionA)
            serviceB = SubscriptionService(sessionB)
            # Start transactions
            # Since neither user has an active subscription, with_for_update() locks nothing!
            taskA = asyncio.create_task(serviceA.create_pending_subscription(user.id, plan.id))
            taskB = asyncio.create_task(serviceB.create_pending_subscription(user.id, plan2.id))

            subA, subB = await asyncio.gather(taskA, taskB)
        async with async_session_factory() as check_session:
            service = SubscriptionService(check_session)
            subs = await service.list_user_subscriptions(user.id)
            pending_subs = [s for s in subs if s.status == SubscriptionStatus.PENDING]

            # If the application lock worked, maybe it would block. But for different plans, the pending check is on different plans.
            # So BOTH will be created.
            assert len(pending_subs) == 2, "Both pending subscriptions were created, no lock occurred."

    run_async(_test())
