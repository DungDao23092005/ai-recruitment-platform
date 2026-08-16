import socket
import uuid
from unittest.mock import patch

import pytest

from tests.integration.api.conftest import API_V1

_RESUME_BODY = {
    "full_name": "Jane Doe",
    "skills": ["Python", "FastAPI"],
}

_JOB_BODY = {
    "title": "Backend Engineer",
    "required_skills": ["Python", "FastAPI"],
}

_MATCH_RESULT_KEYS = [
    "overall_score",
    "cosine_similarity",
    "skill_coverage_score",
    "experience_match_score",
]


def _qdrant_available() -> bool:
    try:
        with socket.create_connection(("localhost", 6333), timeout=1):
            return True
    except OSError:
        return False


QDRANT_AVAILABLE = _qdrant_available()


def _skip_if_no_qdrant():
    if not QDRANT_AVAILABLE:
        pytest.skip("BLOCKED BY ENVIRONMENT: Qdrant not available on localhost:6333")


def _vector(dim: int = 384) -> list[float]:
    return [0.1] * dim


class TestMatch:
    def test_match_returns_result(self, candidate_client, run_async):
        resp = run_async(
            candidate_client.post(
                f"{API_V1}/ai/match",
                json={
                    "parsed_resume": _RESUME_BODY,
                    "parsed_job": _JOB_BODY,
                    "resume_vector": _vector(),
                    "job_vector": _vector(),
                },
            )
        )

        assert resp.status_code == 200
        body = resp.json()
        for key in _MATCH_RESULT_KEYS:
            assert key in body


class TestParseResume:
    def test_parse_resume_requires_auth(self, client, run_async):
        resp = run_async(
            client.post(
                f"{API_V1}/ai/parse-resume",
                files={"file": ("r.pdf", b"%PDF-1.7 fake", "application/pdf")},
            )
        )

        assert resp.status_code in (401, 403)

    @pytest.mark.skipif(
        not QDRANT_AVAILABLE,
        reason="BLOCKED BY ENVIRONMENT: Qdrant not available",
    )
    @patch("app.services.ai_matching_service.PDFTextExtractor.extract")
    def test_parse_resume_indexes(self, mock_extract, candidate_client, run_async):
        mock_extract.return_value = "Fake CV with Python skills"
        profile = run_async(
            candidate_client.post(
                f"{API_V1}/users/me/candidate-profile",
                json={"full_name": "Jane Doe", "title": "Engineer"},
            )
        )
        assert profile.status_code == 201

        resp = run_async(
            candidate_client.post(
                f"{API_V1}/ai/parse-resume",
                files={
                    "file": (
                        "resume.pdf",
                        b"%PDF-1.7 Fake CV with Python skills",
                        "application/pdf",
                    )
                },
            )
        )

        if resp.status_code != 200:
            print("ERROR RESPONSE:", resp.json())
        assert resp.status_code == 200
        assert "full_name" in resp.json()


class TestParseJD:
    def test_parse_jd_requires_auth(self, client, run_async):
        resp = run_async(
            client.post(
                f"{API_V1}/ai/parse-jd",
                json={"job_title": "Dev", "job_description": "Build APIs"},
            )
        )

        assert resp.status_code in (401, 403)

    @pytest.mark.skipif(
        not QDRANT_AVAILABLE,
        reason="BLOCKED BY ENVIRONMENT: Qdrant not available",
    )
    def test_parse_jd_indexes(self, recruiter_client, run_async):
        resp = run_async(
            recruiter_client.post(
                f"{API_V1}/ai/parse-jd",
                json={
                    "job_title": "Backend Engineer",
                    "job_description": "We are hiring a Python developer.",
                },
            )
        )

        assert resp.status_code == 200
        assert resp.json()["title"]


class TestRecommendationsJobs:
    def test_requires_auth(self, client, run_async):
        resp = run_async(client.get(f"{API_V1}/ai/recommendations/jobs"))

        assert resp.status_code in (401, 403)

    def test_forbidden_for_recruiter(self, recruiter_client, run_async):
        resp = run_async(
            recruiter_client.get(f"{API_V1}/ai/recommendations/jobs")
        )

        assert resp.status_code == 403

    def test_invalid_limit(self, candidate_client, run_async):
        resp = run_async(
            candidate_client.get(
                f"{API_V1}/ai/recommendations/jobs?limit=0"
            )
        )

        assert resp.status_code == 422

    @pytest.mark.skipif(
        not QDRANT_AVAILABLE,
        reason="BLOCKED BY ENVIRONMENT: Qdrant not available",
    )
    def test_recommends_jobs_for_candidate(
        self, candidate_client, run_async
    ):
        profile = run_async(
            candidate_client.post(
                f"{API_V1}/users/me/candidate-profile",
                json={"full_name": "Jane Doe", "title": "Engineer"},
            )
        )
        assert profile.status_code == 201

        resp = run_async(
            candidate_client.get(f"{API_V1}/ai/recommendations/jobs")
        )

        assert resp.status_code in (200, 404)


