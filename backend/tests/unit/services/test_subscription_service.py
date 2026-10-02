import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    InvalidTransitionException,
)
from app.domain.enums import SubscriptionStatus
from app.domain.models.base import utc_now
from app.models import RecruitmentPlan, Subscription, User
from app.repositories import RecruitmentPlanRepository, SubscriptionRepository
from app.services.subscription_service import SubscriptionService


def make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    return session


def make_plan(plan_id: uuid.UUID | None = None) -> RecruitmentPlan:
    return RecruitmentPlan(
        id=plan_id or uuid.uuid4(),
        name="Test Plan",
        price=1000000,
        currency="VND",
        duration_days=30,
        max_job_posts=5,
    )


def make_subscription(
    sub_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    plan_id: uuid.UUID | None = None,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    expires_at: datetime | None = None,
) -> Subscription:
    now = utc_now()
    return Subscription(
        id=sub_id or uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        plan_id=plan_id or uuid.uuid4(),
        status=status,
        started_at=now - timedelta(days=1),
        expires_at=expires_at if expires_at is not None else now + timedelta(days=30),
    )


def make_user(user_id: uuid.UUID | None = None) -> User:
    return User(
        id=user_id or uuid.uuid4(),
        email="test@example.com",
        password_hash="hash",
        role="candidate",
    )


def make_service(session: MagicMock) -> SubscriptionService:
    service = SubscriptionService(session)
    service.subscriptions = AsyncMock(spec=SubscriptionRepository)
    service.plans = AsyncMock(spec=RecruitmentPlanRepository)
    return service


class TestGetCurrentActiveSubscription:
    def test_returns_active_subscription(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        sub = make_subscription(user_id=user_id)
        service.subscriptions.get_active_by_user_id.return_value = sub

        result = asyncio.run(service.get_current_active_subscription(user_id))

        assert result is sub
        service.subscriptions.get_active_by_user_id.assert_awaited_once()

    def test_returns_none_when_no_active(self):
        session = make_session()
        service = make_service(session)
        service.subscriptions.get_active_by_user_id.return_value = None

        result = asyncio.run(service.get_current_active_subscription(uuid.uuid4()))

        assert result is None


class TestGetSubscriptionById:
    def test_returns_subscription(self):
        session = make_session()
        service = make_service(session)
        sub = make_subscription()
        service.subscriptions.get_by_id_including_deleted.return_value = sub

        result = asyncio.run(service.get_subscription_by_id(sub.id, sub.user_id))

        assert result is sub

    def test_raises_not_found(self):
        session = make_session()
        service = make_service(session)
        service.subscriptions.get_by_id_including_deleted.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.get_subscription_by_id(uuid.uuid4()))

    def test_raises_not_found_for_other_user(self):
        session = make_session()
        service = make_service(session)
        sub = make_subscription()
        service.subscriptions.get_by_id_including_deleted.return_value = sub

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.get_subscription_by_id(sub.id, uuid.uuid4()))


