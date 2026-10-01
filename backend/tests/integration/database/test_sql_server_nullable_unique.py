import pytest
import uuid
from sqlalchemy.exc import IntegrityError
from app.domain.enums import UserRole, PaymentProvider
from app.models import User, RecruitmentPlan, Subscription, PaymentOrder

def test_sql_server_nullable_unique(session, run_async):
    async def _test():
        user = User(email=f"test_{uuid.uuid4()}@example.com", password_hash="hash", role=UserRole.CANDIDATE)
        session.add(user)
        plan = RecruitmentPlan(name="Test Plan", price=1000, currency="VND", duration_days=30, max_job_posts=1)
        session.add(plan)
        await session.flush()

        # Case A: Two rows with NULL provider_order_id must both succeed
        order1 = PaymentOrder(
            user_id=user.id, plan_id=plan.id, amount=1000, currency="VND",
            provider=PaymentProvider.MOMO, internal_order_id=str(uuid.uuid4()),
            provider_order_id=None
        )
        session.add(order1)

        order2 = PaymentOrder(
            user_id=user.id, plan_id=plan.id, amount=1000, currency="VND",
            provider=PaymentProvider.MOMO, internal_order_id=str(uuid.uuid4()),
            provider_order_id=None
        )
        session.add(order2)
        await session.flush()  # Both should succeed, no exception

        # Case B: Two rows with same provider_order_id must fail
        order3 = PaymentOrder(
            user_id=user.id, plan_id=plan.id, amount=1000, currency="VND",
            provider=PaymentProvider.MOMO, internal_order_id=str(uuid.uuid4()),
            provider_order_id="ABC"
        )
        session.add(order3)
        await session.flush()

        order4 = PaymentOrder(
            user_id=user.id, plan_id=plan.id, amount=1000, currency="VND",
            provider=PaymentProvider.MOMO, internal_order_id=str(uuid.uuid4()),
            provider_order_id="ABC"
        )
        session.add(order4)

        with pytest.raises(IntegrityError):
            await session.flush()

        await session.rollback()

        # Re-add user and plan for Case C
        session.add(user)
        session.add(plan)

        # Case C: Two rows with different provider_order_id must succeed
        order5 = PaymentOrder(
            user_id=user.id, plan_id=plan.id, amount=1000, currency="VND",
            provider=PaymentProvider.MOMO, internal_order_id=str(uuid.uuid4()),
            provider_order_id="DEF"
        )
        session.add(order5)

        order6 = PaymentOrder(
            user_id=user.id, plan_id=plan.id, amount=1000, currency="VND",
            provider=PaymentProvider.MOMO, internal_order_id=str(uuid.uuid4()),
            provider_order_id="GHI"
        )
        session.add(order6)
        await session.flush()

    run_async(_test())
