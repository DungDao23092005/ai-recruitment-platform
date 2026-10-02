import uuid

import pytest
from fastapi import Depends
import httpx

from app.api.v1.endpoints import admin_subscriptions as admin_subs_endpoints
from app.api.v1.endpoints import subscriptions as subs_endpoints
from app.main import app
from app.services.subscription_service import SubscriptionService
from app.core.security import get_password_hash
from app.domain.enums import UserRole
from app.models import User
from app.database.session import async_session_factory
from tests.integration.api.conftest import API_V1, run


@pytest.fixture
def subscription_service_override():
    from app.api.deps import get_db as app_get_db

    async def _override(db=Depends(app_get_db)):
        return SubscriptionService(db)

    app.dependency_overrides[subs_endpoints._get_subscription_service] = _override
    app.dependency_overrides[admin_subs_endpoints._get_subscription_service] = _override
    yield
    app.dependency_overrides.pop(subs_endpoints._get_subscription_service, None)
    app.dependency_overrides.pop(admin_subs_endpoints._get_subscription_service, None)


@pytest.fixture
def admin_sub_client(client):
    """Create an admin client for subscription tests."""
    email = f"admin-sub-{uuid.uuid4()}@example.com"
    password_hash = get_password_hash("password123")

    async def create_admin():
        async with async_session_factory() as session:
            admin_user = User(
                email=email,
                password_hash=password_hash,
                role=UserRole.ADMIN,
                is_active=True,
            )
            session.add(admin_user)
            await session.commit()
            await session.refresh(admin_user)
            return admin_user

    run(create_admin())

    login = run(
        client.post(
            f"{API_V1}/auth/login",
            data={"username": email, "password": "password123"},
        )
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )


async def _get_candidate_user():
    from sqlalchemy import select
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.role == UserRole.CANDIDATE))
        return result.scalar_one_or_none()


class TestUserSubscriptionAccess:
    def test_anonymous_access_401(self, client, run_async):
        """Unauthenticated user cannot access subscription endpoints."""
        resp = run_async(client.get(f"{API_V1}/subscriptions/me"))
        assert resp.status_code == 401

    def test_candidate_can_get_own_subscription(self, candidate_client, run_async, subscription_service_override):
        """Candidate can get their own active subscription (or 404 if none)."""
        resp = run_async(candidate_client.get(f"{API_V1}/subscriptions/me"))
        assert resp.status_code in (200, 404)

    def test_recruiter_can_get_own_subscription(self, recruiter_client, run_async, subscription_service_override):
        """Recruiter can get their own active subscription."""
        resp = run_async(recruiter_client.get(f"{API_V1}/subscriptions/me"))
        assert resp.status_code in (200, 404)

    def test_candidate_can_get_subscription_history(self, candidate_client, run_async, subscription_service_override):
        """Candidate can view their subscription history."""
        resp = run_async(candidate_client.get(f"{API_V1}/subscriptions/me/history"))
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_user_cannot_access_another_user_subscription(self, candidate_client, run_async, subscription_service_override, admin_sub_client):
        """A user cannot access another user's subscription by ID."""
        # Try to access a non-existent subscription ID
        resp = run_async(candidate_client.get(f"{API_V1}/subscriptions/{uuid.uuid4()}"))
        assert resp.status_code == 404


