"""Real SQL Server integration tests for admin subscription invalidation events.

Proves that a minimal ``admin.subscription.changed`` event is published to the
``admin:subscriptions`` channel AFTER the mutation commits, once per genuine
transition, for each supported flow, and that neither a rolled-back mutation nor
a Redis publish failure can emit or break anything.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings

# Ensure the VNPAY provider can build/sign links in the test environment.
settings.VNPAY_TMN_CODE = "TESTTMN"
settings.VNPAY_HASH_SECRET = "testhashsecret123"

from app.core.exceptions import ConflictException  # noqa: E402
from app.database.session import async_session_factory  # noqa: E402
from app.domain.enums import SubscriptionAuditAction, SubscriptionStatus, UserRole  # noqa: E402
from app.models import RecruitmentPlan, Subscription, User  # noqa: E402
from app.services.admin_subscription_service import AdminSubscriptionService  # noqa: E402
from app.services.payment_service import PaymentService  # noqa: E402
from app.services.subscription_realtime import (  # noqa: E402
    ACTION_ACTIVATED,
    ACTION_ORDER_CREATED,
    ACTION_PLAN_CHANGED,
    ACTION_REVOKED,
    ADMIN_SUBSCRIPTIONS_CHANNEL,
)


pytestmark = pytest.mark.integration

_PUBSUB_TARGET = "app.services.subscription_realtime.pubsub_manager"


def _fake_manager() -> MagicMock:
    manager = MagicMock()
    manager.publish = AsyncMock()
    return manager


async def _seed_user(session, *, role: UserRole = UserRole.CANDIDATE) -> User:
    user = User(
        email=f"rt-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="hashed",
        role=role,
    )
    session.add(user)
    await session.flush()
    return user


async def _seed_plan(session, *, price: int = 299_000, name: str = "Professional") -> RecruitmentPlan:
    plan = RecruitmentPlan(
        name=name,
        price=price,
        currency="VND",
        duration_days=30,
        max_job_posts=10,
        max_candidate_searches=10,
        max_ai_features=10,
        is_active=True,
        display_order=1,
    )
    session.add(plan)
    await session.flush()
    return plan


async def _seed_active_subscription(session, user, plan) -> Subscription:
    now = datetime.now(timezone.utc)
    sub = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        started_at=now,
        expires_at=now + timedelta(days=30),
        max_job_posts=plan.max_job_posts,
    )
    session.add(sub)
    await session.flush()
    return sub


def _assert_event(message: dict, *, action: str, user_id, subscription_id):
    assert message["action"] == action
    assert message["user_id"] == str(user_id)
    assert message["subscription_id"] == str(subscription_id)


def test_provision_publishes_activated_event_after_commit(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan = await _seed_plan(setup)
            user = await _seed_user(setup)
            admin = await _seed_user(setup, role=UserRole.ADMIN)
            await setup.commit()
            plan_id, user_id, admin_id = plan.id, user.id, admin.id

        manager = _fake_manager()
        with patch(_PUBSUB_TARGET, manager):
            async with async_session_factory() as session:
                sub = await AdminSubscriptionService(session).provision(
                    admin_id=admin_id, user_id=user_id, plan_id=plan_id
                )
                sub_id = sub.id
                # The event must only appear once the commit has happened and the
                # scheduled task has had a chance to run.
                await asyncio.sleep(0.05)

        assert manager.publish.await_count == 1
        channel, message = manager.publish.await_args.args
        assert channel == ADMIN_SUBSCRIPTIONS_CHANNEL
        _assert_event(message, action=ACTION_ACTIVATED, user_id=user_id, subscription_id=sub_id)

    run_async(_run())


def test_change_plan_publishes_plan_changed_event(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan = await _seed_plan(setup, name="Starter", price=99_000)
            target = await _seed_plan(setup, name="Enterprise", price=999_000)
            user = await _seed_user(setup)
            admin = await _seed_user(setup, role=UserRole.ADMIN)
            sub = await _seed_active_subscription(setup, user, plan)
            await setup.commit()
            sub_id, target_id, admin_id, user_id = sub.id, target.id, admin.id, user.id

        manager = _fake_manager()
        with patch(_PUBSUB_TARGET, manager):
            async with async_session_factory() as session:
                await AdminSubscriptionService(session).change_plan(
                    admin_id=admin_id,
                    subscription_id=sub_id,
                    target_plan_id=target_id,
                    reason="Nâng cấp theo yêu cầu",
                )
                await asyncio.sleep(0.05)

        assert manager.publish.await_count == 1
        channel, message = manager.publish.await_args.args
        assert channel == ADMIN_SUBSCRIPTIONS_CHANNEL
        _assert_event(message, action=ACTION_PLAN_CHANGED, user_id=user_id, subscription_id=sub_id)

    run_async(_run())


def test_revoke_publishes_revoked_event(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan = await _seed_plan(setup)
            user = await _seed_user(setup)
            admin = await _seed_user(setup, role=UserRole.ADMIN)
            sub = await _seed_active_subscription(setup, user, plan)
            await setup.commit()
            sub_id, admin_id, user_id = sub.id, admin.id, user.id

        manager = _fake_manager()
        with patch(_PUBSUB_TARGET, manager):
            async with async_session_factory() as session:
                await AdminSubscriptionService(session).revoke(
                    admin_id=admin_id,
                    subscription_id=sub_id,
                    reason="Thu hồi thử nghiệm",
                )
                await asyncio.sleep(0.05)

        assert manager.publish.await_count == 1
        channel, message = manager.publish.await_args.args
        assert channel == ADMIN_SUBSCRIPTIONS_CHANNEL
        _assert_event(message, action=ACTION_REVOKED, user_id=user_id, subscription_id=sub_id)

    run_async(_run())


def test_checkout_publishes_order_created_event(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan = await _seed_plan(setup)
            user = await _seed_user(setup)
            await setup.commit()
            plan_id, user_id = plan.id, user.id

        manager = _fake_manager()
        with patch(_PUBSUB_TARGET, manager):
            async with async_session_factory() as session:
                _, _, sub_id = await PaymentService(session).create_vnpay_payment(
                    user_id, plan_id, "127.0.0.1"
                )
                await asyncio.sleep(0.05)

        assert manager.publish.await_count == 1
        channel, message = manager.publish.await_args.args
        assert channel == ADMIN_SUBSCRIPTIONS_CHANNEL
        _assert_event(message, action=ACTION_ORDER_CREATED, user_id=user_id, subscription_id=sub_id)

    run_async(_run())


def test_rolled_back_mutation_publishes_no_event(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan = await _seed_plan(setup)
            user = await _seed_user(setup)
            admin = await _seed_user(setup, role=UserRole.ADMIN)
            await setup.commit()
            plan_id, user_id, admin_id = plan.id, user.id, admin.id

        manager = _fake_manager()
        with patch(_PUBSUB_TARGET, manager):
            async with async_session_factory() as session:
                with patch.object(
                    session, "commit", new=AsyncMock(side_effect=RuntimeError("db down"))
                ):
                    with pytest.raises(RuntimeError):
                        await AdminSubscriptionService(session).provision(
                            admin_id=admin_id, user_id=user_id, plan_id=plan_id
                        )
                await asyncio.sleep(0.05)

        manager.publish.assert_not_awaited()

    run_async(_run())


def test_publish_failure_does_not_break_committed_mutation(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan = await _seed_plan(setup)
            user = await _seed_user(setup)
            admin = await _seed_user(setup, role=UserRole.ADMIN)
            await setup.commit()
            plan_id, user_id, admin_id = plan.id, user.id, admin.id

        manager = _fake_manager()
        manager.publish = AsyncMock(side_effect=RuntimeError("redis down"))
        with patch(_PUBSUB_TARGET, manager):
            async with async_session_factory() as session:
                sub = await AdminSubscriptionService(session).provision(
                    admin_id=admin_id, user_id=user_id, plan_id=plan_id
                )
                await asyncio.sleep(0.05)
                assert sub.status == SubscriptionStatus.ACTIVE

        # The mutation is committed even though publishing failed.
        async with async_session_factory() as check:
            stored = await check.get(Subscription, sub.id)
            assert stored is not None
            assert stored.status == SubscriptionStatus.ACTIVE

    run_async(_run())
