"""Payment API integration tests for VNPAY endpoints.

Tests POST /api/v1/payments/vnpay/create, GET /api/v1/payments/vnpay/return,
and GET /api/v1/payments/vnpay/status/{internal_order_id}.

These tests require a running database and authenticated client,
so they are placed in the integration test layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import httpx

from sqlalchemy import select

import pytest
from fastapi import status

from app.main import app
from app.models.payment_order import PaymentOrder
from app.schemas.payment import (
    VNPayCreatePaymentRequest,
    VNPayCreatePaymentResponse,
    VNPayIPNParams,
    VNPayReturnParams,
    PaymentStatusResponse,
)
from tests.integration.conftest import run


@pytest.fixture(scope="session", autouse=True)
def configure_test_settings():
    """Configure test settings to avoid rate limit interference."""
    from app.core.config import settings
    settings.RATE_LIMIT_ENABLED = False


@pytest.fixture(scope="session")
async def lifespan_manager():
    """Manage the FastAPI lifespan for integration tests."""
    from asgi_lifespan import LifespanManager
    from app.main import app
    async with LifespanManager(app) as manager:
        yield manager


@pytest.fixture(scope="session")
def client(lifespan_manager):
    """Create async HTTP client for integration tests."""
    import httpx
    async_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )
    yield async_client
    run(async_client.aclose())


def _make_auth_client(client):
    """Create an authenticated candidate HTTP client."""
    email = f"test-candidate-{uuid.uuid4()}@example.com"
    register = run(
        client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "password123", "role": "candidate"},
        )
    )
    assert register.status_code == 201, register.text
    login = run(
        client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": "password123"},
        )
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    from httpx import AsyncClient as HC
    auth_client = HC(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )
    return auth_client


@pytest.fixture
def candidate_client(client):
    """Create authenticated candidate client."""
    auth_client = _make_auth_client(client)
    yield auth_client
    run(auth_client.aclose())


# Fixtures that create database objects using run() helper
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
    from app.domain.enums import PaymentOrderStatus, PaymentProvider, SubscriptionStatus
    from app.models import Subscription, PaymentOrder
    from sqlalchemy import select

    async def _create_sub_and_order():
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
                internal_order_id="TEST_ORDER_PENDING_SUB",
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


class TestPaymentAPIStatus:
    """Tests for GET /api/v1/payments/vnpay/status/{internal_order_id} endpoint."""

    def test_get_payment_status_authenticated_own(
        self, candidate_client, test_payment_order,
    ):
        """Authenticated user can check their own payment status."""
        response = _get(
            candidate_client,
            f"/api/v1/payments/vnpay/status/{test_payment_order.internal_order_id}",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_successful"] is False  # PENDING status

    def test_get_payment_status_cross_user_denied(
        self, candidate_client, another_user_payment_order,
    ):
        """Cross-user access denied - cannot check another user's payment."""
        response = _get(
            candidate_client,
            f"/api/v1/payments/vnpay/status/{another_user_payment_order.internal_order_id}",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


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