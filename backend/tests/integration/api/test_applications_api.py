import uuid

import pytest

from tests.integration.api.conftest import API_V1, PASSWORD

COMPANY_BODY = {
    "name": "Acme Corp",
    "slug": "acme-corp",
    "tax_code": "123456789",
    "size": "startup",
}

JOB_BODY = {
    "title": "Backend Engineer",
    "description": "Build robust APIs",
    "job_type": "full_time",
    "workplace_type": "remote",
    "location": "Ho Chi Minh",
    "status": "published",
}


@pytest.fixture
def published_job(recruiter_client, run_async):
    company = run_async(
        recruiter_client.post(f"{API_V1}/companies", json=COMPANY_BODY)
    ).json()
    job = run_async(
        recruiter_client.post(
            f"{API_V1}/jobs",
            json={**JOB_BODY, "company_id": company["id"]},
        )
    ).json()
    return job


def create_candidate_profile(candidate_client, run_async):
    return run_async(
        candidate_client.post(
            f"{API_V1}/users/me/candidate-profile",
            json={"full_name": "Jane Doe", "title": "Engineer"},
        )
    )


class TestCandidateProfile:
    def test_create_candidate_profile(self, candidate_client, run_async):
        resp = create_candidate_profile(candidate_client, run_async)

        assert resp.status_code == 201
        body = resp.json()
        assert body["full_name"] == "Jane Doe"
        assert body["user_id"]

    def test_duplicate_profile_returns_400(
        self, candidate_client, run_async
    ):
        first = create_candidate_profile(candidate_client, run_async)
        assert first.status_code == 201

        second = create_candidate_profile(candidate_client, run_async)

        assert second.status_code == 400
        assert "already has a candidate profile" in second.json()["detail"]


class TestApplyJob:
    def test_candidate_applies_successfully(
        self, candidate_client, run_async, published_job
    ):
        create_candidate_profile(candidate_client, run_async)

        resp = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": published_job["id"]},
            )
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["job_id"] == published_job["id"]
        assert body["status"] == "applied"

    def test_candidate_without_profile_returns_400(
        self, candidate_client, run_async, published_job
    ):
        resp = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": published_job["id"]},
            )
        )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Candidate profile required"

    def test_duplicate_application_returns_400(
        self, candidate_client, run_async, published_job
    ):
        create_candidate_profile(candidate_client, run_async)
        first = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": published_job["id"]},
            )
        )
        assert first.status_code == 201

        second = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": published_job["id"]},
            )
        )

        assert second.status_code == 400
        assert "already applied" in second.json()["detail"]

    def test_nonexistent_job_returns_404(
        self, candidate_client, run_async
    ):
        create_candidate_profile(candidate_client, run_async)

        resp = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": str(uuid.uuid4())},
            )
        )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


class TestApplicationStatusUpdate:
    def test_recruiter_updates_status(
        self,
        candidate_client,
        recruiter_client,
        run_async,
        published_job,
    ):
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": published_job["id"]},
            )
        ).json()

        resp = run_async(
            recruiter_client.patch(
                f"{API_V1}/applications/{application['id']}/status",
                json={"status": "under_review"},
            )
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "under_review"

    def test_invalid_transition_returns_400(
        self,
        candidate_client,
        recruiter_client,
        run_async,
        published_job,
    ):
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": published_job["id"]},
            )
        ).json()

        resp = run_async(
            recruiter_client.patch(
                f"{API_V1}/applications/{application['id']}/status",
                json={"status": "accepted"},
            )
        )

        assert resp.status_code == 400
        assert "Invalid Application status transition" in resp.json()["detail"]

    def test_candidate_cannot_update_status(
        self,
        candidate_client,
        run_async,
        published_job,
    ):
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": published_job["id"]},
            )
        ).json()

        resp = run_async(
            candidate_client.patch(
                f"{API_V1}/applications/{application['id']}/status",
                json={"status": "under_review"},
            )
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Not enough permissions"

    def test_nonexistent_application_returns_404(
        self, recruiter_client, run_async
    ):
        resp = run_async(
            recruiter_client.patch(
                f"{API_V1}/applications/{uuid.uuid4()}/status",
                json={"status": "under_review"},
            )
        )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_recruiter_cannot_set_withdrawn_returns_400(
        self,
        candidate_client,
        recruiter_client,
        run_async,
        published_job,
    ):
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": published_job["id"]},
            )
        ).json()

        resp = run_async(
            recruiter_client.patch(
                f"{API_V1}/applications/{application['id']}/status",
                json={"status": "withdrawn"},
            )
        )

        assert resp.status_code == 400
        assert "not recruiter-managed" in resp.json()["detail"]

    def test_recruiter_cannot_set_applied_returns_400(
        self,
        candidate_client,
        recruiter_client,
        run_async,
        published_job,
    ):
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": published_job["id"]},
            )
        ).json()

        resp = run_async(
            recruiter_client.patch(
                f"{API_V1}/applications/{application['id']}/status",
                json={"status": "applied"},
            )
        )

        assert resp.status_code == 400
        assert "not recruiter-managed" in resp.json()["detail"]

    def test_recruiter_full_chain_success(
        self,
        candidate_client,
        recruiter_client,
        run_async,
        published_job,
    ):
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": published_job["id"]},
            )
        ).json()

        chain = [
            "under_review",
            "shortlisted",
            "interviewing",
            "accepted",
        ]
        for target in chain:
            resp = run_async(
                recruiter_client.patch(
                    f"{API_V1}/applications/{application['id']}/status",
                    json={"status": target},
                )
            )
            assert resp.status_code == 200, target
            assert resp.json()["status"] == target


