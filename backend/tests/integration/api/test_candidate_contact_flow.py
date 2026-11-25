from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from tests.integration.api.conftest import (
    API_V1,
    seed_confirmed_resume,
)

@pytest.fixture
def recruiter_workspace(recruiter_client, run_async):
    """Set up a recruiter company workspace."""
    unique_suffix = str(uuid.uuid4())[:8]
    comp_resp = run_async(
        recruiter_client.post(
            f"{API_V1}/companies",
            json={
                "name": f"Global Talent Search Corp {unique_suffix}",
                "slug": f"global-talent-search-{unique_suffix}",
                "tax_code": f"{uuid.uuid4().int % 10000000000:010d}",
                "size": "startup",
            },
        )
    )
    assert comp_resp.status_code == 201, comp_resp.text
    company = comp_resp.json()

    # Set active workspace header on client
    recruiter_client.headers["X-Company-ID"] = company["id"]
    return company


@pytest.fixture
def discoverable_candidate(candidate_client, run_async):
    """Create a searchable candidate with a confirmed primary resume."""
    profile_resp = run_async(
        candidate_client.post(
            f"{API_V1}/users/me/candidate-profile",
            json={
                "full_name": "Nguyen Van A",
                "title": "Senior Python Developer",
                "phone": "0987654321",
                "is_searchable": True,
            },
        )
    )
    assert profile_resp.status_code in (200, 201), profile_resp.text
    profile = profile_resp.json()

    resume = run_async(
        seed_confirmed_resume(
            profile["id"],
            parsed_data={
                "summary": "Experienced Python backend engineer",
                "total_years_experience": 5,
                "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
                "experiences": [
                    {
                        "company": "Tech Solutions",
                        "position": "Backend Lead",
                        "start_date": "2021-01",
                        "end_date": None,
                        "is_current": True,
                        "description": "Led backend microservices development.",
                        "skills_used": ["Python", "FastAPI"],
                    }
                ],
                "education": [
                    {
                        "institution": "University of Technology",
                        "degree": "Bachelor",
                        "field_of_study": "Computer Science",
                        "start_year": "2016",
                        "end_year": "2020",
                    }
                ],
            },
            is_primary=True,
            is_confirmed=True,
        )
    )
    return {"profile": profile, "resume": resume}


class TestCandidateContactLifecycle:
    def test_full_contact_authorization_and_privacy_lifecycle(
        self,
        recruiter_client,
        candidate_client,
        recruiter_workspace,
        discoverable_candidate,
        run_async,
    ):
        candidate_id = discoverable_candidate["profile"]["id"]

        # 1. Recruiter previews candidate via AI discovery endpoint
        preview_resp = run_async(
            recruiter_client.get(f"{API_V1}/ai/candidates/{candidate_id}/preview")
        )
        assert preview_resp.status_code == 200, preview_resp.text
        preview = preview_resp.json()

        # Invariant: preview NEVER reveals email or phone
        assert "email" not in preview
        assert "phone" not in preview
        assert preview["full_name"] == "Nguyen Van A"
        assert preview["title"] == "Senior Python Developer"
        assert "Python" in preview["skills"]
        assert preview["can_request_contact"] is True
        assert preview["contact_request_status"] is None

        # 2. Recruiter attempts to access contact details before request -> 403
        contact_resp = run_async(
            recruiter_client.get(
                f"{API_V1}/contact-requests/candidates/{candidate_id}/contact"
            )
        )
        assert contact_resp.status_code == 403

        # 3. Recruiter sends contact authorization request
        create_resp = run_async(
            recruiter_client.post(
                f"{API_V1}/contact-requests",
                json={"candidate_id": candidate_id},
            )
        )
        assert create_resp.status_code == 201, create_resp.text
        request_data = create_resp.json()
        assert request_data["status"] == "pending"
        request_id = request_data["id"]

        # 4. Duplicate request while pending returns 409 Conflict
        dup_resp = run_async(
            recruiter_client.post(
                f"{API_V1}/contact-requests",
                json={"candidate_id": candidate_id},
            )
        )
        assert dup_resp.status_code == 409

        # 5. Candidate views incoming contact requests
        cand_list_resp = run_async(
            candidate_client.get(f"{API_V1}/candidate/contact-requests")
        )
        assert cand_list_resp.status_code == 200, cand_list_resp.text
        cand_requests = cand_list_resp.json()
        assert len(cand_requests) >= 1
        assert any(r["id"] == request_id for r in cand_requests)

        # 6. Candidate accepts contact request
        accept_resp = run_async(
            candidate_client.post(
                f"{API_V1}/candidate/contact-requests/{request_id}/accept"
            )
        )
        assert accept_resp.status_code == 200, accept_resp.text
        assert accept_resp.json()["status"] == "accepted"

        # 7. Recruiter now accesses authorized contact disclosure
        disclosed_resp = run_async(
            recruiter_client.get(
                f"{API_V1}/contact-requests/candidates/{candidate_id}/contact"
            )
        )
        assert disclosed_resp.status_code == 200, disclosed_resp.text
        disclosed = disclosed_resp.json()
        assert disclosed["candidate_id"] == candidate_id
        assert disclosed["full_name"] == "Nguyen Van A"
        assert "@" in disclosed["email"]
        assert disclosed["phone"] == "0987654321"

        # 8. AI Preview STILL never contains email or phone even after acceptance
        preview_after_resp = run_async(
            recruiter_client.get(f"{API_V1}/ai/candidates/{candidate_id}/preview")
        )
        assert preview_after_resp.status_code == 200
        preview_after = preview_after_resp.json()
        assert "email" not in preview_after
        assert "phone" not in preview_after
        assert preview_after["contact_request_status"] == "accepted"

        # 9. Candidate revokes contact authorization
        revoke_resp = run_async(
            candidate_client.post(
                f"{API_V1}/candidate/contact-requests/{request_id}/revoke"
            )
        )
        assert revoke_resp.status_code == 200, revoke_resp.text
        assert revoke_resp.json()["status"] == "revoked"

        # 10. Recruiter immediately loses contact access -> 403 Forbidden
        revoked_contact_resp = run_async(
            recruiter_client.get(
                f"{API_V1}/contact-requests/candidates/{candidate_id}/contact"
            )
        )
        assert revoked_contact_resp.status_code == 403

        # 11. Recruiter cannot re-request contact during 90-day cooldown -> 409 Conflict
        rerequest_resp = run_async(
            recruiter_client.post(
                f"{API_V1}/contact-requests",
                json={"candidate_id": candidate_id},
            )
        )
        assert rerequest_resp.status_code == 409
        assert "90 ngày" in rerequest_resp.json()["detail"]


