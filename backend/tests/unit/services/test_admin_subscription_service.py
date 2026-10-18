import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.orm.attributes import set_committed_value

from app.core.exceptions import ConflictException, EntityNotFoundException
from app.domain.enums import (
    PaymentOrderStatus,
    PaymentProvider,
    SubscriptionAuditAction,
    SubscriptionStatus,
)
from app.domain.models.base import utc_now
from app.models import PaymentOrder, Subscription
from app.repositories import (
    PaymentOrderRepository,
    RecruitmentPlanRepository,
    SubscriptionAuditLogRepository,
    SubscriptionRepository,
)
from app.repositories.subscription_repository import AdminSubscriptionRepresentative
from app.services.admin_subscription_service import (
    AdminSubscriptionService,
    _effective_status,
)


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


def make_subscription(**overrides) -> Subscription:
    values = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "plan_id": uuid.uuid4(),
        "status": SubscriptionStatus.ACTIVE,
        "started_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "expires_at": datetime(2027, 1, 1, tzinfo=timezone.utc),
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "max_job_posts": 5,
        "max_candidate_searches": 10,
        "max_ai_features": 3,
        "job_posts_used": 1,
        "candidate_searches_used": 2,
        "ai_features_used": 0,
    }
    values.update(overrides)
    return Subscription(**values)


def make_order(**overrides) -> PaymentOrder:
    values = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "plan_id": uuid.uuid4(),
        "subscription_id": uuid.uuid4(),
        "internal_order_id": f"VNPAY_{uuid.uuid4().hex[:12]}",
        "provider": PaymentProvider.VNPAY,
        "status": PaymentOrderStatus.PAID,
        "amount": 299000,
        "currency": "VND",
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return PaymentOrder(**values)


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