class TestAdminStatusAuthorization:
    """Admin may drive recruiter-managed transitions but never WITHDRAWN/APPLIED."""

    @staticmethod
    def create_application(recruiter_client, candidate_client, run_async):
        company = run_async(
            recruiter_client.post(f"{API_V1}/companies", json=COMPANY_BODY)
        ).json()
        job = run_async(
            recruiter_client.post(
                f"{API_V1}/jobs",
                json={**JOB_BODY, "company_id": company["id"]},
            )
        ).json()
        create_candidate_profile(candidate_client, run_async)
        return run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job["id"]}
            )
        ).json()

    def test_admin_cannot_set_withdrawn_returns_400(
        self,
        admin_client,
        recruiter_client,
        candidate_client,
        run_async,
    ):
        application = self.create_application(
            recruiter_client, candidate_client, run_async
        )

        resp = run_async(
            admin_client.patch(
                f"{API_V1}/applications/{application['id']}/status",
                json={"status": "withdrawn"},
            )
        )

        assert resp.status_code == 400
        assert "not recruiter-managed" in resp.json()["detail"]

    def test_admin_cannot_set_applied_returns_400(
        self,
        admin_client,
        recruiter_client,
        candidate_client,
        run_async,
    ):
        application = self.create_application(
            recruiter_client, candidate_client, run_async
        )

        resp = run_async(
            admin_client.patch(
                f"{API_V1}/applications/{application['id']}/status",
                json={"status": "applied"},
            )
        )

        assert resp.status_code == 400
        assert "not recruiter-managed" in resp.json()["detail"]