class TestCandidateContactDeclineFlow:
    def test_decline_and_30_day_cooldown(
        self,
        recruiter_client,
        candidate_client,
        recruiter_workspace,
        discoverable_candidate,
        run_async,
    ):
        candidate_id = discoverable_candidate["profile"]["id"]

        # Recruiter creates request
        req_resp = run_async(
            recruiter_client.post(
                f"{API_V1}/contact-requests",
                json={"candidate_id": candidate_id},
            )
        )
        assert req_resp.status_code == 201
        request_id = req_resp.json()["id"]

        # Candidate declines request
        decline_resp = run_async(
            candidate_client.post(
                f"{API_V1}/candidate/contact-requests/{request_id}/decline"
            )
        )
        assert decline_resp.status_code == 200
        assert decline_resp.json()["status"] == "declined"

        # Contact disclosure remains forbidden
        contact_resp = run_async(
            recruiter_client.get(
                f"{API_V1}/contact-requests/candidates/{candidate_id}/contact"
            )
        )
        assert contact_resp.status_code == 403

        # Immediate re-request fails with 30-day cooldown 409
        rerequest_resp = run_async(
            recruiter_client.post(
                f"{API_V1}/contact-requests",
                json={"candidate_id": candidate_id},
            )
        )
        assert rerequest_resp.status_code == 409
        assert "30 ngày" in rerequest_resp.json()["detail"]


class TestNonSearchableCandidatePrivacy:
    def test_non_searchable_candidate_blocks_preview_and_request(
        self,
        recruiter_client,
        candidate_client,
        recruiter_workspace,
        run_async,
    ):
        # Candidate creates profile with is_searchable = False
        profile_resp = run_async(
            candidate_client.post(
                f"{API_V1}/users/me/candidate-profile",
                json={
                    "full_name": "Private Candidate",
                    "title": "Secret Agent",
                    "is_searchable": False,
                },
            )
        )
        assert profile_resp.status_code in (200, 201), profile_resp.text
        candidate_id = profile_resp.json()["id"]

        # Preview blocked with 403
        preview_resp = run_async(
            recruiter_client.get(f"{API_V1}/ai/candidates/{candidate_id}/preview")
        )
        assert preview_resp.status_code == 403

        # Contact request creation blocked with 403
        req_resp = run_async(
            recruiter_client.post(
                f"{API_V1}/contact-requests",
                json={"candidate_id": candidate_id},
            )
        )
        assert req_resp.status_code == 403
