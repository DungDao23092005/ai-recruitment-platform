import uuid
from sqlalchemy import select

from app.domain.enums import UserRole, PaymentProvider
from app.models import User, RecruitmentPlan, Subscription, PaymentOrder, PaymentTransaction

def test_financial_delete_safety(session, run_async):
    async def _test():
        # Create User
        user = User(email=f"test_{uuid.uuid4()}@example.com", password_hash="hash", role=UserRole.CANDIDATE)
        session.add(user)

        # Create Plan
        plan = RecruitmentPlan(name="Test Plan", price=1000, currency="VND", duration_days=30, max_job_posts=1)
        session.add(plan)

        await session.flush()

        # Create Subscription
        sub = Subscription(user_id=user.id, plan_id=plan.id)
        session.add(sub)
        await session.flush()

        # Create PaymentOrder
        order = PaymentOrder(
            user_id=user.id, plan_id=plan.id, subscription_id=sub.id, amount=1000,
            currency="VND", provider=PaymentProvider.MOMO, internal_order_id=str(uuid.uuid4())
        )
        session.add(order)
        await session.flush()

        # Create PaymentTransaction
        txn = PaymentTransaction(payment_order_id=order.id)
        session.add(txn)
        await session.flush()

        from sqlalchemy.exc import IntegrityError
        import pytest

        # Attempt to delete the user
        # SQLAlchemy will try to either delete the children or nullify their non-nullable FKs.
        # This MUST fail safely with an IntegrityError rather than silently destroying history.
        with pytest.raises(IntegrityError):
            await session.delete(user)
            await session.flush()

        # Ensure we roll back the failed transaction
        await session.rollback()

    run_async(_test())