class TestCandidateWithdraw:
    """PATCH /applications/mine/{id}/withdraw — candidate-owned withdrawal only."""

    @staticmethod
    def create_application(recruiter_client, candidate_client, run_async):
        company = run_async(
            recruiter_client.post(f"{API_V1}/companies", json=COMPANY_BODY)
        ).json()
        job = run_async(
            recruiter_client.post(
                f"{API_V1}/jobs",
                json={**JOB_BODY, "company_id": company["id"]},
            )
        ).json()
        create_candidate_profile(candidate_client, run_async)
        return run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job["id"]}
            )
        ).json()

    @staticmethod
    def advance_to(recruiter_client, run_async, application_id, target):
        chain = {
            "under_review": ["under_review"],
            "shortlisted": ["under_review", "shortlisted"],
            "interviewing": ["under_review", "shortlisted", "interviewing"],
            "accepted": [
                "under_review",
                "shortlisted",
                "interviewing",
                "accepted",
            ],
            "rejected": [
                "under_review",
                "shortlisted",
                "interviewing",
                "rejected",
            ],
        }[target]
        for step in chain:
            resp = run_async(
                recruiter_client.patch(
                    f"{API_V1}/applications/{application_id}/status",
                    json={"status": step},
                )
            )
            assert resp.status_code == 200, step

    def test_candidate_withdraws_own_application(
        self,
        candidate_client,
        recruiter_client,
        run_async,
    ):
        application = self.create_application(
            recruiter_client, candidate_client, run_async
        )

        resp = run_async(
            candidate_client.patch(
                f"{API_V1}/applications/mine/{application['id']}/withdraw"
            )
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "withdrawn"

    def test_candidate_withdraw_other_candidate_application_returns_404(
        self,
        candidate_client,
        candidate_b_client,
        recruiter_client,
        run_async,
    ):
        application = self.create_application(
            recruiter_client, candidate_client, run_async
        )

        resp = run_async(
            candidate_b_client.patch(
                f"{API_V1}/applications/mine/{application['id']}/withdraw"
            )
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == (
            f"Application {application['id']} not found"
        )

    def test_withdraw_nonexistent_application_returns_404(
        self, candidate_client, run_async
    ):
        create_candidate_profile(candidate_client, run_async)

        resp = run_async(
            candidate_client.patch(
                f"{API_V1}/applications/mine/{uuid.uuid4()}/withdraw"
            )
        )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_candidate_without_profile_withdraw_returns_404(
        self, candidate_client, run_async
    ):
        resp = run_async(
            candidate_client.patch(
                f"{API_V1}/applications/mine/{uuid.uuid4()}/withdraw"
            )
        )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_recruiter_cannot_withdraw_returns_403(
        self,
        recruiter_client,
        candidate_client,
        run_async,
    ):
        application = self.create_application(
            recruiter_client, candidate_client, run_async
        )

        resp = run_async(
            recruiter_client.patch(
                f"{API_V1}/applications/mine/{application['id']}/withdraw"
            )
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Not enough permissions"

    def test_anonymous_withdraw_returns_401(self, client, run_async):
        resp = run_async(
            client.patch(
                f"{API_V1}/applications/mine/{uuid.uuid4()}/withdraw"
            )
        )

        assert resp.status_code == 401

    def test_withdraw_accepted_application_returns_400(
        self,
        candidate_client,
        recruiter_client,
        run_async,
    ):
        application = self.create_application(
            recruiter_client, candidate_client, run_async
        )
        self.advance_to(
            recruiter_client, run_async, application["id"], "accepted"
        )

        resp = run_async(
            candidate_client.patch(
                f"{API_V1}/applications/mine/{application['id']}/withdraw"
            )
        )

        assert resp.status_code == 400
        assert "Invalid Application status transition" in resp.json()["detail"]

    def test_withdraw_rejected_application_returns_400(
        self,
        candidate_client,
        recruiter_client,
        run_async,
    ):
        application = self.create_application(
            recruiter_client, candidate_client, run_async
        )
        self.advance_to(
            recruiter_client, run_async, application["id"], "rejected"
        )

        resp = run_async(
            candidate_client.patch(
                f"{API_V1}/applications/mine/{application['id']}/withdraw"
            )
        )

        assert resp.status_code == 400
        assert "Invalid Application status transition" in resp.json()["detail"]

    def test_withdraw_already_withdrawn_returns_400(
        self,
        candidate_client,
        recruiter_client,
        run_async,
    ):
        application = self.create_application(
            recruiter_client, candidate_client, run_async
        )
        first = run_async(
            candidate_client.patch(
                f"{API_V1}/applications/mine/{application['id']}/withdraw"
            )
        )
        assert first.status_code == 200

        second = run_async(
            candidate_client.patch(
                f"{API_V1}/applications/mine/{application['id']}/withdraw"
            )
        )

        assert second.status_code == 400
        assert "Invalid Application status transition" in second.json()["detail"]

    def test_withdrawn_application_reflected_in_recruiter_listing(
        self,
        candidate_client,
        recruiter_client,
        run_async,
    ):
        company = run_async(
            recruiter_client.post(f"{API_V1}/companies", json=COMPANY_BODY)
        ).json()
        job = run_async(
            recruiter_client.post(
                f"{API_V1}/jobs",
                json={**JOB_BODY, "company_id": company["id"]},
            )
        ).json()
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job["id"]}
            )
        ).json()

        withdraw = run_async(
            candidate_client.patch(
                f"{API_V1}/applications/mine/{application['id']}/withdraw"
            )
        )
        assert withdraw.status_code == 200

        resp = run_async(
            recruiter_client.get(
                f"{API_V1}/applications", params={"job_id": job["id"]}
            )
        )

        assert resp.status_code == 200
        assert resp.json()[0]["status"] == "withdrawn"


