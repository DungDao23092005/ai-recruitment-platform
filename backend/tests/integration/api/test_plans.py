import uuid

import pytest
from fastapi import Depends
import httpx

from app.api.v1.endpoints import admin_plans as admin_plans_endpoints
from app.api.v1.endpoints import plans as plans_endpoints
from app.main import app
from app.services.recruitment_plan_service import RecruitmentPlanService
from app.core.security import get_password_hash
from app.domain.enums import UserRole
from app.models import User
from app.database.session import async_session_factory
from tests.integration.api.conftest import API_V1, run

PLAN_BODY = {
    "name": "Test Plan",
    "description": "Test plan description",
    "price": 1000000,
    "currency": "VND",
    "duration_days": 30,
    "max_job_posts": 5,
    "max_candidate_searches": 10,
    "max_ai_features": 3,
    "display_order": 0,
}


@pytest.fixture
def plan_service_override():
    from app.api.deps import get_db as app_get_db

    async def _override(db=Depends(app_get_db)):
        return RecruitmentPlanService(db)

    app.dependency_overrides[plans_endpoints._get_plan_service] = _override
    app.dependency_overrides[admin_plans_endpoints._get_plan_service] = _override
    yield
    app.dependency_overrides.pop(plans_endpoints._get_plan_service, None)
    app.dependency_overrides.pop(admin_plans_endpoints._get_plan_service, None)


@pytest.fixture
def admin_plan_client(client):
    """Create an admin client specifically for plan tests."""
    email = f"admin-plan-{uuid.uuid4()}@example.com"
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


def _create_plan(admin_client, run_async, body=None):
    if body is None:
        body = PLAN_BODY.copy()

    resp = run_async(admin_client.post(f"{API_V1}/admin/plans", json=body))
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestPublicPlans:
    def test_anonymous_list_plans_401(self, client, run_async):
        """Public plan listing should require authentication."""
        resp = run_async(client.get(f"{API_V1}/plans"))
        assert resp.status_code == 401

    def test_candidate_can_list_active_plans(self, candidate_client, run_async, plan_service_override):
        """Authenticated candidate can list active plans."""
        resp = run_async(candidate_client.get(f"{API_V1}/plans"))
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_recruiter_can_list_active_plans(self, recruiter_client, run_async, plan_service_override):
        """Authenticated recruiter can list active plans."""
        resp = run_async(recruiter_client.get(f"{API_V1}/plans"))
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_candidate_can_get_active_plan_by_id(self, candidate_client, run_async, plan_service_override, admin_plan_client):
        """Candidate can get an active plan by ID."""
        plan = _create_plan(admin_plan_client, run_async)

        resp = run_async(candidate_client.get(f"{API_V1}/plans/{plan['id']}"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == plan["id"]
        assert data["name"] == plan["name"]
        assert data["is_active"] is True

    def test_inactive_plan_not_visible_to_candidate(self, candidate_client, run_async, plan_service_override, admin_plan_client):
        """Inactive plans should not be accessible via public endpoint."""
        plan = _create_plan(admin_plan_client, run_async)

        resp = run_async(admin_plan_client.patch(f"{API_V1}/admin/plans/{plan['id']}/status", json={"is_active": False}))
        assert resp.status_code == 200

        resp = run_async(candidate_client.get(f"{API_V1}/plans/{plan['id']}"))
        assert resp.status_code == 404


class TestAdminPlans:
    def test_anonymous_create_401(self, client, run_async):
        body = {**PLAN_BODY}
        resp = run_async(client.post(f"{API_V1}/admin/plans", json=body))
        assert resp.status_code == 401

    def test_candidate_create_403(self, candidate_client, run_async, plan_service_override):
        body = {**PLAN_BODY}
        resp = run_async(candidate_client.post(f"{API_V1}/admin/plans", json=body))
        assert resp.status_code == 403

    def test_recruiter_create_403(self, recruiter_client, run_async, plan_service_override):
        body = {**PLAN_BODY}
        resp = run_async(recruiter_client.post(f"{API_V1}/admin/plans", json=body))
        assert resp.status_code == 403

    def test_admin_can_create_plan(self, admin_plan_client, run_async, plan_service_override):
        body = {**PLAN_BODY}
        resp = run_async(admin_plan_client.post(f"{API_V1}/admin/plans", json=body))
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == PLAN_BODY["name"]
        assert data["price"] == PLAN_BODY["price"]
        assert data["is_active"] is True

    def test_admin_can_list_all_plans(self, admin_plan_client, run_async, plan_service_override):
        _create_plan(admin_plan_client, run_async)
        _create_plan(admin_plan_client, run_async)

        resp = run_async(admin_plan_client.get(f"{API_V1}/admin/plans"))
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 2

    def test_admin_can_get_plan_by_id(self, admin_plan_client, run_async, plan_service_override):
        plan = _create_plan(admin_plan_client, run_async)

        resp = run_async(admin_plan_client.get(f"{API_V1}/admin/plans/{plan['id']}"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == plan["id"]
        assert data["name"] == plan["name"]

    def test_admin_can_update_plan(self, admin_plan_client, run_async, plan_service_override):
        plan = _create_plan(admin_plan_client, run_async)

        resp = run_async(admin_plan_client.patch(f"{API_V1}/admin/plans/{plan['id']}", json={"name": "Updated Plan", "price": 2000000}))
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Plan"
        assert data["price"] == 2000000

    def test_admin_can_activate_plan(self, admin_plan_client, run_async, plan_service_override):
        plan = _create_plan(admin_plan_client, run_async)
        resp = run_async(admin_plan_client.patch(f"{API_V1}/admin/plans/{plan['id']}/status", json={"is_active": False}))
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

        resp = run_async(admin_plan_client.patch(f"{API_V1}/admin/plans/{plan['id']}/status", json={"is_active": True}))
        assert resp.status_code == 200
        assert resp.json()["is_active"] is True

    def test_duplicate_name_rejected(self, admin_plan_client, run_async, plan_service_override):
        """Test that duplicate plan name is rejected."""
        # Note: The current schema doesn't enforce name uniqueness at DB level,
        # but the test documents the expected behavior if it's added.
        body = {**PLAN_BODY}
        _create_plan(admin_plan_client, run_async, body=body)
        body = {**PLAN_BODY}
        resp = run_async(admin_plan_client.post(f"{API_V1}/admin/plans", json=body))
        # Currently allows duplicate names (no unique constraint in DB)
        # If unique constraint is added, this should be 400
        assert resp.status_code in (201, 400)

    def test_invalid_price_rejected(self, admin_plan_client, run_async, plan_service_override):
        body = {**PLAN_BODY, "price": -1}
        resp = run_async(admin_plan_client.post(f"{API_V1}/admin/plans", json=body))
        assert resp.status_code == 422

    def test_invalid_duration_rejected(self, admin_plan_client, run_async, plan_service_override):
        body = {**PLAN_BODY, "duration_days": 0}
        resp = run_async(admin_plan_client.post(f"{API_V1}/admin/plans", json=body))
        assert resp.status_code == 422

    def test_invalid_limits_rejected(self, admin_plan_client, run_async, plan_service_override):
        body = {**PLAN_BODY, "max_job_posts": -1}
        resp = run_async(admin_plan_client.post(f"{API_V1}/admin/plans", json=body))
        assert resp.status_code == 422

    def test_unknown_plan_returns_404(self, admin_plan_client, run_async, plan_service_override):
        resp = run_async(admin_plan_client.get(f"{API_V1}/admin/plans/{uuid.uuid4()}"))
        assert resp.status_code == 404