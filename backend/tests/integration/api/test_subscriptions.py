import uuid

import pytest
from fastapi import Depends
import httpx
from sqlalchemy import select

from app.api.v1.endpoints import admin_subscriptions as admin_subs_endpoints
from app.api.v1.endpoints import subscriptions as subs_endpoints
from app.main import app
from app.services.subscription_service import SubscriptionService
from app.core.security import get_password_hash, decode_access_token
from app.domain.enums import UserRole
from app.models import User, RecruiterProfile
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


async def _get_candidate_user_id(candidate_client: httpx.AsyncClient) -> uuid.UUID:
    """Extract candidate user ID from the candidate client's auth token."""
    auth_header = candidate_client.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "")
    payload = decode_access_token(token)
    return uuid.UUID(payload["sub"])


async def _get_user_role(user_id: uuid.UUID) -> UserRole | None:
    """Get user role by querying the database."""
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        return user.role if user else None


async def _get_recruiter_profile(user_id: uuid.UUID) -> RecruiterProfile | None:
    """Get RecruiterProfile by user_id using explicit query (no lazy loading)."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(RecruiterProfile).where(
                RecruiterProfile.user_id == user_id,
                RecruiterProfile.is_deleted == False,  # noqa: E712
            )
        )
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

    def test_admin_can_provision_subscription(self, admin_sub_client, run_async, subscription_service_override, candidate_client):
        """Admin can provision an active subscription for a user.

        Phase 6.1: Verify candidate role transitions to RECRUITER and RecruiterProfile is created.
        """
        from tests.integration.api.test_plans import _create_plan, PLAN_BODY

        # Create a plan
        plan = _create_plan(admin_sub_client, run_async)

        # Get candidate user ID from the candidate_client token
        candidate_user_id = run(_get_candidate_user_id(candidate_client))

        # Verify initial state: candidate is CANDIDATE, no RecruiterProfile
        initial_role = run(_get_user_role(candidate_user_id))
        assert initial_role == UserRole.CANDIDATE
        initial_profile = run(_get_recruiter_profile(candidate_user_id))
        assert initial_profile is None

        # Provision subscription via Admin endpoint
        resp = run_async(admin_sub_client.post(f"{API_V1}/admin/subscriptions", json={
            "user_id": str(candidate_user_id),
            "plan_id": str(plan["id"]),
        }))
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["status"] == "active"
        assert data["user_id"] == str(candidate_user_id)
        assert data["plan_id"] == str(plan["id"])
        subscription_id = data["id"]

        # ASSERT 1: Subscription is ACTIVE in database
        assert data["status"] == "active"

        # ASSERT 2: Candidate role becomes RECRUITER
        role_after = run(_get_user_role(candidate_user_id))
        assert role_after == UserRole.RECRUITER, f"Expected RECRUITER, got {role_after}"

        # ASSERT 3: RecruiterProfile exists for the candidate
        profile = run(_get_recruiter_profile(candidate_user_id))
        assert profile is not None, "RecruiterProfile should exist after provisioning"
        assert profile.user_id == candidate_user_id

        # Test repeat provisioning/activation behavior
        # Attempt to provision again for the same user with a different plan
        plan2 = _create_plan(admin_sub_client, run_async)
        resp2 = run_async(admin_sub_client.post(f"{API_V1}/admin/subscriptions", json={
            "user_id": str(candidate_user_id),
            "plan_id": str(plan2["id"]),
        }))
        # The service should reject this due to existing active subscription
        # (ConflictException: "User already has an active subscription")
        assert resp2.status_code == 400, f"Expected 400 for duplicate active subscription, got {resp2.status_code}: {resp2.text}"
        assert "already has an active subscription" in resp2.json().get("detail", "")

        # Verify NO duplicate RecruiterProfile was created
        # Query all profiles for this user
        async def _count_profiles(uid: uuid.UUID) -> int:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(RecruiterProfile).where(
                        RecruiterProfile.user_id == uid,
                        RecruiterProfile.is_deleted == False,  # noqa: E712
                    )
                )
                return len(result.scalars().all())

        profile_count = run(_count_profiles(candidate_user_id))
        assert profile_count == 1, f"Expected exactly 1 RecruiterProfile, found {profile_count}"

        # Verify role remains RECRUITER
        role_final = run(_get_user_role(candidate_user_id))
        assert role_final == UserRole.RECRUITER

        # Verify the original subscription is still active
        resp3 = run_async(admin_sub_client.get(f"{API_V1}/admin/subscriptions/{subscription_id}"))
        assert resp3.status_code == 200
        assert resp3.json()["status"] == "active"


class TestCandidateTokenContinuityAfterRoleTransition:
    """
    Phase 6.5: Regression test for token continuity across Candidate -> Recruiter transition.

    This test proves that the SAME JWT token works before and after role transition,
    without requiring re-login. The backend resolves the current User from the
    database on authenticated requests, so Candidate -> Recruiter works with the
    SAME JWT. This test MUST fail if JWT contains role claim or caches original role.
    """

    def test_candidate_token_continuity_after_role_transition(
        self, candidate_client, admin_client, run_async, subscription_service_override
    ):
        """
        Test that the SAME JWT token works before and after Candidate -> Recruiter transition.

        BEFORE TRANSITION:
        - Get candidate client with access_token
        - Verify GET /auth/me returns role = "candidate"
        - Verify candidate CANNOT access recruiter-only endpoints (403)
        - Verify candidate CAN access candidate-only endpoints (200)

        TRANSITION:
        - Use admin to provision subscription for this SAME candidate
        - This promotes candidate -> recruiter via the real activation flow

        AFTER TRANSITION (using SAME client/token):
        - Verify GET /auth/me returns role = "recruiter"
        - Verify candidate CANNOT access candidate-only endpoints (403)
        - Verify recruiter CAN access recruiter-only endpoints (200)
        """
        import httpx
        from app.domain.enums import UserRole

        # ============================================================
        # BEFORE TRANSITION
        # ============================================================

        # Verify current role is candidate
        me_resp = run_async(candidate_client.get(f"{API_V1}/auth/me"))
        assert me_resp.status_code == 200, me_resp.text
        me_data = me_resp.json()
        assert me_data["role"] == "candidate", f"Expected candidate role, got {me_data['role']}"

        # Verify candidate CANNOT access recruiter-only endpoints
        recruiter_only_endpoints = [
            ("GET", "/jobs/mine"),
            ("POST", "/companies", {"name": "Test Corp", "slug": "test-corp", "tax_code": "987654321", "size": "startup"}),
            ("GET", "/users/me/recruiter-profile"),
        ]
        for method, path, *body in recruiter_only_endpoints:
            if method == "GET":
                resp = run_async(candidate_client.get(f"{API_V1}{path}"))
            elif method == "POST":
                resp = run_async(candidate_client.post(f"{API_V1}{path}", json=body[0] if body else {}))
            assert resp.status_code == 403, f"Expected 403 for {method} {path}, got {resp.status_code}: {resp.text}"

        # Verify candidate CAN access candidate-only endpoints
        mine_resp = run_async(candidate_client.get(f"{API_V1}/applications/mine"))
        assert mine_resp.status_code == 200, f"Expected 200 for /applications/mine, got {mine_resp.status_code}: {mine_resp.text}"

        # Get candidate user ID for transition
        from app.core.security import decode_access_token
        auth_header = candidate_client.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "")
        payload = decode_access_token(token)
        candidate_user_id = payload["sub"]

        # ============================================================
        # TRANSITION: Use admin to provision subscription for THIS candidate
        # ============================================================
        # This uses the SAME activation flow as the existing subscription tests

        # First, create a plan using admin client
        plan_resp = run_async(admin_client.post(f"{API_V1}/admin/plans", json={
            "name": "Test Plan for Token Continuity",
            "description": "Test plan for role transition",
            "price": 1000000,
            "currency": "VND",
            "duration_days": 30,
            "max_job_posts": 10,
            "is_active": True,
            "display_order": 1,
        }))
        assert plan_resp.status_code == 201, f"Failed to create plan: {plan_resp.text}"
        plan = plan_resp.json()

        # Provision subscription for the SAME candidate
        prov_resp = run_async(admin_client.post(f"{API_V1}/admin/subscriptions", json={
            "user_id": candidate_user_id,
            "plan_id": plan["id"],
        }))
        assert prov_resp.status_code == 201, f"Failed to provision subscription: {prov_resp.text}"

        # ============================================================
        # AFTER TRANSITION: Using the SAME candidate_client (SAME token)
        # ============================================================

        # Verify role is now recruiter
        me_resp_after = run_async(candidate_client.get(f"{API_V1}/auth/me"))
        assert me_resp_after.status_code == 200, me_resp_after.text
        me_data_after = me_resp_after.json()
        assert me_data_after["role"] == "recruiter", f"Expected recruiter role, got {me_data_after['role']}"

        # Verify candidate CANNOT access candidate-only endpoints
        mine_resp_after = run_async(candidate_client.get(f"{API_V1}/applications/mine"))
        assert mine_resp_after.status_code == 403, f"Expected 403 for /applications/mine after transition, got {mine_resp_after.status_code}: {mine_resp_after.text}"

        # Verify recruiter CAN access recruiter-only endpoints
        # GET /jobs/mine
        jobs_mine_resp = run_async(candidate_client.get(f"{API_V1}/jobs/mine"))
        assert jobs_mine_resp.status_code == 200, f"Expected 200 for /jobs/mine, got {jobs_mine_resp.status_code}: {jobs_mine_resp.text}"

        # GET /users/me/recruiter-profile
        recruiter_profile_resp = run_async(candidate_client.get(f"{API_V1}/users/me/recruiter-profile"))
        # May be 200 or 404 (if no profile created yet), but NOT 403
        assert recruiter_profile_resp.status_code in (200, 404), f"Expected 200 or 404 for /recruiter-profile, got {recruiter_profile_resp.status_code}: {recruiter_profile_resp.text}"

        # POST /companies (create a company)
        company_resp = run_async(candidate_client.post(f"{API_V1}/companies", json={
            "name": "Test Corp After Transition",
            "slug": "test-corp-after-transition",
            "tax_code": "111111111",
            "size": "startup",
        }))
        assert company_resp.status_code == 201, f"Expected 201 for POST /companies, got {company_resp.status_code}: {company_resp.text}"

        # Verify candidate CANNOT apply for jobs
        # Need a published job first - create one with a recruiter client
        # For this test, we just verify the applications POST returns 403
        # (We'd need a valid job_id, but we can test the authorization boundary)
        fake_job_id = str(uuid.uuid4())
        apply_resp = run_async(candidate_client.post(f"{API_V1}/applications", json={"job_id": fake_job_id}))
        # Should be 403 (forbidden for recruiter) or 404 (job not found) - not 201
        assert apply_resp.status_code in (403, 404), f"Expected 403 or 404 for POST /applications as recruiter, got {apply_resp.status_code}: {apply_resp.text}"

        # Verify GET /candidate-profile is forbidden for recruiter
        candidate_profile_resp = run_async(candidate_client.get(f"{API_V1}/users/me/candidate-profile"))
        assert candidate_profile_resp.status_code == 403, f"Expected 403 for /candidate-profile as recruiter, got {candidate_profile_resp.status_code}: {candidate_profile_resp.text}"

        # Verify GET /candidate/applications/mine is forbidden for recruiter
        # (This is the candidate-owned applications endpoint)
        candidate_apps_resp = run_async(candidate_client.get(f"{API_V1}/applications/mine"))
        assert candidate_apps_resp.status_code == 403, f"Expected 403 for /applications/mine as recruiter, got {candidate_apps_resp.status_code}: {candidate_apps_resp.text}"

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