class TestApplicationStatusOwnership:
    """PATCH /applications/{id}/status — recruiter must own the application's job.

    Cross-recruiter attempts return 404 (no existence leak) and must not
    mutate the application.
    """

    @staticmethod
    def create_company(client, run_async, slug, tax_code):
        body = {**COMPANY_BODY, "slug": slug, "tax_code": tax_code}
        resp = run_async(client.post(f"{API_V1}/companies", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    @staticmethod
    def create_job(client, run_async, company_id, title, status="published"):
        body = {
            **JOB_BODY,
            "company_id": company_id,
            "title": title,
            "status": status,
        }
        resp = run_async(client.post(f"{API_V1}/jobs", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_recruiter_a_updates_own_application_status(
        self, recruiter_a_client, candidate_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job_a = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job_a["id"]}
            )
        ).json()

        resp = run_async(
            recruiter_a_client.patch(
                f"{API_V1}/applications/{application['id']}/status",
                json={"status": "under_review"},
            )
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "under_review"

    def test_recruiter_b_cannot_update_recruiter_a_application(
        self, recruiter_a_client, recruiter_b_client, candidate_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job_a = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job_a["id"]}
            )
        ).json()

        resp = run_async(
            recruiter_b_client.patch(
                f"{API_V1}/applications/{application['id']}/status",
                json={"status": "under_review"},
            )
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == (
            f"Application {application['id']} not found"
        )

        unchanged = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications", params={"job_id": job_a["id"]}
            )
        ).json()
        assert unchanged[0]["status"] == "applied"

    def test_cross_recruiter_and_nonexistent_responses_indistinguishable(
        self, recruiter_a_client, recruiter_b_client, candidate_client, run_async
    ):
        import re

        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job_a = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job_a["id"]}
            )
        ).json()

        cross_recruiter = run_async(
            recruiter_b_client.patch(
                f"{API_V1}/applications/{application['id']}/status",
                json={"status": "under_review"},
            )
        )
        nonexistent_id = uuid.uuid4()
        nonexistent = run_async(
            recruiter_b_client.patch(
                f"{API_V1}/applications/{nonexistent_id}/status",
                json={"status": "under_review"},
            )
        )

        assert cross_recruiter.status_code == 404
        assert nonexistent.status_code == 404
        assert cross_recruiter.json()["detail"] == (
            f"Application {application['id']} not found"
        )
        pattern = r"^Application [0-9a-fA-F-]{36} not found$"
        assert re.match(pattern, cross_recruiter.json()["detail"]) is not None
        assert re.match(pattern, nonexistent.json()["detail"]) is not None

    def test_recruiter_b_cannot_update_with_any_status(
        self, recruiter_a_client, recruiter_b_client, candidate_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job_a = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job_a["id"]}
            )
        ).json()

        for status in ("under_review", "shortlisted", "rejected"):
            resp = run_async(
                recruiter_b_client.patch(
                    f"{API_V1}/applications/{application['id']}/status",
                    json={"status": status},
                )
            )
            assert resp.status_code == 404, status

        unchanged = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications", params={"job_id": job_a["id"]}
            )
        ).json()
        assert unchanged[0]["status"] == "applied"

    def test_admin_updates_any_application(
        self,
        admin_client,
        recruiter_b_client,
        candidate_client,
        run_async,
    ):
        company_b = self.create_company(
            recruiter_b_client, run_async, "acme-b", "222222222"
        )
        job_b = self.create_job(
            recruiter_b_client, run_async, company_b["id"], "Job B"
        )
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job_b["id"]}
            )
        ).json()

        resp = run_async(
            admin_client.patch(
                f"{API_V1}/applications/{application['id']}/status",
                json={"status": "under_review"},
            )
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "under_review"

    def test_anonymous_gets_401(self, client, run_async):
        resp = run_async(
            client.patch(
                f"{API_V1}/applications/{uuid.uuid4()}/status",
                json={"status": "under_review"},
            )
        )

        assert resp.status_code == 401

    def test_candidate_gets_403(self, candidate_client, run_async):
        resp = run_async(
            candidate_client.patch(
                f"{API_V1}/applications/{uuid.uuid4()}/status",
                json={"status": "under_review"},
            )
        )

        assert resp.status_code == 403


class TestListApplicationsOwnership:
    """GET /applications?job_id= — recruiter may only query own-company jobs."""

    @staticmethod
    def create_company(client, run_async, slug, tax_code):
        body = {**COMPANY_BODY, "slug": slug, "tax_code": tax_code}
        resp = run_async(client.post(f"{API_V1}/companies", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    @staticmethod
    def create_job(client, run_async, company_id, title, status="published"):
        body = {
            **JOB_BODY,
            "company_id": company_id,
            "title": title,
            "status": status,
        }
        resp = run_async(client.post(f"{API_V1}/jobs", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_recruiter_a_lists_own_job_applications(
        self, recruiter_a_client, candidate_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job_a = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job_a["id"]}
            )
        ).json()

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications", params={"job_id": job_a["id"]}
            )
        )

        assert resp.status_code == 200
        ids = [app["id"] for app in resp.json()]
        assert application["id"] in ids

    def test_recruiter_a_cannot_list_recruiter_b_job_applications(
        self, recruiter_a_client, recruiter_b_client, run_async
    ):
        company_b = self.create_company(
            recruiter_b_client, run_async, "acme-b", "222222222"
        )
        job_b = self.create_job(
            recruiter_b_client, run_async, company_b["id"], "Job B"
        )

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications", params={"job_id": job_b["id"]}
            )
        )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_admin_lists_any_job_applications(
        self,
        admin_client,
        recruiter_b_client,
        candidate_client,
        run_async,
    ):
        company_b = self.create_company(
            recruiter_b_client, run_async, "acme-b", "222222222"
        )
        job_b = self.create_job(
            recruiter_b_client, run_async, company_b["id"], "Job B"
        )
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job_b["id"]}
            )
        ).json()

        resp = run_async(
            admin_client.get(
                f"{API_V1}/applications", params={"job_id": job_b["id"]}
            )
        )

        assert resp.status_code == 200
        ids = [app["id"] for app in resp.json()]
        assert application["id"] in ids


