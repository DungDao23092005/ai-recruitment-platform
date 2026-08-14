from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.v1.endpoints.ai import _get_ai_service
from app.core.exceptions import EntityNotFoundException
from app.domain.enums import UserRole
from app.main import app


class _FakeAttrs:
    def __init__(self, profile):
        self._profile = profile

    @property
    def candidate_profile(self):
        async def _resolve():
            return self._profile

        return _resolve()


class _FakeUser:
    def __init__(self, role: UserRole, has_profile: bool = True):
        self.id = uuid.uuid4()
        self.role = role
        self.is_active = True
        profile = (
            SimpleNamespace(id=uuid.uuid4()) if has_profile else None
        )
        self.awaitable_attrs = _FakeAttrs(profile)


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.process_and_index_resume = AsyncMock()
    service.process_and_index_job = AsyncMock()
    service.recommend_jobs_for_candidate = AsyncMock()
    service.recommend_candidates_for_job = AsyncMock()
    return service

@pytest.fixture
def client(mock_service):
    app.dependency_overrides[_get_ai_service] = lambda: mock_service
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _override_user(user):
    async def _override():
        return user

    return _override


@pytest.fixture
def candidate_client(client):
    app.dependency_overrides[get_current_user] = _override_user(
        _FakeUser(UserRole.CANDIDATE)
    )
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def recruiter_client(client):
    app.dependency_overrides[get_current_user] = _override_user(
        _FakeUser(UserRole.RECRUITER)
    )
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def active_client(client):
    app.dependency_overrides[get_current_user] = _override_user(
        _FakeUser(UserRole.ADMIN)
    )
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def unauthorized_client(client):
    async def _override():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    app.dependency_overrides[get_current_user] = _override
    yield client
    app.dependency_overrides.pop(get_current_user, None)


def _parsed_resume():
    return {
        "full_name": "Jane Doe",
        "skills": ["Python"],
    }


def _parsed_job():
    return {
        "title": "Backend Engineer",
        "required_skills": ["Python"],
    }


class TestParseResume:
    def test_parse_resume_success(self, candidate_client, mock_service):
        mock_service.process_and_index_resume.return_value = _parsed_resume()

        resp = candidate_client.post(
            "/api/v1/ai/parse-resume",
            files={"file": ("resume.pdf", b"%PDF-1.7 fake", "application/pdf")},
        )

        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Jane Doe"
        mock_service.process_and_index_resume.assert_called_once()

    def test_parse_resume_unauthorized(self, unauthorized_client, mock_service):
        resp = unauthorized_client.post(
            "/api/v1/ai/parse-resume",
            files={"file": ("resume.pdf", b"%PDF fake", "application/pdf")},
        )

        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        mock_service.process_and_index_resume.assert_not_called()


class TestParseJD:
    def test_parse_jd_success(self, recruiter_client, mock_service):
        mock_service.process_and_index_job.return_value = _parsed_job()

        resp = recruiter_client.post(
            "/api/v1/ai/parse-jd",
            json={
                "job_title": "Backend Engineer",
                "job_description": "Build robust APIs",
            },
        )

        assert resp.status_code == 200
        assert resp.json()["title"] == "Backend Engineer"
        mock_service.process_and_index_job.assert_called_once()

    def test_parse_jd_unauthorized(self, unauthorized_client, mock_service):
        resp = unauthorized_client.post(
            "/api/v1/ai/parse-jd",
            json={"job_title": "Dev", "job_description": "Desc"},
        )

        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        mock_service.process_and_index_job.assert_not_called()


class TestMatch:
    def test_match_success(self, active_client, mock_service):
        mock_service.match_candidate_with_job.return_value = {
            "overall_score": 90.0,
            "cosine_similarity": 0.9,
            "skill_coverage_score": 1.0,
            "experience_match_score": 1.0,
        }

        resp = active_client.post(
            "/api/v1/ai/match",
            json={
                "parsed_resume": _parsed_resume(),
                "parsed_job": _parsed_job(),
            },
        )

        assert resp.status_code == 200
        assert resp.json()["overall_score"] == 90.0
        mock_service.match_candidate_with_job.assert_called_once()


class TestRecommendJobs:
    def test_recommendations_jobs_success(self, candidate_client, mock_service):
        job_id = uuid.uuid4()
        mock_service.recommend_jobs_for_candidate.return_value = [
            {
                "job_id": str(job_id),
                "parsed_job": _parsed_job(),
                "match_result": {
                    "overall_score": 88.0,
                    "cosine_similarity": 0.88,
                    "skill_coverage_score": 1.0,
                    "experience_match_score": 0.5,
                },
            }
        ]

        resp = candidate_client.get("/api/v1/ai/recommendations/jobs")

        assert resp.status_code == 200
        assert resp.json()[0]["job_id"] == str(job_id)
        mock_service.recommend_jobs_for_candidate.assert_called_once()

    def test_recommendations_jobs_invalid_limit(
        self, candidate_client, mock_service
    ):
        resp = candidate_client.get("/api/v1/ai/recommendations/jobs?limit=0")

        assert resp.status_code == 422
        mock_service.recommend_jobs_for_candidate.assert_not_called()

    def test_recommendations_jobs_forbidden_role(
        self, recruiter_client, mock_service
    ):
        resp = recruiter_client.get("/api/v1/ai/recommendations/jobs")

        assert resp.status_code == status.HTTP_403_FORBIDDEN
        mock_service.recommend_jobs_for_candidate.assert_not_called()


class TestRecommendCandidates:
    def test_recommendations_candidates_success(
        self, recruiter_client, mock_service
    ):
        cand_id = uuid.uuid4()
        mock_service.recommend_candidates_for_job.return_value = [
            {
                "candidate_id": str(cand_id),
                "parsed_resume": _parsed_resume(),
                "match_result": {
                    "overall_score": 85.0,
                    "cosine_similarity": 0.85,
                    "skill_coverage_score": 1.0,
                    "experience_match_score": 0.5,
                },
            }
        ]

        resp = recruiter_client.get(
            "/api/v1/ai/recommendations/candidates",
            params={"job_id": str(uuid.uuid4())},
        )

        assert resp.status_code == 200
        assert resp.json()[0]["candidate_id"] == str(cand_id)
        mock_service.recommend_candidates_for_job.assert_called_once()

    def test_recommendations_candidates_invalid_limit(
        self, recruiter_client, mock_service
    ):
        resp = recruiter_client.get(
            "/api/v1/ai/recommendations/candidates",
            params={"job_id": str(uuid.uuid4()), "limit": 101},
        )

        assert resp.status_code == 422
        mock_service.recommend_candidates_for_job.assert_not_called()

    def test_recommendations_candidates_forbidden_role(
        self, candidate_client, mock_service
    ):
        resp = candidate_client.get(
            "/api/v1/ai/recommendations/candidates",
            params={"job_id": str(uuid.uuid4())},
        )

        assert resp.status_code == status.HTTP_403_FORBIDDEN
        mock_service.recommend_candidates_for_job.assert_not_called()


class TestServiceExceptionMapping:
    def test_entity_not_found_maps_to_404(self, candidate_client, mock_service):
        mock_service.recommend_jobs_for_candidate.side_effect = (
            EntityNotFoundException(
                "Resume vector for Candidate x not found in vector repository"
            )
        )

        resp = candidate_client.get("/api/v1/ai/recommendations/jobs")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]