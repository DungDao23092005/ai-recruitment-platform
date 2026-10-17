"""Integration tests for admin user-subscription management.

Covers the admin list/detail/audit surface plus change-plan and revoke,
including the fail-closed pending-VNPAY guard and the append-only audit trail.
"""

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.security import decode_access_token
from app.database.session import async_session_factory
from app.domain.enums import (
    PaymentOrderStatus,
    PaymentProvider,
    SubscriptionAuditAction,
    SubscriptionStatus,
)
from app.domain.models.base import utc_now
from app.models import (
    Notification,
    PaymentOrder,
    RecruitmentPlan,
    Subscription,
    SubscriptionAuditLog,
    User,
)
from tests.integration.api.conftest import API_V1, run
from tests.integration.api.test_plans import _create_plan


def _user_id_from_client(auth_client) -> str:
    header = auth_client.headers.get("Authorization", "")
    token = header.replace("Bearer ", "")
    return decode_access_token(token)["sub"]


async def _insert_pending_vnpay_order(user_id: str, plan_id: str) -> None:
    async with async_session_factory() as session:
        order = PaymentOrder(
            user_id=uuid.UUID(user_id),
            plan_id=uuid.UUID(plan_id),
            amount=299000,
            currency="VND",
            provider=PaymentProvider.VNPAY,
            internal_order_id=f"VNPAY_{uuid.uuid4().hex[:16]}",
            status=PaymentOrderStatus.PENDING,
            expired_at=utc_now() + timedelta(minutes=15),
        )
        session.add(order)
        await session.commit()


async def _insert_paid_order_with_pending_subscription(
    user_id: str, plan_id: str
) -> None:
    async with async_session_factory() as session:
        sub = Subscription(
            user_id=uuid.UUID(user_id),
            plan_id=uuid.UUID(plan_id),
            status=SubscriptionStatus.PENDING,
        )
        session.add(sub)
        await session.flush()
        order = PaymentOrder(
            user_id=uuid.UUID(user_id),
            plan_id=uuid.UUID(plan_id),
            subscription_id=sub.id,
            amount=299000,
            currency="VND",
            provider=PaymentProvider.VNPAY,
            internal_order_id=f"VNPAY_{uuid.uuid4().hex[:16]}",
            status=PaymentOrderStatus.PAID,
            paid_at=utc_now(),
        )
        session.add(order)
        await session.commit()


async def _load_subscription(subscription_id: str) -> Subscription:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.id == uuid.UUID(subscription_id))
        )
        return result.scalar_one()


def _provision(admin_client, run_async, user_id: str, plan_id: str):
    return run_async(
        admin_client.post(
            f"{API_V1}/admin/subscriptions",
            json={"user_id": user_id, "plan_id": plan_id},
        )
    )


class TestAdminSubscriptionList:
    def test_list_is_paginated_and_searches_by_email(
        self, admin_client, candidate_client, run_async
    ):
        plan = _create_plan(admin_client, run_async)
        user_id = _user_id_from_client(candidate_client)
        prov = _provision(admin_client, run_async, user_id, plan["id"])
        assert prov.status_code == 201, prov.text

        resp = run_async(admin_client.get(f"{API_V1}/admin/subscriptions?limit=5"))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body) >= {"items", "total", "skip", "limit"}
        assert body["total"] >= 1

        # Resolve the real email from the DB via the token subject.
        async def _email_for(user_id: str) -> str:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(User).where(User.id == uuid.UUID(user_id))
                )
                return result.scalar_one().email

        resolved_email = run(_email_for(user_id))
        search = run_async(
            admin_client.get(
                f"{API_V1}/admin/subscriptions", params={"search": resolved_email}
            )
        )
        assert search.status_code == 200, search.text
        items = search.json()["items"]
        assert len(items) == 1
        assert items[0]["user_email"] == resolved_email
        assert items[0]["plan_name"] == plan["name"]

    def test_detail_returns_history_and_audit(
        self, admin_client, candidate_client, run_async
    ):
        plan = _create_plan(admin_client, run_async)
        user_id = _user_id_from_client(candidate_client)
        prov = _provision(admin_client, run_async, user_id, plan["id"])
        sub_id = prov.json()["id"]

        resp = run_async(admin_client.get(f"{API_V1}/admin/subscriptions/{sub_id}"))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["subscription"]["id"] == sub_id
        assert data["subscription"]["plan_name"] == plan["name"]
        assert len(data["history"]) == 1
        assert len(data["audit_logs"]) == 1
        log = data["audit_logs"][0]
        assert log["action"] == "provision"
        assert log["new_plan_id"] == plan["id"]
        assert log["admin_email"]


