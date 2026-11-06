"""End-to-end coverage for interviewer assignments and access boundaries."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.database.session import async_session_factory
from app.main import app
from app.models import (
    CompanyMembership,
    EmailOutbox,
    InterviewAssignment,
    InterviewEvaluation,
    Resume,
)
from tests.integration.api.conftest import API_V1, PASSWORD, apply_job_with_resume

pytestmark = pytest.mark.integration

COMPANY_BODY = {
    "name": "Assignment Corp",
    "slug": "assignment-corp",
    "tax_code": "112233445",
    "size": "startup",
}

JOB_BODY = {
    "title": "Backend Engineer",
    "description": "Build reliable hiring services",
    "job_type": "full_time",
    "workplace_type": "remote",
    "location": "Ho Chi Minh",
    "status": "published",
}

RECRUITER_NOTES = "INTERNAL: compare against the panel rubric"


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
                .where(
                    EmailOutbox.to_email == email,
                    EmailOutbox.event_type == "company_invitation",
                )
                .order_by(EmailOutbox.created_at.desc())
            )
            assert outbox is not None
            return outbox.text_body.split("#token=", 1)[1].splitlines()[0]

    return run_async(_load())


def _invite_member(
    recruiter_client,
    client,
    run_async,
    company_id: str,
    role: str,
) -> tuple[httpx.AsyncClient, str]:
    email = f"{role}-{uuid.uuid4()}@example.com"
    invitee = _register_and_login(client, run_async, email)
    created = run_async(
        recruiter_client.post(
            f"{API_V1}/workspaces/invitations",
            headers={"X-Company-ID": company_id},
            json={"email": email, "role": role},
        )
    )
    assert created.status_code == 201, created.text
    token = _invitation_token(run_async, email)
    accepted = run_async(
        invitee.post(
            f"{API_V1}/invitations/accept", json={"token": token}
        )
    )
    assert accepted.status_code == 200, accepted.text
    return invitee, email


def _setup_application(recruiter_client, candidate_client, run_async):
    company = run_async(
        recruiter_client.post(f"{API_V1}/companies", json=COMPANY_BODY)
    )
    assert company.status_code == 201, company.text
    company_body = company.json()
    job = run_async(
        recruiter_client.post(
            f"{API_V1}/jobs",
            json={**JOB_BODY, "company_id": company_body["id"]},
        )
    )
    assert job.status_code == 201, job.text
    profile = run_async(
        candidate_client.post(
            f"{API_V1}/users/me/candidate-profile",
            json={
                "full_name": "Assigned Candidate",
                "title": "Engineer",
                "phone": "+84 912 345 678",
            },
        )
    )
    assert profile.status_code == 201, profile.text
    application = apply_job_with_resume(
        candidate_client, run_async, job.json()["id"]
    )
    assert application.status_code == 201, application.text
    return company_body, job.json(), application.json()


def _schedule_interview(recruiter_client, run_async, application_id: str) -> dict:
    response = run_async(
        recruiter_client.post(
            f"{API_V1}/applications/{application_id}/interviews",
            json={
                "scheduled_at": (
                    datetime.now(timezone.utc) + timedelta(days=2)
                ).isoformat(),
                "duration_minutes": 60,
                "interview_type": "technical",
                "location": "Room 3",
                "notes": RECRUITER_NOTES,
            },
        )
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestInterviewAssignmentAccess:
    def test_interviewer_only_sees_assigned_interviews(
        self, client, recruiter_client, candidate_client, run_async
    ):
        company, _, application = _setup_application(
            recruiter_client, candidate_client, run_async
        )
        first = _schedule_interview(recruiter_client, run_async, application["id"])
        second = _schedule_interview(recruiter_client, run_async, application["id"])
        interviewer, _ = _invite_member(
            recruiter_client,
            client,
            run_async,
            company["id"],
            "interviewer",
        )
        headers = {"X-Company-ID": company["id"]}
        try:
            members = run_async(
                recruiter_client.get(
                    f"{API_V1}/workspaces/members", headers=headers
                )
            )
            interviewer_member = next(
                member
                for member in members.json()
                if member["role"] == "interviewer"
            )

            assigned = run_async(
                recruiter_client.post(
                    f"{API_V1}/interviews/{first['id']}/assignments",
                    headers=headers,
                    json={"user_id": interviewer_member["user_id"]},
                )
            )
            assert assigned.status_code == 201, assigned.text

            mine = run_async(
                interviewer.get(f"{API_V1}/interviews/mine", headers=headers)
            )
            assert mine.status_code == 200, mine.text
            assert [item["id"] for item in mine.json()] == [first["id"]]
            assert "notes" not in mine.text

            detail = run_async(
                interviewer.get(
                    f"{API_V1}/interviews/{first['id']}", headers=headers
                )
            )
            assert detail.status_code == 200, detail.text
            assert "notes" not in detail.json()
            assert detail.json()["location"] == "Room 3"

            context = run_async(
                interviewer.get(
                    f"{API_V1}/interviews/{first['id']}/application",
                    headers=headers,
                )
            )
            assert context.status_code == 200, context.text
            context_body = context.json()
            assert context_body["candidate"]["full_name"] == "Assigned Candidate"
            assert context_body["candidate"]["title"] == "Engineer"
            assert context_body["candidate"]["email"] is None
            assert context_body["candidate"]["phone"] is None
            assert "@example.com" not in context.text
            assert "5678" not in context.text
            assert context_body["resume"]["parsed_data"] is None

            async def _populate_resume_parsed_data(resume_id: str) -> None:
                async with async_session_factory() as session:
                    resume_obj = await session.get(Resume, uuid.UUID(resume_id))
                    assert resume_obj is not None
                    resume_obj.parsed_data = {
                        "full_name": "Assigned Candidate",
                        "title": "Senior Backend Engineer",
                        "email": "candidate.secret@example.com",
                        "phone": "+84 912 345 678",
                        "address": "123 Nguyen Hue Street, District 1",
                        "linkedin": "https://linkedin.com/in/assigned-candidate",
                        "website": "https://assigned-candidate.dev",
                        "summary": (
                            "Distributed systems engineer. Contact: "
                            "candidate.secret@example.com or +84 912 345 678 "
                            "or https://linkedin.com/in/assigned-candidate"
                        ),
                        "skills": ["Python", "FastAPI"],
                        "experiences": [
                            {
                                "company": "Acme Corp",
                                "position": "Backend Engineer",
                                "description": "Built core APIs",
                            }
                        ],
                        "education": [
                            {
                                "institution": "HCMUT",
                                "degree": "BSc Computer Science",
                                "start_year": 2016,
                                "end_year": 2020,
                            }
                        ],
                        "projects": [
                            {
                                "name": "Hiring Engine",
                                "description": "Workflow service",
                                "skills_used": ["Python"],
                            }
                        ],
                    }
                    await session.commit()

            run_async(_populate_resume_parsed_data(context_body["resume"]["id"]))

            enriched_context = run_async(
                interviewer.get(
                    f"{API_V1}/interviews/{first['id']}/application",
                    headers=headers,
                )
            )
            assert enriched_context.status_code == 200, enriched_context.text
            enriched_body = enriched_context.json()
            assert enriched_body["candidate"]["email"] is None
            assert enriched_body["candidate"]["phone"] is None
            parsed_cv = enriched_body["resume"]["parsed_data"]
            assert parsed_cv["full_name"] == "Assigned Candidate"
            assert parsed_cv["title"] == "Senior Backend Engineer"
            assert parsed_cv["email"] is None
            assert parsed_cv["phone"] is None
            assert parsed_cv["skills"] == ["Python", "FastAPI"]
            assert parsed_cv["experiences"][0]["company"] == "Acme Corp"
            assert parsed_cv["education"][0]["institution"] == "HCMUT"
            assert parsed_cv["projects"][0]["name"] == "Hiring Engine"
            assert "candidate.secret" not in enriched_context.text
            assert "example.com" not in enriched_context.text
            assert "5678" not in enriched_context.text
            assert "Nguyen Hue" not in enriched_context.text
            assert "linkedin.com" not in enriched_context.text
            assert "assigned-candidate.dev" not in enriched_context.text

            manager_context = run_async(
                recruiter_client.get(
                    f"{API_V1}/interviews/{first['id']}/application",
                    headers=headers,
                )
            )
            assert manager_context.status_code == 200, manager_context.text
            assert manager_context.json() == enriched_body

            unassigned = run_async(
                interviewer.get(
                    f"{API_V1}/interviews/{second['id']}", headers=headers
                )
            )
            assert unassigned.status_code == 404

            unassigned_context = run_async(
                interviewer.get(
                    f"{API_V1}/interviews/{second['id']}/application",
                    headers=headers,
                )
            )
            assert unassigned_context.status_code == 404

            old_recruiter_route = run_async(
                interviewer.get(
                    f"{API_V1}/applications/{application['id']}/interviews",
                    headers=headers,
                )
            )
            assert old_recruiter_route.status_code == 403

            manager_routes = [
                run_async(
                    interviewer.get(
                        f"{API_V1}/jobs/mine", headers=headers
                    )
                ),
                run_async(
                    interviewer.get(
                        f"{API_V1}/analytics/recruiter-dashboard",
                        headers=headers,
                    )
                ),
                run_async(
                    interviewer.get(
                        f"{API_V1}/users/me/recruiter-metrics",
                        headers=headers,
                    )
                ),
                run_async(
                    interviewer.get(
                        f"{API_V1}/ai/search/candidates",
                        headers=headers,
                        params={"q": "engineer"},
                    )
                ),
                run_async(
                    interviewer.get(
                        f"{API_V1}/workspaces/members", headers=headers
                    )
                ),
                run_async(
                    interviewer.get(
                        f"{API_V1}/workspaces/invitations",
                        headers=headers,
                    )
                ),
                run_async(
                    interviewer.patch(
                        f"{API_V1}/companies/{company['id']}",
                        headers=headers,
                        json={"name": "Hijacked Corp"},
                    )
                ),
            ]
            assert [response.status_code for response in manager_routes] == [
                403,
                403,
                403,
                403,
                403,
                403,
                403,
            ]

            duplicate = run_async(
                recruiter_client.post(
                    f"{API_V1}/interviews/{first['id']}/assignments",
                    headers=headers,
                    json={"user_id": interviewer_member["user_id"]},
                )
            )
            assert duplicate.status_code == 409

            removed = run_async(
                recruiter_client.delete(
                    f"{API_V1}/interviews/{first['id']}/assignments/"
                    f"{assigned.json()['id']}",
                    headers=headers,
                )
            )
            assert removed.status_code == 204

            after_removal = run_async(
                interviewer.get(f"{API_V1}/interviews/mine", headers=headers)
            )
            assert after_removal.status_code == 200
            assert after_removal.json() == []

            denied_after_removal = run_async(
                interviewer.get(
                    f"{API_V1}/interviews/{first['id']}", headers=headers
                )
            )
            assert denied_after_removal.status_code == 404
        finally:
            run_async(interviewer.aclose())

    def test_cross_company_member_cannot_be_assigned(
        self, client, recruiter_client, candidate_client, run_async
    ):
        company, _, application = _setup_application(
            recruiter_client, candidate_client, run_async
        )
        interview = _schedule_interview(
            recruiter_client, run_async, application["id"]
        )
        other_company = run_async(
            recruiter_client.post(
                f"{API_V1}/companies",
                json={
                    **COMPANY_BODY,
                    "name": "Other Assignment Corp",
                    "slug": f"other-{uuid.uuid4().hex[:8]}",
                    "tax_code": f"TAX-{uuid.uuid4().hex[:8]}",
                },
            )
        )
        assert other_company.status_code == 201, other_company.text
        outsider, _ = _invite_member(
            recruiter_client,
            client,
            run_async,
            other_company.json()["id"],
            "interviewer",
        )
        try:
            members = run_async(
                recruiter_client.get(
                    f"{API_V1}/workspaces/members",
                    headers={"X-Company-ID": other_company.json()["id"]},
                )
            )
            outsider_member = next(
                member
                for member in members.json()
                if member["role"] == "interviewer"
            )
            response = run_async(
                recruiter_client.post(
                    f"{API_V1}/interviews/{interview['id']}/assignments",
                    headers={"X-Company-ID": company["id"]},
                    json={"user_id": outsider_member["user_id"]},
                )
            )
            assert response.status_code == 404
        finally:
            run_async(outsider.aclose())


class TestInterviewerScorecardWorkflow:
    def test_blind_draft_then_submit_visibility(
        self, client, recruiter_client, candidate_client, run_async
    ):
        company, _, application = _setup_application(
            recruiter_client, candidate_client, run_async
        )
        interview = _schedule_interview(
            recruiter_client, run_async, application["id"]
        )
        first, first_email = _invite_member(
            recruiter_client, client, run_async, company["id"], "interviewer"
        )
        second, second_email = _invite_member(
            recruiter_client, client, run_async, company["id"], "interviewer"
        )
        headers = {"X-Company-ID": company["id"]}
        try:
            members = run_async(
                recruiter_client.get(
                    f"{API_V1}/workspaces/members", headers=headers
                )
            )
            first_member = next(
                member
                for member in members.json()
                if member["email"] == first_email
            )
            second_member = next(
                member
                for member in members.json()
                if member["email"] == second_email
            )
            for member in (first_member, second_member):
                assigned = run_async(
                    recruiter_client.post(
                        f"{API_V1}/interviews/{interview['id']}/assignments",
                        headers=headers,
                        json={"user_id": member["user_id"]},
                    )
                )
                assert assigned.status_code == 201, assigned.text

            eval_url = f"{API_V1}/interviews/{interview['id']}/evaluations"
            first_draft = run_async(
                first.post(eval_url, headers=headers, json={"rating": 5})
            )
            assert first_draft.status_code == 201, first_draft.text
            first_eval = first_draft.json()
            assert first_eval["status"] == "draft"

            second_view = run_async(second.get(eval_url, headers=headers))
            assert second_view.status_code == 200, second_view.text
            assert second_view.json() == []

            first_view = run_async(first.get(eval_url, headers=headers))
            assert [row["id"] for row in first_view.json()] == [first_eval["id"]]

            cross_update = run_async(
                second.patch(
                    f"{eval_url}/{first_eval['id']}",
                    headers=headers,
                    json={"rating": 1},
                )
            )
            assert cross_update.status_code == 403, cross_update.text

            submitted = run_async(
                first.post(
                    f"{eval_url}/{first_eval['id']}/submit", headers=headers
                )
            )
            assert submitted.status_code == 200, submitted.text
            assert submitted.json()["status"] == "submitted"
            assert submitted.json()["submitted_at"] is not None

            second_view = run_async(second.get(eval_url, headers=headers))
            assert second_view.json() == []

            second_draft = run_async(
                second.post(eval_url, headers=headers, json={"rating": 3})
            )
            assert second_draft.status_code == 201, second_draft.text
            second_eval = second_draft.json()

            second_view = run_async(second.get(eval_url, headers=headers))
            assert [row["id"] for row in second_view.json()] == [second_eval["id"]]

            manager_view = run_async(
                recruiter_client.get(
                    f"{API_V1}/applications/{application['id']}/evaluations",
                    headers=headers,
                )
            )
            assert [row["id"] for row in manager_view.json()] == [first_eval["id"]]

            second_submit = run_async(
                second.post(
                    f"{eval_url}/{second_eval['id']}/submit", headers=headers
                )
            )
            assert second_submit.status_code == 200, second_submit.text

            second_view = run_async(second.get(eval_url, headers=headers))
            assert {row["id"] for row in second_view.json()} == {
                first_eval["id"],
                second_eval["id"],
            }
            assert all(row["status"] == "submitted" for row in second_view.json())

            manager_view = run_async(
                recruiter_client.get(
                    f"{API_V1}/applications/{application['id']}/evaluations",
                    headers=headers,
                )
            )
            assert {row["id"] for row in manager_view.json()} == {
                first_eval["id"],
                second_eval["id"],
            }

            immutable = run_async(
                first.patch(
                    f"{eval_url}/{first_eval['id']}",
                    headers=headers,
                    json={"rating": 2},
                )
            )
            assert immutable.status_code == 409, immutable.text

            legacy_route = run_async(
                first.get(
                    f"{API_V1}/applications/{application['id']}/evaluations",
                    headers=headers,
                )
            )
            assert legacy_route.status_code == 403, legacy_route.text
        finally:
            run_async(first.aclose())
            run_async(second.aclose())

    def test_unassigned_interviewer_cannot_create_scorecard(
        self, client, recruiter_client, candidate_client, run_async
    ):
        company, _, application = _setup_application(
            recruiter_client, candidate_client, run_async
        )
        interview = _schedule_interview(
            recruiter_client, run_async, application["id"]
        )
        interviewer, _ = _invite_member(
            recruiter_client, client, run_async, company["id"], "interviewer"
        )
        headers = {"X-Company-ID": company["id"]}
        try:
            response = run_async(
                interviewer.post(
                    f"{API_V1}/interviews/{interview['id']}/evaluations",
                    headers=headers,
                    json={"rating": 4},
                )
            )
            assert response.status_code == 404, response.text
        finally:
            run_async(interviewer.aclose())

    def test_unassigned_recruiter_cannot_create_or_submit_scorecard(
        self, client, recruiter_client, candidate_client, run_async
    ):
        company, _, application = _setup_application(
            recruiter_client, candidate_client, run_async
        )
        interview = _schedule_interview(
            recruiter_client, run_async, application["id"]
        )
        other_recruiter, _ = _invite_member(
            recruiter_client, client, run_async, company["id"], "recruiter"
        )
        headers = {"X-Company-ID": company["id"]}
        try:
            view = run_async(
                other_recruiter.get(
                    f"{API_V1}/interviews/{interview['id']}",
                    headers=headers,
                )
            )
            assert view.status_code == 200, view.text

            attempt = run_async(
                other_recruiter.post(
                    f"{API_V1}/interviews/{interview['id']}/evaluations",
                    headers=headers,
                    json={"rating": 4},
                )
            )
            assert attempt.status_code == 403, attempt.text
        finally:
            run_async(other_recruiter.aclose())

    def test_membership_revocation_soft_deletes_assignments_atomically_and_preserves_scorecards(
        self, client, recruiter_client, candidate_client, run_async
    ):
        company, _, application = _setup_application(
            recruiter_client, candidate_client, run_async
        )
        interview = _schedule_interview(
            recruiter_client, run_async, application["id"]
        )
        interviewer, interviewer_email = _invite_member(
            recruiter_client, client, run_async, company["id"], "interviewer"
        )
        headers = {"X-Company-ID": company["id"]}
        try:
            members = run_async(
                recruiter_client.get(
                    f"{API_V1}/workspaces/members", headers=headers
                )
            )
            assert members.status_code == 200, members.text
            interviewer_member = next(
                m for m in members.json() if m["email"] == interviewer_email
            )

            assigned = run_async(
                recruiter_client.post(
                    f"{API_V1}/interviews/{interview['id']}/assignments",
                    headers=headers,
                    json={"user_id": interviewer_member["user_id"]},
                )
            )
            assert assigned.status_code == 201, assigned.text
            assignment_id = assigned.json()["id"]

            draft = run_async(
                interviewer.post(
                    f"{API_V1}/interviews/{interview['id']}/evaluations",
                    headers=headers,
                    json={"rating": 5, "recommendation": "strong_hire"},
                )
            )
            assert draft.status_code == 201, draft.text
            eval_id = draft.json()["id"]

            submitted = run_async(
                interviewer.post(
                    f"{API_V1}/interviews/{interview['id']}/evaluations/{eval_id}/submit",
                    headers=headers,
                )
            )
            assert submitted.status_code == 200, submitted.text

            revoked = run_async(
                recruiter_client.delete(
                    f"{API_V1}/workspaces/members/{interviewer_member['membership_id']}",
                    headers=headers,
                )
            )
            assert revoked.status_code == 204, revoked.text

            async def _check_db():
                async with async_session_factory() as session:
                    assignment_row = await session.scalar(
                        select(InterviewAssignment).where(
                            InterviewAssignment.id == uuid.UUID(assignment_id)
                        )
                    )
                    assert assignment_row is not None
                    assert assignment_row.is_deleted is True

                    eval_row = await session.scalar(
                        select(InterviewEvaluation).where(
                            InterviewEvaluation.id == uuid.UUID(eval_id)
                        )
                    )
                    assert eval_row is not None
                    assert eval_row.is_deleted is False
                    assert eval_row.status == "submitted"

            run_async(_check_db())

            revoked_access = run_async(
                interviewer.get(
                    f"{API_V1}/interviews/{interview['id']}",
                    headers=headers,
                )
            )
            assert revoked_access.status_code in {403, 404}, revoked_access.text

            admin_view = run_async(
                recruiter_client.get(
                    f"{API_V1}/applications/{application['id']}/evaluations",
                    headers=headers,
                )
            )
            assert admin_view.status_code == 200, admin_view.text
            assert any(item["id"] == eval_id for item in admin_view.json())
        finally:
            run_async(interviewer.aclose())

    @pytest.mark.parametrize("target_role", ["admin", "recruiter"])
    def test_unassigned_manager_loses_own_draft_visibility_and_mutation_but_keeps_submitted_read(
        self,
        client,
        recruiter_client,
        candidate_client,
        run_async,
        target_role: str,
    ):
        company, _, application = _setup_application(
            recruiter_client, candidate_client, run_async
        )
        interview = _schedule_interview(
            recruiter_client, run_async, application["id"]
        )
        submitted_peer, submitted_peer_email = _invite_member(
            recruiter_client, client, run_async, company["id"], "interviewer"
        )
        draft_peer, draft_peer_email = _invite_member(
            recruiter_client, client, run_async, company["id"], "interviewer"
        )
        target_client, target_email = _invite_member(
            recruiter_client, client, run_async, company["id"], target_role
        )
        headers = {"X-Company-ID": company["id"]}
        eval_url = f"{API_V1}/interviews/{interview['id']}/evaluations"
        try:
            members_resp = run_async(
                recruiter_client.get(
                    f"{API_V1}/workspaces/members", headers=headers
                )
            )
            assert members_resp.status_code == 200, members_resp.text
            members = members_resp.json()
            submitted_peer_member = next(
                m for m in members if m["email"] == submitted_peer_email
            )
            draft_peer_member = next(
                m for m in members if m["email"] == draft_peer_email
            )
            target_member = next(
                m for m in members if m["email"] == target_email
            )
            assert target_member["role"] == target_role

            assignments: dict[str, str] = {}
            for key, member in (
                ("submitted_peer", submitted_peer_member),
                ("draft_peer", draft_peer_member),
                ("target", target_member),
            ):
                assigned = run_async(
                    recruiter_client.post(
                        f"{API_V1}/interviews/{interview['id']}/assignments",
                        headers=headers,
                        json={"user_id": member["user_id"]},
                    )
                )
                assert assigned.status_code == 201, assigned.text
                assignments[key] = assigned.json()["id"]

            peer_submitted_draft = run_async(
                submitted_peer.post(
                    eval_url, headers=headers, json={"rating": 5}
                )
            )
            assert peer_submitted_draft.status_code == 201, peer_submitted_draft.text
            peer_submitted_id = peer_submitted_draft.json()["id"]
            peer_submit = run_async(
                submitted_peer.post(
                    f"{eval_url}/{peer_submitted_id}/submit", headers=headers
                )
            )
            assert peer_submit.status_code == 200, peer_submit.text

            peer_draft = run_async(
                draft_peer.post(eval_url, headers=headers, json={"rating": 2})
            )
            assert peer_draft.status_code == 201, peer_draft.text
            peer_draft_id = peer_draft.json()["id"]

            own_draft = run_async(
                target_client.post(
                    eval_url, headers=headers, json={"rating": 4}
                )
            )
            assert own_draft.status_code == 201, own_draft.text
            own_draft_id = own_draft.json()["id"]

            while_assigned = run_async(
                target_client.get(eval_url, headers=headers)
            )
            assert while_assigned.status_code == 200, while_assigned.text
            assert {row["id"] for row in while_assigned.json()} == {
                peer_submitted_id,
                own_draft_id,
            }

            unassigned = run_async(
                recruiter_client.delete(
                    f"{API_V1}/interviews/{interview['id']}/assignments/"
                    f"{assignments['target']}",
                    headers=headers,
                )
            )
            assert unassigned.status_code == 204, unassigned.text

            async def _verify_historical_assignment_and_active_membership():
                async with async_session_factory() as session:
                    hist_assignment = await session.scalar(
                        select(InterviewAssignment).where(
                            InterviewAssignment.id
                            == uuid.UUID(assignments["target"])
                        )
                    )
                    assert hist_assignment is not None
                    assert hist_assignment.is_deleted is True

                    membership_row = await session.scalar(
                        select(CompanyMembership).where(
                            CompanyMembership.id
                            == uuid.UUID(target_member["membership_id"])
                        )
                    )
                    assert membership_row is not None
                    assert membership_row.is_deleted is False
                    assert membership_row.status.value == "active"

            run_async(_verify_historical_assignment_and_active_membership())

            after_unassign = run_async(
                target_client.get(eval_url, headers=headers)
            )
            assert after_unassign.status_code == 200, after_unassign.text
            after_ids = [row["id"] for row in after_unassign.json()]
            assert after_ids == [peer_submitted_id]
            assert own_draft_id not in after_ids
            assert peer_draft_id not in after_ids

            legacy_app_list = run_async(
                target_client.get(
                    f"{API_V1}/applications/{application['id']}/evaluations",
                    headers=headers,
                )
            )
            assert legacy_app_list.status_code == 200, legacy_app_list.text
            assert [row["id"] for row in legacy_app_list.json()] == [
                peer_submitted_id
            ]

            legacy_interview_list = run_async(
                target_client.get(
                    f"{API_V1}/applications/{application['id']}/interviews/"
                    f"{interview['id']}/evaluations",
                    headers=headers,
                )
            )
            assert (
                legacy_interview_list.status_code == 200
            ), legacy_interview_list.text
            assert [row["id"] for row in legacy_interview_list.json()] == [
                peer_submitted_id
            ]

            update_after_unassign = run_async(
                target_client.patch(
                    f"{eval_url}/{own_draft_id}",
                    headers=headers,
                    json={"rating": 3},
                )
            )
            assert update_after_unassign.status_code == 403

            submit_after_unassign = run_async(
                target_client.post(
                    f"{eval_url}/{own_draft_id}/submit",
                    headers=headers,
                )
            )
            assert submit_after_unassign.status_code == 403

            delete_after_unassign = run_async(
                target_client.delete(
                    f"{eval_url}/{own_draft_id}",
                    headers=headers,
                )
            )
            assert delete_after_unassign.status_code == 403
        finally:
            run_async(submitted_peer.aclose())
            run_async(draft_peer.aclose())
            run_async(target_client.aclose())
