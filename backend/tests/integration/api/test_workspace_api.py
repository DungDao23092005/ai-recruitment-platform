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