class TestAdminSubscriptionAccess:
    def test_anonymous_admin_access_401(self, client, run_async):
        """Admin subscription endpoints require admin auth."""
        resp = run_async(client.get(f"{API_V1}/admin/subscriptions"))
        assert resp.status_code == 401

    def test_candidate_admin_access_403(self, candidate_client, run_async, subscription_service_override):
        """Candidate cannot access admin subscription endpoints."""
        resp = run_async(candidate_client.get(f"{API_V1}/admin/subscriptions"))
        assert resp.status_code == 403

    def test_recruiter_admin_access_403(self, recruiter_client, run_async, subscription_service_override):
        """Recruiter cannot access admin subscription endpoints."""
        resp = run_async(recruiter_client.get(f"{API_V1}/admin/subscriptions"))
        assert resp.status_code == 403

    def test_admin_can_list_subscriptions(self, admin_sub_client, run_async, subscription_service_override):
        """Admin can list all subscriptions."""
        resp = run_async(admin_sub_client.get(f"{API_V1}/admin/subscriptions"))
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_admin_can_provision_subscription(self, admin_sub_client, run_async, subscription_service_override):
        """Admin can provision an active subscription for a user."""
        from tests.integration.api.test_plans import _create_plan, PLAN_BODY

        # Create a plan
        plan = _create_plan(admin_sub_client, run_async)

        # Get candidate user
        candidate_user = run(_get_candidate_user())
        if not candidate_user:
            pytest.skip("No candidate user available")

        # Provision subscription
        resp = run_async(admin_sub_client.post(f"{API_V1}/admin/subscriptions", json={
            "user_id": str(candidate_user.id),
            "plan_id": str(plan["id"]),
        }))
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["status"] == "active"
        assert data["user_id"] == str(candidate_user.id)
        assert data["plan_id"] == str(plan["id"])

    def test_admin_can_get_subscription(self, admin_sub_client, run_async, subscription_service_override):
        """Admin can get any subscription by ID."""
        from tests.integration.api.test_plans import _create_plan

        plan = _create_plan(admin_sub_client, run_async)
        candidate_user = run(_get_candidate_user())
        if not candidate_user:
            pytest.skip("No candidate user available")

        prov = run_async(admin_sub_client.post(f"{API_V1}/admin/subscriptions", json={
            "user_id": str(candidate_user.id),
            "plan_id": str(plan["id"]),
        }))
        assert prov.status_code == 201
        sub_id = prov.json()["id"]

        resp = run_async(admin_sub_client.get(f"{API_V1}/admin/subscriptions/{sub_id}"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == sub_id

    def test_admin_can_cancel_subscription(self, admin_sub_client, run_async, subscription_service_override):
        """Admin can cancel a subscription."""
        from tests.integration.api.test_plans import _create_plan

        plan = _create_plan(admin_sub_client, run_async)
        candidate_user = run(_get_candidate_user())
        if not candidate_user:
            pytest.skip("No candidate user available")

        prov = run_async(admin_sub_client.post(f"{API_V1}/admin/subscriptions", json={
            "user_id": str(candidate_user.id),
            "plan_id": str(plan["id"]),
        }))
        assert prov.status_code == 201
        sub_id = prov.json()["id"]

        resp = run_async(admin_sub_client.post(f"{API_V1}/admin/subscriptions/{sub_id}/cancel"))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "cancelled"

    def test_cannot_provision_for_inactive_plan(self, admin_sub_client, run_async, subscription_service_override):
        """Admin cannot provision subscription for inactive plan."""
        from tests.integration.api.test_plans import _create_plan

        plan = _create_plan(admin_sub_client, run_async)

        # Deactivate the plan
        resp = run_async(admin_sub_client.patch(f"{API_V1}/admin/plans/{plan['id']}/status", json={"is_active": False}))
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

        candidate_user = run(_get_candidate_user())
        if not candidate_user:
            pytest.skip("No candidate user available")

        resp = run_async(admin_sub_client.post(f"{API_V1}/admin/subscriptions", json={
            "user_id": str(candidate_user.id),
            "plan_id": str(plan["id"]),
        }))
        assert resp.status_code == 404  # Plan not found or inactive

    def test_candidate_cannot_create_active_subscription(self, candidate_client, run_async, subscription_service_override, admin_sub_client):
        """Candidate cannot directly create an active paid subscription."""
        from tests.integration.api.test_plans import _create_plan

        plan = _create_plan(admin_sub_client, run_async)

        resp = run_async(candidate_client.post(f"{API_V1}/subscriptions", json={
            "plan_id": str(plan["id"]),
        }))
        assert resp.status_code in (404, 405, 422)


class TestSubscriptionOwnership:
    def test_ownership_enforced(self, candidate_client, candidate_b_client, run_async, subscription_service_override, admin_sub_client):
        """A user cannot retrieve another user's subscription via ID."""
        from tests.integration.api.test_plans import _create_plan
        plan = _create_plan(admin_sub_client, run_async)
        # Get candidate_b_client's user ID by registering/logging in
        # We need to get the user ID from the candidate_b_client token
        # First, let's get the user ID from the database using candidate_b_client's token
        from app.database.session import async_session_factory
        from app.domain.enums import UserRole
        from app.core.security import decode_access_token
        from sqlalchemy import select
        # Extract user ID from candidate_b_client's token
        auth_header = candidate_b_client.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "")
        payload = decode_access_token(token)
        candidate_b_user_id = uuid.UUID(payload["sub"])
        prov = run_async(admin_sub_client.post(f"{API_V1}/admin/subscriptions", json={
            "user_id": str(candidate_b_user_id),
            "plan_id": str(plan["id"]),
        }))
        assert prov.status_code == 201
        sub_id = prov.json()["id"]

        # candidate_client (different user) tries to access candidate_b_user's subscription
        resp = run_async(candidate_client.get(f"{API_V1}/subscriptions/{sub_id}"))
        assert resp.status_code == 404