class TestApplicationCandidateEnrichment:
    """GET /applications?job_id= returns safe candidate profile display data."""

    @staticmethod
    def create_company(client, run_async, slug, tax_code):
        body = {**COMPANY_BODY, "slug": slug, "tax_code": tax_code}
        resp = run_async(client.post(f"{API_V1}/companies", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    @staticmethod
    def create_job(client, run_async, company_id, title, status="published"):
        body = {
            **JOB_BODY,
            "company_id": company_id,
            "title": title,
            "status": status,
        }
        resp = run_async(client.post(f"{API_V1}/jobs", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_application_contains_candidate_full_name(
        self, recruiter_a_client, candidate_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job_a = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job_a["id"]}
            )
        ).json()

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications", params={"job_id": job_a["id"]}
            )
        )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        app = body[0]
        assert app["id"] == application["id"]
        assert app["candidate"] is not None
        assert app["candidate"]["full_name"] == "Jane Doe"
        assert app["candidate"]["title"] == "Engineer"
        assert "email" not in app["candidate"]
        assert "phone" not in app["candidate"]
        assert "user_id" not in app["candidate"]

    def test_application_response_omits_sensitive_candidate_fields(
        self, recruiter_a_client, candidate_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job_a = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )
        profile = create_candidate_profile(candidate_client, run_async).json()
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job_a["id"]}
            )
        ).json()

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications", params={"job_id": job_a["id"]}
            )
        )

        assert resp.status_code == 200
        candidate = resp.json()[0]["candidate"]
        assert candidate["id"] == profile["id"]
        assert set(candidate.keys()) == {"id", "full_name", "title"}
        raw = resp.text
        assert "password" not in raw.lower()
        assert "phone" not in raw

    def test_candidate_full_name_null_fallback(
        self, recruiter_a_client, candidate_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job_a = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )
        run_async(
            candidate_client.post(
                f"{API_V1}/users/me/candidate-profile",
                json={"full_name": None, "title": None},
            )
        )
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job_a["id"]}
            )
        ).json()

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications", params={"job_id": job_a["id"]}
            )
        )

        assert resp.status_code == 200
        candidate = resp.json()[0]["candidate"]
        assert candidate["full_name"] is None
        assert candidate["title"] is None