class TestEffectiveStatus:
    def test_active_with_future_expiry_stays_active(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        sub = make_subscription(
            status=SubscriptionStatus.ACTIVE, expires_at=now + timedelta(days=1)
        )

        assert _effective_status(sub, now) == SubscriptionStatus.ACTIVE

    def test_active_past_expiry_reports_expired(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        sub = make_subscription(
            status=SubscriptionStatus.ACTIVE, expires_at=now - timedelta(seconds=1)
        )

        assert _effective_status(sub, now) == SubscriptionStatus.EXPIRED

    def test_active_without_expiry_stays_active(self):
        sub = make_subscription(status=SubscriptionStatus.ACTIVE, expires_at=None)

        assert _effective_status(sub, utc_now()) == SubscriptionStatus.ACTIVE

    def test_naive_expiry_is_treated_as_utc(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        sub = make_subscription(
            status=SubscriptionStatus.ACTIVE,
            expires_at=datetime(2026, 5, 31, 23, 59),
        )

        assert _effective_status(sub, now) == SubscriptionStatus.EXPIRED

    def test_non_active_status_is_untouched(self):
        sub = make_subscription(status=SubscriptionStatus.CANCELLED)

        assert _effective_status(sub, utc_now()) == SubscriptionStatus.CANCELLED


class TestListItemMapping:
    def test_maps_diagnostics_and_flags(self):
        service = make_service()
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        sub = make_subscription(
            status=SubscriptionStatus.ACTIVE,
            expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        incident = make_order(subscription_id=sub.id, amount=123456)

        item = service._to_list_item(
            sub,
            total_subscriptions=3,
            active_count=2,
            has_unresolved_payment=True,
            incident=incident,
            now=now,
            user_email="a@example.com",
        )

        assert item.effective_status == SubscriptionStatus.EXPIRED
        assert item.status == SubscriptionStatus.ACTIVE
        assert item.total_subscriptions == 3
        assert item.has_multiple_active is True
        assert item.has_unresolved_payment is True
        assert item.is_entitlement_incident is True
        assert item.incident_subscription_id == incident.subscription_id
        assert item.incident_internal_order_id == incident.internal_order_id
        assert item.incident_amount == 123456
        assert item.user_email == "a@example.com"

    def test_single_active_without_diagnostics(self):
        service = make_service()
        sub = make_subscription()

        item = service._to_list_item(
            sub, total_subscriptions=1, active_count=1, now=utc_now()
        )

        assert item.has_multiple_active is False
        assert item.has_unresolved_payment is False
        assert item.is_entitlement_incident is False
        assert item.incident_subscription_id is None
        assert item.incident_internal_order_id is None
        assert item.incident_amount is None

    def test_reads_plan_and_user_relationships_when_loaded(self):
        service = make_service()
        sub = make_subscription()
        set_committed_value(sub, "user", SimpleNamespace(email="rel@example.com"))
        set_committed_value(sub, "plan", make_plan(name="Gói quan hệ"))

        item = service._to_list_item(sub, now=utc_now())

        assert item.user_email == "rel@example.com"
        assert item.plan_name == "Gói quan hệ"


class TestHistoryMapping:
    def test_history_item_includes_plan_name_and_payments(self):
        service = make_service()
        sub = make_subscription()
        set_committed_value(sub, "plan", make_plan(name="Gói lịch sử"))
        order = make_order(subscription_id=sub.id, amount=99000)

        item = service._to_history_item(sub, [order])

        assert item.plan_name == "Gói lịch sử"
        assert len(item.payments) == 1
        payment = item.payments[0]
        assert payment.internal_order_id == order.internal_order_id
        assert payment.amount == 99000
        assert payment.subscription_id == sub.id

    def test_history_item_without_plan_or_payments(self):
        service = make_service()
        sub = make_subscription()

        item = service._to_history_item(sub, [])

        assert item.plan_name is None
        assert item.payments == []


class TestPaymentDiagnostics:
    def test_combines_pending_and_incident(self):
        service = make_service()
        u1, u2, u3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        incident = make_order(user_id=u2)
        service.payment_orders.list_active_pending_user_ids = AsyncMock(
            return_value={u1}
        )
        service.payment_orders.list_entitlement_incidents = AsyncMock(
            return_value=[incident]
        )

        result = asyncio.run(service._payment_diagnostics([u1, u2, u3], utc_now()))

        assert result[u1] == (True, None)
        assert result[u2][0] is True
        assert result[u2][1] is incident
        assert result[u3] == (False, None)

    def test_keeps_first_incident_per_user(self):
        service = make_service()
        user_id = uuid.uuid4()
        newest = make_order(user_id=user_id, internal_order_id="NEWEST")
        older = make_order(user_id=user_id, internal_order_id="OLDER")
        service.payment_orders.list_active_pending_user_ids = AsyncMock(
            return_value=set()
        )
        service.payment_orders.list_entitlement_incidents = AsyncMock(
            return_value=[newest, older]
        )

        result = asyncio.run(service._payment_diagnostics([user_id], utc_now()))

        assert result[user_id][1] is newest

    def test_empty_user_ids_short_circuits(self):
        service = make_service()
        service.payment_orders.list_active_pending_user_ids = AsyncMock()

        assert asyncio.run(service._payment_diagnostics([], utc_now())) == {}
        service.payment_orders.list_active_pending_user_ids.assert_not_awaited()


class TestListSubscriptionsWiring:
    def test_returns_items_and_total_for_representatives(self):
        service = make_service()
        user_id = uuid.uuid4()
        sub = make_subscription(user_id=user_id)
        reps = [
            AdminSubscriptionRepresentative(
                subscription=sub, total_subscriptions=2, active_count=1
            )
        ]
        service.subscriptions.list_admin = AsyncMock(return_value=(reps, 7))
        service.payment_orders.list_active_pending_user_ids = AsyncMock(
            return_value={user_id}
        )
        service.payment_orders.list_entitlement_incidents = AsyncMock(return_value=[])

        items, total = asyncio.run(service.list_subscriptions(skip=0, limit=10))

        assert total == 7
        assert len(items) == 1
        assert items[0].id == sub.id
        assert items[0].total_subscriptions == 2
        assert items[0].has_multiple_active is False
        assert items[0].has_unresolved_payment is True
        service.subscriptions.list_admin.assert_awaited_once()

    def test_empty_representatives_skip_payment_queries(self):
        service = make_service()
        service.subscriptions.list_admin = AsyncMock(return_value=([], 0))
        service.payment_orders.list_active_pending_user_ids = AsyncMock()

        items, total = asyncio.run(service.list_subscriptions(skip=0, limit=10))

        assert (items, total) == ([], 0)
        service.payment_orders.list_active_pending_user_ids.assert_not_awaited()


class TestGetDetailWiring:
    def _stub_diagnostics(self, service):
        service.payment_orders.list_active_pending_user_ids = AsyncMock(
            return_value=set()
        )
        service.payment_orders.list_entitlement_incidents = AsyncMock(return_value=[])

    def test_uses_representative_with_full_history(self):
        service = make_service()
        user_id = uuid.uuid4()
        target = make_subscription(user_id=user_id)
        representative = make_subscription(user_id=user_id)
        order = make_order(user_id=user_id, subscription_id=target.id)
        log = SimpleNamespace(
            id=uuid.uuid4(),
            admin_id=uuid.uuid4(),
            admin=None,
            user_id=user_id,
            subscription_id=target.id,
            action=SubscriptionAuditAction.PROVISION,
            old_plan_id=None,
            new_plan_id=uuid.uuid4(),
            reason="Khởi tạo",
            created_at=utc_now(),
        )
        service.subscriptions.get_by_id_including_deleted = AsyncMock(
            return_value=target
        )
        service.subscriptions.get_representative_for_user = AsyncMock(
            return_value=representative
        )
        service.subscriptions.count_by_user_ids = AsyncMock(
            return_value={user_id: (2, 1)}
        )
        service.subscriptions.get_by_user_id = AsyncMock(
            return_value=[representative, target]
        )
        service.payment_orders.list_by_subscription_ids = AsyncMock(
            return_value=[order]
        )
        service.audit.list_by_user = AsyncMock(return_value=[log])
        service._user_email = AsyncMock(return_value="detail@example.com")
        self._stub_diagnostics(service)

        detail = asyncio.run(service.get_detail(target.id))

        assert detail.subscription.id == representative.id
        assert detail.subscription.user_email == "detail@example.com"
        assert detail.subscription.total_subscriptions == 2
        history_ids = {item.id for item in detail.history}
        assert {representative.id, target.id} <= history_ids
        target_item = next(item for item in detail.history if item.id == target.id)
        assert [p.internal_order_id for p in target_item.payments] == [
            order.internal_order_id
        ]
        assert detail.audit_logs[0].action == SubscriptionAuditAction.PROVISION

    def test_falls_back_to_target_when_no_representative(self):
        service = make_service()
        user_id = uuid.uuid4()
        target = make_subscription(user_id=user_id)
        service.subscriptions.get_by_id_including_deleted = AsyncMock(
            return_value=target
        )
        service.subscriptions.get_representative_for_user = AsyncMock(return_value=None)
        service.subscriptions.count_by_user_ids = AsyncMock(
            return_value={user_id: (1, 0)}
        )
        service.subscriptions.get_by_user_id = AsyncMock(return_value=[target])
        service.payment_orders.list_by_subscription_ids = AsyncMock(return_value=[])
        service.audit.list_by_user = AsyncMock(return_value=[])
        service._user_email = AsyncMock(return_value=None)
        self._stub_diagnostics(service)

        detail = asyncio.run(service.get_detail(target.id))

        assert detail.subscription.id == target.id
        assert detail.history[0].id == target.id

    def test_unknown_subscription_raises(self):
        service = make_service()
        service.subscriptions.get_by_id_including_deleted = AsyncMock(return_value=None)

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.get_detail(uuid.uuid4()))
