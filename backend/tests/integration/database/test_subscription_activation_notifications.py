"""Real SQL Server integration tests for subscription activation notifications.

Proves that the one-time ``subscription_activated`` notification is created
exactly once for each genuine PENDING -> ACTIVE transition, in the same
transaction as the activation, across the supported activation pathways:

- VNPAY IPN success
- VNPAY QueryDr reconciliation (shared finalize path)
- Direct / admin provisioning (SubscriptionService.activate_subscription)

and that it is NOT created when the payment is PAID but the subscription stays
PENDING (activation refused), nor when Redis publishing fails.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.core.config import settings

# Configure VNPAY test settings BEFORE importing the provider/service.
settings.VNPAY_TMN_CODE = "TESTTMN"
settings.VNPAY_HASH_SECRET = "testhashsecret123"

from app.core.exceptions import InvalidTransitionException  # noqa: E402
from app.database.session import async_session_factory  # noqa: E402
from app.domain.enums import (  # noqa: E402
    CompanySize,
    MembershipRole,
    MembershipStatus,
    PaymentOrderStatus,
    PaymentProvider,
    PlanAudience,
    SubscriptionScope,
    SubscriptionStatus,
    UserRole,
)
from app.models import (  # noqa: E402
    Company,
    CompanyMembership,
    EmailOutbox,
    Notification,
    PaymentOrder,
    PaymentTransaction,
    RecruitmentPlan,
    Subscription,
    User,
)
from app.repositories.subscription_repository import (  # noqa: E402
    SubscriptionRepository,
)
from app.services.notification_service import (  # noqa: E402
    COMPANY_RETURNED_TO_FREE_TYPE,
    VIETNAM_TZ,
)
from app.services.payment_providers.vnpay import VNPAYProvider  # noqa: E402
from app.services.payment_service import PaymentService  # noqa: E402
from app.services.subscription_service import SubscriptionService  # noqa: E402


pytestmark = pytest.mark.integration

ACTIVATION_TYPE = "subscription_activated"


async def _count_activation_notifications(session, user_id: uuid.UUID) -> int:
    stmt = select(func.count(Notification.id)).where(
        Notification.user_id == user_id,
        Notification.notification_type == ACTIVATION_TYPE,
        Notification.is_deleted == False,  # noqa: E712
    )
    return (await session.execute(stmt)).scalar_one()


async def _get_activation_notification(session, user_id: uuid.UUID) -> Notification | None:
    stmt = select(Notification).where(
        Notification.user_id == user_id,
        Notification.notification_type == ACTIVATION_TYPE,
        Notification.is_deleted == False,  # noqa: E712
    )
    return (await session.execute(stmt)).scalars().first()


async def _seed(session, *, plan_name="Professional", price=299_000, duration_days=30):
    plan = RecruitmentPlan(
        name=plan_name,
        price=price,
        currency="VND",
        duration_days=duration_days,
        max_job_posts=10,
        max_candidate_searches=10,
        max_ai_features=10,
        is_active=True,
        display_order=1,
    )
    user = User(
        email=f"notif-{uuid.uuid4()}@example.com",
        password_hash="hash",
        role=UserRole.CANDIDATE,
    )
    session.add_all([plan, user])
    await session.flush()
    return plan, user


async def _seed_pending_subscription(session, user, plan):
    sub = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.PENDING,
    )
    session.add(sub)
    await session.flush()
    return sub


async def _seed_pending_order(session, user, plan, sub, internal_order_id: str):
    order = PaymentOrder(
        user_id=user.id,
        plan_id=plan.id,
        subscription_id=sub.id,
        amount=plan.price,
        currency="VND",
        provider=PaymentProvider.VNPAY,
        internal_order_id=internal_order_id,
        status=PaymentOrderStatus.PENDING,
        expired_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    session.add(order)
    await session.flush()
    return order


async def _seed_company(session) -> Company:
    suffix = uuid.uuid4().hex[:10]
    company = Company(
        name=f"Company {suffix}",
        slug=f"company-{suffix}",
        tax_code=f"TAX{suffix}".upper(),
        size=CompanySize.SME,
    )
    session.add(company)
    await session.flush()
    return company


async def _seed_company_membership(
    session,
    company: Company,
    user: User,
    *,
    role: MembershipRole = MembershipRole.ADMIN,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> CompanyMembership:
    membership = CompanyMembership(
        company_id=company.id,
        user_id=user.id,
        role=role,
        status=status,
    )
    session.add(membership)
    await session.flush()
    return membership


async def _seed_company_plan(
    session,
    *,
    plan_name: str = "Company Professional",
    price: int = 499_000,
    duration_days: int = 30,
) -> RecruitmentPlan:
    plan = RecruitmentPlan(
        name=plan_name,
        price=price,
        currency="VND",
        duration_days=duration_days,
        max_job_posts=10,
        max_candidate_searches=10,
        max_ai_features=10,
        plan_audience=PlanAudience.COMPANY,
        is_free=False,
        is_active=True,
        display_order=1,
    )
    session.add(plan)
    await session.flush()
    return plan


async def _seed_company_pending_order(
    session,
    *,
    purchaser: User,
    company: Company,
    plan: RecruitmentPlan,
    internal_order_id: str,
) -> tuple[Subscription, PaymentOrder]:
    sub = Subscription(
        user_id=purchaser.id,
        company_id=company.id,
        plan_id=plan.id,
        scope=SubscriptionScope.COMPANY_RECRUITING,
        is_free=False,
        status=SubscriptionStatus.PENDING,
    )
    session.add(sub)
    await session.flush()
    order = PaymentOrder(
        user_id=purchaser.id,
        company_id=company.id,
        plan_id=plan.id,
        subscription_id=sub.id,
        scope=SubscriptionScope.COMPANY_RECRUITING,
        amount=plan.price,
        currency="VND",
        provider=PaymentProvider.VNPAY,
        internal_order_id=internal_order_id,
        status=PaymentOrderStatus.PENDING,
        expired_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    session.add(order)
    await session.flush()
    return sub, order


async def _activation_notifications_for_subscription(session, sub_id):
    stmt = select(Notification).where(
        Notification.notification_type == ACTIVATION_TYPE,
        Notification.entity_type == "subscription",
        Notification.entity_id == sub_id,
        Notification.is_deleted == False,  # noqa: E712
    )
    return list((await session.execute(stmt)).scalars().all())


def _ipn_params(order: PaymentOrder, provider: VNPAYProvider, txn_no: str = "13524458") -> dict:
    params = {
        "vnp_TmnCode": settings.VNPAY_TMN_CODE,
        "vnp_Amount": str(order.amount * 100),
        "vnp_BankCode": "NCB",
        "vnp_BankTranNo": "VNP123456",
        "vnp_CardType": "ATM",
        "vnp_PayDate": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        "vnp_OrderInfo": "Test activation",
        "vnp_TransactionNo": txn_no,
        "vnp_ResponseCode": "00",
        "vnp_TransactionStatus": "00",
        "vnp_TxnRef": order.internal_order_id,
    }
    params["vnp_SecureHash"] = provider.generate_secure_hash(params)
    return params


def test_ipn_activation_creates_exactly_one_notification(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan, user = await _seed(setup)
            sub = await _seed_pending_subscription(setup, user, plan)
            order = await _seed_pending_order(
                setup, user, plan, sub, "VNPAY_NOTIF_IPN_001"
            )
            await setup.commit()
            user_id, sub_id, plan_name = user.id, sub.id, plan.name

        provider = VNPAYProvider()
        async with async_session_factory() as session:
            params = _ipn_params(order, provider)
            result = await PaymentService(session).process_vnpay_ipn(params, "127.0.0.1")
            assert result["RspCode"] == "00", result

        async with async_session_factory() as check:
            count = await _count_activation_notifications(check, user_id)
            assert count == 1, f"expected exactly 1 activation notification, got {count}"
            notif = await _get_activation_notification(check, user_id)
            assert notif is not None
            assert notif.title == "Kích hoạt gói dịch vụ thành công"
            assert notif.entity_type == "subscription"
            assert notif.entity_id == sub_id
            assert plan_name in notif.content

    run_async(_run())


def test_duplicate_ipn_does_not_duplicate_notification(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan, user = await _seed(setup)
            sub = await _seed_pending_subscription(setup, user, plan)
            order = await _seed_pending_order(
                setup, user, plan, sub, "VNPAY_NOTIF_IPN_002"
            )
            await setup.commit()
            user_id = user.id

        provider = VNPAYProvider()
        params = _ipn_params(order, provider)
        async with async_session_factory() as session:
            svc = PaymentService(session)
            first = await svc.process_vnpay_ipn(params, "127.0.0.1")
            second = await svc.process_vnpay_ipn(params, "127.0.0.1")
            assert first["RspCode"] == "00"
            assert second["RspCode"] == "00"

        async with async_session_factory() as check:
            count = await _count_activation_notifications(check, user_id)
            assert count == 1, f"duplicate IPN produced {count} notifications"

    run_async(_run())


def test_concurrent_duplicate_ipn_creates_single_notification(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan, user = await _seed(setup)
            sub = await _seed_pending_subscription(setup, user, plan)
            order = await _seed_pending_order(
                setup, user, plan, sub, "VNPAY_NOTIF_IPN_003"
            )
            await setup.commit()
            user_id = user.id

        provider = VNPAYProvider()
        params = _ipn_params(order, provider)

        async with async_session_factory() as session_a, async_session_factory() as session_b:
            service_a = PaymentService(session_a)
            service_b = PaymentService(session_b)
            result_a, result_b = await asyncio.gather(
                service_a.process_vnpay_ipn(params, "127.0.0.1"),
                service_b.process_vnpay_ipn(params, "127.0.0.1"),
            )
            assert result_a["RspCode"] == "00", result_a
            assert result_b["RspCode"] == "00", result_b

        async with async_session_factory() as check:
            count = await _count_activation_notifications(check, user_id)
            assert count == 1, f"concurrent duplicate IPN produced {count} notifications"

    run_async(_run())


def test_querydr_finalize_after_ipn_does_not_duplicate_notification(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan, user = await _seed(setup)
            sub = await _seed_pending_subscription(setup, user, plan)
            order = await _seed_pending_order(
                setup, user, plan, sub, "VNPAY_NOTIF_IPN_004"
            )
            await setup.commit()
            user_id, order_id = user.id, order.id

        provider = VNPAYProvider()
        async with async_session_factory() as session:
            svc = PaymentService(session)
            ipn = await svc.process_vnpay_ipn(_ipn_params(order, provider), "127.0.0.1")
            assert ipn["RspCode"] == "00"

        # Simulate the QueryDr reconciliation finalize on the now-PAID order. It
        # must observe PAID under the order lock and bail out without notifying.
        async with async_session_factory() as session:
            svc = PaymentService(session)
            locked = await svc.payment_orders.get_by_internal_order_id(
                "VNPAY_NOTIF_IPN_004"
            )
            assert locked is not None and locked.id == order_id
            await svc._finalize_reconciled_success(locked, {})

        async with async_session_factory() as check:
            count = await _count_activation_notifications(check, user_id)
            assert count == 1, f"QueryDr after IPN produced {count} notifications"

    run_async(_run())


def test_paid_order_without_activation_creates_no_success_notification(run_async):
    """PAID order + PENDING subscription (activation refused) => no success notification."""

    async def _run():
        async with async_session_factory() as setup:
            high_plan, user = await _seed(setup, plan_name="Enterprise", price=999_000)
            # Existing ACTIVE subscription on the high-tier plan.
            active = Subscription(
                user_id=user.id,
                plan_id=high_plan.id,
                status=SubscriptionStatus.ACTIVE,
                started_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                max_job_posts=10,
            )
            setup.add(active)
            # A cheaper plan checkout: activation would be a downgrade -> refused.
            low_plan = RecruitmentPlan(
                name="Starter",
                price=99_000,
                currency="VND",
                duration_days=30,
                max_job_posts=1,
                is_active=True,
                display_order=2,
            )
            setup.add(low_plan)
            await setup.flush()
            sub = await _seed_pending_subscription(setup, user, low_plan)
            order = await _seed_pending_order(
                setup, user, low_plan, sub, "VNPAY_NOTIF_IPN_005"
            )
            await setup.commit()
            user_id, sub_id = user.id, sub.id

        provider = VNPAYProvider()
        async with async_session_factory() as session:
            result = await PaymentService(session).process_vnpay_ipn(
                _ipn_params(order, provider), "127.0.0.1"
            )
            assert result["RspCode"] == "00", result

        async with async_session_factory() as check:
            # Payment recorded as PAID...
            order_row = await check.get(PaymentOrder, order.id)
            assert order_row.status == PaymentOrderStatus.PAID
            # ...but the subscription stayed PENDING...
            sub_row = await check.get(Subscription, sub_id)
            assert sub_row.status == SubscriptionStatus.PENDING
            # ...and no activation success notification was emitted.
            count = await _count_activation_notifications(check, user_id)
            assert count == 0, f"expected no activation notification, got {count}"

    run_async(_run())


def test_direct_activation_creates_one_notification_and_repeat_is_idempotent(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan, user = await _seed(setup)
            sub = await _seed_pending_subscription(setup, user, plan)
            await setup.commit()
            user_id, sub_id, plan_name = user.id, sub.id, plan.name

        async with async_session_factory() as session:
            await SubscriptionService(session).activate_subscription(sub_id)

        async with async_session_factory() as check:
            count = await _count_activation_notifications(check, user_id)
            assert count == 1, f"direct activation produced {count} notifications"
            notif = await _get_activation_notification(check, user_id)
            assert notif is not None
            assert notif.title == "Kích hoạt gói dịch vụ thành công"
            assert notif.entity_type == "subscription"
            assert notif.entity_id == sub_id
            assert plan_name in notif.content
            sub_row = await check.get(Subscription, sub_id)
            assert sub_row.status == SubscriptionStatus.ACTIVE

        # A repeat activation must raise and must not create a second notification.
        async with async_session_factory() as session:
            with pytest.raises(InvalidTransitionException):
                await SubscriptionService(session).activate_subscription(sub_id)

        async with async_session_factory() as check:
            count = await _count_activation_notifications(check, user_id)
            assert count == 1, f"repeat activation produced {count} notifications"

    run_async(_run())


def test_concurrent_direct_activation_creates_single_notification(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan, user = await _seed(setup)
            sub = await _seed_pending_subscription(setup, user, plan)
            await setup.commit()
            user_id, sub_id = user.id, sub.id

        async def _activate():
            async with async_session_factory() as session:
                return await SubscriptionService(session).activate_subscription(sub_id)

        results = await asyncio.gather(_activate(), _activate(), return_exceptions=True)
        successes = [r for r in results if not isinstance(r, Exception)]
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(successes) == 1, f"expected 1 success, got {results}"
        assert len(exceptions) == 1, f"expected 1 failure, got {results}"
        assert isinstance(exceptions[0], InvalidTransitionException)

        async with async_session_factory() as check:
            count = await _count_activation_notifications(check, user_id)
            assert count == 1, f"concurrent direct activation produced {count} notifications"

    run_async(_run())


def test_activation_rollback_leaves_no_notification(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan, user = await _seed(setup)
            sub = await _seed_pending_subscription(setup, user, plan)
            await setup.commit()
            user_id, sub_id = user.id, sub.id

        async with async_session_factory() as session:
            service = SubscriptionService(session)
            with patch.object(
                session, "commit", new=AsyncMock(side_effect=RuntimeError("db down"))
            ):
                with pytest.raises(RuntimeError):
                    await service.activate_subscription(sub_id)

        async with async_session_factory() as check:
            count = await _count_activation_notifications(check, user_id)
            assert count == 0, f"rolled-back activation left {count} notifications"
            sub_row = await check.get(Subscription, sub_id)
            assert sub_row.status == SubscriptionStatus.PENDING

    run_async(_run())


def test_company_ipn_activation_notifies_each_active_admin_only(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan = await _seed_company_plan(setup)
            company = await _seed_company(setup)
            purchaser = (
                await _seed(setup, plan_name="Ignored Candidate Plan")
            )[1]
            admin_a = User(
                email=f"admin-a-{uuid.uuid4()}@example.com",
                password_hash="hash",
                role=UserRole.RECRUITER,
            )
            admin_b = User(
                email=f"admin-b-{uuid.uuid4()}@example.com",
                password_hash="hash",
                role=UserRole.RECRUITER,
            )
            recruiter = User(
                email=f"recruiter-{uuid.uuid4()}@example.com",
                password_hash="hash",
                role=UserRole.RECRUITER,
            )
            interviewer = User(
                email=f"interviewer-{uuid.uuid4()}@example.com",
                password_hash="hash",
                role=UserRole.RECRUITER,
            )
            revoked_admin = User(
                email=f"revoked-{uuid.uuid4()}@example.com",
                password_hash="hash",
                role=UserRole.RECRUITER,
            )
            setup.add_all([admin_a, admin_b, recruiter, interviewer, revoked_admin])
            await setup.flush()
            await _seed_company_membership(
                setup, company, purchaser, role=MembershipRole.RECRUITER
            )
            await _seed_company_membership(setup, company, admin_a)
            await _seed_company_membership(setup, company, admin_b)
            await _seed_company_membership(
                setup, company, recruiter, role=MembershipRole.RECRUITER
            )
            await _seed_company_membership(
                setup, company, interviewer, role=MembershipRole.INTERVIEWER
            )
            await _seed_company_membership(
                setup,
                company,
                revoked_admin,
                role=MembershipRole.ADMIN,
                status=MembershipStatus.REVOKED,
            )
            sub, order = await _seed_company_pending_order(
                setup,
                purchaser=purchaser,
                company=company,
                plan=plan,
                internal_order_id="VNPAY_COMPANY_NOTIF_001",
            )
            await setup.commit()
            sub_id = sub.id
            admin_ids = {admin_a.id, admin_b.id}
            non_admin_ids = {
                purchaser.id,
                recruiter.id,
                interviewer.id,
                revoked_admin.id,
            }

        provider = VNPAYProvider()
        async with async_session_factory() as session:
            result = await PaymentService(session).process_vnpay_ipn(
                _ipn_params(order, provider), "127.0.0.1"
            )
            assert result["RspCode"] == "00", result

        async with async_session_factory() as check:
            notifications = await _activation_notifications_for_subscription(
                check, sub_id
            )
            assert len(notifications) == 2
            assert {n.user_id for n in notifications} == admin_ids
            assert {n.user_id for n in notifications}.isdisjoint(non_admin_ids)
            for notification in notifications:
                assert notification.entity_type == "subscription"
                assert notification.entity_id == sub_id
                assert notification.title == "Kích hoạt gói dịch vụ thành công"
                assert plan.name in notification.content

    run_async(_run())


def test_duplicate_company_ipn_does_not_duplicate_admin_notifications(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan = await _seed_company_plan(setup)
            company = await _seed_company(setup)
            purchaser = (await _seed(setup))[1]
            admin = User(
                email=f"admin-{uuid.uuid4()}@example.com",
                password_hash="hash",
                role=UserRole.RECRUITER,
            )
            setup.add(admin)
            await setup.flush()
            await _seed_company_membership(
                setup, company, purchaser, role=MembershipRole.RECRUITER
            )
            await _seed_company_membership(setup, company, admin)
            sub, order = await _seed_company_pending_order(
                setup,
                purchaser=purchaser,
                company=company,
                plan=plan,
                internal_order_id="VNPAY_COMPANY_NOTIF_002",
            )
            await setup.commit()
            sub_id, admin_id = sub.id, admin.id

        provider = VNPAYProvider()
        params = _ipn_params(order, provider)
        async with async_session_factory() as session:
            svc = PaymentService(session)
            first = await svc.process_vnpay_ipn(params, "127.0.0.1")
            second = await svc.process_vnpay_ipn(params, "127.0.0.1")
            assert first["RspCode"] == "00"
            assert second["RspCode"] == "00"

        async with async_session_factory() as check:
            notifications = await _activation_notifications_for_subscription(
                check, sub_id
            )
            assert len(notifications) == 1
            assert notifications[0].user_id == admin_id

    run_async(_run())


def test_company_failed_payment_creates_no_activation_notification(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan = await _seed_company_plan(setup)
            company = await _seed_company(setup)
            purchaser = (await _seed(setup))[1]
            admin = User(
                email=f"admin-{uuid.uuid4()}@example.com",
                password_hash="hash",
                role=UserRole.RECRUITER,
            )
            setup.add(admin)
            await setup.flush()
            await _seed_company_membership(setup, company, admin)
            sub, order = await _seed_company_pending_order(
                setup,
                purchaser=purchaser,
                company=company,
                plan=plan,
                internal_order_id="VNPAY_COMPANY_NOTIF_003",
            )
            await setup.commit()
            sub_id, order_id = sub.id, order.id

        provider = VNPAYProvider()
        params = _ipn_params(order, provider)
        params["vnp_ResponseCode"] = "24"
        params["vnp_TransactionStatus"] = "02"
        params.pop("vnp_SecureHash", None)
        params["vnp_SecureHash"] = provider.generate_secure_hash(params)
        async with async_session_factory() as session:
            result = await PaymentService(session).process_vnpay_ipn(
                params, "127.0.0.1"
            )
            assert result["RspCode"] == "00"

        async with async_session_factory() as check:
            notifications = await _activation_notifications_for_subscription(
                check, sub_id
            )
            assert notifications == []
            order_row = await check.get(PaymentOrder, order_id)
            assert order_row.status == PaymentOrderStatus.FAILED
            sub_row = await check.get(Subscription, sub_id)
            assert sub_row.status == SubscriptionStatus.CANCELLED

    run_async(_run())


def test_company_paid_expiration_notifies_active_admins_only(run_async):
    async def _run():
        async with async_session_factory() as setup:
            paid_plan = await _seed_company_plan(setup)
            free_plan = RecruitmentPlan(
                name="Company Free",
                price=0,
                currency="VND",
                duration_days=30,
                max_job_posts=1,
                max_candidate_searches=1,
                max_ai_features=1,
                plan_audience=PlanAudience.COMPANY,
                is_free=True,
                is_active=True,
                display_order=0,
            )
            setup.add(free_plan)
            company = await _seed_company(setup)
            owner = (await _seed(setup))[1]
            admin = User(
                email=f"admin-{uuid.uuid4()}@example.com",
                password_hash="hash",
                role=UserRole.RECRUITER,
            )
            recruiter = User(
                email=f"recruiter-{uuid.uuid4()}@example.com",
                password_hash="hash",
                role=UserRole.RECRUITER,
            )
            interviewer = User(
                email=f"interviewer-{uuid.uuid4()}@example.com",
                password_hash="hash",
                role=UserRole.RECRUITER,
            )
            revoked_admin = User(
                email=f"revoked-{uuid.uuid4()}@example.com",
                password_hash="hash",
                role=UserRole.RECRUITER,
            )
            setup.add_all([admin, recruiter, interviewer, revoked_admin])
            await setup.flush()
            await _seed_company_membership(
                setup, company, owner, role=MembershipRole.RECRUITER
            )
            await _seed_company_membership(setup, company, admin)
            await _seed_company_membership(
                setup, company, recruiter, role=MembershipRole.RECRUITER
            )
            await _seed_company_membership(
                setup, company, interviewer, role=MembershipRole.INTERVIEWER
            )
            await _seed_company_membership(
                setup,
                company,
                revoked_admin,
                role=MembershipRole.ADMIN,
                status=MembershipStatus.REVOKED,
            )
            now = datetime.now(timezone.utc)
            paid_sub = Subscription(
                user_id=owner.id,
                company_id=company.id,
                plan_id=paid_plan.id,
                scope=SubscriptionScope.COMPANY_RECRUITING,
                is_free=False,
                status=SubscriptionStatus.ACTIVE,
                started_at=now - timedelta(days=31),
                expires_at=now - timedelta(days=1),
                max_job_posts=paid_plan.max_job_posts,
            )
            setup.add(paid_sub)
            await setup.commit()
            paid_sub_id = paid_sub.id
            admin_id = admin.id
            non_admin_ids = {
                owner.id,
                recruiter.id,
                interviewer.id,
                revoked_admin.id,
            }
            company_id = company.id
            paid_plan_name = paid_plan.name

        async with async_session_factory() as session:
            count = await SubscriptionService(
                session
            ).check_and_expire_subscriptions(
                now=datetime.now(timezone.utc)
            )
            assert count == 1

        async with async_session_factory() as check:
            stmt = select(Notification).where(
                Notification.notification_type
                == COMPANY_RETURNED_TO_FREE_TYPE,
                Notification.entity_type == "subscription",
                Notification.entity_id == paid_sub_id,
                Notification.is_deleted == False,  # noqa: E712
            )
            notifications = list((await check.execute(stmt)).scalars().all())
            assert len(notifications) == 1
            assert notifications[0].user_id == admin_id
            assert notifications[0].user_id not in non_admin_ids
            assert paid_plan_name in notifications[0].content
            assert "đã hết hạn" in notifications[0].content
            assert "gói miễn phí" in notifications[0].content

            paid_row = await check.get(Subscription, paid_sub_id)
            assert paid_row.status == SubscriptionStatus.EXPIRED
            free_stmt = (
                select(Subscription)
                .where(
                    Subscription.company_id == company_id,
                    Subscription.is_free == True,  # noqa: E712
                    Subscription.status == SubscriptionStatus.ACTIVE,
                )
            )
            free_row = (await check.execute(free_stmt)).scalars().first()
            assert free_row is not None

    run_async(_run())


def test_concurrent_expiration_workers_create_one_notification_per_admin(
    run_async,
):
    async def _run():
        async with async_session_factory() as setup:
            paid_plan = await _seed_company_plan(setup)
            free_plan = RecruitmentPlan(
                name="Company Free",
                price=0,
                currency="VND",
                duration_days=30,
                max_job_posts=1,
                max_candidate_searches=1,
                max_ai_features=1,
                plan_audience=PlanAudience.COMPANY,
                is_free=True,
                is_active=True,
                display_order=0,
            )
            setup.add(free_plan)
            company = await _seed_company(setup)
            owner = (await _seed(setup))[1]
            admin_a = User(
                email=f"admin-a-{uuid.uuid4()}@example.com",
                password_hash="hash",
                role=UserRole.RECRUITER,
            )
            admin_b = User(
                email=f"admin-b-{uuid.uuid4()}@example.com",
                password_hash="hash",
                role=UserRole.RECRUITER,
            )
            setup.add_all([admin_a, admin_b])
            await setup.flush()
            await _seed_company_membership(
                setup, company, owner, role=MembershipRole.RECRUITER
            )
            await _seed_company_membership(setup, company, admin_a)
            await _seed_company_membership(setup, company, admin_b)
            now = datetime.now(timezone.utc)
            paid_sub = Subscription(
                user_id=owner.id,
                company_id=company.id,
                plan_id=paid_plan.id,
                scope=SubscriptionScope.COMPANY_RECRUITING,
                is_free=False,
                status=SubscriptionStatus.ACTIVE,
                started_at=now - timedelta(days=31),
                expires_at=now - timedelta(days=1),
                max_job_posts=paid_plan.max_job_posts,
            )
            setup.add(paid_sub)
            await setup.commit()
            paid_sub_id = paid_sub.id
            admin_ids = {admin_a.id, admin_b.id}
            company_id = company.id

        async def _expire():
            async with async_session_factory() as session:
                return await SubscriptionService(
                    session
                ).check_and_expire_subscriptions(
                    now=datetime.now(timezone.utc)
                )

        results = await asyncio.gather(
            _expire(), _expire(), return_exceptions=True
        )
        assert [r for r in results if isinstance(r, Exception)] == []
        assert sum(results) >= 1

        async with async_session_factory() as check:
            stmt = select(Notification).where(
                Notification.notification_type
                == COMPANY_RETURNED_TO_FREE_TYPE,
                Notification.entity_type == "subscription",
                Notification.entity_id == paid_sub_id,
                Notification.is_deleted == False,  # noqa: E712
            )
            notifications = list((await check.execute(stmt)).scalars().all())
            assert len(notifications) == 2
            assert {n.user_id for n in notifications} == admin_ids

            paid_row = await check.get(Subscription, paid_sub_id)
            assert paid_row.status == SubscriptionStatus.EXPIRED
            free_stmt = (
                select(Subscription)
                .where(
                    Subscription.company_id == company_id,
                    Subscription.is_free == True,  # noqa: E712
                    Subscription.status == SubscriptionStatus.ACTIVE,
                )
            )
            free_rows = list((await check.execute(free_stmt)).scalars().all())
            assert len(free_rows) == 1

    run_async(_run())


def test_redis_publish_failure_does_not_break_activation(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan, user = await _seed(setup)
            sub = await _seed_pending_subscription(setup, user, plan)
            await setup.commit()
            user_id, sub_id = user.id, sub.id

        from app.core.pubsub import pubsub_manager

        with patch.object(
            pubsub_manager,
            "publish",
            new=AsyncMock(side_effect=RuntimeError("redis down")),
        ):
            async with async_session_factory() as session:
                await SubscriptionService(session).activate_subscription(sub_id)

        async with async_session_factory() as check:
            sub_row = await check.get(Subscription, sub_id)
            assert sub_row.status == SubscriptionStatus.ACTIVE
            count = await _count_activation_notifications(check, user_id)
            assert count == 1, f"expected notification to persist despite Redis failure, got {count}"

    run_async(_run())

def test_company_receipt_failure_rolls_back_payment_activation_and_notices(run_async):
    async def _run():
        async with async_session_factory() as setup:
            plan = await _seed_company_plan(setup)
            company = await _seed_company(setup)
            purchaser = (await _seed(setup))[1]
            admin = User(
                email=f"admin-{uuid.uuid4()}@example.com",
                password_hash="hash",
                role=UserRole.RECRUITER,
            )
            setup.add(admin)
            await setup.flush()
            await _seed_company_membership(setup, company, admin)
            sub, order = await _seed_company_pending_order(
                setup,
                purchaser=purchaser,
                company=company,
                plan=plan,
                internal_order_id="VNPAY_COMPANY_ATOMIC_001",
            )
            await setup.commit()
            sub_id, order_id = sub.id, order.id
            purchaser_email = purchaser.email
            order_reference = order.internal_order_id

        provider = VNPAYProvider()
        params = _ipn_params(order, provider)
        with patch(
            "app.services.payment_service.schedule_payment_receipt_email",
            new=AsyncMock(side_effect=RuntimeError("outbox unavailable")),
        ):
            async with async_session_factory() as session:
                result = await PaymentService(session).process_vnpay_ipn(
                    params, "127.0.0.1"
                )

        assert result == {
            "RspCode": "99",
            "Message": "Internal processing error",
        }

        async with async_session_factory() as check:
            order_row = await check.get(PaymentOrder, order_id)
            sub_row = await check.get(Subscription, sub_id)
            assert order_row.status == PaymentOrderStatus.PENDING
            assert sub_row.status == SubscriptionStatus.PENDING

            transactions = list(
                (
                    await check.execute(
                        select(PaymentTransaction).where(
                            PaymentTransaction.payment_order_id == order_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert transactions == []

            notifications = await _activation_notifications_for_subscription(
                check, sub_id
            )
            assert notifications == []

            outbox_rows = list(
                (
                    await check.execute(
                        select(EmailOutbox).where(
                            EmailOutbox.to_email == purchaser_email,
                            EmailOutbox.idempotency_key
                            == f"payment_receipt:{order_reference}",
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert outbox_rows == []

    run_async(_run())


def test_legacy_expiration_sweep_leaves_company_and_candidate_rows_untouched(
    run_async,
):
    async def _run():
        async with async_session_factory() as setup:
            company = await _seed_company(setup)
            company_owner = (await _seed(setup))[1]
            candidate_plan, candidate = await _seed(
                setup, plan_name="Candidate Paid"
            )
            legacy_user = (
                await _seed(setup, plan_name="Legacy Recruiter Plan")
            )[1]
            now = datetime.now(timezone.utc)
            company_paid = Subscription(
                user_id=company_owner.id,
                company_id=company.id,
                plan_id=candidate_plan.id,
                scope=SubscriptionScope.COMPANY_RECRUITING,
                is_free=False,
                status=SubscriptionStatus.ACTIVE,
                started_at=now - timedelta(days=31),
                expires_at=now - timedelta(days=1),
            )
            candidate_paid = Subscription(
                user_id=candidate.id,
                plan_id=candidate_plan.id,
                scope=SubscriptionScope.CANDIDATE_PERSONAL,
                is_free=False,
                status=SubscriptionStatus.ACTIVE,
                started_at=now - timedelta(days=31),
                expires_at=now - timedelta(days=1),
            )
            legacy_paid = Subscription(
                user_id=legacy_user.id,
                plan_id=candidate_plan.id,
                scope=SubscriptionScope.LEGACY_RECRUITER_PERSONAL,
                is_free=False,
                status=SubscriptionStatus.ACTIVE,
                started_at=now - timedelta(days=31),
                expires_at=now - timedelta(days=1),
            )
            setup.add_all([company_paid, candidate_paid, legacy_paid])
            await setup.commit()
            company_paid_id = company_paid.id
            candidate_paid_id = candidate_paid.id
            legacy_paid_id = legacy_paid.id

        async with async_session_factory() as session:
            count = await SubscriptionRepository(session).expire_stale_active(
                now=datetime.now(timezone.utc)
            )
            assert count == 1
            await session.commit()

        async with async_session_factory() as check:
            assert (
                await check.get(Subscription, legacy_paid_id)
            ).status == SubscriptionStatus.EXPIRED
            assert (
                await check.get(Subscription, company_paid_id)
            ).status == SubscriptionStatus.ACTIVE
            assert (
                await check.get(Subscription, candidate_paid_id)
            ).status == SubscriptionStatus.ACTIVE

    run_async(_run())