class TestRecommendationsCandidates:
    def test_requires_auth(self, client, run_async):
        resp = run_async(
            client.get(f"{API_V1}/ai/recommendations/candidates")
        )

        assert resp.status_code in (401, 403)

    def test_forbidden_for_candidate(self, candidate_client, run_async):
        resp = run_async(
            candidate_client.get(
                f"{API_V1}/ai/recommendations/candidates",
                params={"job_id": str(uuid.uuid4())},
            )
        )

        assert resp.status_code == 403

    def test_invalid_limit(self, recruiter_client, run_async):
        resp = run_async(
            recruiter_client.get(
                f"{API_V1}/ai/recommendations/candidates",
                params={"job_id": str(uuid.uuid4()), "limit": 101},
            )
        )

        assert resp.status_code == 422

    @pytest.mark.skipif(
        not QDRANT_AVAILABLE,
        reason="BLOCKED BY ENVIRONMENT: Qdrant not available",
    )
    def test_recommends_candidates_for_job(
        self, recruiter_client, run_async
    ):
        resp = run_async(
            recruiter_client.get(
                f"{API_V1}/ai/recommendations/candidates",
                params={"job_id": str(uuid.uuid4())},
            )
        )

        assert resp.status_code in (200, 404)


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


class TestRecommendationsCandidatesOwnership:
    """GET /ai/recommendations/candidates — job ownership enforced."""

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

    def test_recruiter_a_own_job_allowed(
        self, recruiter_a_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job_a = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/ai/recommendations/candidates",
                params={"job_id": job_a["id"]},
            )
        )

        assert resp.status_code == 200

    def test_recruiter_a_cannot_query_recruiter_b_job(
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
                f"{API_V1}/ai/recommendations/candidates",
                params={"job_id": job_b["id"]},
            )
        )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_anonymous_gets_401(self, client, run_async):
        resp = run_async(
            client.get(
                f"{API_V1}/ai/recommendations/candidates",
                params={"job_id": str(uuid.uuid4())},
            )
        )

        assert resp.status_code in (401, 403)

    @pytest.mark.skipif(
        not QDRANT_AVAILABLE,
        reason="BLOCKED BY ENVIRONMENT: Qdrant not available",
    )
    def test_form_created_job_without_vector_not_fail(
        self, recruiter_a_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job_a = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/ai/recommendations/candidates",
                params={"job_id": job_a["id"]},
            )
        )

        assert resp.status_code == 200
        data = resp.json()
        if isinstance(data, dict):
            assert "Job vector for Job" not in data.get("detail", "")
        else:
            assert isinstance(data, list)


def _configured_qdrant_available() -> bool:
    try:
        from app.core.config import settings

        with socket.create_connection(
            (settings.QDRANT_HOST, settings.QDRANT_PORT), timeout=2
        ):
            return True
    except OSError:
        return False


CONFIGURED_QDRANT_AVAILABLE = _configured_qdrant_available()


class TestRecommendationsCandidateName:
    """BUG 2 — AI recommendations resolve real candidate display data."""

    @pytest.mark.skipif(
        not CONFIGURED_QDRANT_AVAILABLE,
        reason="BLOCKED BY ENVIRONMENT: Qdrant not available",
    )
    def test_recommendation_includes_candidate_full_name(
        self, recruiter_a_client, candidate_client, run_async
    ):
        from app.ai.vector_db.qdrant_client import QdrantVectorRepository

        company = run_async(
            recruiter_a_client.post(
                f"{API_V1}/companies",
                json={
                    "name": "Acme Corp",
                    "slug": "acme-corp",
                    "tax_code": "123456789",
                    "size": "startup",
                },
            )
        )
        assert company.status_code == 201, company.text
        job = run_async(
            recruiter_a_client.post(
                f"{API_V1}/jobs",
                json={
                    "title": "Backend Engineer",
                    "description": "Build robust APIs",
                    "company_id": company.json()["id"],
                    "job_type": "full_time",
                    "workplace_type": "remote",
                    "location": "Ho Chi Minh",
                    "status": "published",
                },
            )
        ).json()
        profile = run_async(
            candidate_client.post(
                f"{API_V1}/users/me/candidate-profile",
                json={
                    "full_name": "Integration Jane",
                    "title": "Backend Engineer",
                },
            )
        )
        assert profile.status_code == 201, profile.text
        candidate_id = profile.json()["id"]

        repo = QdrantVectorRepository()
        try:
            run_async(repo.init_collections())
            run_async(
                repo.upsert_job_vector(
                    job_id=job["id"],
                    vector=_vector(),
                    skills=["Python"],
                )
            )
            run_async(
                repo.upsert_resume_vector(
                    candidate_id=candidate_id,
                    vector=_vector(),
                    skills=["Python"],
                )
            )

            resp = run_async(
                recruiter_a_client.get(
                    f"{API_V1}/ai/recommendations/candidates",
                    params={"job_id": job["id"]},
                )
            )
        finally:
            run_async(
                repo.delete_vector(collection_name="jobs", point_id=job["id"])
            )
            run_async(
                repo.delete_vector(
                    collection_name="resumes", point_id=candidate_id
                )
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body, "expected at least one recommendation"
        matched = [r for r in body if r["candidate_id"] == candidate_id]
        assert matched, "recommendation for seeded candidate not found"
        assert matched[0]["parsed_resume"]["full_name"] == "Integration Jane"
        assert matched[0]["parsed_resume"]["title"] == "Backend Engineer"
        assert matched[0]["parsed_resume"]["skills"] == ["Python"]
        assert matched[0]["parsed_resume"]["email"] is None
        assert matched[0]["parsed_resume"]["phone"] is None
        assert "candidate_id" in matched[0]
        assert "password" not in resp.text.lower()