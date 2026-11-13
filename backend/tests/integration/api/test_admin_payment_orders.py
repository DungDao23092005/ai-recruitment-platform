"""Integration tests for the admin payment-order read model."""

import uuid

from sqlalchemy import select

from app.core.security import get_password_hash
from app.database.session import async_session_factory
from app.domain.enums import (
    PaymentOrderStatus,
    PaymentProvider,
    PlanAudience,
    SubscriptionScope,
    UserRole,
)
from app.models import PaymentOrder, RecruitmentPlan, User
from tests.integration.api.conftest import API_V1, run


async def _create_user(role: UserRole, prefix: str) -> User:
    async with async_session_factory() as session:
        user = User(
            email=f"{prefix}@example.com",
            password_hash=get_password_hash("password123"),
            role=role,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _create_candidate_plan() -> RecruitmentPlan:
    async with async_session_factory() as session:
        plan = RecruitmentPlan(
            name=f"Payment Plan {uuid.uuid4().hex[:8]}",
            description="Payment test plan",
            price=199000,
            currency="VND",
            duration_days=30,
            max_job_posts=0,
            max_candidate_searches=0,
            max_ai_features=10,
            plan_audience=PlanAudience.CANDIDATE,
            is_free=False,
            is_active=True,
            display_order=1,
        )
        session.add(plan)
        await session.commit()
        await session.refresh(plan)
        return plan


async def _insert_order(
    user_id: uuid.UUID,
    plan_id: uuid.UUID,
    *,
    status: PaymentOrderStatus = PaymentOrderStatus.PENDING,
    provider: PaymentProvider = PaymentProvider.VNPAY,
    internal_order_id: str | None = None,
    paid_at=None,
) -> PaymentOrder:
    async with async_session_factory() as session:
        order = PaymentOrder(
            user_id=user_id,
            plan_id=plan_id,
            scope=SubscriptionScope.CANDIDATE_PERSONAL,
            amount=199000,
            currency="VND",
            provider=provider,
            internal_order_id=internal_order_id or f"ORD-{uuid.uuid4().hex[:12]}",
            status=status,
            paid_at=paid_at,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order


def _list(admin_client, run_async, **params) -> dict:
    resp = run_async(
        admin_client.get(f"{API_V1}/admin/payment-orders", params=params)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestAdminPaymentOrders:
    def test_list_returns_read_model_without_secrets(
        self, admin_client, run_async
    ):
        user = run(_create_user(UserRole.CANDIDATE, f"pay-{uuid.uuid4().hex[:8]}"))
        plan = run(_create_candidate_plan())
        order = run(_insert_order(user.id, plan.id))

        body = _list(admin_client, run_async, limit=10)
        item = next(row for row in body["items"] if row["id"] == str(order.id))

        assert item["user_email"] == user.email
        assert item["plan_name"] == plan.name
        assert item["plan_audience"] == "candidate"
        assert item["scope"] == "candidate_personal"
        assert item["status"] == "pending"
        assert item["provider"] == "vnpay"
        assert item["company_id"] is None
        forbidden = {
            "provider_order_id",
            "provider_request_id",
            "vnp_secure_hash",
            "vnp_txn_ref",
            "raw_payload",
        }
        assert forbidden.isdisjoint(item.keys())

    def test_filters_by_status_provider_and_scope(
        self, admin_client, run_async
    ):
        user = run(_create_user(UserRole.CANDIDATE, f"pay-f-{uuid.uuid4().hex[:8]}"))
        plan = run(_create_candidate_plan())
        paid = run(
            _insert_order(
                user.id,
                plan.id,
                status=PaymentOrderStatus.PAID,
                provider=PaymentProvider.VNPAY,
            )
        )
        run(
            _insert_order(
                user.id,
                plan.id,
                status=PaymentOrderStatus.PENDING,
                provider=PaymentProvider.MOMO,
            )
        )

        paid_body = _list(
            admin_client, run_async, status="paid", provider="vnpay", scope="candidate_personal"
        )
        assert [row["id"] for row in paid_body["items"]] == [str(paid.id)]

        empty = _list(admin_client, run_async, scope="company_recruiting")
        assert empty["items"] == []
        assert empty["total"] == 0

    def test_search_matches_order_id_and_user_email(
        self, admin_client, run_async
    ):
        prefix = f"pay-s-{uuid.uuid4().hex[:8]}"
        user = run(_create_user(UserRole.CANDIDATE, prefix))
        plan = run(_create_candidate_plan())
        order = run(
            _insert_order(
                user.id,
                plan.id,
                internal_order_id=f"SEARCH-{uuid.uuid4().hex[:10]}",
            )
        )

        by_order = _list(admin_client, run_async, search=order.internal_order_id)
        assert [row["id"] for row in by_order["items"]] == [str(order.id)]

        by_email = _list(admin_client, run_async, search=prefix)
        assert [row["id"] for row in by_email["items"]] == [str(order.id)]

    def test_pagination_and_limit_validation(self, admin_client, run_async):
        user = run(_create_user(UserRole.CANDIDATE, f"pay-p-{uuid.uuid4().hex[:8]}"))
        plan = run(_create_candidate_plan())
        run(_insert_order(user.id, plan.id))
        run(_insert_order(user.id, plan.id))

        page = _list(admin_client, run_async, skip=0, limit=1)
        assert len(page["items"]) == 1
        assert page["total"] >= 2
        assert page["skip"] == 0
        assert page["limit"] == 1

        invalid = run_async(
            admin_client.get(
                f"{API_V1}/admin/payment-orders", params={"limit": 101}
            )
        )
        assert invalid.status_code == 422

    def test_non_admin_is_forbidden(self, candidate_client, recruiter_client, run_async):
        for client in (candidate_client, recruiter_client):
            resp = run_async(client.get(f"{API_V1}/admin/payment-orders"))
            assert resp.status_code == 403

    def test_anonymous_is_unauthorized(self, client, run_async):
        resp = run_async(client.get(f"{API_V1}/admin/payment-orders"))
        assert resp.status_code == 401

    def test_empty_list_shape(self, admin_client, run_async):
        async def _clear() -> None:
            async with async_session_factory() as session:
                for order in (await session.scalars(select(PaymentOrder))).all():
                    await session.delete(order)
                await session.commit()

        run(_clear())
        body = _list(admin_client, run_async)
        assert body == {"items": [], "total": 0, "skip": 0, "limit": 10}
