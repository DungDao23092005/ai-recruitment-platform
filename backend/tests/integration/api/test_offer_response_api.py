"""Offer prerequisites and candidate-owned offer responses."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.integration.api.conftest import API_V1

COMPANY_BODY = {
    "name": "Offer Corp",
    "slug": "offer-corp",
    "tax_code": "556677889",
    "size": "startup",
}

JOB_BODY = {
    "title": "Offer Engineer",
    "description": "Build offer workflows",
    "job_type": "full_time",
    "workplace_type": "remote",
    "location": "Ho Chi Minh",
    "status": "published",
}


@pytest.fixture
def pipeline(recruiter_client, candidate_client, run_async):
    company = run_async(
        recruiter_client.post(f"{API_V1}/companies", json=COMPANY_BODY)
    ).json()
    job = run_async(
        recruiter_client.post(
            f"{API_V1}/jobs", json={**JOB_BODY, "company_id": company["id"]}
        )
    ).json()
    run_async(
        candidate_client.post(
            f"{API_V1}/users/me/candidate-profile",
            json={"full_name": "Offer Candidate", "title": "Engineer"},
        )
    )
    application = run_async(
        candidate_client.post(
            f"{API_V1}/applications", json={"job_id": job["id"]}
        )
    ).json()
    return application


def _set_status(client, run_async, application_id, value):
    return run_async(
        client.patch(
            f"{API_V1}/applications/{application_id}/status",
            json={"status": value},
        )
    )


def _schedule(recruiter_client, run_async, application_id):
    scheduled_at = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    resp = run_async(
        recruiter_client.post(
            f"{API_V1}/applications/{application_id}/interviews",
            json={
                "scheduled_at": scheduled_at,
                "duration_minutes": 60,
                "interview_type": "technical",
                "location": "Room 1",
            },
        )
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _interview_action(
    candidate_client, run_async, application_id, interview_id, action, notes=None
):
    payload = {"action": action}
    if notes is not None:
        payload["candidate_notes"] = notes
    return run_async(
        candidate_client.patch(
            f"{API_V1}/applications/{application_id}/interviews/"
            f"{interview_id}/action",
            json=payload,
        )
    )


def _advance_to_interviewing(recruiter_client, run_async, application_id):
    for value in ("under_review", "shortlisted", "interviewing"):
        resp = _set_status(recruiter_client, run_async, application_id, value)
        assert resp.status_code == 200, resp.text


def _make_offer(recruiter_client, candidate_client, run_async, application_id):
    _advance_to_interviewing(recruiter_client, run_async, application_id)
    interview = _schedule(recruiter_client, run_async, application_id)
    confirm = _interview_action(
        candidate_client, run_async, application_id, interview["id"], "confirm"
    )
    assert confirm.status_code == 200, confirm.text
    offered = _set_status(
        recruiter_client, run_async, application_id, "offered"
    )
    assert offered.status_code == 200, offered.text
    return interview


def _respond(client, run_async, application_id, action, notes=None):
    payload = {"action": action}
    if notes is not None:
        payload["notes"] = notes
    return run_async(
        client.patch(
            f"{API_V1}/applications/mine/{application_id}/offer",
            json=payload,
        )
    )


class TestOfferInterviewPrerequisites:
    def test_offer_without_interviews_is_rejected(
        self, pipeline, recruiter_client, run_async
    ):
        _advance_to_interviewing(recruiter_client, run_async, pipeline["id"])

        resp = _set_status(
            recruiter_client, run_async, pipeline["id"], "offered"
        )

        assert resp.status_code == 400
        assert "chưa có buổi phỏng vấn" in resp.json()["detail"]

    def test_offer_with_only_scheduled_interview_is_rejected(
        self, pipeline, recruiter_client, run_async
    ):
        _advance_to_interviewing(recruiter_client, run_async, pipeline["id"])
        _schedule(recruiter_client, run_async, pipeline["id"])

        resp = _set_status(
            recruiter_client, run_async, pipeline["id"], "offered"
        )

        assert resp.status_code == 400
        assert "chờ xác nhận" in resp.json()["detail"]

    def test_offer_with_only_declined_interview_is_rejected(
        self, pipeline, recruiter_client, candidate_client, run_async
    ):
        _advance_to_interviewing(recruiter_client, run_async, pipeline["id"])
        interview = _schedule(recruiter_client, run_async, pipeline["id"])
        declined = _interview_action(
            candidate_client,
            run_async,
            pipeline["id"],
            interview["id"],
            "decline",
            "Không phù hợp",
        )
        assert declined.status_code == 200, declined.text

        # Declining the only interview now returns the application to
        # screening. Move it back to interviewing so this test still exercises
        # the offer prerequisite rather than the generic transition guard.
        for value in ("shortlisted", "interviewing"):
            moved = _set_status(
                recruiter_client, run_async, pipeline["id"], value
            )
            assert moved.status_code == 200, moved.text

        resp = _set_status(
            recruiter_client, run_async, pipeline["id"], "offered"
        )

        assert resp.status_code == 400
        assert "xác nhận hoặc" in resp.json()["detail"]

    def test_offer_with_confirmed_and_pending_interview_is_rejected(
        self, pipeline, recruiter_client, candidate_client, run_async
    ):
        _advance_to_interviewing(recruiter_client, run_async, pipeline["id"])
        first = _schedule(recruiter_client, run_async, pipeline["id"])
        confirm = _interview_action(
            candidate_client, run_async, pipeline["id"], first["id"], "confirm"
        )
        assert confirm.status_code == 200, confirm.text
        _schedule(recruiter_client, run_async, pipeline["id"])

        resp = _set_status(
            recruiter_client, run_async, pipeline["id"], "offered"
        )

        assert resp.status_code == 400
        assert "chờ xác nhận" in resp.json()["detail"]

    def test_offer_with_confirmed_interview_succeeds(
        self, pipeline, recruiter_client, candidate_client, run_async
    ):
        _make_offer(
            recruiter_client,
            candidate_client,
            run_async,
            pipeline["id"],
        )

        listing = run_async(
            recruiter_client.get(
                f"{API_V1}/applications",
                params={"job_id": pipeline["job_id"]},
            )
        )
        assert listing.status_code == 200, listing.text
        assert listing.json()[0]["status"] == "offered"

    def test_cancelled_interview_is_ignored(
        self, pipeline, recruiter_client, candidate_client, run_async
    ):
        _advance_to_interviewing(recruiter_client, run_async, pipeline["id"])
        first = _schedule(recruiter_client, run_async, pipeline["id"])
        confirm = _interview_action(
            candidate_client, run_async, pipeline["id"], first["id"], "confirm"
        )
        assert confirm.status_code == 200, confirm.text
        pending = _schedule(recruiter_client, run_async, pipeline["id"])
        cancel = run_async(
            recruiter_client.delete(
                f"{API_V1}/applications/interviews/{pending['id']}"
            )
        )
        assert cancel.status_code == 200, cancel.text

        offered = _set_status(
            recruiter_client, run_async, pipeline["id"], "offered"
        )

        assert offered.status_code == 200, offered.text
        assert offered.json()["status"] == "offered"


class TestCandidateOfferResponse:
    def test_candidate_accepts_offer(
        self, pipeline, recruiter_client, candidate_client, run_async
    ):
        _make_offer(
            recruiter_client, candidate_client, run_async, pipeline["id"]
        )

        resp = _respond(
            candidate_client, run_async, pipeline["id"], "accept"
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "accepted"

    def test_candidate_declines_offer_with_notes(
        self, pipeline, recruiter_client, candidate_client, run_async
    ):
        _make_offer(
            recruiter_client, candidate_client, run_async, pipeline["id"]
        )

        resp = _respond(
            candidate_client,
            run_async,
            pipeline["id"],
            "decline",
            "Đã nhận lời mời khác",
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "rejected"

        activities = run_async(
            recruiter_client.get(
                f"{API_V1}/applications/{pipeline['id']}/activities"
            )
        )
        assert activities.status_code == 200, activities.text
        offers = [
            row
            for row in activities.json()
            if row["from_status"] == "offered"
            and row["to_status"] == "rejected"
        ]
        assert offers
        assert offers[0]["note"] == "Đã nhận lời mời khác"

    def test_second_response_is_rejected(
        self, pipeline, recruiter_client, candidate_client, run_async
    ):
        _make_offer(
            recruiter_client, candidate_client, run_async, pipeline["id"]
        )
        first = _respond(
            candidate_client, run_async, pipeline["id"], "accept"
        )
        assert first.status_code == 200, first.text

        second = _respond(
            candidate_client, run_async, pipeline["id"], "decline"
        )

        assert second.status_code == 400
        assert "đang ở trạng thái" in second.json()["detail"]

    def test_other_candidate_gets_404(
        self, pipeline, recruiter_client, candidate_client, candidate_b_client, run_async
    ):
        _make_offer(
            recruiter_client, candidate_client, run_async, pipeline["id"]
        )

        resp = _respond(
            candidate_b_client, run_async, pipeline["id"], "accept"
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == (
            f"Application {pipeline['id']} not found"
        )

    def test_recruiter_cannot_use_candidate_response_endpoint(
        self, pipeline, recruiter_client, candidate_client, run_async
    ):
        _make_offer(
            recruiter_client, candidate_client, run_async, pipeline["id"]
        )

        resp = _respond(
            recruiter_client, run_async, pipeline["id"], "accept"
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Not enough permissions"

    def test_recruiter_cannot_accept_on_candidate_behalf(
        self, pipeline, recruiter_client, candidate_client, run_async
    ):
        _make_offer(
            recruiter_client, candidate_client, run_async, pipeline["id"]
        )

        resp = _set_status(
            recruiter_client, run_async, pipeline["id"], "accepted"
        )

        assert resp.status_code == 400
        assert "not recruiter-managed" in resp.json()["detail"]

    def test_recruiter_cannot_reject_an_open_offer(
        self, pipeline, recruiter_client, candidate_client, run_async
    ):
        _make_offer(
            recruiter_client, candidate_client, run_async, pipeline["id"]
        )

        resp = _set_status(
            recruiter_client, run_async, pipeline["id"], "rejected"
        )

        assert resp.status_code == 400
        assert "not available" in resp.json()["detail"]

    def test_response_requires_an_offer(
        self, pipeline, candidate_client, run_async
    ):
        resp = _respond(
            candidate_client, run_async, pipeline["id"], "accept"
        )

        assert resp.status_code == 400
        assert "đang ở trạng thái" in resp.json()["detail"]

    def test_notes_over_limit_are_rejected(
        self, pipeline, recruiter_client, candidate_client, run_async
    ):
        _make_offer(
            recruiter_client, candidate_client, run_async, pipeline["id"]
        )

        resp = _respond(
            candidate_client,
            run_async,
            pipeline["id"],
            "decline",
            "x" * 1001,
        )

        assert resp.status_code == 422

    def test_invalid_action_is_rejected(
        self, pipeline, recruiter_client, candidate_client, run_async
    ):
        _make_offer(
            recruiter_client, candidate_client, run_async, pipeline["id"]
        )

        resp = _respond(
            candidate_client, run_async, pipeline["id"], "withdraw"
        )

        assert resp.status_code == 422
