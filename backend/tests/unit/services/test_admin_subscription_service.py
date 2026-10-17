import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ConflictException
from app.domain.enums import SubscriptionAuditAction, SubscriptionStatus
from app.models import Subscription
from app.repositories import (
    PaymentOrderRepository,
    RecruitmentPlanRepository,
    SubscriptionAuditLogRepository,
    SubscriptionRepository,
)
from app.services.admin_subscription_service import AdminSubscriptionService


def make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    return session


def make_service() -> AdminSubscriptionService:
    service = AdminSubscriptionService(make_session())
    service.subscriptions = AsyncMock(spec=SubscriptionRepository)
    service.plans = AsyncMock(spec=RecruitmentPlanRepository)
    service.payment_orders = AsyncMock(spec=PaymentOrderRepository)
    service.audit = AsyncMock(spec=SubscriptionAuditLogRepository)
    return service


def make_plan(**overrides):
    values = {
        "id": uuid.uuid4(),
        "name": "Gói mới",
        "duration_days": 60,
        "max_job_posts": 2,
        "max_candidate_searches": 2,
        "max_ai_features": 2,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class TestPendingPaymentGuard:
    def test_blocks_on_unexpired_pending_order(self):
        service = make_service()
        service.payment_orders.get_active_pending_for_user = AsyncMock(
            return_value=[SimpleNamespace(id=uuid.uuid4())]
        )
        service.payment_orders.has_paid_order_with_pending_subscription = AsyncMock(
            return_value=False
        )

        with pytest.raises(ConflictException):
            asyncio.run(service._assert_no_unresolved_payment(uuid.uuid4()))

    def test_blocks_on_paid_order_with_pending_subscription(self):
        service = make_service()
        service.payment_orders.get_active_pending_for_user = AsyncMock(return_value=[])
        service.payment_orders.has_paid_order_with_pending_subscription = AsyncMock(
            return_value=True
        )

        with pytest.raises(ConflictException):
            asyncio.run(service._assert_no_unresolved_payment(uuid.uuid4()))

    def test_passes_when_no_unresolved_payment(self):
        service = make_service()
        service.payment_orders.get_active_pending_for_user = AsyncMock(return_value=[])
        service.payment_orders.has_paid_order_with_pending_subscription = AsyncMock(
            return_value=False
        )

        asyncio.run(service._assert_no_unresolved_payment(uuid.uuid4()))


class TestApplyPlanSnapshot:
    def test_resets_usage_and_snapshots_quota(self):
        service = make_service()
        sub = Subscription(
            user_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            status=SubscriptionStatus.PENDING,
            job_posts_used=4,
            candidate_searches_used=3,
            ai_features_used=2,
        )
        plan = make_plan()
        now = datetime(2026, 10, 17, tzinfo=timezone.utc)

        service._apply_plan_snapshot(sub, plan, now, reset_usage=True)

        assert sub.plan_id == plan.id
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.started_at == now
        assert sub.expires_at == now + timedelta(days=plan.duration_days)
        assert sub.max_job_posts == 2
        assert sub.job_posts_used == 0

    def test_preserves_usage_when_not_resetting(self):
        service = make_service()
        sub = Subscription(
            user_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            status=SubscriptionStatus.ACTIVE,
            job_posts_used=9,
            candidate_searches_used=9,
            ai_features_used=9,
        )
        plan = make_plan()
        now = datetime(2026, 10, 17, tzinfo=timezone.utc)

        service._apply_plan_snapshot(sub, plan, now, reset_usage=False)

        assert sub.job_posts_used == 9
        assert sub.candidate_searches_used == 9
        assert sub.ai_features_used == 9
        assert sub.max_job_posts == 2


class TestChangePlanGuards:
    def test_rejects_target_equal_to_current_plan(self):
        service = make_service()
        plan_id = uuid.uuid4()
        sub = Subscription(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE,
        )
        service.subscriptions.get_by_id_including_deleted = AsyncMock(return_value=sub)
        service._lock_user = AsyncMock()
        service._assert_no_unresolved_payment = AsyncMock()
        service.plans.get_active_by_id = AsyncMock(
            return_value=make_plan(id=plan_id)
        )

        with pytest.raises(ConflictException):
            asyncio.run(
                service.change_plan(
                    admin_id=uuid.uuid4(),
                    subscription_id=sub.id,
                    target_plan_id=plan_id,
                    reason="đổi sang chính nó",
                )
            )

    def test_add_audit_builds_append_only_row(self):
        service = make_service()
        admin_id = uuid.uuid4()
        sub = Subscription(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            status=SubscriptionStatus.ACTIVE,
        )

        log = service._add_audit(
            admin_id=admin_id,
            subscription=sub,
            action=SubscriptionAuditAction.CHANGE_PLAN,
            old_plan_id=sub.plan_id,
            new_plan_id=uuid.uuid4(),
            reason="  lý do hợp lệ  ",
        )

        assert log.admin_id == admin_id
        assert log.user_id == sub.user_id
        assert log.subscription_id == sub.id
        assert log.action == SubscriptionAuditAction.CHANGE_PLAN
        assert log.reason == "lý do hợp lệ"
        service.session.add.assert_called_once_with(log)
