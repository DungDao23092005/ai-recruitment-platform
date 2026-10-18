"""Integration tests for admin user-subscription management.

Covers the admin list/detail/audit surface plus change-plan and revoke,
including the fail-closed pending-VNPAY guard and the append-only audit trail.
"""

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.security import decode_access_token, get_password_hash
from app.database.session import async_session_factory
from app.domain.enums import (
    PaymentOrderStatus,
    PaymentProvider,
    SubscriptionAuditAction,
    SubscriptionStatus,
    UserRole,
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


# --------------------------------------------------------------------------
# Helpers for the one-row-per-user ranking surface
# --------------------------------------------------------------------------


async def _create_recruiter_user(email_prefix: str, suffix: str = "") -> str:
    async with async_session_factory() as session:
        user = User(
            email=f"{email_prefix}{suffix}@example.com",
            password_hash=get_password_hash("password123"),
            role=UserRole.RECRUITER,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return str(user.id)


async def _insert_subscription(
    user_id: str,
    plan_id: str,
    status: SubscriptionStatus,
    *,
    created_at=None,
    started_at=None,
    expires_at=None,
    job_posts_used: int = 0,
) -> str:
    async with async_session_factory() as session:
        sub = Subscription(
            user_id=uuid.UUID(user_id),
            plan_id=uuid.UUID(plan_id),
            status=status,
            created_at=created_at or utc_now(),
            started_at=started_at,
            expires_at=expires_at,
            job_posts_used=job_posts_used,
        )
        session.add(sub)
        await session.commit()
        await session.refresh(sub)
        return str(sub.id)


async def _insert_order(
    user_id: str,
    plan_id: str,
    *,
    status: PaymentOrderStatus,
    subscription_id: str | None = None,
    expired_at=None,
    paid_at=None,
    amount: int = 299000,
    internal_order_id: str | None = None,
) -> str:
    ref = internal_order_id or f"VNPAY_{uuid.uuid4().hex[:16]}"
    async with async_session_factory() as session:
        order = PaymentOrder(
            user_id=uuid.UUID(user_id),
            plan_id=uuid.UUID(plan_id),
            subscription_id=uuid.UUID(subscription_id) if subscription_id else None,
            amount=amount,
            currency="VND",
            provider=PaymentProvider.VNPAY,
            internal_order_id=ref,
            status=status,
            expired_at=expired_at,
            paid_at=paid_at,
        )
        session.add(order)
        await session.commit()
    return ref


async def _active_subscription(
    user_id: str,
    plan_id: str,
    *,
    created_at=None,
    days: int = 30,
) -> str:
    now = utc_now()
    return await _insert_subscription(
        user_id,
        plan_id,
        SubscriptionStatus.ACTIVE,
        created_at=created_at or now,
        started_at=created_at or now,
        expires_at=now + timedelta(days=days),
    )


def _list(admin_client, run_async, search: str, **params) -> dict:
    query = {"limit": 100, "search": search}
    query.update(params)
    resp = run_async(admin_client.get(f"{API_V1}/admin/subscriptions", params=query))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _detail(admin_client, run_async, subscription_id: str) -> dict:
    resp = run_async(
        admin_client.get(f"{API_V1}/admin/subscriptions/{subscription_id}")
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestOneRowPerUserRanking:
    def test_single_active_user_is_one_row(self, admin_client, run_async):
        prefix = f"onerow-a-{uuid.uuid4().hex[:8]}"
        plan = _create_plan(admin_client, run_async)
        user_id = run(_create_recruiter_user(prefix))
        sub_id = run(_active_subscription(user_id, plan["id"]))

        body = _list(admin_client, run_async, prefix)

        assert body["total"] == 1
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["id"] == sub_id
        assert item["status"] == "active"
        assert item["effective_status"] == "active"
        assert item["total_subscriptions"] == 1
        assert item["has_multiple_active"] is False
        assert item["has_unresolved_payment"] is False
        assert item["is_entitlement_incident"] is False
        assert item["incident_subscription_id"] is None
        assert item["incident_internal_order_id"] is None
        assert item["incident_amount"] is None

    def test_active_plus_history_uses_active_representative(
        self, admin_client, run_async
    ):
        prefix = f"onerow-b-{uuid.uuid4().hex[:8]}"
        plan = _create_plan(admin_client, run_async)
        user_id = run(_create_recruiter_user(prefix))
        now = utc_now()
        run(
            _insert_subscription(
                user_id,
                plan["id"],
                SubscriptionStatus.CANCELLED,
                created_at=now - timedelta(days=40),
                started_at=now - timedelta(days=60),
                expires_at=now - timedelta(days=40),
            )
        )
        run(
            _insert_subscription(
                user_id,
                plan["id"],
                SubscriptionStatus.PENDING,
                created_at=now - timedelta(days=45),
            )
        )
        active_id = run(
            _active_subscription(user_id, plan["id"], created_at=now - timedelta(days=1))
        )

        body = _list(admin_client, run_async, prefix)

        assert body["total"] == 1
        item = body["items"][0]
        assert item["id"] == active_id
        assert item["status"] == "active"
        assert item["total_subscriptions"] == 3
        assert item["has_multiple_active"] is False

    def test_multiple_abandoned_pending_is_one_row(self, admin_client, run_async):
        prefix = f"onerow-c-{uuid.uuid4().hex[:8]}"
        plan = _create_plan(admin_client, run_async)
        user_id = run(_create_recruiter_user(prefix))
        now = utc_now()
        newest = run(
            _insert_subscription(
                user_id,
                plan["id"],
                SubscriptionStatus.PENDING,
                created_at=now - timedelta(days=1),
            )
        )
        run(
            _insert_subscription(
                user_id,
                plan["id"],
                SubscriptionStatus.PENDING,
                created_at=now - timedelta(days=2),
            )
        )
        run(
            _insert_subscription(
                user_id,
                plan["id"],
                SubscriptionStatus.PENDING,
                created_at=now - timedelta(days=3),
            )
        )

        body = _list(admin_client, run_async, prefix)

        assert body["total"] == 1
        item = body["items"][0]
        assert item["id"] == newest
        assert item["status"] == "pending"
        assert item["total_subscriptions"] == 3
        assert item["has_unresolved_payment"] is False
        assert item["is_entitlement_incident"] is False

    def test_live_vnpay_pending_flags_and_blocks_action(
        self, admin_client, run_async
    ):
        prefix = f"onerow-d-{uuid.uuid4().hex[:8]}"
        plan = _create_plan(admin_client, run_async)
        user_id = run(_create_recruiter_user(prefix))
        active_id = run(_active_subscription(user_id, plan["id"]))
        run(
            _insert_order(
                user_id,
                plan["id"],
                status=PaymentOrderStatus.PENDING,
                expired_at=utc_now() + timedelta(minutes=15),
            )
        )

        body = _list(admin_client, run_async, prefix)
        item = body["items"][0]
        assert item["id"] == active_id
        assert item["has_unresolved_payment"] is True
        assert item["is_entitlement_incident"] is False

        resp = run_async(
            admin_client.post(
                f"{API_V1}/admin/subscriptions/{active_id}/revoke",
                json={"reason": "Thu hồi khi còn thanh toán treo"},
            )
        )
        assert resp.status_code == 409, resp.text

    def test_expired_vnpay_pending_does_not_block(self, admin_client, run_async):
        prefix = f"onerow-e-{uuid.uuid4().hex[:8]}"
        plan_a = _create_plan(admin_client, run_async)
        plan_b = _create_plan(admin_client, run_async)
        user_id = run(_create_recruiter_user(prefix))
        active_id = run(_active_subscription(user_id, plan_a["id"]))
        run(
            _insert_order(
                user_id,
                plan_a["id"],
                status=PaymentOrderStatus.PENDING,
                expired_at=utc_now() - timedelta(minutes=5),
            )
        )

        body = _list(admin_client, run_async, prefix)
        item = body["items"][0]
        assert item["id"] == active_id
        assert item["has_unresolved_payment"] is False

        resp = run_async(
            admin_client.post(
                f"{API_V1}/admin/subscriptions/{active_id}/change-plan",
                json={
                    "target_plan_id": plan_b["id"],
                    "reason": "Đổi gói khi đơn VNPAY đã hết hạn",
                },
            )
        )
        assert resp.status_code == 200, resp.text

    def test_paid_order_with_pending_subscription_is_representative(
        self, admin_client, run_async
    ):
        prefix = f"onerow-f-{uuid.uuid4().hex[:8]}"
        plan = _create_plan(admin_client, run_async)
        user_id = run(_create_recruiter_user(prefix))
        now = utc_now()
        sub_id = run(
            _insert_subscription(
                user_id, plan["id"], SubscriptionStatus.PENDING, created_at=now
            )
        )
        ref = run(
            _insert_order(
                user_id,
                plan["id"],
                status=PaymentOrderStatus.PAID,
                subscription_id=sub_id,
                paid_at=now,
                amount=123456,
            )
        )

        body = _list(admin_client, run_async, prefix)

        assert body["total"] == 1
        item = body["items"][0]
        assert item["id"] == sub_id
        assert item["status"] == "pending"
        assert item["is_entitlement_incident"] is True
        assert item["has_unresolved_payment"] is True
        assert item["incident_subscription_id"] == sub_id
        assert item["incident_internal_order_id"] == ref
        assert item["incident_amount"] == 123456

    def test_active_with_new_paid_pending_incident(self, admin_client, run_async):
        prefix = f"onerow-g-{uuid.uuid4().hex[:8]}"
        plan_a = _create_plan(admin_client, run_async)
        plan_b = _create_plan(admin_client, run_async)
        user_id = run(_create_recruiter_user(prefix))
        now = utc_now()
        active_id = run(
            _active_subscription(user_id, plan_a["id"], created_at=now - timedelta(days=10))
        )
        pending_id = run(
            _insert_subscription(
                user_id, plan_b["id"], SubscriptionStatus.PENDING, created_at=now
            )
        )
        run(
            _insert_order(
                user_id,
                plan_b["id"],
                status=PaymentOrderStatus.PAID,
                subscription_id=pending_id,
                paid_at=now,
            )
        )

        body = _list(admin_client, run_async, prefix)
        item = body["items"][0]
        assert item["id"] == active_id
        assert item["is_entitlement_incident"] is True
        assert item["has_unresolved_payment"] is True
        assert item["incident_subscription_id"] == pending_id

        resp = run_async(
            admin_client.post(
                f"{API_V1}/admin/subscriptions/{active_id}/revoke",
                json={"reason": "Thu hồi khi có sự cố quyền lợi"},
            )
        )
        assert resp.status_code == 409, resp.text

    def test_multiple_incidents_single_row_and_preserved_in_detail(
        self, admin_client, run_async
    ):
        prefix = f"onerow-h-{uuid.uuid4().hex[:8]}"
        plan = _create_plan(admin_client, run_async)
        user_id = run(_create_recruiter_user(prefix))
        now = utc_now()
        s1 = run(
            _insert_subscription(
                user_id,
                plan["id"],
                SubscriptionStatus.PENDING,
                created_at=now - timedelta(minutes=10),
            )
        )
        s2 = run(
            _insert_subscription(
                user_id, plan["id"], SubscriptionStatus.PENDING, created_at=now
            )
        )
        o1 = run(
            _insert_order(
                user_id,
                plan["id"],
                status=PaymentOrderStatus.PAID,
                subscription_id=s1,
                paid_at=now - timedelta(minutes=10),
            )
        )
        o2 = run(
            _insert_order(
                user_id,
                plan["id"],
                status=PaymentOrderStatus.PAID,
                subscription_id=s2,
                paid_at=now,
            )
        )

        body = _list(admin_client, run_async, prefix)
        assert body["total"] == 1
        item = body["items"][0]
        assert item["is_entitlement_incident"] is True
        assert item["incident_subscription_id"] == s2
        assert item["incident_internal_order_id"] == o2

        detail = _detail(admin_client, run_async, item["id"])
        history = {h["id"]: h for h in detail["history"]}
        assert {s1, s2} <= set(history)
        refs = {p["internal_order_id"] for h in detail["history"] for p in h["payments"]}
        assert {o1, o2} <= refs

    def test_two_active_picks_newest_and_flags_multiple(self, admin_client, run_async):
        prefix = f"onerow-i-{uuid.uuid4().hex[:8]}"
        plan = _create_plan(admin_client, run_async)
        user_id = run(_create_recruiter_user(prefix))
        now = utc_now()
        older = run(
            _active_subscription(user_id, plan["id"], created_at=now - timedelta(days=5))
        )
        newer = run(_active_subscription(user_id, plan["id"], created_at=now))

        body = _list(admin_client, run_async, prefix)
        item = body["items"][0]
        assert item["id"] == newer
        assert item["has_multiple_active"] is True
        assert item["total_subscriptions"] == 2

        detail = _detail(admin_client, run_async, item["id"])
        active_ids = {
            h["id"] for h in detail["history"] if h["status"] == "active"
        }
        assert {older, newer} <= active_ids

    def test_only_cancelled_and_expired_picks_most_recent(
        self, admin_client, run_async
    ):
        prefix = f"onerow-j-{uuid.uuid4().hex[:8]}"
        plan = _create_plan(admin_client, run_async)
        user_id = run(_create_recruiter_user(prefix))
        base = utc_now()
        run(
            _insert_subscription(
                user_id,
                plan["id"],
                SubscriptionStatus.CANCELLED,
                created_at=base - timedelta(days=20),
                started_at=base - timedelta(days=30),
                expires_at=base - timedelta(days=10),
            )
        )
        expired_id = run(
            _insert_subscription(
                user_id,
                plan["id"],
                SubscriptionStatus.EXPIRED,
                created_at=base - timedelta(days=5),
                started_at=base - timedelta(days=40),
                expires_at=base - timedelta(days=1),
            )
        )

        body = _list(admin_client, run_async, prefix)
        item = body["items"][0]
        assert item["id"] == expired_id
        assert item["effective_status"] == "expired"

    def test_db_active_but_expired_shows_effective_expired(
        self, admin_client, run_async
    ):
        prefix = f"onerow-k-{uuid.uuid4().hex[:8]}"
        plan = _create_plan(admin_client, run_async)
        user_id = run(_create_recruiter_user(prefix))
        now = utc_now()
        sub_id = run(
            _insert_subscription(
                user_id,
                plan["id"],
                SubscriptionStatus.ACTIVE,
                created_at=now - timedelta(days=40),
                started_at=now - timedelta(days=40),
                expires_at=now - timedelta(days=1),
            )
        )

        body = _list(admin_client, run_async, prefix)
        item = body["items"][0]
        assert item["id"] == sub_id
        assert item["status"] == "active"
        assert item["effective_status"] == "expired"

        stored = run(_load_subscription(sub_id))
        assert stored.status == SubscriptionStatus.ACTIVE

    def test_status_filter_applies_to_representative_only(
        self, admin_client, run_async
    ):
        prefix = f"onerow-l-{uuid.uuid4().hex[:8]}"
        plan = _create_plan(admin_client, run_async)
        now = utc_now()
        user_a = run(_create_recruiter_user(prefix, "-a"))
        run(_active_subscription(user_a, plan["id"]))
        run(
            _insert_subscription(
                user_a,
                plan["id"],
                SubscriptionStatus.CANCELLED,
                created_at=now - timedelta(days=5),
                started_at=now - timedelta(days=10),
                expires_at=now - timedelta(days=5),
            )
        )
        user_b = run(_create_recruiter_user(prefix, "-b"))
        run(
            _insert_subscription(
                user_b,
                plan["id"],
                SubscriptionStatus.CANCELLED,
                created_at=now - timedelta(days=5),
                started_at=now - timedelta(days=10),
                expires_at=now - timedelta(days=5),
            )
        )

        cancelled = _list(admin_client, run_async, prefix, status_filter="cancelled")
        assert cancelled["total"] == 1
        assert cancelled["items"][0]["user_email"] == f"{prefix}-b@example.com"

        active = _list(admin_client, run_async, prefix, status_filter="active")
        assert active["total"] == 1
        assert active["items"][0]["user_email"] == f"{prefix}-a@example.com"

    def test_pagination_counts_distinct_users(self, admin_client, run_async):
        prefix = f"onerow-m-{uuid.uuid4().hex[:8]}"
        plan = _create_plan(admin_client, run_async)
        now = utc_now()
        user_ids = []
        for index in range(15):
            user_id = run(_create_recruiter_user(prefix, f"-{index:02d}"))
            user_ids.append(user_id)
            extra = 2 if index < 10 else 4
            run(
                _active_subscription(
                    user_id, plan["id"], created_at=now - timedelta(minutes=1)
                )
            )
            for offset in range(extra - 1):
                run(
                    _insert_subscription(
                        user_id,
                        plan["id"],
                        SubscriptionStatus.CANCELLED,
                        created_at=now - timedelta(days=offset + 1),
                        started_at=now - timedelta(days=offset + 11),
                        expires_at=now - timedelta(days=offset + 1),
                    )
                )

        page1 = _list(admin_client, run_async, prefix, limit=10, skip=0)
        assert page1["total"] == 15
        assert len(page1["items"]) == 10
        ids1 = [item["user_id"] for item in page1["items"]]
        assert len(set(ids1)) == 10

        page2 = _list(admin_client, run_async, prefix, limit=10, skip=10)
        assert len(page2["items"]) == 5
        ids2 = [item["user_id"] for item in page2["items"]]
        assert set(ids1).isdisjoint(ids2)
        assert set(ids1) | set(ids2) == set(user_ids)

    def test_equal_created_at_tie_breaker_is_stable(self, admin_client, run_async):
        prefix = f"onerow-n-{uuid.uuid4().hex[:8]}"
        plan = _create_plan(admin_client, run_async)
        user_id = run(_create_recruiter_user(prefix))
        stamp = utc_now()
        ids = [
            run(_active_subscription(user_id, plan["id"], created_at=stamp))
            for _ in range(2)
        ]

        first = _list(admin_client, run_async, prefix)
        second = _list(admin_client, run_async, prefix)
        assert first["items"][0]["id"] == second["items"][0]["id"]
        assert first["items"][0]["id"] in ids
        assert first["items"][0]["has_multiple_active"] is True

    def test_detail_returns_plan_names_history_payments_and_audit(
        self, admin_client, run_async
    ):
        prefix = f"onerow-o-{uuid.uuid4().hex[:8]}"
        plan = _create_plan(admin_client, run_async)
        user_id = run(_create_recruiter_user(prefix))
        prov = _provision(admin_client, run_async, user_id, plan["id"])
        assert prov.status_code == 201, prov.text
        active_id = prov.json()["id"]

        now = utc_now()
        old_id = run(
            _insert_subscription(
                user_id,
                plan["id"],
                SubscriptionStatus.CANCELLED,
                created_at=now - timedelta(days=60),
                started_at=now - timedelta(days=90),
                expires_at=now - timedelta(days=60),
            )
        )
        ref = run(
            _insert_order(
                user_id,
                plan["id"],
                status=PaymentOrderStatus.PAID,
                subscription_id=old_id,
                paid_at=now - timedelta(days=90),
                amount=199000,
            )
        )

        detail = _detail(admin_client, run_async, active_id)
        assert detail["subscription"]["id"] == active_id
        history = {h["id"]: h for h in detail["history"]}
        assert {active_id, old_id} <= set(history)
        assert history[active_id]["plan_name"] == plan["name"]
        assert history[old_id]["plan_name"] == plan["name"]
        assert any(
            p["internal_order_id"] == ref and p["amount"] == 199000
            for p in history[old_id]["payments"]
        )
        actions = {log["action"] for log in detail["audit_logs"]}
        assert SubscriptionAuditAction.PROVISION.value in actions

    def test_actions_target_specific_subscription_id(
        self, admin_client, candidate_client, run_async
    ):
        plan = _create_plan(admin_client, run_async)
        user_id = _user_id_from_client(candidate_client)
        prov = _provision(admin_client, run_async, user_id, plan["id"])
        assert prov.status_code == 201, prov.text
        sub_id = prov.json()["id"]

        async def _email_for(uid: str) -> str:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(User).where(User.id == uuid.UUID(uid))
                )
                return result.scalar_one().email

        email = run(_email_for(user_id))
        body = _list(admin_client, run_async, email)
        assert body["total"] == 1
        assert body["items"][0]["id"] == sub_id

        revoked = run_async(
            admin_client.post(
                f"{API_V1}/admin/subscriptions/{sub_id}/revoke",
                json={"reason": "Thu hồi đúng theo id đại diện"},
            )
        )
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["status"] == "cancelled"

        detail = _detail(admin_client, run_async, sub_id)
        assert SubscriptionAuditAction.REVOKE.value in {
            log["action"] for log in detail["audit_logs"]
        }

        notifications = run_async(
            candidate_client.get(f"{API_V1}/notifications")
        )
        assert notifications.status_code == 200, notifications.text
        assert any(
            n["notification_type"] == "subscription_revoked"
            for n in notifications.json()
        )
