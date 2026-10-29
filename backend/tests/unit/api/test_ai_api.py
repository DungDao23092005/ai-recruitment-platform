from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.api.v1.endpoints.ai import (
    _get_ai_service,
    _get_explainable_ai_service,
    _get_interview_generator_service,
    _get_rag_chat_service,
    _get_semantic_search_service,
)
from app.core.exceptions import (
    AIError,
    EmptyDocumentError,
    EntityNotFoundException,
    ForbiddenException,
    InvalidDocumentError,
)
from app.domain.enums import JobStatus, UserRole
from app.main import app
from app.services.quota_enforcement_service import QuotaEnforcementService, ReservationResult

KNOWN_JOB_ID = uuid.uuid4()
KNOWN_COMPANY_ID = uuid.uuid4()


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


def _make_db_job() -> MagicMock:
    job = MagicMock()
    job.id = KNOWN_JOB_ID
    job.company_id = KNOWN_COMPANY_ID
    job.title = "Backend Developer"
    job.description = "Python FastAPI backend role."
    job.status = JobStatus.PUBLISHED
    job.is_deleted = False
    job.company = SimpleNamespace(id=KNOWN_COMPANY_ID, name="TechNova AI")
    job.skills = []
    job.required_skills = []
    job.preferred_skills = []
    job.minimum_years_experience = None
    job.education_level = None
    return job


def _make_db_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = UserRole.RECRUITER
    user.recruiter_profile = SimpleNamespace(company_id=KNOWN_COMPANY_ID)
    return user