class TestListUserSubscriptions:
    def test_returns_subscriptions(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        subs = [make_subscription(user_id=user_id) for _ in range(3)]
        service.subscriptions.get_by_user_id.return_value = subs

        result = asyncio.run(service.list_user_subscriptions(user_id))

        assert result == subs


class TestCreatePendingSubscription:
    def test_creates_pending_subscription(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        plan = make_plan(plan_id=plan_id)

        # Mock _lock_user_for_subscription
        user = make_user(user_id=user_id)
        mock_lock_result = MagicMock()
        mock_lock_result.scalar_one_or_none.return_value = user
        # Mock _check_active_overlap
        mock_check_result = MagicMock()
        mock_check_result.scalar_one_or_none.return_value = None
        # Mock pending check
        mock_pending_result = MagicMock()
        mock_pending_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [mock_lock_result, mock_check_result, mock_pending_result]

        service.plans.get_active_by_id.return_value = plan
        service.subscriptions.get_by_user_id.return_value = []

        sub = asyncio.run(service.create_pending_subscription(user_id, plan_id))

        assert isinstance(sub, Subscription)
        assert sub.user_id == user_id
        assert sub.plan_id == plan_id
        assert sub.status == SubscriptionStatus.PENDING
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    def test_raises_plan_not_found(self):
        session = make_session()
        service = make_service(session)
        service.plans.get_active_by_id.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.create_pending_subscription(uuid.uuid4(), uuid.uuid4()))

    def test_raises_conflict_when_active_exists(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        plan = make_plan(plan_id=plan_id)
        active_sub = make_subscription(user_id=user_id)

        user = make_user(user_id=user_id)
        mock_lock_result = MagicMock()
        mock_lock_result.scalar_one_or_none.return_value = user
        mock_check_result = MagicMock()
        mock_check_result.scalar_one_or_none.return_value = active_sub

        session.execute.side_effect = [mock_lock_result, mock_check_result]

        service.plans.get_active_by_id.return_value = plan

        with pytest.raises(ConflictException):
            asyncio.run(service.create_pending_subscription(user_id, plan_id))

    def test_returns_existing_pending_for_same_plan(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        plan = make_plan(plan_id=plan_id)
        pending_sub = make_subscription(user_id=user_id, plan_id=plan_id, status=SubscriptionStatus.PENDING)

        user = make_user(user_id=user_id)
        mock_lock_result = MagicMock()
        mock_lock_result.scalar_one_or_none.return_value = user
        mock_check_result = MagicMock()
        mock_check_result.scalar_one_or_none.return_value = None
        mock_pending_result = MagicMock()
        mock_pending_result.scalar_one_or_none.return_value = pending_sub

        session.execute.side_effect = [mock_lock_result, mock_check_result, mock_pending_result]

        service.plans.get_active_by_id.return_value = plan

        sub = asyncio.run(service.create_pending_subscription(user_id, plan_id))

        assert sub is pending_sub


class TestActivateSubscription:
    def test_activates_pending_subscription(self):
        session = make_session()
        service = make_service(session)
        sub_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        plan = make_plan(plan_id=plan_id)
        sub = make_subscription(sub_id=sub_id, plan_id=plan_id, status=SubscriptionStatus.PENDING)

        user = make_user(user_id=sub.user_id)
        mock_lock_result = MagicMock()
        mock_lock_result.scalar_one_or_none.return_value = user
        mock_check_result = MagicMock()
        mock_check_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [mock_lock_result, mock_check_result]

        service.subscriptions.get_by_id_including_deleted.return_value = sub
        service.plans.get_active_by_id.return_value = plan

        result = asyncio.run(service.activate_subscription(sub_id))

        assert result is sub
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.started_at is not None
        assert sub.expires_at is not None
        assert sub.expires_at > sub.started_at

    def test_raises_not_found(self):
        session = make_session()
        service = make_service(session)
        service.subscriptions.get_by_id_including_deleted.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.activate_subscription(uuid.uuid4()))

    def test_raises_invalid_transition(self):
        session = make_session()
        service = make_service(session)
        sub = make_subscription(status=SubscriptionStatus.ACTIVE)
        service.subscriptions.get_by_id_including_deleted.return_value = sub

        with pytest.raises(InvalidTransitionException):
            asyncio.run(service.activate_subscription(sub.id))

    def test_raises_inactive_plan(self):
        session = make_session()
        service = make_service(session)
        sub = make_subscription(status=SubscriptionStatus.PENDING)
        service.subscriptions.get_by_id_including_deleted.return_value = sub
        service.plans.get_active_by_id.return_value = None

        # Mock the new locking and check calls
        user = make_user(user_id=sub.user_id)
        mock_lock_result = MagicMock()
        mock_lock_result.scalar_one_or_none.return_value = user
        mock_check_result = MagicMock()
        mock_check_result.scalar_one_or_none.return_value = None
        session.execute.side_effect = [mock_lock_result, mock_check_result]

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.activate_subscription(sub.id))

    def test_raises_conflict_when_active_exists(self):
        """Activate should fail if user already has another active subscription."""
        session = make_session()
        service = make_service(session)
        sub_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        plan = make_plan(plan_id=plan_id)
        sub = make_subscription(sub_id=sub_id, plan_id=plan_id, status=SubscriptionStatus.PENDING)
        other_active = make_subscription(user_id=sub.user_id, status=SubscriptionStatus.ACTIVE)

        user = make_user(user_id=sub.user_id)
        mock_lock_result = MagicMock()
        mock_lock_result.scalar_one_or_none.return_value = user
        mock_check_result = MagicMock()
        mock_check_result.scalar_one_or_none.return_value = other_active

        session.execute.side_effect = [mock_lock_result, mock_check_result]

        service.subscriptions.get_by_id_including_deleted.return_value = sub
        service.plans.get_active_by_id.return_value = plan

        with pytest.raises(ConflictException):
            asyncio.run(service.activate_subscription(sub_id))


class TestCancelSubscription:
    def test_cancels_active_subscription(self):
        session = make_session()
        service = make_service(session)
        sub = make_subscription(status=SubscriptionStatus.ACTIVE)
        service.subscriptions.get_by_id_including_deleted.return_value = sub

        result = asyncio.run(service.cancel_subscription(sub.id))

        assert result is sub
        assert sub.status == SubscriptionStatus.CANCELLED

    def test_cancels_pending_subscription(self):
        session = make_session()
        service = make_service(session)
        sub = make_subscription(status=SubscriptionStatus.PENDING)
        service.subscriptions.get_by_id_including_deleted.return_value = sub

        result = asyncio.run(service.cancel_subscription(sub.id))

        assert result is sub
        assert sub.status == SubscriptionStatus.CANCELLED

    def test_raises_invalid_transition_for_expired(self):
        session = make_session()
        service = make_service(session)
        sub = make_subscription(status=SubscriptionStatus.EXPIRED)
        service.subscriptions.get_by_id_including_deleted.return_value = sub

        with pytest.raises(InvalidTransitionException):
            asyncio.run(service.cancel_subscription(sub.id))

    def test_user_must_match(self):
        session = make_session()
        service = make_service(session)
        sub = make_subscription(user_id=uuid.uuid4(), status=SubscriptionStatus.ACTIVE)
        service.subscriptions.get_by_id_including_deleted.return_value = sub

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.cancel_subscription(sub.id, uuid.uuid4()))


