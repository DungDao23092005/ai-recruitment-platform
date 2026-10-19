"""API coverage for recruiter-only internal notes on an application.

Notes are strictly recruiter/admin and never appear in any candidate response.
Editing/deleting is restricted to the author or an admin, and a note belonging to
another company is indistinguishable from a missing one (non-enumerating 404).
"""

from __future__ import annotations

import pytest

from tests.integration.api.conftest import API_V1

COMPANY_BODY = {
    "name": "Notes Corp",
    "slug": "notes-corp",
    "tax_code": "556677889",
    "size": "startup",
}

JOB_BODY = {
    "title": "Backend Engineer",
    "description": "Build the pipeline",
    "job_type": "full_time",
    "workplace_type": "remote",
    "location": "Ha Noi",
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
            json={"full_name": "Note Candidate", "title": "Engineer"},
        )
    )
    application = run_async(
        candidate_client.post(
            f"{API_V1}/applications", json={"job_id": job["id"]}
        )
    ).json()
    return {"application": application, "job": job}


class TestNoteCreateAndList:
    def test_recruiter_creates_and_lists_note(self, pipeline, recruiter_client, run_async):
        app_id = pipeline["application"]["id"]

        created = run_async(
            recruiter_client.post(
                f"{API_V1}/applications/{app_id}/notes",
                json={"content": "  Ứng viên rất phù hợp  "},
            )
        )
        assert created.status_code == 201, created.text
        note = created.json()
        assert note["content"] == "Ứng viên rất phù hợp"
        assert note["application_id"] == app_id

        listed = run_async(
            recruiter_client.get(f"{API_V1}/applications/{app_id}/notes")
        )
        assert listed.status_code == 200, listed.text
        assert [n["id"] for n in listed.json()] == [note["id"]]

    def test_blank_content_is_rejected(self, pipeline, recruiter_client, run_async):
        app_id = pipeline["application"]["id"]
        resp = run_async(
            recruiter_client.post(
                f"{API_V1}/applications/{app_id}/notes",
                json={"content": "   "},
            )
        )
        assert resp.status_code == 422, resp.text

    def test_pagination_bounds_are_enforced(self, pipeline, recruiter_client, run_async):
        app_id = pipeline["application"]["id"]
        too_big = run_async(
            recruiter_client.get(
                f"{API_V1}/applications/{app_id}/notes", params={"limit": 101}
            )
        )
        assert too_big.status_code == 422

        negative = run_async(
            recruiter_client.get(
                f"{API_V1}/applications/{app_id}/notes", params={"skip": -1}
            )
        )
        assert negative.status_code == 422


class TestNoteAuthorization:
    def test_candidate_cannot_read_notes(self, pipeline, candidate_client, run_async):
        app_id = pipeline["application"]["id"]
        resp = run_async(
            candidate_client.get(f"{API_V1}/applications/{app_id}/notes")
        )
        assert resp.status_code == 403, resp.text

    def test_candidate_cannot_create_notes(self, pipeline, candidate_client, run_async):
        app_id = pipeline["application"]["id"]
        resp = run_async(
            candidate_client.post(
                f"{API_V1}/applications/{app_id}/notes",
                json={"content": "sneaky"},
            )
        )
        assert resp.status_code == 403, resp.text

    def test_foreign_recruiter_gets_404(self, pipeline, recruiter_b_client, run_async):
        app_id = pipeline["application"]["id"]
        resp = run_async(
            recruiter_b_client.post(
                f"{API_V1}/applications/{app_id}/notes",
                json={"content": "not mine"},
            )
        )
        assert resp.status_code == 404, resp.text

    def test_admin_may_read_any_note(self, pipeline, recruiter_client, admin_client, run_async):
        app_id = pipeline["application"]["id"]
        run_async(
            recruiter_client.post(
                f"{API_V1}/applications/{app_id}/notes", json={"content": "hi"}
            )
        )
        resp = run_async(admin_client.get(f"{API_V1}/applications/{app_id}/notes"))
        assert resp.status_code == 200, resp.text
        assert len(resp.json()) == 1


class TestNoteMutation:
    def test_author_updates_then_deletes(self, pipeline, recruiter_client, run_async):
        app_id = pipeline["application"]["id"]
        note = run_async(
            recruiter_client.post(
                f"{API_V1}/applications/{app_id}/notes", json={"content": "first"}
            )
        ).json()

        updated = run_async(
            recruiter_client.patch(
                f"{API_V1}/applications/{app_id}/notes/{note['id']}",
                json={"content": "second"},
            )
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["content"] == "second"

        deleted = run_async(
            recruiter_client.delete(
                f"{API_V1}/applications/{app_id}/notes/{note['id']}"
            )
        )
        assert deleted.status_code == 204, deleted.text

        remaining = run_async(
            recruiter_client.get(f"{API_V1}/applications/{app_id}/notes")
        )
        assert remaining.json() == []

        gone = run_async(
            recruiter_client.patch(
                f"{API_V1}/applications/{app_id}/notes/{note['id']}",
                json={"content": "again"},
            )
        )
        assert gone.status_code == 404, gone.text

    def test_foreign_recruiter_cannot_update(self, pipeline, recruiter_client, recruiter_b_client, run_async):
        app_id = pipeline["application"]["id"]
        note = run_async(
            recruiter_client.post(
                f"{API_V1}/applications/{app_id}/notes", json={"content": "mine"}
            )
        ).json()

        resp = run_async(
            recruiter_b_client.patch(
                f"{API_V1}/applications/{app_id}/notes/{note['id']}",
                json={"content": "hijacked"},
            )
        )
        assert resp.status_code == 404, resp.text

    def test_admin_may_update_and_delete(self, pipeline, recruiter_client, admin_client, run_async):
        app_id = pipeline["application"]["id"]
        note = run_async(
            recruiter_client.post(
                f"{API_V1}/applications/{app_id}/notes", json={"content": "author text"}
            )
        ).json()

        updated = run_async(
            admin_client.patch(
                f"{API_V1}/applications/{app_id}/notes/{note['id']}",
                json={"content": "admin text"},
            )
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["content"] == "admin text"

        deleted = run_async(
            admin_client.delete(
                f"{API_V1}/applications/{app_id}/notes/{note['id']}"
            )
        )
        assert deleted.status_code == 204, deleted.text

    def test_missing_note_is_404(self, pipeline, recruiter_client, run_async):
        app_id = pipeline["application"]["id"]
        import uuid

        resp = run_async(
            recruiter_client.patch(
                f"{API_V1}/applications/{app_id}/notes/{uuid.uuid4()}",
                json={"content": "x"},
            )
        )
        assert resp.status_code == 404, resp.text