def _fake_db_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()

    def _execute(stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars().unique().first.return_value = None
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
        if "from jobs" in compiled:
            result.scalars().unique().first.return_value = _make_db_job()
        elif "from users" in compiled:
            result.scalar_one_or_none.return_value = _make_db_user()
        return result

    session.execute = AsyncMock(side_effect=_execute)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


async def _override_get_db():
    yield _fake_db_session()


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.parse_and_save_resume_draft = AsyncMock()
    service.process_and_index_job = AsyncMock()
    service.match_candidate_with_job = AsyncMock()
    service.recommend_jobs_for_candidate = AsyncMock()
    service.recommend_candidates_for_job = AsyncMock()
    service.embedding_service = MagicMock()
    service.embedding_service.embed_job = AsyncMock(return_value=[0.1] * 384)
    service.embedding_service.embed_resume = AsyncMock(return_value=[0.1] * 384)
    return service


@pytest.fixture
def mock_explain_service():
    service = MagicMock()
    service.explain_match = AsyncMock()
    return service


@pytest.fixture
def mock_search_service():
    service = MagicMock()
    service.search_jobs = AsyncMock()
    service.search_candidates = AsyncMock()
    return service


@pytest.fixture
def mock_rag_chat_service():
    service = MagicMock()
    service.chat = AsyncMock()
    return service


@pytest.fixture
def mock_interview_generator_service():
    service = MagicMock()
    service.generate_questions = AsyncMock()
    return service


@pytest.fixture
def mock_quota_service():
    """Mock QuotaEnforcementService for unit tests."""
    with patch('app.api.v1.endpoints.ai.QuotaEnforcementService') as mock_class:
        service = MagicMock(spec=QuotaEnforcementService)
        # Default to success for all reservation methods
        reservation_result = ReservationResult(
            usage_id=uuid.uuid4(),
            remaining=5,
            limit=10,
            used=5,
            bypassed=False,
        )
        service.reserve_ai_quota = AsyncMock(return_value=reservation_result)
        service.reserve_search_quota = AsyncMock(return_value=reservation_result)
        service.finalize_reservation = AsyncMock()
        service.release_reservation = AsyncMock()
        mock_class.return_value = service
        yield service


@pytest.fixture
def client(
    mock_service,
    mock_explain_service,
    mock_search_service,
    mock_rag_chat_service,
    mock_interview_generator_service,
    mock_quota_service,
):
    app.dependency_overrides[_get_ai_service] = lambda: mock_service
    app.dependency_overrides[_get_explainable_ai_service] = (
        lambda: mock_explain_service
    )
    app.dependency_overrides[_get_semantic_search_service] = (
        lambda: mock_search_service
    )
    app.dependency_overrides[_get_rag_chat_service] = (
        lambda: mock_rag_chat_service
    )
    app.dependency_overrides[_get_interview_generator_service] = (
        lambda: mock_interview_generator_service
    )
    app.dependency_overrides[get_db] = _override_get_db
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


def _resume_draft():
    now = "2026-01-15T10:30:00+00:00"
    return {
        "id": uuid.uuid4(),
        "candidate_id": uuid.uuid4(),
        "title": None,
        "is_primary": False,
        "is_confirmed": False,
        "confirmed_at": None,
        "parsed_data": _parsed_resume(),
        "created_at": now,
        "updated_at": now,
    }


def _parsed_job():
    return {
        "title": "Backend Engineer",
        "required_skills": ["Python"],
    }


class TestParseResume:
    def test_parse_resume_returns_unconfirmed_draft(
        self, candidate_client, mock_service
    ):
        draft = _resume_draft()
        mock_service.parse_and_save_resume_draft.return_value = draft

        resp = candidate_client.post(
            "/api/v1/ai/parse-resume",
            files={"file": ("resume.pdf", b"%PDF-1.7 fake", "application/pdf")},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(draft["id"])
        assert body["parsed_data"]["full_name"] == "Jane Doe"
        assert body["is_primary"] is False
        assert body["is_confirmed"] is False
        assert body["confirmed_at"] is None
        mock_service.parse_and_save_resume_draft.assert_called_once()
        call_kwargs = (
            mock_service.parse_and_save_resume_draft.call_args.kwargs
        )
        assert call_kwargs["candidate_id"]
        assert call_kwargs["pdf_source"] == b"%PDF-1.7 fake"
        assert call_kwargs["source_name"] == "resume.pdf"

    def test_parse_resume_unauthorized(self, unauthorized_client, mock_service):
        resp = unauthorized_client.post(
            "/api/v1/ai/parse-resume",
            files={"file": ("resume.pdf", b"%PDF fake", "application/pdf")},
        )

        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        mock_service.parse_and_save_resume_draft.assert_not_called()

    def test_parse_resume_ai_error_maps_to_502(
        self, candidate_client, mock_service
    ):
        mock_service.parse_and_save_resume_draft.side_effect = AIError(
            "Failed to embed resume"
        )

        resp = candidate_client.post(
            "/api/v1/ai/parse-resume",
            files={"file": ("resume.pdf", b"%PDF-1.7 fake", "application/pdf")},
        )

        assert resp.status_code == status.HTTP_502_BAD_GATEWAY
        assert "Failed to embed resume" in resp.json()["detail"]
        mock_service.parse_and_save_resume_draft.assert_called_once()


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

    def test_parse_jd_provider_quota_error_releases_reservation(
        self, recruiter_client, mock_service, mock_quota_service
    ):
        from app.core.exceptions import AIProviderQuotaExceededError

        mock_service.process_and_index_job.side_effect = (
            AIProviderQuotaExceededError(retry_after=30)
        )

        resp = recruiter_client.post(
            "/api/v1/ai/parse-jd",
            json={"job_title": "Dev", "job_description": "Desc"},
        )

        assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert resp.headers.get("Retry-After") == "30"
        mock_quota_service.release_reservation.assert_called_once()
        mock_quota_service.finalize_reservation.assert_not_called()

    def test_parse_jd_provider_unavailable_releases_reservation(
        self, recruiter_client, mock_service, mock_quota_service
    ):
        from app.core.exceptions import AIProviderUnavailableError

        mock_service.process_and_index_job.side_effect = (
            AIProviderUnavailableError(retry_after=45)
        )

        resp = recruiter_client.post(
            "/api/v1/ai/parse-jd",
            json={"job_title": "Dev", "job_description": "Desc"},
        )

        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert resp.headers.get("Retry-After") == "45"
        mock_quota_service.release_reservation.assert_called_once()
        mock_quota_service.finalize_reservation.assert_not_called()

    def test_parse_jd_unexpected_error_releases_reservation(
        self, recruiter_client, mock_service, mock_quota_service
    ):
        mock_service.process_and_index_job.side_effect = RuntimeError(
            "vector store down"
        )

        with pytest.raises(RuntimeError, match="vector store down"):
            recruiter_client.post(
                "/api/v1/ai/parse-jd",
                json={"job_title": "Dev", "job_description": "Desc"},
            )

        mock_quota_service.release_reservation.assert_called_once()
        mock_quota_service.finalize_reservation.assert_not_called()

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

    def test_recommendations_candidates_consumes_search_quota(
        self, recruiter_client, mock_service, mock_quota_service
    ):
        mock_service.recommend_candidates_for_job.return_value = [
            {
                "candidate_id": str(uuid.uuid4()),
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
        mock_quota_service.reserve_search_quota.assert_called_once()
        kwargs = mock_quota_service.reserve_search_quota.call_args.kwargs
        assert kwargs["is_admin"] is False
        mock_quota_service.finalize_reservation.assert_called_once()
        # Candidate recommendations must not consume AI feature quota
        mock_quota_service.reserve_ai_quota.assert_not_called()

    def test_recommendations_candidates_no_subscription_returns_403(
        self, recruiter_client, mock_service, mock_quota_service
    ):
        mock_quota_service.reserve_search_quota.side_effect = ForbiddenException(
            "Bạn chưa có gói đăng ký hợp lệ."
        )

        resp = recruiter_client.get(
            "/api/v1/ai/recommendations/candidates",
            params={"job_id": str(uuid.uuid4())},
        )

        assert resp.status_code == status.HTTP_403_FORBIDDEN
        mock_service.recommend_candidates_for_job.assert_not_called()
        mock_quota_service.finalize_reservation.assert_not_called()

    def test_recommendations_candidates_search_failure_releases_reservation(
        self, recruiter_client, mock_service, mock_quota_service
    ):
        mock_service.recommend_candidates_for_job.side_effect = Exception(
            "search engine down"
        )

        with pytest.raises(Exception, match="search engine down"):
            recruiter_client.get(
                "/api/v1/ai/recommendations/candidates",
                params={"job_id": str(uuid.uuid4())},
            )

        mock_quota_service.release_reservation.assert_called_once()
        mock_quota_service.finalize_reservation.assert_not_called()

    def test_recommendations_candidates_admin_bypasses_quota(
        self, active_client, mock_service, mock_quota_service
    ):
        mock_service.recommend_candidates_for_job.return_value = [
            {
                "candidate_id": str(uuid.uuid4()),
                "parsed_resume": _parsed_resume(),
                "match_result": {
                    "overall_score": 85.0,
                    "cosine_similarity": 0.85,
                    "skill_coverage_score": 1.0,
                    "experience_match_score": 0.5,
                },
            }
        ]

        resp = active_client.get(
            "/api/v1/ai/recommendations/candidates",
            params={"job_id": str(uuid.uuid4())},
        )

        assert resp.status_code == 200
        mock_quota_service.reserve_search_quota.assert_called_once()
        kwargs = mock_quota_service.reserve_search_quota.call_args.kwargs
        assert kwargs["is_admin"] is True

    def test_recommendations_candidates_idempotency_key_forwarded(
        self, recruiter_client, mock_service, mock_quota_service
    ):
        mock_service.recommend_candidates_for_job.return_value = [
            {
                "candidate_id": str(uuid.uuid4()),
                "parsed_resume": _parsed_resume(),
                "match_result": {
                    "overall_score": 85.0,
                    "cosine_similarity": 0.85,
                    "skill_coverage_score": 1.0,
                    "experience_match_score": 0.5,
                },
            }
        ]

        key = "idem-rec-1"
        resp = recruiter_client.get(
            "/api/v1/ai/recommendations/candidates",
            params={"job_id": str(uuid.uuid4())},
            headers={"Idempotency-Key": key},
        )

        assert resp.status_code == 200
        kwargs = mock_quota_service.reserve_search_quota.call_args.kwargs
        assert kwargs["idempotency_key"] == key


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


def _match_result_payload():
    return {
        "overall_score": 82.0,
        "cosine_similarity": 0.85,
        "skill_coverage_score": 0.8,
        "preferred_skill_coverage_score": 0.5,
        "education_score": 1.0,
        "project_score": 1.0,
        "experience_match_score": 0.75,
        "matching_skills": ["React", "TypeScript"],
        "skill_gap": ["GraphQL"],
        "match_reasons": ["Strong skill overlap"],
    }


def _explain_response_payload():
    return {
        "match_score": 85.0,
        "summary": "The candidate matches the role well.",
        "strengths": ["Strong overlap in React and TypeScript"],
        "missing_skills": ["GraphQL"],
        "experience_analysis": "Candidate has 5 years experience vs 4 required.",
        "education_analysis": "x",
        "evidence": [],
        "recommendation": "Proceed to interview.",
        "confidence": 0.9,
    }


class TestExplainMatch:
    """The legacy POST endpoint is retired: fail-closed for every caller.

    It used to explain a caller-supplied match_result/candidate/job payload,
    which could not be tied to a trusted resource. See
    ``tests/unit/api/test_ai_explain_match_deprecated.py`` for the dedicated
    security suite; these tests keep the endpoint-level contract covered here.
    """

    def test_explain_match_authenticated_returns_410(
        self, active_client, mock_explain_service
    ):
        resp = active_client.post(
            "/api/v1/ai/explain-match",
            json={
                "match_result": _match_result_payload(),
                "candidate": _parsed_resume(),
                "job": _parsed_job(),
            },
        )

        assert resp.status_code == status.HTTP_410_GONE
        assert "match-explanation" in resp.json()["detail"]
        mock_explain_service.explain_match.assert_not_called()

    def test_explain_match_requires_match_result(
        self, active_client, mock_explain_service
    ):
        resp = active_client.post(
            "/api/v1/ai/explain-match",
            json={"candidate": _parsed_resume(), "job": _parsed_job()},
        )

        assert resp.status_code == 422
        mock_explain_service.explain_match.assert_not_called()

    def test_explain_match_unauthorized(self, unauthorized_client):
        resp = unauthorized_client.post(
            "/api/v1/ai/explain-match",
            json={"match_result": _match_result_payload()},
        )

        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_explain_match_never_calls_provider_even_with_provider_errors(
        self, active_client, mock_explain_service
    ):
        mock_explain_service.explain_match.side_effect = EmptyDocumentError(
            "match_result has no overall_score to explain"
        )

        resp = active_client.post(
            "/api/v1/ai/explain-match",
            json={"match_result": _match_result_payload()},
        )

        assert resp.status_code == status.HTTP_410_GONE
        mock_explain_service.explain_match.assert_not_called()

    def test_explain_match_retired_for_admin_role(
        self, active_client, mock_explain_service
    ):
        resp = active_client.post(
            "/api/v1/ai/explain-match",
            json={"match_result": _match_result_payload()},
        )

        assert resp.status_code == status.HTTP_410_GONE
        mock_explain_service.explain_match.assert_not_called()

    def test_explain_match_retired_for_candidate_role(
        self, candidate_client, mock_explain_service
    ):
        resp = candidate_client.post(
            "/api/v1/ai/explain-match",
            json={"match_result": _match_result_payload()},
        )

        assert resp.status_code == status.HTTP_410_GONE
        mock_explain_service.explain_match.assert_not_called()

    def test_explain_match_retired_for_recruiter_role(
        self, recruiter_client, mock_explain_service
    ):
        resp = recruiter_client.post(
            "/api/v1/ai/explain-match",
            json={"match_result": _match_result_payload()},
        )

        assert resp.status_code == status.HTTP_410_GONE
        mock_explain_service.explain_match.assert_not_called()


def _search_result_payload():
    return [
        {
            "id": "1234",
            "score": 0.87,
            "skills": ["Python", "FastAPI"],
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    ]


class TestSearchJobs:
    def test_search_jobs_success(self, active_client, mock_search_service):
        mock_search_service.search_jobs.return_value = (
            _search_result_payload()
        )

        resp = active_client.get(
            "/api/v1/ai/search/jobs", params={"q": "python backend"}
        )

        assert resp.status_code == 200
        assert resp.json()[0]["id"] == "1234"
        assert resp.json()[0]["score"] == 0.87
        mock_search_service.search_jobs.assert_called_once()

    def test_search_jobs_passes_score_threshold(
        self, active_client, mock_search_service
    ):
        mock_search_service.search_jobs.return_value = _search_result_payload()

        resp = active_client.get(
            "/api/v1/ai/search/jobs",
            params={"q": "react", "score_threshold": 0.5},
        )

        assert resp.status_code == 200
        mock_search_service.search_jobs.assert_called_once()
        kwargs = mock_search_service.search_jobs.call_args.kwargs
        assert kwargs["score_threshold"] == 0.5

    def test_search_jobs_empty_query_rejected(
        self, active_client, mock_search_service
    ):
        resp = active_client.get(
            "/api/v1/ai/search/jobs", params={"q": ""}
        )

        assert resp.status_code == 422
        mock_search_service.search_jobs.assert_not_called()

    def test_search_jobs_missing_query_rejected(
        self, active_client, mock_search_service
    ):
        resp = active_client.get("/api/v1/ai/search/jobs")

        assert resp.status_code == 422
        mock_search_service.search_jobs.assert_not_called()

    def test_search_jobs_invalid_limit(self, active_client, mock_search_service):
        resp = active_client.get(
            "/api/v1/ai/search/jobs", params={"q": "react", "limit": 0}
        )

        assert resp.status_code == 422
        mock_search_service.search_jobs.assert_not_called()

    def test_search_jobs_invalid_threshold(
        self, active_client, mock_search_service
    ):
        resp = active_client.get(
            "/api/v1/ai/search/jobs",
            params={"q": "react", "score_threshold": 1.5},
        )

        assert resp.status_code == 422
        mock_search_service.search_jobs.assert_not_called()

    def test_search_jobs_unauthorized(self, unauthorized_client):
        resp = unauthorized_client.get(
            "/api/v1/ai/search/jobs", params={"q": "react"}
        )

        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_search_jobs_empty_document_maps_to_400(
        self, active_client, mock_search_service
    ):
        mock_search_service.search_jobs.side_effect = EmptyDocumentError(
            "Text for embedding generation cannot be empty"
        )

        resp = active_client.get(
            "/api/v1/ai/search/jobs", params={"q": "react"}
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_search_jobs_provider_failure_maps_to_502(
        self, active_client, mock_search_service
    ):
        mock_search_service.search_jobs.side_effect = InvalidDocumentError(
            "Failed to generate embedding vector"
        )

        resp = active_client.get(
            "/api/v1/ai/search/jobs", params={"q": "react"}
        )

        assert resp.status_code == status.HTTP_502_BAD_GATEWAY

    def test_search_jobs_qdrant_failure_maps_to_502(
        self, active_client, mock_search_service
    ):
        mock_search_service.search_jobs.side_effect = AIError(
            "Failed to search similar vectors in collection 'jobs'"
        )

        resp = active_client.get(
            "/api/v1/ai/search/jobs", params={"q": "react"}
        )

        assert resp.status_code == status.HTTP_502_BAD_GATEWAY


class TestSearchCandidates:
    def test_search_candidates_success(
        self, recruiter_client, mock_search_service
    ):
        mock_search_service.search_candidates.return_value = (
            _search_result_payload()
        )

        resp = recruiter_client.get(
            "/api/v1/ai/search/candidates", params={"q": "react developer"}
        )

        assert resp.status_code == 200
        assert resp.json()[0]["id"] == "1234"
        mock_search_service.search_candidates.assert_called_once()

    def test_search_candidates_unauthorized(self, unauthorized_client):
        resp = unauthorized_client.get(
            "/api/v1/ai/search/candidates", params={"q": "react"}
        )

        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_search_candidates_forbidden_for_candidate(
        self, candidate_client, mock_search_service
    ):
        resp = candidate_client.get(
            "/api/v1/ai/search/candidates", params={"q": "react"}
        )

        assert resp.status_code == status.HTTP_403_FORBIDDEN
        mock_search_service.search_candidates.assert_not_called()

    def test_search_candidates_admin_allowed(
        self, active_client, mock_search_service
    ):
        mock_search_service.search_candidates.return_value = (
            _search_result_payload()
        )

        resp = active_client.get(
            "/api/v1/ai/search/candidates", params={"q": "react"}
        )

        assert resp.status_code == 200
        mock_search_service.search_candidates.assert_called_once()

    def test_search_candidates_empty_query_rejected(
        self, recruiter_client, mock_search_service
    ):
        resp = recruiter_client.get(
            "/api/v1/ai/search/candidates", params={"q": ""}
        )

        assert resp.status_code == 422
        mock_search_service.search_candidates.assert_not_called()

    def test_search_candidates_provider_failure_maps_to_502(
        self, recruiter_client, mock_search_service
    ):
        mock_search_service.search_candidates.side_effect = (
            InvalidDocumentError("Failed to generate embedding vector")
        )

        resp = recruiter_client.get(
            "/api/v1/ai/search/candidates", params={"q": "react"}
        )

        assert resp.status_code == status.HTTP_502_BAD_GATEWAY


def _chat_response_payload():
    return {
        "answer": "Dựa trên dữ kiện được cung cấp, bạn nên tập trung vào Python.",
        "confidence": 0.9,
        "sources": [
            {
                "source_type": "job",
                "entity_id": str(uuid.uuid4()),
                "title": "Job abc12345",
                "relevance_score": 0.87,
                "skills": ["Python", "FastAPI"],
            }
        ],
        "suggested_followups": ["Lộ trình AI Engineer?"],
    }


class TestChat:
    def test_chat_success(self, active_client, mock_rag_chat_service):
        mock_rag_chat_service.chat.return_value = _chat_response_payload()

        resp = active_client.post(
            "/api/v1/ai/chat",
            json={"message": "Tư vấn lộ trình AI Engineer"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"].startswith("Dựa trên dữ kiện")
        assert body["sources"][0]["source_type"] == "job"
        assert body["suggested_followups"] == ["Lộ trình AI Engineer?"]
        mock_rag_chat_service.chat.assert_called_once()

    def test_chat_passes_history(self, active_client, mock_rag_chat_service):
        mock_rag_chat_service.chat.return_value = _chat_response_payload()

        resp = active_client.post(
            "/api/v1/ai/chat",
            json={
                "message": "Tiếp tục tư vấn",
                "history": [
                    {"role": "user", "content": "Xin chào"},
                    {"role": "assistant", "content": "Chào bạn!"},
                ],
            },
        )

        assert resp.status_code == 200
        kwargs = mock_rag_chat_service.chat.call_args.kwargs
        assert kwargs["message"] == "Tiếp tục tư vấn"
        assert len(kwargs["history"]) == 2
        assert kwargs["history"][0].role == "user"

    def test_chat_unauthorized(self, unauthorized_client):
        resp = unauthorized_client.post(
            "/api/v1/ai/chat", json={"message": "Xin chào"}
        )

        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_chat_empty_message_rejected(self, active_client):
        resp = active_client.post(
            "/api/v1/ai/chat", json={"message": ""}
        )

        assert resp.status_code == 422

    def test_chat_missing_message_rejected(self, active_client):
        resp = active_client.post("/api/v1/ai/chat", json={})

        assert resp.status_code == 422

    def test_chat_too_long_message_rejected(self, active_client):
        resp = active_client.post(
            "/api/v1/ai/chat", json={"message": "a" * 2001}
        )

        assert resp.status_code == 422

    def test_chat_history_over_limit_rejected(self, active_client):
        resp = active_client.post(
            "/api/v1/ai/chat",
            json={
                "message": "Xin chào",
                "history": [
                    {"role": "user", "content": "x"}
                    for _ in range(11)
                ],
            },
        )

        assert resp.status_code == 422

    def test_chat_empty_document_maps_to_400(
        self, active_client, mock_rag_chat_service
    ):
        mock_rag_chat_service.chat.side_effect = EmptyDocumentError(
            "Chat message cannot be empty"
        )

        resp = active_client.post(
            "/api/v1/ai/chat", json={"message": "Xin chào"}
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_chat_invalid_document_maps_to_400(
        self, active_client, mock_rag_chat_service
    ):
        mock_rag_chat_service.chat.side_effect = InvalidDocumentError(
            "Gemini API request failed"
        )

        resp = active_client.post(
            "/api/v1/ai/chat", json={"message": "Xin chào"}
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_chat_ai_failure_maps_to_502(
        self, active_client, mock_rag_chat_service
    ):
        mock_rag_chat_service.chat.side_effect = AIError("Qdrant down")

        resp = active_client.post(
            "/api/v1/ai/chat", json={"message": "Xin chào"}
        )

        assert resp.status_code == status.HTTP_502_BAD_GATEWAY

    def test_chat_accepts_candidate_role(
        self, candidate_client, mock_rag_chat_service
    ):
        mock_rag_chat_service.chat.return_value = _chat_response_payload()

        resp = candidate_client.post(
            "/api/v1/ai/chat", json={"message": "Xin chào"}
        )

        assert resp.status_code == 200

    def test_chat_accepts_recruiter_role(
        self, recruiter_client, mock_rag_chat_service
    ):
        mock_rag_chat_service.chat.return_value = _chat_response_payload()

        resp = recruiter_client.post(
            "/api/v1/ai/chat", json={"message": "Xin chào"}
        )

        assert resp.status_code == 200

    def test_chat_quota_exceeded_returns_429(
        self, active_client, mock_rag_chat_service
    ):
        """Test that AIProviderQuotaExceededError returns HTTP 429 with Retry-After header."""
        from app.core.exceptions import AIProviderQuotaExceededError

        mock_rag_chat_service.chat.side_effect = AIProviderQuotaExceededError(
            "AI provider quota exceeded.", retry_after=60
        )

        resp = active_client.post(
            "/api/v1/ai/chat", json={"message": "Xin chào"}
        )

        assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        body = resp.json()
        assert body["detail"] == "AI provider quota exceeded."
        assert resp.headers.get("Retry-After") == "60"


def _interview_question_payload():
    return {
        "question": "Explain how you handle React state.",
        "reason": "Because they have React experience",
        "category": "technical",
        "difficulty": "medium",
        "target_skill_or_topic": "React",
        "evaluation_criteria": "Demonstrates understanding of state management.",
        "sample_answer_points": ["Mentions hooks", "Explains trade-offs"],
    }


def _interview_response_payload():
    return {
        "job_title": "Senior Frontend Engineer",
        "candidate_title": "Frontend Engineer",
        "total_questions": 1,
        "questions": [_interview_question_payload()],
    }


def _interview_request_payload():
    return {
        "job": {
            "title": "Senior Frontend Engineer",
            "summary": "Build modern web applications with React.",
            "required_skills": ["React", "TypeScript"],
            "preferred_skills": ["Next.js"],
            "minimum_years_experience": 4,
        },
        "candidate": {
            "full_name": "John Doe",
            "title": "Frontend Engineer",
            "skills": ["React", "TypeScript"],
        },
        "num_questions": 5,
        "difficulty": "medium",
        "focus_areas": ["Performance"],
    }


class TestGenerateInterviewQuestions:
    def test_generate_questions_success(
        self, recruiter_client, mock_interview_generator_service
    ):
        mock_interview_generator_service.generate_questions.return_value = (
            _interview_response_payload()
        )

        resp = recruiter_client.post(
            "/api/v1/ai/generate-interview-questions",
            json=_interview_request_payload(),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["job_title"] == "Senior Frontend Engineer"
        assert body["total_questions"] == 1
        assert body["questions"][0]["category"] == "technical"
        mock_interview_generator_service.generate_questions.assert_called_once()

    def test_generate_questions_passes_config(
        self, recruiter_client, mock_interview_generator_service
    ):
        mock_interview_generator_service.generate_questions.return_value = (
            _interview_response_payload()
        )

        resp = recruiter_client.post(
            "/api/v1/ai/generate-interview-questions",
            json=_interview_request_payload(),
        )

        assert resp.status_code == 200
        request = (
            mock_interview_generator_service.generate_questions.call_args.args[0]
        )
        assert request.num_questions == 5
        assert request.difficulty == "medium"
        assert request.focus_areas == ["Performance"]

    def test_generate_questions_admin_allowed(
        self, active_client, mock_interview_generator_service
    ):
        mock_interview_generator_service.generate_questions.return_value = (
            _interview_response_payload()
        )

        resp = active_client.post(
            "/api/v1/ai/generate-interview-questions",
            json=_interview_request_payload(),
        )

        assert resp.status_code == 200
        mock_interview_generator_service.generate_questions.assert_called_once()

    def test_generate_questions_anonymous_unauthorized(
        self, unauthorized_client, mock_interview_generator_service
    ):
        resp = unauthorized_client.post(
            "/api/v1/ai/generate-interview-questions",
            json=_interview_request_payload(),
        )

        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        mock_interview_generator_service.generate_questions.assert_not_called()

    def test_generate_questions_candidate_forbidden(
        self, candidate_client, mock_interview_generator_service
    ):
        resp = candidate_client.post(
            "/api/v1/ai/generate-interview-questions",
            json=_interview_request_payload(),
        )

        assert resp.status_code == status.HTTP_403_FORBIDDEN
        mock_interview_generator_service.generate_questions.assert_not_called()

    def test_generate_questions_invalid_difficulty_rejected(
        self, recruiter_client, mock_interview_generator_service
    ):
        payload = _interview_request_payload()
        payload["difficulty"] = "expert"

        resp = recruiter_client.post(
            "/api/v1/ai/generate-interview-questions", json=payload
        )

        assert resp.status_code == 422
        mock_interview_generator_service.generate_questions.assert_not_called()

    def test_generate_questions_num_questions_out_of_range_rejected(
        self, recruiter_client, mock_interview_generator_service
    ):
        payload = _interview_request_payload()
        payload["num_questions"] = 0

        resp = recruiter_client.post(
            "/api/v1/ai/generate-interview-questions", json=payload
        )

        assert resp.status_code == 422
        mock_interview_generator_service.generate_questions.assert_not_called()

    def test_generate_questions_missing_job_rejected(
        self, recruiter_client, mock_interview_generator_service
    ):
        payload = _interview_request_payload()
        payload.pop("job")

        resp = recruiter_client.post(
            "/api/v1/ai/generate-interview-questions", json=payload
        )

        assert resp.status_code == 422
        mock_interview_generator_service.generate_questions.assert_not_called()

    def test_generate_questions_empty_job_maps_to_400(
        self, recruiter_client, mock_interview_generator_service
    ):
        mock_interview_generator_service.generate_questions.side_effect = (
            EmptyDocumentError("job has no content to generate questions from")
        )

        resp = recruiter_client.post(
            "/api/v1/ai/generate-interview-questions",
            json=_interview_request_payload(),
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_generate_questions_invalid_llm_response_maps_to_422(
        self, recruiter_client, mock_interview_generator_service
    ):
        mock_interview_generator_service.generate_questions.side_effect = (
            InvalidDocumentError("AI interview generator returned no questions")
        )

        resp = recruiter_client.post(
            "/api/v1/ai/generate-interview-questions",
            json=_interview_request_payload(),
        )

        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_generate_questions_ai_failure_maps_to_502(
        self, recruiter_client, mock_interview_generator_service
    ):
        mock_interview_generator_service.generate_questions.side_effect = AIError(
            "Gemini API request failed"
        )

        resp = recruiter_client.post(
            "/api/v1/ai/generate-interview-questions",
            json=_interview_request_payload(),
        )

        assert resp.status_code == status.HTTP_502_BAD_GATEWAY

    def test_generate_questions_quota_exceeded_returns_429(
        self, recruiter_client, mock_interview_generator_service
    ):
        from app.core.exceptions import AIProviderQuotaExceededError
        mock_interview_generator_service.generate_questions.side_effect = (
            AIProviderQuotaExceededError("AI provider quota exceeded", retry_after=60)
        )

        resp = recruiter_client.post(
            "/api/v1/ai/generate-interview-questions",
            json=_interview_request_payload(),
        )

        assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert resp.headers.get("Retry-After") == "60"

    def test_generate_questions_provider_unavailable_returns_503(
        self, recruiter_client, mock_interview_generator_service
    ):
        from app.core.exceptions import AIProviderUnavailableError
        mock_interview_generator_service.generate_questions.side_effect = (
            AIProviderUnavailableError("AI provider temporarily unavailable", retry_after=30)
        )

        resp = recruiter_client.post(
            "/api/v1/ai/generate-interview-questions",
            json=_interview_request_payload(),
        )

        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert resp.headers.get("Retry-After") == "30"

    def test_generate_questions_generic_ai_error_returns_502(
        self, recruiter_client, mock_interview_generator_service
    ):
        from app.core.exceptions import AIError
        mock_interview_generator_service.generate_questions.side_effect = AIError(
            "Generic AI provider error"
        )

        resp = recruiter_client.post(
            "/api/v1/ai/generate-interview-questions",
            json=_interview_request_payload(),
        )

        assert resp.status_code == status.HTTP_502_BAD_GATEWAY


class TestParseJDValidation:
    """Tests for ParseJDRequest validation (SECURITY-06)."""

    def test_valid_job_description_accepted(self, recruiter_client, mock_service):
        """Valid job description under 30k chars is accepted."""
        mock_service.process_and_index_job.return_value = _parsed_job()

        resp = recruiter_client.post(
            "/api/v1/ai/parse-jd",
            json={
                "job_title": "Backend Engineer",
                "job_description": "Build robust APIs with Python and FastAPI",
            },
        )

        assert resp.status_code == 200
        assert resp.json()["title"] == "Backend Engineer"

    def test_job_description_exactly_30000_chars_accepted(self, recruiter_client, mock_service):
        """Job description at exactly 30,000 characters is accepted."""
        mock_service.process_and_index_job.return_value = _parsed_job()

        desc = "A" * 30000
        resp = recruiter_client.post(
            "/api/v1/ai/parse-jd",
            json={
                "job_title": "Backend Engineer",
                "job_description": desc,
            },
        )

        assert resp.status_code == 200

    def test_job_description_over_30000_chars_rejected(self, recruiter_client, mock_service):
        """Job description over 30,000 characters is rejected with 422."""
        mock_service.process_and_index_job.return_value = _parsed_job()

        desc = "A" * 30001
        resp = recruiter_client.post(
            "/api/v1/ai/parse-jd",
            json={
                "job_title": "Backend Engineer",
                "job_description": desc,
            },
        )

        assert resp.status_code == 422

    def test_ai_service_not_called_for_oversized_job_description(self, recruiter_client, mock_service):
        """AI service is not called for oversized job description."""
        mock_service.process_and_index_job.return_value = _parsed_job()

        desc = "A" * 30001
        resp = recruiter_client.post(
            "/api/v1/ai/parse-jd",
            json={
                "job_title": "Backend Engineer",
                "job_description": desc,
            },
        )

        assert resp.status_code == 422
        mock_service.process_and_index_job.assert_not_called()