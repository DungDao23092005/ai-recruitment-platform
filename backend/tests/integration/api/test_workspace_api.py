"""End-to-end SQL Server/API coverage for company workspaces and invitations."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select

from app.database.session import async_session_factory
from app.main import app
from app.models import EmailOutbox
from tests.integration.api.conftest import API_V1, PASSWORD

pytestmark = pytest.mark.integration

COMPANY_BODY = {
    "name": "Workspace Co",
    "slug": "workspace-co",
    "tax_code": "987654321",
    "size": "startup",
}


def _register_and_login(client, run_async, email: str) -> httpx.AsyncClient:
    register = run_async(
        client.post(
            f"{API_V1}/auth/register",
            json={"email": email, "password": PASSWORD, "role": "recruiter"},
        )
    )
    assert register.status_code == 201, register.text
    login = run_async(
        client.post(
            f"{API_V1}/auth/login",
            data={"username": email, "password": PASSWORD},
        )
    )
    assert login.status_code == 200, login.text
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={
            "Authorization": f"Bearer {login.json()['access_token']}"
        },
    )


def _invitation_token(run_async, email: str) -> str:
    async def _load() -> str:
        async with async_session_factory() as session:
            outbox = await session.scalar(
                select(EmailOutbox)
                .where(EmailOutbox.to_email == email)
                .order_by(EmailOutbox.created_at.desc())
            )
            assert outbox is not None
            return outbox.text_body.split("#token=", 1)[1].splitlines()[0]

    return run_async(_load())


def _create_company(recruiter_client, run_async) -> dict:
    response = run_async(
        recruiter_client.post(f"{API_V1}/companies", json=COMPANY_BODY)
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestWorkspaceInvitationFlow:
    def test_full_invitation_acceptance_and_admin_guards(
        self, client, recruiter_client, run_async
    ):
        company = _create_company(recruiter_client, run_async)
        invitee_email = f"invitee-{uuid.uuid4()}@example.com"
        invitee = _register_and_login(client, run_async, invitee_email)

        created = run_async(
            recruiter_client.post(
                f"{API_V1}/workspaces/invitations",
                json={"email": invitee_email, "role": "recruiter"},
            )
        )
        assert created.status_code == 201, created.text
        assert created.json()["status"] == "pending"
        assert "token" not in created.text.lower()

        token = _invitation_token(run_async, invitee_email)
        preview = run_async(
            client.post(
                f"{API_V1}/invitations/preview", json={"token": token}
            )
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["company_slug"] == company["slug"]
        assert preview.json()["can_accept"] is True

        accepted = run_async(
            invitee.post(
                f"{API_V1}/invitations/accept", json={"token": token}
            )
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["workspace"]["company_id"] == company["id"]

        replay = run_async(
            invitee.post(
                f"{API_V1}/invitations/accept", json={"token": token}
            )
        )
        assert replay.status_code == 409

        members = run_async(
            recruiter_client.get(
                f"{API_V1}/workspaces/members",
                headers={"X-Company-ID": company["id"]},
            )
        )
        assert members.status_code == 200, members.text
        member_by_email = {
            member["email"]: member for member in members.json()
        }
        assert invitee_email in member_by_email

        cross_company = run_async(
            recruiter_client.get(
                f"{API_V1}/workspaces/members",
                headers={"X-Company-ID": str(uuid.uuid4())},
            )
        )
        assert cross_company.status_code == 403

        non_admin_invite = run_async(
            invitee.post(
                f"{API_V1}/workspaces/invitations",
                headers={"X-Company-ID": company["id"]},
                json={
                    "email": f"other-{uuid.uuid4()}@example.com",
                    "role": "recruiter",
                },
            )
        )
        assert non_admin_invite.status_code == 403

        owner_membership_id = next(
            member["membership_id"]
            for member in members.json()
            if member["role"] == "admin"
        )
        last_admin = run_async(
            recruiter_client.delete(
                f"{API_V1}/workspaces/members/{owner_membership_id}",
                headers={"X-Company-ID": company["id"]},
            )
        )
        assert last_admin.status_code == 409
        run_async(invitee.aclose())

    def test_admin_can_change_member_role_and_guards_last_admin(
        self, client, recruiter_client, run_async
    ):
        company = _create_company(recruiter_client, run_async)
        invitee_email = f"interviewer-{uuid.uuid4()}@example.com"
        invitee = _register_and_login(client, run_async, invitee_email)

        created = run_async(
            recruiter_client.post(
                f"{API_V1}/workspaces/invitations",
                json={"email": invitee_email, "role": "interviewer"},
            )
        )
        assert created.status_code == 201, created.text
        assert created.json()["role"] == "interviewer"
        token = _invitation_token(run_async, invitee_email)
        accepted = run_async(
            invitee.post(
                f"{API_V1}/invitations/accept", json={"token": token}
            )
        )
        assert accepted.status_code == 200, accepted.text

        members = run_async(
            recruiter_client.get(
                f"{API_V1}/workspaces/members",
                headers={"X-Company-ID": company["id"]},
            )
        )
        assert members.status_code == 200, members.text
        interviewer = next(
            member
            for member in members.json()
            if member["email"] == invitee_email
        )

        promoted = run_async(
            recruiter_client.patch(
                f"{API_V1}/workspaces/members/{interviewer['membership_id']}/role",
                headers={"X-Company-ID": company["id"]},
                json={"role": "admin"},
            )
        )
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["role"] == "admin"

        demoted = run_async(
            recruiter_client.patch(
                f"{API_V1}/workspaces/members/{interviewer['membership_id']}/role",
                headers={"X-Company-ID": company["id"]},
                json={"role": "interviewer"},
            )
        )
        assert demoted.status_code == 200, demoted.text
        assert demoted.json()["role"] == "interviewer"

        non_admin_attempt = run_async(
            invitee.patch(
                f"{API_V1}/workspaces/members/{interviewer['membership_id']}/role",
                headers={"X-Company-ID": company["id"]},
                json={"role": "admin"},
            )
        )
        assert non_admin_attempt.status_code == 403
        run_async(invitee.aclose())

    def test_revoked_invitation_cannot_be_accepted(
        self, client, recruiter_client, run_async
    ):
        company = _create_company(recruiter_client, run_async)
        invitee_email = f"revoked-{uuid.uuid4()}@example.com"
        invitee = _register_and_login(client, run_async, invitee_email)

        created = run_async(
            recruiter_client.post(
                f"{API_V1}/workspaces/invitations",
                json={"email": invitee_email, "role": "recruiter"},
            )
        )
        assert created.status_code == 201, created.text
        invitation_id = created.json()["id"]
        token = _invitation_token(run_async, invitee_email)

        revoked = run_async(
            recruiter_client.post(
                f"{API_V1}/workspaces/invitations/{invitation_id}/revoke",
                headers={"X-Company-ID": company["id"]},
            )
        )
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["status"] == "revoked"

        replay = run_async(
            invitee.post(
                f"{API_V1}/invitations/accept", json={"token": token}
            )
        )
        assert replay.status_code == 409
        run_async(invitee.aclose())

    def test_wrong_email_cannot_accept(
        self, client, recruiter_client, run_async
    ):
        _create_company(recruiter_client, run_async)
        invitee_email = f"intended-{uuid.uuid4()}@example.com"
        wrong_email = f"wrong-{uuid.uuid4()}@example.com"
        wrong_user = _register_and_login(client, run_async, wrong_email)

        created = run_async(
            recruiter_client.post(
                f"{API_V1}/workspaces/invitations",
                json={"email": invitee_email, "role": "recruiter"},
            )
        )
        assert created.status_code == 201, created.text
        token = _invitation_token(run_async, invitee_email)

        response = run_async(
            wrong_user.post(
                f"{API_V1}/invitations/accept", json={"token": token}
            )
        )
        assert response.status_code == 403
        run_async(wrong_user.aclose())


# ============================================================================
# Wave 1.4 Phase 2: Workspace Authorization & Header Validation (P71)
# ============================================================================

from app.domain.enums import MembershipRole, MembershipStatus
from app.models import Subscription
from tests.integration import company_billing_helpers as cbh


def test_p71_invalid_or_unauthorized_supplied_x_company_id_returns_400_or_403(
    run_async,
):
    """P71: Supplied invalid, unknown, revoked, or unauthorized X-Company-ID returns 400/403 and never falls back to personal quota."""
    async def _run():
        async with async_session_factory() as session:
            user = await cbh._create_user(session)
            comp_unauth = await cbh._create_company(session)
            comp_revoked = await cbh._create_company(session)
            await cbh._create_membership(
                session,
                company_id=comp_revoked.id,
                user_id=user.id,
                role=MembershipRole.RECRUITER,
                status=MembershipStatus.REVOKED,
            )
            plan = await cbh._create_plan(session, max_job_posts=5)
            sub = await cbh._create_personal_subscription(
                session, user_id=user.id, plan_id=plan.id
            )
            await session.commit()
            sub_id = sub.id
            comp_unauth_id = comp_unauth.id
            comp_revoked_id = comp_revoked.id
            unknown_company_id = uuid.uuid4()

        client = await cbh._make_jwt_client_for_user(user)
        try:
            job_payload = {
                "title": "Header Validation Job",
                "description": "Desc",
                "job_type": "full_time",
                "workplace_type": "remote",
                "status": "draft",
            }
            # 1. Non-UUID malformed header -> 400
            resp_inv = await client.post(
                f"{API_V1}/jobs",
                headers={"X-Company-ID": "invalid-uuid-string"},
                json=job_payload,
            )
            assert resp_inv.status_code == 400

            # 2. Unknown / nonexistent company UUID header -> 403 or 404
            resp_unk = await client.post(
                f"{API_V1}/jobs",
                headers={"X-Company-ID": str(unknown_company_id)},
                json=job_payload,
            )
            assert resp_unk.status_code in (400, 403, 404)

            # 3. Unauthorized company UUID header (no membership) -> 403
            resp_unauth = await client.post(
                f"{API_V1}/jobs",
                headers={"X-Company-ID": str(comp_unauth_id)},
                json=job_payload,
            )
            assert resp_unauth.status_code == 403

            # 4. Revoked company membership UUID header -> 403
            resp_rev = await client.post(
                f"{API_V1}/jobs",
                headers={"X-Company-ID": str(comp_revoked_id)},
                json=job_payload,
            )
            assert resp_rev.status_code == 403
        finally:
            await client.aclose()

        # In all cases, never fall back to consuming personal quota
        async with async_session_factory() as check:
            s = await check.get(Subscription, sub_id)
            assert s.job_posts_used == 0

    run_async(_run())
