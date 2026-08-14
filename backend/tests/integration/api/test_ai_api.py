import socket
import uuid

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
    def test_parse_resume_indexes(self, candidate_client, run_async):
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