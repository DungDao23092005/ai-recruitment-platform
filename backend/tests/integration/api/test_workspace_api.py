"""End-to-end SQL Server/API coverage for company workspaces and invitations."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.database.base_class import utc_now
from app.database.session import async_session_factory
from app.domain.enums import InvitationStatus, MembershipRole, MembershipStatus
from app.main import app
from app.models import CompanyInvitation, CompanyMembership, EmailOutbox, User
from app.services.workspace_service import hash_invitation_token
from tests.integration.api.conftest import API_V1, PASSWORD

pytestmark = pytest.mark.integration

COMPANY_BODY = {
    "name": "Workspace Co",
    "slug": "workspace-co",
    "tax_code": "987654321",
    "size": "startup",
}


def _register_and_login(
    client, run_async, email: str, role: str = "recruiter"
) -> httpx.AsyncClient:
    register = run_async(
        client.post(
            f"{API_V1}/auth/register",
            json={"email": email, "password": PASSWORD, "role": role},
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
            raw = outbox.text_body.split("#token=", 1)[1].splitlines()[0]
            return raw.split("&", 1)[0]

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
        intended_user = _register_and_login(client, run_async, invitee_email)
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
        run_async(intended_user.aclose())

    def test_in_app_discovery_and_accept_cross_channel(
        self, client, recruiter_client, run_async
    ):
        company = _create_company(recruiter_client, run_async)
        invitee_email = f"inapp-accept-{uuid.uuid4()}@example.com"
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

        # 1. Discover in-app
        mine = run_async(invitee.get(f"{API_V1}/workspaces/invitations/mine"))
        assert mine.status_code == 200, mine.text
        items = mine.json()
        assert len(items) == 1
        assert items[0]["id"] == invitation_id
        assert items[0]["company_id"] == company["id"]
        assert items[0]["role"] == "recruiter"
        assert items[0]["can_accept"] is True

        # 2. Accept in-app
        accepted = run_async(
            invitee.post(f"{API_V1}/workspaces/invitations/{invitation_id}/accept")
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["workspace"]["company_id"] == company["id"]

        # 3. In-app list is now empty
        mine_after = run_async(invitee.get(f"{API_V1}/workspaces/invitations/mine"))
        assert mine_after.status_code == 200
        assert len(mine_after.json()) == 0

        # 4. Cross-channel replay: email accept returns 409 Conflict
        email_accept_replay = run_async(
            invitee.post(f"{API_V1}/invitations/accept", json={"token": token})
        )
        assert email_accept_replay.status_code == 409

        # 5. Cross-channel replay: email decline returns 409 Conflict
        email_decline_replay = run_async(
            invitee.post(f"{API_V1}/invitations/decline", json={"token": token})
        )
        assert email_decline_replay.status_code == 409
        run_async(invitee.aclose())

    def test_in_app_discovery_and_decline_cross_channel(
        self, client, recruiter_client, run_async
    ):
        company = _create_company(recruiter_client, run_async)
        invitee_email = f"inapp-decline-{uuid.uuid4()}@example.com"
        invitee = _register_and_login(client, run_async, invitee_email)

        created = run_async(
            recruiter_client.post(
                f"{API_V1}/workspaces/invitations",
                json={"email": invitee_email, "role": "interviewer"},
            )
        )
        assert created.status_code == 201, created.text
        invitation_id = created.json()["id"]
        token = _invitation_token(run_async, invitee_email)

        # 1. Discover in-app
        mine = run_async(invitee.get(f"{API_V1}/workspaces/invitations/mine"))
        assert mine.status_code == 200
        assert len(mine.json()) == 1

        # 2. Decline in-app
        declined = run_async(
            invitee.post(f"{API_V1}/workspaces/invitations/{invitation_id}/decline")
        )
        assert declined.status_code == 200, declined.text
        assert declined.json()["status"] == "declined"

        # 3. In-app list is now empty
        mine_after = run_async(invitee.get(f"{API_V1}/workspaces/invitations/mine"))
        assert mine_after.status_code == 200
        assert len(mine_after.json()) == 0

        # 4. Cross-channel replay: email accept returns 409 Conflict
        email_accept_replay = run_async(
            invitee.post(f"{API_V1}/invitations/accept", json={"token": token})
        )
        assert email_accept_replay.status_code == 409

        # 5. Cross-channel replay: email decline returns 409 Conflict
        email_decline_replay = run_async(
            invitee.post(f"{API_V1}/invitations/decline", json={"token": token})
        )
        assert email_decline_replay.status_code == 409
        run_async(invitee.aclose())

    def test_email_decline_cross_channel_consistency(
        self, client, recruiter_client, run_async
    ):
        company = _create_company(recruiter_client, run_async)
        invitee_email = f"email-decline-{uuid.uuid4()}@example.com"
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

        # Decline via email endpoint
        decline_resp = run_async(
            invitee.post(f"{API_V1}/invitations/decline", json={"token": token})
        )
        assert decline_resp.status_code == 200, decline_resp.text
        assert decline_resp.json()["status"] == "declined"

        # In-app discovery is empty
        mine = run_async(invitee.get(f"{API_V1}/workspaces/invitations/mine"))
        assert mine.status_code == 200
        assert len(mine.json()) == 0

        # In-app accept attempt returns 409 Conflict
        inapp_accept = run_async(
            invitee.post(f"{API_V1}/workspaces/invitations/{invitation_id}/accept")
        )
        assert inapp_accept.status_code == 409
        run_async(invitee.aclose())

    def test_newly_registered_recipient_receives_in_app_notification(
        self, client, recruiter_client, run_async
    ):
        company = _create_company(recruiter_client, run_async)
        invitee_email = f"newly-registered-{uuid.uuid4()}@example.com"
        me_resp = run_async(recruiter_client.get(f"{API_V1}/auth/me"))
        assert me_resp.status_code == 200, me_resp.text
        recruiter_user_id = uuid.UUID(me_resp.json()["id"])

        # 1. Historical pre-existing invitation seeded in database before recipient registered
        async def _seed_invitation():
            async with async_session_factory() as session:
                inv = CompanyInvitation(
                    company_id=uuid.UUID(company["id"]),
                    email=invitee_email,
                    role=MembershipRole.RECRUITER,
                    token_hash=hash_invitation_token("preexisting-token"),
                    status=InvitationStatus.PENDING,
                    invited_by_id=recruiter_user_id,
                    expires_at=utc_now() + timedelta(days=7),
                )
                session.add(inv)
                await session.commit()
                return str(inv.id)

        invitation_id = run_async(_seed_invitation())

        # 2. Recipient registers and logs in
        invitee = _register_and_login(client, run_async, invitee_email)

        # 3. Recipient discovers invitation in-app
        mine = run_async(invitee.get(f"{API_V1}/workspaces/invitations/mine"))
        assert mine.status_code == 200, mine.text
        items = mine.json()
        assert len(items) == 1
        assert items[0]["id"] == invitation_id

        # 4. In-app notification was created during registration
        notifs = run_async(invitee.get(f"{API_V1}/notifications"))
        assert notifs.status_code == 200, notifs.text
        invitation_notifs = [
            n for n in notifs.json() if n.get("notification_type") == "company_invitation"
        ]
        assert len(invitation_notifs) == 1
        assert invitation_notifs[0]["is_read"] is False

        # 5. Accepting marks notification read
        accept_resp = run_async(
            invitee.post(f"{API_V1}/workspaces/invitations/{invitation_id}/accept")
        )
        assert accept_resp.status_code == 200, accept_resp.text

        notifs_after = run_async(invitee.get(f"{API_V1}/notifications"))
        assert notifs_after.status_code == 200
        invitation_notifs_after = [
            n for n in notifs_after.json() if n.get("notification_type") == "company_invitation"
        ]
        assert len(invitation_notifs_after) == 1
        assert invitation_notifs_after[0]["is_read"] is True
        run_async(invitee.aclose())

    def test_company_admin_receives_notification_when_member_joins(
        self, client, recruiter_client, run_async
    ):
        company = _create_company(recruiter_client, run_async)
        invitee_email = f"joining-member-{uuid.uuid4()}@example.com"
        invitee = _register_and_login(client, run_async, invitee_email)

        # 1. Admin creates invitation
        created = run_async(
            recruiter_client.post(
                f"{API_V1}/workspaces/invitations",
                json={"email": invitee_email, "role": "recruiter"},
            )
        )
        assert created.status_code == 201, created.text
        invitation_id = created.json()["id"]

        # 2. Invitee accepts invitation
        accept_resp = run_async(
            invitee.post(f"{API_V1}/workspaces/invitations/{invitation_id}/accept")
        )
        assert accept_resp.status_code == 200, accept_resp.text
        membership_id = accept_resp.json()["membership_id"]

        # 3. Company administrator retrieves the notification
        admin_notifs = run_async(recruiter_client.get(f"{API_V1}/notifications"))
        assert admin_notifs.status_code == 200, admin_notifs.text
        joined_notifs = [
            n
            for n in admin_notifs.json()
            if n.get("notification_type") == "company_member_joined"
        ]
        assert len(joined_notifs) == 1
        notif = joined_notifs[0]
        assert notif["entity_type"] == "company_membership"
        assert notif["entity_id"] == membership_id
        assert notif["is_read"] is False
        assert invitee_email in notif["content"]
        assert company["name"] in notif["content"]

        # 4. Joining user does not receive self-notification
        invitee_notifs = run_async(invitee.get(f"{API_V1}/notifications"))
        assert invitee_notifs.status_code == 200
        assert not any(
            n.get("notification_type") == "company_member_joined"
            for n in invitee_notifs.json()
        )

        run_async(invitee.aclose())

    def test_admin_revokes_member_and_subsequent_request_with_company_context_returns_403(
        self, client, recruiter_client, run_async
    ):
        company = _create_company(recruiter_client, run_async)
        member_email = f"member-to-revoke-{uuid.uuid4()}@example.com"
        member_client = _register_and_login(client, run_async, member_email)

        # 1. Admin invites member
        created = run_async(
            recruiter_client.post(
                f"{API_V1}/workspaces/invitations",
                json={"email": member_email, "role": "recruiter"},
            )
        )
        assert created.status_code == 201, created.text
        invitation_id = created.json()["id"]

        # 2. Member accepts invitation
        accept_resp = run_async(
            member_client.post(
                f"{API_V1}/workspaces/invitations/{invitation_id}/accept"
            )
        )
        assert accept_resp.status_code == 200, accept_resp.text
        membership_id = accept_resp.json()["membership_id"]

        # 3. Member can access company workspace endpoints
        access_resp = run_async(
            member_client.get(
                f"{API_V1}/workspaces/members",
                headers={"X-Company-ID": company["id"]},
            )
        )
        assert access_resp.status_code == 200, access_resp.text

        # 4. Admin revokes member
        revoke_resp = run_async(
            recruiter_client.delete(
                f"{API_V1}/workspaces/members/{membership_id}",
                headers={"X-Company-ID": company["id"]},
            )
        )
        assert revoke_resp.status_code == 204, revoke_resp.text

        # 5. Subsequent request with company context returns 403 Forbidden
        subsequent = run_async(
            member_client.get(
                f"{API_V1}/workspaces/members",
                headers={"X-Company-ID": company["id"]},
            )
        )
        assert subsequent.status_code == 403, subsequent.text
        run_async(member_client.aclose())

    def test_invitation_revocation_marks_recipient_notification_read_and_prevents_subsequent_accept(
        self, client, recruiter_client, run_async
    ):
        company = _create_company(recruiter_client, run_async)
        invitee_email = f"invitee-revocation-{uuid.uuid4()}@example.com"
        invitee = _register_and_login(client, run_async, invitee_email)

        # 1. Admin invites existing registered user
        created = run_async(
            recruiter_client.post(
                f"{API_V1}/workspaces/invitations",
                json={"email": invitee_email, "role": "recruiter"},
            )
        )
        assert created.status_code == 201, created.text
        invitation_id = created.json()["id"]

        # 2. Verify recipient receives unread in-app notification
        notifs_before = run_async(invitee.get(f"{API_V1}/notifications"))
        assert notifs_before.status_code == 200, notifs_before.text
        invitation_notifs_before = [
            n
            for n in notifs_before.json()
            if n.get("notification_type") == "company_invitation"
            and n.get("entity_id") == invitation_id
        ]
        assert len(invitation_notifs_before) == 1
        assert invitation_notifs_before[0]["is_read"] is False

        # 3. Admin revokes invitation
        revoke_resp = run_async(
            recruiter_client.post(
                f"{API_V1}/workspaces/invitations/{invitation_id}/revoke",
                headers={"X-Company-ID": company["id"]},
            )
        )
        assert revoke_resp.status_code == 200, revoke_resp.text
        assert revoke_resp.json()["status"] == "revoked"

        # 4. Verify recipient notification is marked as read
        notifs_after = run_async(invitee.get(f"{API_V1}/notifications"))
        assert notifs_after.status_code == 200, notifs_after.text
        invitation_notifs_after = [
            n
            for n in notifs_after.json()
            if n.get("notification_type") == "company_invitation"
            and n.get("entity_id") == invitation_id
        ]
        assert len(invitation_notifs_after) == 1
        assert invitation_notifs_after[0]["is_read"] is True

        # 5. Subsequent in-app accept attempt returns 409 Conflict
        accept_resp = run_async(
            invitee.post(
                f"{API_V1}/workspaces/invitations/{invitation_id}/accept"
            )
        )
        assert accept_resp.status_code == 409, accept_resp.text
        run_async(invitee.aclose())

    def test_admin_invitation_to_unknown_email_returns_404_and_persists_nothing(
        self, recruiter_client, run_async
    ):
        company = _create_company(recruiter_client, run_async)
        unknown_email = f"unknown-{uuid.uuid4()}@example.com"

        resp = run_async(
            recruiter_client.post(
                f"{API_V1}/workspaces/invitations",
                json={"email": unknown_email, "role": "recruiter"},
            )
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"] == "Tài khoản với email này không tồn tại trong hệ thống."

        async def _check_db():
            async with async_session_factory() as session:
                inv = await session.scalar(
                    select(CompanyInvitation).where(
                        CompanyInvitation.email == unknown_email
                    )
                )
                assert inv is None
                outbox = await session.scalar(
                    select(EmailOutbox).where(
                        EmailOutbox.to_email == unknown_email
                    )
                )
                assert outbox is None

        run_async(_check_db())

    def test_admin_invitation_to_inactive_account_returns_403(
        self, client, recruiter_client, run_async
    ):
        company = _create_company(recruiter_client, run_async)
        locked_email = f"locked-{uuid.uuid4()}@example.com"
        locked_client = _register_and_login(client, run_async, locked_email)

        async def _lock_account():
            async with async_session_factory() as session:
                user = await session.scalar(
                    select(User).where(User.email == locked_email)
                )
                assert user is not None
                user.is_active = False
                await session.commit()

        run_async(_lock_account())

        resp = run_async(
            recruiter_client.post(
                f"{API_V1}/workspaces/invitations",
                json={"email": locked_email, "role": "recruiter"},
            )
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Tài khoản này đang bị khóa và không thể nhận lời mời."

        async def _check_no_invitation():
            async with async_session_factory() as session:
                inv = await session.scalar(
                    select(CompanyInvitation).where(
                        CompanyInvitation.email == locked_email
                    )
                )
                assert inv is None

        run_async(_check_no_invitation())
        run_async(locked_client.aclose())

    def test_concurrent_accept_vs_decline(
        self, client, recruiter_client, run_async
    ):
        """Test 1: Concurrent Accept vs Decline on the same invitation.

        Two independent HTTP clients for the same invitee submit competing
        in-app accept and decline requests simultaneously against independent
        database sessions. Exactly one must succeed (200), the other must receive
        409 Conflict, and the database must transition to a single valid terminal state.
        """
        async def _run():
            comp_resp = await recruiter_client.post(
                f"{API_V1}/companies", json=COMPANY_BODY
            )
            assert comp_resp.status_code == 201, comp_resp.text
            company = comp_resp.json()
            company_id = uuid.UUID(company["id"])

            invitee_email = f"conc-acc-dec-{uuid.uuid4()}@example.com"
            reg_resp = await client.post(
                f"{API_V1}/auth/register",
                json={"email": invitee_email, "password": PASSWORD, "role": "recruiter"},
            )
            assert reg_resp.status_code == 201, reg_resp.text

            login_resp = await client.post(
                f"{API_V1}/auth/login",
                data={"username": invitee_email, "password": PASSWORD},
            )
            assert login_resp.status_code == 200, login_resp.text
            invitee_token = login_resp.json()["access_token"]

            async with async_session_factory() as session:
                user = await session.scalar(
                    select(User).where(User.email == invitee_email)
                )
                assert user is not None
                invitee_user_id = user.id

            create_resp = await recruiter_client.post(
                f"{API_V1}/workspaces/invitations",
                json={"email": invitee_email, "role": "recruiter"},
            )
            assert create_resp.status_code == 201, create_resp.text
            invitation_id = uuid.UUID(create_resp.json()["id"])

            client_accept = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {invitee_token}"},
            )
            client_decline = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {invitee_token}"},
            )

            barrier = asyncio.Barrier(2)

            async def _call_accept():
                await barrier.wait()
                return await client_accept.post(
                    f"{API_V1}/workspaces/invitations/{invitation_id}/accept"
                )

            async def _call_decline():
                await barrier.wait()
                return await client_decline.post(
                    f"{API_V1}/workspaces/invitations/{invitation_id}/decline"
                )

            try:
                resp_accept, resp_decline = await asyncio.gather(
                    _call_accept(), _call_decline()
                )
            finally:
                await client_accept.aclose()
                await client_decline.aclose()

            status_codes = {resp_accept.status_code, resp_decline.status_code}
            assert status_codes == {200, 409}, (
                f"Expected exactly one 200 and one 409, got accept={resp_accept.status_code}, decline={resp_decline.status_code}"
            )

            async with async_session_factory() as verify_session:
                invitation = await verify_session.get(CompanyInvitation, invitation_id)
                assert invitation is not None
                assert invitation.is_deleted is False

                memberships = (
                    await verify_session.execute(
                        select(CompanyMembership).where(
                            CompanyMembership.company_id == company_id,
                            CompanyMembership.user_id == invitee_user_id,
                            CompanyMembership.is_deleted == False,
                        )
                    )
                ).scalars().all()

                if resp_accept.status_code == 200:
                    assert invitation.status == InvitationStatus.ACCEPTED
                    assert invitation.accepted_at is not None
                    assert invitation.declined_at is None
                    assert len(memberships) == 1
                    assert memberships[0].status == MembershipStatus.ACTIVE
                    assert memberships[0].role == MembershipRole.RECRUITER
                else:
                    assert invitation.status == InvitationStatus.DECLINED
                    assert invitation.declined_at is not None
                    assert invitation.accepted_at is None
                    assert len(memberships) == 0

        run_async(_run())

    def test_concurrent_accept_vs_accept(
        self, client, recruiter_client, run_async
    ):
        """Test 2: Concurrent Accept vs Accept on the same invitation.

        Two independent HTTP clients for the same invitee submit competing
        in-app accept requests simultaneously against independent database sessions.
        Exactly one request succeeds (200), the other receives 409 Conflict,
        status becomes ACCEPTED, and exactly one active membership is created.
        """
        async def _run():
            comp_resp = await recruiter_client.post(
                f"{API_V1}/companies", json=COMPANY_BODY
            )
            assert comp_resp.status_code == 201, comp_resp.text
            company = comp_resp.json()
            company_id = uuid.UUID(company["id"])

            invitee_email = f"conc-acc-acc-{uuid.uuid4()}@example.com"
            reg_resp = await client.post(
                f"{API_V1}/auth/register",
                json={"email": invitee_email, "password": PASSWORD, "role": "recruiter"},
            )
            assert reg_resp.status_code == 201, reg_resp.text

            login_resp = await client.post(
                f"{API_V1}/auth/login",
                data={"username": invitee_email, "password": PASSWORD},
            )
            assert login_resp.status_code == 200, login_resp.text
            invitee_token = login_resp.json()["access_token"]

            async with async_session_factory() as session:
                user = await session.scalar(
                    select(User).where(User.email == invitee_email)
                )
                assert user is not None
                invitee_user_id = user.id

            create_resp = await recruiter_client.post(
                f"{API_V1}/workspaces/invitations",
                json={"email": invitee_email, "role": "interviewer"},
            )
            assert create_resp.status_code == 201, create_resp.text
            invitation_id = uuid.UUID(create_resp.json()["id"])

            client_1 = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {invitee_token}"},
            )
            client_2 = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {invitee_token}"},
            )

            barrier = asyncio.Barrier(2)

            async def _call_accept_1():
                await barrier.wait()
                return await client_1.post(
                    f"{API_V1}/workspaces/invitations/{invitation_id}/accept"
                )

            async def _call_accept_2():
                await barrier.wait()
                return await client_2.post(
                    f"{API_V1}/workspaces/invitations/{invitation_id}/accept"
                )

            try:
                resp_1, resp_2 = await asyncio.gather(
                    _call_accept_1(), _call_accept_2()
                )
            finally:
                await client_1.aclose()
                await client_2.aclose()

            status_codes = {resp_1.status_code, resp_2.status_code}
            assert status_codes == {200, 409}, (
                f"Expected exactly one 200 and one 409, got resp_1={resp_1.status_code}, resp_2={resp_2.status_code}"
            )

            async with async_session_factory() as verify_session:
                invitation = await verify_session.get(CompanyInvitation, invitation_id)
                assert invitation is not None
                assert invitation.status == InvitationStatus.ACCEPTED
                assert invitation.accepted_at is not None
                assert invitation.declined_at is None
                assert invitation.is_deleted is False

                memberships = (
                    await verify_session.execute(
                        select(CompanyMembership).where(
                            CompanyMembership.company_id == company_id,
                            CompanyMembership.user_id == invitee_user_id,
                            CompanyMembership.is_deleted == False,
                        )
                    )
                ).scalars().all()

                assert len(memberships) == 1
                assert memberships[0].status == MembershipStatus.ACTIVE
                assert memberships[0].role == MembershipRole.INTERVIEWER

        run_async(_run())

    def test_concurrent_admin_revoke_vs_user_accept(
        self, client, recruiter_client, run_async
    ):
        """Test 3: Concurrent Admin Revoke vs User Accept on the same invitation.

        An authorized workspace admin and the invitee submit competing revoke and accept
        requests simultaneously against independent database sessions. Exactly one must
        succeed (200) and the loser must receive 409 Conflict. The final invitation state
        matches the winner (REVOKED with 0 memberships, or ACCEPTED with 1 membership).
        """
        async def _run():
            comp_resp = await recruiter_client.post(
                f"{API_V1}/companies", json=COMPANY_BODY
            )
            assert comp_resp.status_code == 201, comp_resp.text
            company = comp_resp.json()
            company_id = uuid.UUID(company["id"])

            invitee_email = f"conc-rev-acc-{uuid.uuid4()}@example.com"
            reg_resp = await client.post(
                f"{API_V1}/auth/register",
                json={"email": invitee_email, "password": PASSWORD, "role": "recruiter"},
            )
            assert reg_resp.status_code == 201, reg_resp.text

            login_resp = await client.post(
                f"{API_V1}/auth/login",
                data={"username": invitee_email, "password": PASSWORD},
            )
            assert login_resp.status_code == 200, login_resp.text
            invitee_token = login_resp.json()["access_token"]

            async with async_session_factory() as session:
                user = await session.scalar(
                    select(User).where(User.email == invitee_email)
                )
                assert user is not None
                invitee_user_id = user.id

            create_resp = await recruiter_client.post(
                f"{API_V1}/workspaces/invitations",
                json={"email": invitee_email, "role": "recruiter"},
            )
            assert create_resp.status_code == 201, create_resp.text
            invitation_id = uuid.UUID(create_resp.json()["id"])

            admin_auth_header = recruiter_client.headers.get("Authorization")
            assert admin_auth_header is not None

            admin_http_client = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers={
                    "Authorization": admin_auth_header,
                    "X-Company-ID": str(company_id),
                },
            )
            invitee_http_client = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {invitee_token}"},
            )

            barrier = asyncio.Barrier(2)

            async def _call_revoke():
                await barrier.wait()
                return await admin_http_client.post(
                    f"{API_V1}/workspaces/invitations/{invitation_id}/revoke"
                )

            async def _call_accept():
                await barrier.wait()
                return await invitee_http_client.post(
                    f"{API_V1}/workspaces/invitations/{invitation_id}/accept"
                )

            try:
                resp_revoke, resp_accept = await asyncio.gather(
                    _call_revoke(), _call_accept()
                )
            finally:
                await admin_http_client.aclose()
                await invitee_http_client.aclose()

            status_codes = {resp_revoke.status_code, resp_accept.status_code}
            assert status_codes == {200, 409}, (
                f"Expected exactly one 200 and one 409, got revoke={resp_revoke.status_code}, accept={resp_accept.status_code}"
            )

            async with async_session_factory() as verify_session:
                invitation = await verify_session.get(CompanyInvitation, invitation_id)
                assert invitation is not None
                assert invitation.is_deleted is False

                memberships = (
                    await verify_session.execute(
                        select(CompanyMembership).where(
                            CompanyMembership.company_id == company_id,
                            CompanyMembership.user_id == invitee_user_id,
                            CompanyMembership.is_deleted == False,
                        )
                    )
                ).scalars().all()

                if resp_revoke.status_code == 200:
                    assert invitation.status == InvitationStatus.REVOKED
                    assert invitation.revoked_at is not None
                    assert invitation.accepted_at is None
                    assert len(memberships) == 0
                else:
                    assert invitation.status == InvitationStatus.ACCEPTED
                    assert invitation.accepted_at is not None
                    assert invitation.revoked_at is None
                    assert len(memberships) == 1
                    assert memberships[0].status == MembershipStatus.ACTIVE
                    assert memberships[0].role == MembershipRole.RECRUITER

        run_async(_run())


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


class TestCandidateWorkspaceRestriction:
    def test_candidate_cannot_be_invited_to_workspace(
        self, client, recruiter_client, run_async
    ):
        company = _create_company(recruiter_client, run_async)
        candidate_email = f"candidate-{uuid.uuid4()}@example.com"
        _register_and_login(client, run_async, candidate_email, role="candidate")

        # Recruiter tries to invite candidate
        invite_resp = run_async(
            recruiter_client.post(
                f"{API_V1}/workspaces/invitations",
                headers={"X-Company-ID": company["id"]},
                json={"email": candidate_email, "role": "recruiter"},
            )
        )
        assert invite_resp.status_code == 403
        assert (
            invite_resp.json()["detail"]
            == "Không thể gửi lời mời. Tài khoản ứng viên không thể tham gia không gian làm việc của công ty. Chỉ tài khoản nhân sự công ty mới được mời."
        )

        # Confirm no invitation exists in database
        async def _check_db():
            async with async_session_factory() as session:
                inv = await session.scalar(
                    select(CompanyInvitation).where(
                        CompanyInvitation.email == candidate_email
                    )
                )
                assert inv is None

        run_async(_check_db())

    def test_candidate_cannot_accept_invitation_but_can_decline(
        self, client, recruiter_client, run_async
    ):
        company = _create_company(recruiter_client, run_async)
        candidate_email = f"candidate-accept-{uuid.uuid4()}@example.com"
        candidate_client = _register_and_login(
            client, run_async, candidate_email, role="candidate"
        )

        # Seed a pending invitation in DB directly (simulating pre-existing pending invite)
        token = f"token-{uuid.uuid4()}-{uuid.uuid4()}"
        token_hash = hash_invitation_token(token)

        async def _seed_invitation():
            async with async_session_factory() as session:
                recruiter_user = await session.scalar(
                    select(User).where(User.email.like("%recruiter%"))
                )
                inv = CompanyInvitation(
                    company_id=uuid.UUID(company["id"]),
                    email=candidate_email,
                    role=MembershipRole.RECRUITER,
                    token_hash=token_hash,
                    status=InvitationStatus.PENDING,
                    invited_by_id=recruiter_user.id if recruiter_user else uuid.uuid4(),
                    expires_at=utc_now() + timedelta(days=7),
                )
                session.add(inv)
                await session.commit()
                return inv.id

        invitation_id = run_async(_seed_invitation())

        # Candidate attempts to accept via token -> 403 Forbidden
        accept_resp = run_async(
            candidate_client.post(
                f"{API_V1}/invitations/accept",
                json={"token": token},
            )
        )
        assert accept_resp.status_code == 403
        assert (
            accept_resp.json()["detail"]
            == "Tài khoản ứng viên không thể tham gia không gian làm việc của công ty. Vui lòng sử dụng tài khoản dành cho nhân sự công ty."
        )

        # Verify invitation remains PENDING and no membership created
        async def _verify_still_pending():
            async with async_session_factory() as session:
                inv = await session.scalar(
                    select(CompanyInvitation).where(
                        CompanyInvitation.id == invitation_id
                    )
                )
                assert inv is not None
                assert inv.status == InvitationStatus.PENDING

                cand_user = await session.scalar(
                    select(User).where(User.email == candidate_email)
                )
                assert cand_user.role.value == "candidate"

                mem = await session.scalar(
                    select(CompanyMembership).where(
                        CompanyMembership.user_id == cand_user.id,
                        CompanyMembership.company_id == uuid.UUID(company["id"]),
                    )
                )
                assert mem is None

        run_async(_verify_still_pending())

        # Candidate declines invitation -> 200 OK
        decline_resp = run_async(
            candidate_client.post(
                f"{API_V1}/invitations/decline",
                json={"token": token},
            )
        )
        assert decline_resp.status_code == 200
        assert decline_resp.json()["status"] == "declined"

        # Verify invitation is DECLINED in DB and still no membership
        async def _verify_declined():
            async with async_session_factory() as session:
                inv = await session.scalar(
                    select(CompanyInvitation).where(
                        CompanyInvitation.id == invitation_id
                    )
                )
                assert inv is not None
                assert inv.status == InvitationStatus.DECLINED

                cand_user = await session.scalar(
                    select(User).where(User.email == candidate_email)
                )
                mem = await session.scalar(
                    select(CompanyMembership).where(
                        CompanyMembership.user_id == cand_user.id,
                        CompanyMembership.company_id == uuid.UUID(company["id"]),
                    )
                )
                assert mem is None

        run_async(_verify_declined())