class TestGetMyApplications:
    """GET /applications/mine — candidate-owned application history."""

    @staticmethod
    def create_job(recruiter_client, run_async, title, suffix=""):
        company = run_async(
            recruiter_client.post(
                f"{API_V1}/companies",
                json={
                    **COMPANY_BODY,
                    "slug": f"acme-corp-{suffix or uuid.uuid4().hex[:8]}",
                    "tax_code": f"12{suffix or uuid.uuid4().hex[:8]}",
                },
            )
        ).json()
        job = run_async(
            recruiter_client.post(
                f"{API_V1}/jobs",
                json={**JOB_BODY, "company_id": company["id"], "title": title},
            )
        ).json()
        return job

    def test_anonymous_returns_401(self, client, run_async):
        resp = run_async(client.get(f"{API_V1}/applications/mine"))

        assert resp.status_code == 401

    def test_recruiter_returns_403(self, recruiter_client, run_async):
        resp = run_async(recruiter_client.get(f"{API_V1}/applications/mine"))

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Not enough permissions"

    def test_admin_allowed_by_existing_architecture(
        self, admin_client, run_async
    ):
        resp = run_async(admin_client.get(f"{API_V1}/applications/mine"))

        assert resp.status_code == 200
        assert resp.json() == []

    def test_empty_list_when_no_applications(self, candidate_client, run_async):
        create_candidate_profile(candidate_client, run_async)

        resp = run_async(candidate_client.get(f"{API_V1}/applications/mine"))

        assert resp.status_code == 200
        assert resp.json() == []

    def test_candidate_without_profile_gets_empty_list(
        self, candidate_client, run_async
    ):
        resp = run_async(candidate_client.get(f"{API_V1}/applications/mine"))

        assert resp.status_code == 200
        assert resp.json() == []

    def test_candidate_sees_only_own_applications(
        self,
        candidate_client,
        candidate_b_client,
        recruiter_client,
        run_async,
    ):
        create_candidate_profile(candidate_client, run_async)
        create_candidate_profile(candidate_b_client, run_async)
        job = self.create_job(recruiter_client, run_async, "Owned Job")
        run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job["id"]}
            )
        )

        mine = run_async(candidate_client.get(f"{API_V1}/applications/mine"))
        theirs = run_async(
            candidate_b_client.get(f"{API_V1}/applications/mine")
        )

        assert mine.status_code == 200
        assert len(mine.json()) == 1
        assert theirs.status_code == 200
        assert theirs.json() == []

    def test_response_contains_job_and_company_details(
        self, candidate_client, recruiter_client, run_async
    ):
        create_candidate_profile(candidate_client, run_async)
        job = self.create_job(recruiter_client, run_async, "Backend Engineer")
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job["id"]}
            )
        ).json()

        resp = run_async(candidate_client.get(f"{API_V1}/applications/mine"))

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        app = body[0]
        assert app["id"] == application["id"]
        assert app["job_id"] == job["id"]
        assert app["job_title"] == "Backend Engineer"
        assert app["company_name"] == COMPANY_BODY["name"]
        assert app["status"] == "applied"
        assert app["created_at"]
        assert app["updated_at"]

    def test_newest_first_ordering(
        self, candidate_client, recruiter_client, run_async
    ):
        create_candidate_profile(candidate_client, run_async)
        job_a = self.create_job(recruiter_client, run_async, "Job A")
        job_b = self.create_job(recruiter_client, run_async, "Job B")
        run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job_a["id"]}
            )
        )
        run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job_b["id"]}
            )
        )

        resp = run_async(candidate_client.get(f"{API_V1}/applications/mine"))

        assert resp.status_code == 200
        titles = [app["job_title"] for app in resp.json()]
        assert titles == ["Job B", "Job A"]

    def test_pagination_skip_limit(
        self, candidate_client, recruiter_client, run_async
    ):
        create_candidate_profile(candidate_client, run_async)
        jobs = [
            self.create_job(recruiter_client, run_async, f"Job {i}")
            for i in range(3)
        ]
        for job in jobs:
            run_async(
                candidate_client.post(
                    f"{API_V1}/applications", json={"job_id": job["id"]}
                )
            )

        first = run_async(
            candidate_client.get(
                f"{API_V1}/applications/mine", params={"skip": 0, "limit": 2}
            )
        )
        second = run_async(
            candidate_client.get(
                f"{API_V1}/applications/mine", params={"skip": 2, "limit": 2}
            )
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert len(first.json()) == 2
        assert len(second.json()) == 1
        titles = [app["job_title"] for app in first.json() + second.json()]
        assert titles == ["Job 2", "Job 1", "Job 0"]