class TestAdminChangePlan:
    def test_change_plan_mutates_in_place_and_preserves_usage(
        self, admin_client, candidate_client, run_async
    ):
        plan_a = _create_plan(admin_client, run_async)
        plan_b = _create_plan(
            admin_client,
            run_async,
            {
                "name": "Gói mới",
                "description": "Nâng cấp",
                "price": 999000,
                "currency": "VND",
                "duration_days": 60,
                "max_job_posts": 2,
                "max_candidate_searches": 2,
                "max_ai_features": 2,
                "display_order": 1,
            },
        )
        user_id = _user_id_from_client(candidate_client)
        prov = _provision(admin_client, run_async, user_id, plan_a["id"])
        assert prov.status_code == 201, prov.text
        sub_id = prov.json()["id"]

        # Simulate prior usage that exceeds the new plan's quota.
        async def _set_usage() -> None:
            async with async_session_factory() as session:
                sub = (
                    await session.execute(
                        select(Subscription).where(
                            Subscription.id == uuid.UUID(sub_id)
                        )
                    )
                ).scalar_one()
                sub.job_posts_used = 5
                sub.candidate_searches_used = 1
                await session.commit()

        run(_set_usage())

        resp = run_async(
            admin_client.post(
                f"{API_V1}/admin/subscriptions/{sub_id}/change-plan",
                json={"target_plan_id": plan_b["id"], "reason": "Khách yêu cầu nâng cấp"},
            )
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["plan_id"] == plan_b["id"]
        assert body["status"] == "active"
        # Counters are preserved (never reset, never negative).
        assert body["job_posts_used"] == 5
        assert body["max_job_posts"] == 2

        # Audit trail records the old -> new plan transition.
        detail = run_async(admin_client.get(f"{API_V1}/admin/subscriptions/{sub_id}"))
        logs = detail.json()["audit_logs"]
        change = [log for log in logs if log["action"] == "change_plan"]
        assert len(change) == 1
        assert change[0]["old_plan_id"] == plan_a["id"]
        assert change[0]["new_plan_id"] == plan_b["id"]

        # The buyer is notified.
        listing = run_async(candidate_client.get(f"{API_V1}/notifications"))
        assert any(
            n["notification_type"] == "subscription_plan_changed"
            for n in listing.json()
        )

    def test_change_to_same_plan_conflicts(
        self, admin_client, candidate_client, run_async
    ):
        plan = _create_plan(admin_client, run_async)
        user_id = _user_id_from_client(candidate_client)
        sub_id = _provision(admin_client, run_async, user_id, plan["id"]).json()["id"]

        resp = run_async(
            admin_client.post(
                f"{API_V1}/admin/subscriptions/{sub_id}/change-plan",
                json={"target_plan_id": plan["id"], "reason": "không đổi gì cả"},
            )
        )
        assert resp.status_code == 409, resp.text

    def test_change_to_inactive_plan_is_404(
        self, admin_client, candidate_client, run_async
    ):
        plan_a = _create_plan(admin_client, run_async)
        plan_b = _create_plan(admin_client, run_async)
        run_async(
            admin_client.patch(
                f"{API_V1}/admin/plans/{plan_b['id']}/status",
                json={"is_active": False},
            )
        )
        user_id = _user_id_from_client(candidate_client)
        sub_id = _provision(admin_client, run_async, user_id, plan_a["id"]).json()["id"]

        resp = run_async(
            admin_client.post(
                f"{API_V1}/admin/subscriptions/{sub_id}/change-plan",
                json={"target_plan_id": plan_b["id"], "reason": "đổi sang gói khóa"},
            )
        )
        assert resp.status_code == 404, resp.text

    def test_change_plan_requires_meaningful_reason(
        self, admin_client, candidate_client, run_async
    ):
        plan = _create_plan(admin_client, run_async)
        user_id = _user_id_from_client(candidate_client)
        sub_id = _provision(admin_client, run_async, user_id, plan["id"]).json()["id"]

        resp = run_async(
            admin_client.post(
                f"{API_V1}/admin/subscriptions/{sub_id}/change-plan",
                json={"target_plan_id": plan["id"], "reason": "abc"},
            )
        )
        assert resp.status_code == 422, resp.text

    def test_change_plan_blocked_by_pending_vnpay_order(
        self, admin_client, candidate_client, run_async
    ):
        plan_a = _create_plan(admin_client, run_async)
        plan_b = _create_plan(admin_client, run_async)
        user_id = _user_id_from_client(candidate_client)
        sub_id = _provision(admin_client, run_async, user_id, plan_a["id"]).json()["id"]

        run(_insert_pending_vnpay_order(user_id, plan_a["id"]))

        resp = run_async(
            admin_client.post(
                f"{API_V1}/admin/subscriptions/{sub_id}/change-plan",
                json={"target_plan_id": plan_b["id"], "reason": "đổi gói dù đang chờ"},
            )
        )
        assert resp.status_code == 409, resp.text
        assert "VNPAY" in resp.json()["detail"]

        # Subscription untouched.
        sub = run(_load_subscription(sub_id))
        assert str(sub.plan_id) == plan_a["id"]


class TestAdminRevoke:
    def test_revoke_sets_cancelled_and_audits(
        self, admin_client, candidate_client, run_async
    ):
        plan = _create_plan(admin_client, run_async)
        user_id = _user_id_from_client(candidate_client)
        sub_id = _provision(admin_client, run_async, user_id, plan["id"]).json()["id"]

        resp = run_async(
            admin_client.post(
                f"{API_V1}/admin/subscriptions/{sub_id}/revoke",
                json={"reason": "Vi phạm điều khoản sử dụng"},
            )
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "cancelled"

        detail = run_async(admin_client.get(f"{API_V1}/admin/subscriptions/{sub_id}"))
        logs = [log for log in detail.json()["audit_logs"] if log["action"] == "revoke"]
        assert len(logs) == 1
        assert logs[0]["old_plan_id"] == plan["id"]
        assert logs[0]["new_plan_id"] is None

        listing = run_async(candidate_client.get(f"{API_V1}/notifications"))
        assert any(
            n["notification_type"] == "subscription_revoked" for n in listing.json()
        )

    def test_revoke_twice_conflicts(self, admin_client, candidate_client, run_async):
        plan = _create_plan(admin_client, run_async)
        user_id = _user_id_from_client(candidate_client)
        sub_id = _provision(admin_client, run_async, user_id, plan["id"]).json()["id"]

        first = run_async(
            admin_client.post(
                f"{API_V1}/admin/subscriptions/{sub_id}/revoke",
                json={"reason": "Thu hồi lần một"},
            )
        )
        assert first.status_code == 200
        second = run_async(
            admin_client.post(
                f"{API_V1}/admin/subscriptions/{sub_id}/revoke",
                json={"reason": "Thu hồi lần hai"},
            )
        )
        assert second.status_code == 409, second.text

    def test_revoke_blocked_by_unresolved_entitlement(
        self, admin_client, candidate_client, run_async
    ):
        plan = _create_plan(admin_client, run_async)
        user_id = _user_id_from_client(candidate_client)
        sub_id = _provision(admin_client, run_async, user_id, plan["id"]).json()["id"]

        run(_insert_paid_order_with_pending_subscription(user_id, plan["id"]))

        resp = run_async(
            admin_client.post(
                f"{API_V1}/admin/subscriptions/{sub_id}/revoke",
                json={"reason": "Thu hồi khi có sự cố thanh toán"},
            )
        )
        assert resp.status_code == 409, resp.text


class TestProvisionGuard:
    def test_provision_blocked_by_pending_vnpay_order(
        self, admin_client, candidate_client, run_async
    ):
        plan = _create_plan(admin_client, run_async)
        user_id = _user_id_from_client(candidate_client)
        run(_insert_pending_vnpay_order(user_id, plan["id"]))

        resp = _provision(admin_client, run_async, user_id, plan["id"])
        assert resp.status_code == 409, resp.text

    def test_provision_creates_audit_and_notification(
        self, admin_client, candidate_client, run_async
    ):
        plan = _create_plan(admin_client, run_async)
        user_id = _user_id_from_client(candidate_client)
        resp = _provision(admin_client, run_async, user_id, plan["id"])
        assert resp.status_code == 201, resp.text
        sub_id = resp.json()["id"]

        detail = run_async(admin_client.get(f"{API_V1}/admin/subscriptions/{sub_id}"))
        assert detail.json()["audit_logs"][0]["action"] == "provision"

        listing = run_async(candidate_client.get(f"{API_V1}/notifications"))
        assert any(
            n["notification_type"] == "subscription_activated"
            for n in listing.json()
        )


class TestAuditTrailIsImmutable:
    def test_plan_with_audit_reference_cannot_be_deleted(
        self, admin_client, candidate_client, run_async
    ):
        plan = _create_plan(admin_client, run_async)
        user_id = _user_id_from_client(candidate_client)
        sub_id = _provision(admin_client, run_async, user_id, plan["id"]).json()["id"]

        # A standalone plan that is referenced only by an audit log.
        standalone_plan = _create_plan(admin_client, run_async)

        async def _insert_audit() -> None:
            async with async_session_factory() as session:
                log = SubscriptionAuditLog(
                    admin_id=uuid.UUID(user_id),
                    user_id=uuid.UUID(user_id),
                    subscription_id=uuid.UUID(sub_id),
                    action=SubscriptionAuditAction.REVOKE,
                    old_plan_id=uuid.UUID(standalone_plan["id"]),
                    new_plan_id=None,
                    reason="Tham chiếu kiểm toán",
                )
                session.add(log)
                await session.commit()

        run(_insert_audit())

        resp = run_async(
            admin_client.delete(f"{API_V1}/admin/plans/{standalone_plan['id']}")
        )
        assert resp.status_code == 409, resp.text
        assert "lịch sử thay đổi gói" in resp.json()["detail"]

    def test_audit_logs_are_appended_and_listed(
        self, admin_client, candidate_client, run_async
    ):
        plan = _create_plan(admin_client, run_async)
        user_id = _user_id_from_client(candidate_client)
        sub_id = _provision(admin_client, run_async, user_id, plan["id"]).json()["id"]

        run_async(
            admin_client.post(
                f"{API_V1}/admin/subscriptions/{sub_id}/revoke",
                json={"reason": "Thu hồi để kiểm thử audit"},
            )
        )

        detail = run_async(admin_client.get(f"{API_V1}/admin/subscriptions/{sub_id}"))
        actions = [log["action"] for log in detail.json()["audit_logs"]]
        assert actions.count("provision") == 1
        assert actions.count("revoke") == 1
        # Append-only: nothing disappears.
        assert len(actions) == 2

    def test_notifications_persisted_for_audit_actions(
        self, admin_client, candidate_client, run_async
    ):
        plan = _create_plan(admin_client, run_async)
        user_id = _user_id_from_client(candidate_client)
        sub_id = _provision(admin_client, run_async, user_id, plan["id"]).json()["id"]
        run_async(
            admin_client.post(
                f"{API_V1}/admin/subscriptions/{sub_id}/revoke",
                json={"reason": "Thu hồi để kiểm thử thông báo"},
            )
        )

        async def _count() -> int:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(Notification).where(
                        Notification.user_id == uuid.UUID(user_id)
                    )
                )
                return len(result.scalars().all())

        assert run(_count()) >= 2
