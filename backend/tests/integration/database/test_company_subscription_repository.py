"""Wave 1.4 Phase 2 — Company Subscription Repository & Persistence integration tests.

Scenarios:
- P12: Effective active includes null expires_at
- P13: Effective active includes future expires_at
- P14: Effective active excludes past or equal expires_at
- P15: Stale query identifies active with expires_at <= now
- P22: Company subscription creation persists user_id never null
"""

from __future__ import annotations

from datetime import timedelta
import uuid

import pytest
from sqlalchemy import select

from app.database.session import async_session_factory
from app.domain.enums import MembershipRole, SubscriptionStatus
from app.domain.models.base import utc_now
from app.models import PaymentOrder, Subscription
from app.repositories.subscription_repository import SubscriptionRepository
from app.services.payment_service import PaymentService
from tests.integration.company_billing_helpers import (
    _create_company,
    _create_company_subscription,
    _create_membership,
    _create_plan,
    _create_user,
)

pytestmark = pytest.mark.integration


def test_p12_effective_active_includes_null_expires_at(run_async):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            plan = await _create_plan(session)
            sub = await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
                expires_at=None,
            )
            await session.commit()

            repo = SubscriptionRepository(session)
            found = await repo.get_active_by_company_id(company.id, utc_now())
            assert found is not None
            assert found.id == sub.id

    run_async(_run())


def test_p13_effective_active_includes_future_expires_at(run_async):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            plan = await _create_plan(session)
            now = utc_now()
            sub = await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
                expires_at=now + timedelta(hours=2),
            )
            await session.commit()

            repo = SubscriptionRepository(session)
            found = await repo.get_active_by_company_id(company.id, now)
            assert found is not None
            assert found.id == sub.id

    run_async(_run())


def test_p14_effective_active_excludes_past_or_equal_expires_at(run_async):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            plan = await _create_plan(session)
            now = utc_now()
            await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
                expires_at=now,
            )
            await session.commit()

            repo = SubscriptionRepository(session)
            found = await repo.get_active_by_company_id(company.id, now)
            assert found is None

    run_async(_run())


def test_p15_stale_query_identifies_active_with_expires_at_lte_now(run_async):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            plan = await _create_plan(session)
            now = utc_now()
            sub = await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
                expires_at=now - timedelta(minutes=1),
            )
            await session.commit()

            repo = SubscriptionRepository(session)
            expired_count = await repo.expire_stale_active_for_company(
                company.id, now
            )
            await session.commit()
            assert expired_count == 1
            await session.refresh(sub)
            assert sub.status == SubscriptionStatus.EXPIRED

    run_async(_run())


def test_p22_company_subscription_creation_persists_user_id_never_null(
    run_async,
):
    """P22: Company subscription creation persists Subscription.user_id == current_user.id, never NULL."""
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session)
            await session.commit()
            user_id, company_id, plan_id = user.id, company.id, plan.id

        async with async_session_factory() as session:
            _, ref, sub_id = await PaymentService(
                session
            ).create_company_vnpay_payment(
                user_id=user_id,
                company_id=company_id,
                plan_id=plan_id,
                client_ip="127.0.0.1",
            )
            order = await session.scalar(
                select(PaymentOrder).where(
                    PaymentOrder.internal_order_id == ref
                )
            )
            assert order is not None
            assert order.user_id == user_id
            assert order.company_id == company_id
            sub = await session.get(Subscription, sub_id)
            assert sub is not None
            assert sub.user_id is not None
            assert sub.user_id == user_id
            assert sub.company_id == company_id

    run_async(_run())
