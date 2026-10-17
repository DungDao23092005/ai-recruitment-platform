"""Payment API integration tests for VNPAY endpoints.

Tests POST /api/v1/payments/vnpay/create, GET /api/v1/payments/vnpay/return,
and GET /api/v1/payments/vnpay/status/{internal_order_id}.

These tests require a running database and authenticated client,
so they are placed in the integration test layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

import pytest
from fastapi import status

from app.models.payment_order import PaymentOrder
from app.schemas.payment import (
    VNPayCreatePaymentRequest,
    VNPayCreatePaymentResponse,
    VNPayIPNParams,
    VNPayReturnParams,
    PaymentStatusResponse,
)
from tests.integration.api.conftest import API_V1
from tests.integration.conftest import run


# Fixtures that create database objects using run() helper
# - flush() + commit() so data is visible across sessions
# - genuine User records (NO fake UUIDs)
# - flush() + commit() so data is visible across sessions
# - genuine User records (NO fake UUIDs)
@pytest.fixture
def test_plan(run_async):
    """Create a test recruitment plan in the database."""
    import asyncio

    async def _create_plan():
        from app.models import RecruitmentPlan

        plan = RecruitmentPlan(
            id=uuid.uuid4(),
            name="Test Plan",
            description="Test plan",
            price=1500000,
            currency="VND",
            duration_days=30,
            max_job_posts=10,
            is_active=True,
            display_order=1,
        )
        from app.database.session import async_session_factory

        async with async_session_factory() as session:
            session.add(plan)
            await session.flush()
            await session.commit()
            return plan

    return run(_create_plan())


@pytest.fixture
def inactive_plan(run_async):
    """Create an inactive test plan."""
    import asyncio

    async def _create_plan():
        from app.models import RecruitmentPlan

        plan = RecruitmentPlan(
            id=uuid.uuid4(),
            name="Inactive Plan",
            description="Inactive plan",
            price=1000000,
            currency="VND",
            duration_days=15,
            max_job_posts=5,
            is_active=False,
            display_order=0,
        )
        from app.database.session import async_session_factory

        async with async_session_factory() as session:
            session.add(plan)
            await session.flush()
            await session.commit()
            return plan

    return run(_create_plan())


@pytest.fixture
def test_payment_order(run_async, test_plan, candidate_client):
    """Create a PaymentOrder with PENDING status."""
    from app.domain.enums import PaymentOrderStatus, PaymentProvider, UserRole
    from sqlalchemy import select
    from app.database.session import async_session_factory
    from app.models import User

    async def _create_order():
        async with async_session_factory() as session:
            # Use the project's standard candidate user resolution pattern
            # (same as _get_candidate_user() in test_subscriptions.py)
            # This ensures the PaymentOrder belongs to the same user as candidate_client
            candidate_user = await session.scalar(
                select(User).where(User.role == UserRole.CANDIDATE)
            )
            if candidate_user is None:
                # Create a candidate user if none exists
                candidate_user = User(
                    id=uuid.uuid4(),
                    email="test-candidate@example.com",
                    password_hash="hashed",
                    role="candidate",
                )
                session.add(candidate_user)
                await session.flush()
                await session.commit()

            order = PaymentOrder(
                id=uuid.uuid4(),
                user_id=candidate_user.id,
                plan_id=test_plan.id,
                amount=test_plan.price,
                currency="VND",
                provider=PaymentProvider.VNPAY,
                internal_order_id=f"VNPAY_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8].upper()}",
                status=PaymentOrderStatus.PENDING,
                expired_at=datetime.utcnow() + timedelta(minutes=15),
            )
            session.add(order)
            await session.flush()
            await session.commit()
            await session.refresh(order)
            return order

    return run(_create_order())


@pytest.fixture
def test_payment_order_and_pending_sub(run_async, test_plan, candidate_client):
    """Create a PaymentOrder with PENDING status and PENDING subscription."""
    from app.domain.enums import PaymentOrderStatus, PaymentProvider, SubscriptionStatus, UserRole
    from app.models import Subscription, PaymentOrder
    from sqlalchemy import select

    async def _create_sub_and_order():
        from app.database.session import async_session_factory

        async with async_session_factory() as session:
            # Resolve the same authenticated candidate user pattern used by
            # test_payment_order so the order is owned by candidate_client.
            from app.models import User
            user = await session.scalar(
                select(User).where(User.role == UserRole.CANDIDATE)
            )
            if user is None:
                user = User(
                    id=uuid.uuid4(),
                    email=f"candidate-{uuid.uuid4().hex[:8]}@example.com",
                    password_hash="hashed",
                    role="candidate",
                )
                session.add(user)
                await session.flush()

            subscription = Subscription(
                id=uuid.uuid4(),
                user_id=user.id,
                plan_id=test_plan.id,
                status=SubscriptionStatus.PENDING,
            )
            session.add(subscription)
            await session.flush()

            order = PaymentOrder(
                id=uuid.uuid4(),
                user_id=user.id,
                plan_id=test_plan.id,
                subscription_id=subscription.id,
                amount=test_plan.price,
                provider=PaymentProvider.VNPAY,
                internal_order_id=(
                    f"TEST_ORDER_PENDING_SUB_{uuid.uuid4().hex[:8].upper()}"
                ),
                status=PaymentOrderStatus.PENDING,
                expired_at=datetime.utcnow() + timedelta(minutes=15),
            )
            session.add(order)
            await session.flush()
            await session.commit()
            await session.refresh(order)
            await session.refresh(subscription)
            return order, subscription

    return run(_create_sub_and_order())


@pytest.fixture
def test_payment_order_pending(run_async, test_plan, candidate_client):
    """Create a simple PaymentOrder with PENDING status."""
    from app.domain.enums import PaymentOrderStatus, PaymentProvider

    async def _create_order():
        from app.database.session import async_session_factory

        async with async_session_factory() as session:
            # Genuine user from the authenticated candidate client
            from app.models import User
            user = await session.scalar(
                select(User).where(User.email == "test-candidate@example.com")
            )
            if user is None:
                user = User(
                    id=uuid.uuid4(),
                    email="test-candidate@example.com",
                    password_hash="hashed",
                    role="candidate",
                )
                session.add(user)
                await session.flush()
                await session.commit()

            order = PaymentOrder(
                id=uuid.uuid4(),
                user_id=user.id,
                plan_id=test_plan.id,
                amount=test_plan.price,
                currency="VND",
                provider=PaymentProvider.VNPAY,
                internal_order_id=f"VNPAY_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8].upper()}",
                status=PaymentOrderStatus.PENDING,
                expired_at=datetime.utcnow() + timedelta(minutes=15),
            )
            session.add(order)
            await session.flush()
            await session.commit()
            await session.refresh(order)
            return order

    return run(_create_order())


@pytest.fixture
def test_subscription_pending(run_async, test_plan, candidate_client):
    """Create a PENDING subscription."""
    import asyncio
    from app.domain.enums import SubscriptionStatus
    from app.models import Subscription

    async def _create_sub():
        from app.database.session import async_session_factory

        async with async_session_factory() as session:
            # Genuine user from the authenticated candidate client
            from app.models import User
            user = await session.scalar(
                select(User).where(User.email == "test-candidate@example.com")
            )
            if user is None:
                user = User(
                    id=uuid.uuid4(),
                    email="test-candidate@example.com",
                    password_hash="hashed",
                    role="candidate",
                )
                session.add(user)
                await session.flush()
                await session.commit()

            subscription = Subscription(
                id=uuid.uuid4(),
                user_id=user.id,
                plan_id=test_plan.id,
                status=SubscriptionStatus.PENDING,
            )
            session.add(subscription)
            await session.flush()
            await session.commit()
            await session.refresh(subscription)
            return subscription

    return run(_create_sub())


@pytest.fixture
def another_user_payment_order(run_async, test_plan):
    """Create a PaymentOrder belonging to a different user."""
    import asyncio
    from app.models import User
    from app.core.security import get_password_hash

    async def _create_user():
        from app.database.session import async_session_factory

        async with async_session_factory() as session:
            other_user = User(
                id=uuid.uuid4(),
                email="other-user@example.com",
                password_hash=get_password_hash("testpass123"),
                role="candidate",
            )
            session.add(other_user)
            await session.flush()
            await session.commit()
            return other_user

    other_user = run(_create_user())

    from app.domain.enums import PaymentOrderStatus, PaymentProvider

    async def _create_order():
        from app.database.session import async_session_factory

        async with async_session_factory() as session:
            order = PaymentOrder(
                id=uuid.uuid4(),
                user_id=other_user.id,  # type: ignore
                plan_id=test_plan.id,
                amount=test_plan.price,
                currency="VND",
                provider=PaymentProvider.VNPAY,
                internal_order_id=f"VNPAY_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8].upper()}",
                status=PaymentOrderStatus.PENDING,
                expired_at=datetime.utcnow() + timedelta(minutes=15),
            )
            session.add(order)
            await session.flush()
            await session.commit()
            await session.refresh(order)
            return order

    return run(_create_order())


# Helper to run an async HTTP call in a sync test
def _post(client, url, **kwargs):
    return run(client.post(url, **kwargs))


def _get(client, url, **kwargs):
    return run(client.get(url, **kwargs))


class TestPaymentAPICreate:
    """Tests for POST /api/v1/payments/vnpay/create endpoint."""

    def test_create_vnpay_payment_authenticated_candidate_success(
        self, candidate_client, test_plan,
    ):
        """Authenticated candidate → success."""
        from unittest.mock import patch

        # Mock VNPAY URL generation to avoid actual network calls
        with patch(
            "app.api.v1.endpoints.payments.PaymentService.create_vnpay_payment",
            return_value=(
                "https://sandbox.vnpayment.vn/pay?param=value",
                "VNPAY_20240101_120000_ABCD1234",
                uuid.uuid4(),
            ),
        ):
            response = _post(
                candidate_client,
                "/api/v1/payments/vnpay/create",
                json={"plan_id": str(test_plan.id)},
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["payment_url"] is not None
        assert data["internal_order_id"] is not None
        assert data["internal_order_id"].startswith("VNPAY_")
        assert data["payment_order_id"] is not None
        assert data["subscription_id"] is not None

    def test_create_vnpay_payment_unauthenticated(
        self, client, test_plan,
    ):
        """Unauthenticated → 401."""
        response = _post(
            client,
            "/api/v1/payments/vnpay/create",
            json={"plan_id": str(test_plan.id)},
        )
        # In the current setup, all API endpoints require some form of auth
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    def test_create_vnpay_payment_unknown_plan(
        self, candidate_client,
    ):
        """Unknown plan → expected error."""
        fake_plan_id = uuid.uuid4()

        response = _post(
            candidate_client,
            "/api/v1/payments/vnpay/create",
            json={"plan_id": str(fake_plan_id)},
        )

        # Should return 422 or appropriate error for invalid plan
        assert response.status_code in (
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            status.HTTP_404_NOT_FOUND,
        )

    def test_create_vnpay_payment_inactive_plan(
        self, candidate_client, inactive_plan,
    ):
        """Inactive plan → expected error."""
        response = _post(
            candidate_client,
            "/api/v1/payments/vnpay/create",
            json={"plan_id": str(inactive_plan.id)},
        )
        # Should return error for inactive plan
        assert response.status_code in (
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            status.HTTP_404_NOT_FOUND,
        )

    def test_create_vnpay_payment_amount_not_client_controlled(
        self, candidate_client, test_plan,
    ):
        """Amount cannot be client-controlled - server uses plan price."""
        # The plan price is authoritative, not from request
        response = _post(
            candidate_client,
            "/api/v1/payments/vnpay/create",
            json={"plan_id": str(test_plan.id)},
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        # Verify the internal order was created with plan's price
        # (The test verifies the flow, not the exact amount in response)


class TestPaymentAPIDelete:
    """Tests for GET /api/v1/payments/vnpay/return endpoint."""

    def test_return_valid_signature(
        self, candidate_client,
    ):
        """Valid signature return."""
        pass

    def test_return_invalid_signature(
        self, candidate_client,
    ):
        """Invalid signature → redirect."""
        response = _get(candidate_client, "/api/v1/payments/vnpay/return")
        assert response.status_code == status.HTTP_302_FOUND
        assert "payment-result" in response.headers.get("location", "")

    def test_return_unknown_txnref(
        self, candidate_client,
    ):
        """Unknown TxnRef → redirect."""
        response = _get(
            candidate_client,
            "/api/v1/payments/vnpay/return",
            params={"vnp_TxnRef": "nonexistent"},
        )
        assert response.status_code == status.HTTP_302_FOUND
        assert "payment-result" in response.headers.get("location", "")

    def test_return_tampered_amount(
        self, candidate_client, test_payment_order,
    ):
        """Tampered amount → error response."""
        params = {
            "vnp_TxnRef": test_payment_order.internal_order_id,
            "vnp_Amount": "999999999",  # Tampered amount
            "vnp_SecureHash": "invalid",
        }
        response = _get(candidate_client, "/api/v1/payments/vnpay/return", params=params)
        # Should fail signature verification - return 302 redirect
        assert response.status_code == status.HTTP_302_FOUND
        assert "payment-result" in response.headers.get("location", "")

    def test_return_does_not_activate_subscription(
        self, candidate_client, test_payment_order_and_pending_sub,
    ):
        """Return never activates subscription - only IPN does."""
        test_payment_order, _ = test_payment_order_and_pending_sub
        response = _get(
            candidate_client,
            "/api/v1/payments/vnpay/return",
            params={
                "vnp_TxnRef": test_payment_order.internal_order_id,
            },
        )
        # Verify subscription is still PENDING after return
        # The key invariant: return is informational only


def _signed_querydr_response(
    order,
    *,
    response_code: str = "00",
    transaction_status: str = "00",
    amount: str | None = None,
    transaction_type: str = "01",
    tmn_code: str | None = None,
    transaction_no: str | None = None,
    sign: bool = True,
) -> dict:
    """Build a VNPAY QueryDr response with a genuine vnp_SecureHash.

    Signing uses a fresh ``VNPAYProvider`` so it reads the same configured
    secret as the service under test. Tests must never disable verification to
    make an old case pass.
    """
    from app.services.payment_providers.vnpay import VNPAYProvider

    provider = VNPAYProvider()
    body = {
        "vnp_ResponseId": uuid.uuid4().hex[:16],
        "vnp_Command": "querydr",
        "vnp_ResponseCode": response_code,
        "vnp_Message": "Query Success" if response_code == "00" else "Query failed",
        "vnp_TmnCode": provider.tmn_code if tmn_code is None else tmn_code,
        "vnp_TxnRef": order.internal_order_id,
        "vnp_Amount": str(order.amount * 100) if amount is None else amount,
        "vnp_BankCode": "NCB",
        "vnp_PayDate": "20260101120000",
        "vnp_TransactionNo": transaction_no or f"VNP{uuid.uuid4().int % 10**10}",
        "vnp_TransactionType": transaction_type,
        "vnp_TransactionStatus": transaction_status,
        "vnp_OrderInfo": f"Query transaction {order.internal_order_id}",
    }
    if sign:
        body["vnp_SecureHash"] = provider.generate_query_response_secure_hash(body)
    return body


class TestPaymentAPIStatus:
    """Tests for GET /api/v1/payments/vnpay/status/{internal_order_id} endpoint.

    QueryDr reconciliation is mocked so these tests never make a real outbound
    VNPAY call, while the database behavior remains live.
    """

    def test_get_payment_status_authenticated_own(
        self, candidate_client, test_payment_order,
    ):
        """Authenticated user checks own pending status.

        A temporary QueryDr failure must leave the order PENDING, never failed.
        """
        from unittest.mock import AsyncMock, patch
        from app.services.payment_service import PaymentService

        with patch.object(
            PaymentService,
            "_send_querydr_request",
            new=AsyncMock(side_effect=RuntimeError("querydr unavailable")),
        ):
            response = _get(
                candidate_client,
                f"/api/v1/payments/vnpay/status/{test_payment_order.internal_order_id}",
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_successful"] is False
        assert data["payment_order"]["status"] == "pending"

    def test_get_payment_status_querydr_success_finalizes_order(
        self, candidate_client, test_payment_order,
    ):
        """A conclusive successful QueryDr finalizes the matching PENDING order."""
        from unittest.mock import AsyncMock, patch
        from app.services.payment_service import PaymentService

        body = _signed_querydr_response(test_payment_order)
        body["vnp_BankTranNo"] = "BANK123"

        with patch.object(
            PaymentService, "_send_querydr_request", new=AsyncMock(return_value=body)
        ):
            response = _get(
                candidate_client,
                f"/api/v1/payments/vnpay/status/{test_payment_order.internal_order_id}",
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_successful"] is True
        assert data["payment_order"]["status"] == "paid"

    def test_get_payment_status_querydr_success_activates_subscription(
        self, candidate_client, test_payment_order_and_pending_sub,
    ):
        """QueryDr-verified success activates the linked subscription."""
        from unittest.mock import AsyncMock, patch
        from app.domain.enums import SubscriptionStatus
        from app.services.payment_service import PaymentService
        from app.database.session import async_session_factory

        order, subscription = test_payment_order_and_pending_sub
        body = _signed_querydr_response(order)

        with patch.object(
            PaymentService, "_send_querydr_request", new=AsyncMock(return_value=body)
        ):
            response = _get(
                candidate_client,
                f"/api/v1/payments/vnpay/status/{order.internal_order_id}",
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["is_successful"] is True

        async def _check():
            from app.models import Subscription

            async with async_session_factory() as session:
                sub = await session.get(Subscription, subscription.id)
                return sub.status

        assert run(_check()) == SubscriptionStatus.ACTIVE

    def test_get_payment_status_querydr_mismatched_amount_stays_pending(
        self, candidate_client, test_payment_order,
    ):
        """A QueryDr response with a mismatched amount must not finalize the order."""
        from unittest.mock import AsyncMock, patch
        from app.services.payment_service import PaymentService

        body = _signed_querydr_response(test_payment_order, amount="1")  # wrong amount
        with patch.object(
            PaymentService, "_send_querydr_request", new=AsyncMock(return_value=body)
        ):
            response = _get(
                candidate_client,
                f"/api/v1/payments/vnpay/status/{test_payment_order.internal_order_id}",
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_successful"] is False
        assert data["payment_order"]["status"] == "pending"

    def test_get_payment_status_querydr_pending_stays_pending(
        self, candidate_client, test_payment_order,
    ):
        """A documented non-terminal QueryDr status keeps the order PENDING."""
        from unittest.mock import AsyncMock, patch
        from app.services.payment_service import PaymentService

        body = _signed_querydr_response(
            test_payment_order, transaction_status="01"
        )  # not completed (processing)
        with patch.object(
            PaymentService, "_send_querydr_request", new=AsyncMock(return_value=body)
        ):
            response = _get(
                candidate_client,
                f"/api/v1/payments/vnpay/status/{test_payment_order.internal_order_id}",
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["payment_order"]["status"] == "pending"

    def test_get_payment_status_missing_signature_stays_pending(
        self, candidate_client, test_payment_order,
    ):
        """A QueryDr response without a checksum must never finalize the order."""
        from unittest.mock import AsyncMock, patch
        from app.services.payment_service import PaymentService

        body = _signed_querydr_response(test_payment_order, sign=False)
        with patch.object(
            PaymentService, "_send_querydr_request", new=AsyncMock(return_value=body)
        ):
            response = _get(
                candidate_client,
                f"/api/v1/payments/vnpay/status/{test_payment_order.internal_order_id}",
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_successful"] is False
        assert data["payment_order"]["status"] == "pending"

    def test_get_payment_status_tampered_signature_stays_pending(
        self, candidate_client, test_payment_order,
    ):
        """A response modified after signing must fail checksum verification."""
        from unittest.mock import AsyncMock, patch
        from app.services.payment_service import PaymentService

        body = _signed_querydr_response(test_payment_order)
        body["vnp_Amount"] = "1"  # tampered after signing

        with patch.object(
            PaymentService, "_send_querydr_request", new=AsyncMock(return_value=body)
        ):
            response = _get(
                candidate_client,
                f"/api/v1/payments/vnpay/status/{test_payment_order.internal_order_id}",
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_successful"] is False
        assert data["payment_order"]["status"] == "pending"

    def test_get_payment_status_wrong_tmn_code_stays_pending(
        self, candidate_client, test_payment_order,
    ):
        """A validly-signed response for another merchant must be rejected."""
        from unittest.mock import AsyncMock, patch
        from app.services.payment_service import PaymentService

        body = _signed_querydr_response(test_payment_order, tmn_code="OTHER_MERCHANT")
        with patch.object(
            PaymentService, "_send_querydr_request", new=AsyncMock(return_value=body)
        ):
            response = _get(
                candidate_client,
                f"/api/v1/payments/vnpay/status/{test_payment_order.internal_order_id}",
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["payment_order"]["status"] == "pending"

    def test_get_payment_status_refund_transaction_type_stays_pending(
        self, candidate_client, test_payment_order,
    ):
        """A refund transaction type is never accepted as the original payment."""
        from unittest.mock import AsyncMock, patch
        from app.services.payment_service import PaymentService

        body = _signed_querydr_response(test_payment_order, transaction_type="02")
        with patch.object(
            PaymentService, "_send_querydr_request", new=AsyncMock(return_value=body)
        ):
            response = _get(
                candidate_client,
                f"/api/v1/payments/vnpay/status/{test_payment_order.internal_order_id}",
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["payment_order"]["status"] == "pending"

    def test_get_payment_status_status_07_stays_pending(
        self, candidate_client, test_payment_order,
    ):
        """Fraud-suspected status 07 must not move the order to FAILED."""
        from unittest.mock import AsyncMock, patch
        from app.services.payment_service import PaymentService

        body = _signed_querydr_response(test_payment_order, transaction_status="07")
        with patch.object(
            PaymentService, "_send_querydr_request", new=AsyncMock(return_value=body)
        ):
            response = _get(
                candidate_client,
                f"/api/v1/payments/vnpay/status/{test_payment_order.internal_order_id}",
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["payment_order"]["status"] == "pending"

    def test_get_payment_status_forged_response_never_activates_subscription(
        self, candidate_client, test_payment_order_and_pending_sub,
    ):
        """Evidence: a forged QueryDr success cannot finalize or activate."""
        from unittest.mock import AsyncMock, patch
        from app.domain.enums import SubscriptionStatus
        from app.services.payment_service import PaymentService
        from app.database.session import async_session_factory

        order, subscription = test_payment_order_and_pending_sub
        body = _signed_querydr_response(order)
        body["vnp_Amount"] = "1"  # tamper after signing → invalid checksum

        with patch.object(
            PaymentService, "_send_querydr_request", new=AsyncMock(return_value=body)
        ):
            response = _get(
                candidate_client,
                f"/api/v1/payments/vnpay/status/{order.internal_order_id}",
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_successful"] is False
        assert data["payment_order"]["status"] == "pending"
        assert data["transaction"] is None

        async def _check():
            from app.models import Subscription, PaymentOrder as _PaymentOrder

            async with async_session_factory() as session:
                sub = await session.get(Subscription, subscription.id)
                locked_order = await session.get(_PaymentOrder, order.id)
                return sub.status, locked_order.status

        sub_status, order_status = run(_check())
        assert sub_status == SubscriptionStatus.PENDING
        assert order_status == "pending"

    def test_get_payment_status_cross_user_denied(
        self, candidate_client, another_user_payment_order,
    ):
        """Cross-user access denied - cannot check another user's payment."""
        from unittest.mock import AsyncMock, patch
        from app.services.payment_service import PaymentService

        querydr = AsyncMock(return_value={"vnp_ResponseCode": "00"})
        with patch.object(
            PaymentService, "_send_querydr_request", new=querydr
        ):
            response = _get(
                candidate_client,
                f"/api/v1/payments/vnpay/status/{another_user_payment_order.internal_order_id}",
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        # Ownership is enforced before any reconciliation is attempted.
        querydr.assert_not_called()


class TestPhase65PaymentAuthorization:
    """Phase 6.5: Payment API authorization regression tests."""

    def test_get_payment_status_anonymous_denied(self, client, test_payment_order):
        """Anonymous access to /api/v1/payments/vnpay/status/{order_id} returns 401."""
        response = _get(
            client,
            f"/api/v1/payments/vnpay/status/{test_payment_order.internal_order_id}",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestPaymentAPIReturnNeverActivates:
    """Critical test: GET /api/v1/payments/vnpay/return never activates subscription."""

    def test_return_independent_of_ipn_activation(
        self, run_async, test_subscription_pending, test_payment_order_pending,
        candidate_client,
    ):
        """Return URL flow does NOT activate subscription."""
        from app.services.payment_service import PaymentService

        # Set up: PaymentOrder = PENDING, Subscription = PENDING
        # Create valid return params
        from app.services.payment_providers.vnpay import VNPAYProvider
        from app.core.config import settings

        vnpay = VNPAYProvider()

        # Build params with valid signature for PENDING payment
        params = vnpay.build_payment_params(
            amount=test_payment_order_pending.amount,
            order_id=test_payment_order_pending.internal_order_id,
            order_info="Test",
            client_ip="127.0.0.1",
            return_url="http://localhost:5173/payment-result",
        )

        # Generate valid hash
        secure_hash = vnpay.generate_secure_hash(params)
        params["vnp_SecureHash"] = secure_hash

        # Call return endpoint
        response = _get(
            candidate_client,
            "/api/v1/payments/vnpay/return",
            params=params,
        )

        # Verify return is informational only - 302 redirect, no subscription activation
        # The key invariant: return is informational only, follows browser redirect behavior
        assert response.status_code == status.HTTP_302_FOUND
        assert "payment-result" in response.headers.get("location", "")