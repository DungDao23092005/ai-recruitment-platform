"""Real SQL Server integration tests for subscription lifecycle emails.

Verifies which flows send an email, to whom, that nothing is sent for an unpaid
checkout, and that activation emails are idempotent across payment retries.
``EmailService.send_email`` is spied so no provider call ever leaves the test.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings

settings.VNPAY_TMN_CODE = "TESTTMN"
settings.VNPAY_HASH_SECRET = "testhashsecret123"

from app.database.session import async_session_factory  # noqa: E402
from app.domain.enums import (  # noqa: E402
    PaymentOrderStatus,
    PaymentProvider,
    SubscriptionStatus,
    UserRole,
)
from app.models import PaymentOrder, RecruitmentPlan, Subscription, User  # noqa: E402
from app.services.admin_subscription_service import AdminSubscriptionService  # noqa: E402
from app.services.email_service import EmailService  # noqa: E402
from app.services.payment_providers.vnpay import VNPAYProvider  # noqa: E402
from app.services.payment_service import PaymentService  # noqa: E402
from app.services.subscription_email_service import (  # noqa: E402
    SUBJECT_ACTIVATED,
    SUBJECT_PAYMENT_RECEIPT,
    SUBJECT_PLAN_CHANGED,
    SUBJECT_REVOKED,
)


pytestmark = pytest.mark.integration


@pytest.fixture
def email_spy():
    spy = AsyncMock()
    with patch.object(EmailService, "send_email", new=spy):
        yield spy


async def _seed_user(session, *, role: UserRole = UserRole.CANDIDATE, tag: str = "mail") -> User:
    user = User(
        email=f"{tag}-{uuid.uuid4().hex[:10]}@example.com",
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


def _ipn_params(order: PaymentOrder, provider: VNPAYProvider) -> dict:
    params = {
        "vnp_TmnCode": settings.VNPAY_TMN_CODE,
        "vnp_Amount": str(order.amount * 100),
        "vnp_BankCode": "NCB",
        "vnp_BankTranNo": "VNP123456",
        "vnp_CardType": "ATM",
        "vnp_PayDate": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        "vnp_OrderInfo": "Test email",
        "vnp_TransactionNo": "13524458",
        "vnp_ResponseCode": "00",
        "vnp_TransactionStatus": "00",
        "vnp_TxnRef": order.internal_order_id,
    }
    params["vnp_SecureHash"] = provider.generate_secure_hash(params)
    return params


def test_provision_emails_the_subscription_owner(run_async, email_spy):
    async def _run():
        async with async_session_factory() as setup:
            plan = await _seed_plan(setup)
            user = await _seed_user(setup)
            admin = await _seed_user(setup, role=UserRole.ADMIN, tag="admin")
            await setup.commit()
            plan_id, user_id, user_email = plan.id, user.id, user.email
            admin_id, admin_email = admin.id, admin.email

        async with async_session_factory() as session:
            await AdminSubscriptionService(session).provision(
                admin_id=admin_id,
                user_id=user_id,
                plan_id=plan_id,
            )
            await asyncio.sleep(0.05)

        assert email_spy.await_count == 1
        to_email, subject, html, _ = email_spy.await_args.args
        assert to_email == user_email
        assert to_email != admin_email
        assert subject == SUBJECT_ACTIVATED.format(plan_name="Professional")
        assert "Professional" in html

    run_async(_run())


def test_change_plan_emails_the_owner(run_async, email_spy):
    async def _run():
        async with async_session_factory() as setup:
            plan = await _seed_plan(setup, name="Starter", price=99_000)
            target = await _seed_plan(setup, name="Enterprise", price=999_000)
            user = await _seed_user(setup)
            admin = await _seed_user(setup, role=UserRole.ADMIN, tag="admin")
            sub = await _seed_active_subscription(setup, user, plan)
            await setup.commit()
            sub_id, target_id, admin_id, user_email = sub.id, target.id, admin.id, user.email

        async with async_session_factory() as session:
            await AdminSubscriptionService(session).change_plan(
                admin_id=admin_id,
                subscription_id=sub_id,
                target_plan_id=target_id,
                reason="Nâng cấp",
            )
            await asyncio.sleep(0.05)

        assert email_spy.await_count == 1
        to_email, subject, html, _ = email_spy.await_args.args
        assert to_email == user_email
        assert subject == SUBJECT_PLAN_CHANGED
        assert "Enterprise" in html

    run_async(_run())


def test_revoke_emails_the_owner(run_async, email_spy):
    async def _run():
        async with async_session_factory() as setup:
            plan = await _seed_plan(setup)
            user = await _seed_user(setup)
            admin = await _seed_user(setup, role=UserRole.ADMIN, tag="admin")
            sub = await _seed_active_subscription(setup, user, plan)
            await setup.commit()
            sub_id, admin_id, user_email = sub.id, admin.id, user.email

        async with async_session_factory() as session:
            await AdminSubscriptionService(session).revoke(
                admin_id=admin_id,
                subscription_id=sub_id,
                reason="Thu hồi",
            )
            await asyncio.sleep(0.05)

        assert email_spy.await_count == 1
        to_email, subject, html, _ = email_spy.await_args.args
        assert to_email == user_email
        assert subject == SUBJECT_REVOKED
        assert "Đã hủy" in html

    run_async(_run())


def test_unpaid_checkout_sends_no_email(run_async, email_spy):
    async def _run():
        async with async_session_factory() as setup:
            plan = await _seed_plan(setup)
            user = await _seed_user(setup)
            await setup.commit()
            plan_id, user_id = plan.id, user.id

        async with async_session_factory() as session:
            await PaymentService(session).create_vnpay_payment(user_id, plan_id, "127.0.0.1")
            await asyncio.sleep(0.05)

        email_spy.assert_not_awaited()

    run_async(_run())


def test_vnpay_receipt_is_idempotent_across_ipn_retries(run_async, email_spy):
    async def _run():
        async with async_session_factory() as setup:
            plan = await _seed_plan(setup)
            user = await _seed_user(setup)
            sub = Subscription(
                user_id=user.id,
                plan_id=plan.id,
                status=SubscriptionStatus.PENDING,
            )
            setup.add(sub)
            await setup.flush()
            order = PaymentOrder(
                user_id=user.id,
                plan_id=plan.id,
                subscription_id=sub.id,
                amount=plan.price,
                currency="VND",
                provider=PaymentProvider.VNPAY,
                internal_order_id=f"VNPAY_MAIL_{uuid.uuid4().hex[:8]}",
                status=PaymentOrderStatus.PENDING,
                expired_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            )
            setup.add(order)
            await setup.commit()
            order_id, user_email = order.id, user.email

        provider = VNPAYProvider()
        async with async_session_factory() as session:
            svc = PaymentService(session)
            order_row = await session.get(PaymentOrder, order_id)
            params = _ipn_params(order_row, provider)
            first = await svc.process_vnpay_ipn(params, "127.0.0.1")
            second = await svc.process_vnpay_ipn(params, "127.0.0.1")
            assert first["RspCode"] == "00"
            assert second["RspCode"] == "00"
            await asyncio.sleep(0.05)

        assert email_spy.await_count == 1, "duplicate IPN must not resend the receipt"
        to_email, subject, _, _ = email_spy.await_args.args
        assert to_email == user_email
        assert subject == SUBJECT_PAYMENT_RECEIPT.format(plan_name="Professional")

    run_async(_run())


async def _seed_pending_order(session, *, tag: str) -> tuple[PaymentOrder, uuid.UUID, str]:
    plan = await _seed_plan(session, name="Professional", price=299_000)
    user = await _seed_user(session)
    sub = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.PENDING,
    )
    session.add(sub)
    await session.flush()
    order = PaymentOrder(
        user_id=user.id,
        plan_id=plan.id,
        subscription_id=sub.id,
        amount=plan.price,
        currency="VND",
        provider=PaymentProvider.VNPAY,
        internal_order_id=f"VNPAY_{tag}_{uuid.uuid4().hex[:8]}",
        status=PaymentOrderStatus.PENDING,
        expired_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    session.add(order)
    await session.flush()
    return order, order.id, user.email


def test_vnpay_ipn_success_sends_enriched_receipt(run_async, email_spy):
    async def _run():
        async with async_session_factory() as setup:
            order, order_id, user_email = await _seed_pending_order(setup, tag="RCP")
            await setup.commit()

        provider = VNPAYProvider()
        async with async_session_factory() as session:
            svc = PaymentService(session)
            order_row = await session.get(PaymentOrder, order_id)
            params = _ipn_params(order_row, provider)
            assert params["vnp_TransactionNo"] == "13524458"
            result = await svc.process_vnpay_ipn(params, "127.0.0.1")
            assert result["RspCode"] == "00"
            await asyncio.sleep(0.05)

        assert email_spy.await_count == 1
        to_email, subject, html, text = email_spy.await_args.args
        assert to_email == user_email
        assert subject == SUBJECT_PAYMENT_RECEIPT.format(plan_name="Professional")
        for body in (html, text):
            assert "Professional" in body
            assert "299.000 ₫" in body
            assert "Đã thanh toán" in body
            assert "Đang hoạt động" in body
            assert order_row.internal_order_id in body
            assert "13524458" in body
        # Timestamp shape HH:mm DD/MM/YYYY (Vietnam local).
        assert re.search(r"\d{2}:\d{2} \d{2}/\d{2}/\d{4}", text)

    run_async(_run())


def test_vnpay_querydr_success_sends_enriched_receipt(run_async, email_spy):
    async def _run():
        async with async_session_factory() as setup:
            order, order_id, user_email = await _seed_pending_order(setup, tag="QRY")
            await setup.commit()

        provider = VNPAYProvider()
        async with async_session_factory() as session:
            svc = PaymentService(session)
            order_row = await session.get(PaymentOrder, order_id)
            body = {
                "vnp_ResponseCode": "00",
                "vnp_TransactionStatus": "00",
                "vnp_TmnCode": settings.VNPAY_TMN_CODE,
                "vnp_TxnRef": order_row.internal_order_id,
                "vnp_Amount": str(order_row.amount * 100),
                "vnp_TransactionType": "01",
                "vnp_TransactionNo": "99887766",
                "vnp_PayDate": "20260505101530",
                "vnp_OrderInfo": "Query transaction",
            }
            body["vnp_SecureHash"] = provider.generate_query_response_secure_hash(body)

            with patch.object(
                svc, "_send_querydr_request", new=AsyncMock(return_value=body)
            ):
                await svc._reconcile_pending_vnpay_payment(order_row)
            await asyncio.sleep(0.05)

        assert email_spy.await_count == 1
        to_email, subject, html, text = email_spy.await_args.args
        assert to_email == user_email
        assert subject == SUBJECT_PAYMENT_RECEIPT.format(plan_name="Professional")
        assert order_row.internal_order_id in html
        assert "99887766" in text

    run_async(_run())


def test_vnpay_failed_payment_sends_no_receipt(run_async, email_spy):
    async def _run():
        async with async_session_factory() as setup:
            order, order_id, _ = await _seed_pending_order(setup, tag="FAIL")
            await setup.commit()

        provider = VNPAYProvider()
        async with async_session_factory() as session:
            svc = PaymentService(session)
            order_row = await session.get(PaymentOrder, order_id)
            params = _ipn_params(order_row, provider)
            params["vnp_ResponseCode"] = "24"
            params["vnp_TransactionStatus"] = "02"
            params["vnp_SecureHash"] = provider.generate_secure_hash(params)
            await svc.process_vnpay_ipn(params, "127.0.0.1")
            await asyncio.sleep(0.05)

        email_spy.assert_not_awaited()

    run_async(_run())


def test_vnpay_invalid_signature_sends_no_receipt(run_async, email_spy):
    async def _run():
        async with async_session_factory() as setup:
            order, order_id, _ = await _seed_pending_order(setup, tag="SIG")
            await setup.commit()

        provider = VNPAYProvider()
        async with async_session_factory() as session:
            svc = PaymentService(session)
            order_row = await session.get(PaymentOrder, order_id)
            params = _ipn_params(order_row, provider)
            params["vnp_SecureHash"] = "0" * 128  # tampered signature
            result = await svc.process_vnpay_ipn(params, "127.0.0.1")
            assert result["RspCode"] == "97"
            await asyncio.sleep(0.05)

        email_spy.assert_not_awaited()

    run_async(_run())