class TestConcurrency:
    """Test that concurrent subscription creation cannot create overlapping active subscriptions."""

    def test_concurrent_create_pending_race_condition(self):
        """
        This test simulates the race condition where two concurrent requests
        try to create an active subscription for the same user.

        The protection mechanism is locking the User row (which always exists)
        using SELECT FOR UPDATE, which serializes the critical section.

        In this unit test we verify the logic flow - the actual database locking
        behavior is tested in integration tests against real SQL Server.
        """
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        plan = make_plan(plan_id=plan_id)

        # First call - no active subscription
        user = make_user(user_id=user_id)
        mock_lock_result1 = MagicMock()
        mock_lock_result1.scalar_one_or_none.return_value = user
        mock_check_result1 = MagicMock()
        mock_check_result1.scalar_one_or_none.return_value = None
        mock_pending_result1 = MagicMock()
        mock_pending_result1.scalar_one_or_none.return_value = None
        session.execute.side_effect = [mock_lock_result1, mock_check_result1, mock_pending_result1]

        service.plans.get_active_by_id.return_value = plan

        sub1 = asyncio.run(service.create_pending_subscription(user_id, plan_id))

        assert sub1.status == SubscriptionStatus.PENDING

        # Second call - now there's a pending subscription for the same plan
        mock_lock_result2 = MagicMock()
        mock_lock_result2.scalar_one_or_none.return_value = user
        mock_check_result2 = MagicMock()
        mock_check_result2.scalar_one_or_none.return_value = None
        mock_pending_result2 = MagicMock()
        mock_pending_result2.scalar_one_or_none.return_value = sub1
        session.execute.side_effect = [mock_lock_result2, mock_check_result2, mock_pending_result2]

        sub2 = asyncio.run(service.create_pending_subscription(user_id, plan_id))

        assert sub2 is sub1  # Should return the same pending subscription


class TestCheckAndExpireSubscriptions:
    def test_expires_overdue_subscriptions(self):
        session = make_session()
        service = make_service(session)
        now = utc_now()

        expired_sub1 = make_subscription(
            expires_at=now - timedelta(days=1),
            status=SubscriptionStatus.ACTIVE,
        )
        expired_sub2 = make_subscription(
            expires_at=now - timedelta(hours=1),
            status=SubscriptionStatus.ACTIVE,
        )
        active_sub = make_subscription(
            expires_at=now + timedelta(days=10),
            status=SubscriptionStatus.ACTIVE,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [expired_sub1, expired_sub2]
        session.execute.return_value = mock_result

        count = asyncio.run(service.check_and_expire_subscriptions(now))

        assert count == 2
        assert expired_sub1.status == SubscriptionStatus.EXPIRED
        assert expired_sub2.status == SubscriptionStatus.EXPIRED
        assert active_sub.status == SubscriptionStatus.ACTIVE
        session.commit.assert_awaited_once()

    def test_returns_zero_when_none_expired(self):
        session = make_session()
        service = make_service(session)
        now = utc_now()

        active_sub = make_subscription(
            expires_at=now + timedelta(days=10),
            status=SubscriptionStatus.ACTIVE,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        count = asyncio.run(service.check_and_expire_subscriptions(now))

        assert count == 0
        session.commit.assert_not_awaited()