from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
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
    InvalidDocumentError,
)
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
def client(
    mock_service,
    mock_explain_service,
    mock_search_service,
    mock_rag_chat_service,
    mock_interview_generator_service,
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


def _match_result_payload():
    return {
        "overall_score": 82.0,
        "cosine_similarity": 0.85,
        "skill_coverage_score": 0.8,
        "experience_match_score": 0.75,
        "matching_skills": ["React", "TypeScript"],
        "skill_gap": ["GraphQL"],
        "match_reasons": ["Strong skill overlap"],
    }


def _explain_response_payload():
    return {
        "summary": "The candidate matches the role well.",
        "strengths": ["Strong overlap in React and TypeScript"],
        "skill_gaps": ["GraphQL"],
        "experience_analysis": "Candidate has 5 years experience vs 4 required.",
        "recommendation": "Proceed to interview.",
    }


class TestExplainMatch:
    def test_explain_match_success(self, active_client, mock_explain_service):
        mock_explain_service.explain_match.return_value = (
            _explain_response_payload()
        )

        resp = active_client.post(
            "/api/v1/ai/explain-match",
            json={
                "match_result": _match_result_payload(),
                "candidate": _parsed_resume(),
                "job": _parsed_job(),
            },
        )

        assert resp.status_code == 200
        assert resp.json()["summary"] == "The candidate matches the role well."
        assert resp.json()["strengths"] == [
            "Strong overlap in React and TypeScript"
        ]
        mock_explain_service.explain_match.assert_called_once()

    def test_explain_match_accepts_candidate_and_job_null(
        self, active_client, mock_explain_service
    ):
        mock_explain_service.explain_match.return_value = (
            _explain_response_payload()
        )

        resp = active_client.post(
            "/api/v1/ai/explain-match",
            json={"match_result": _match_result_payload()},
        )

        assert resp.status_code == 200
        mock_explain_service.explain_match.assert_called_once()

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

    def test_explain_match_empty_document_maps_to_400(
        self, active_client, mock_explain_service
    ):
        mock_explain_service.explain_match.side_effect = EmptyDocumentError(
            "match_result has no overall_score to explain"
        )

        resp = active_client.post(
            "/api/v1/ai/explain-match",
            json={"match_result": _match_result_payload()},
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "overall_score" in resp.json()["detail"]

    def test_explain_match_invalid_document_maps_to_422(
        self, active_client, mock_explain_service
    ):
        mock_explain_service.explain_match.side_effect = InvalidDocumentError(
            "AI explanation returned an empty summary"
        )

        resp = active_client.post(
            "/api/v1/ai/explain-match",
            json={"match_result": _match_result_payload()},
        )

        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "empty summary" in resp.json()["detail"]

    def test_explain_match_accepts_admin_role(
        self, active_client, mock_explain_service
    ):
        mock_explain_service.explain_match.return_value = (
            _explain_response_payload()
        )

        resp = active_client.post(
            "/api/v1/ai/explain-match",
            json={"match_result": _match_result_payload()},
        )

        assert resp.status_code == 200

    def test_explain_match_accepts_candidate_role(
        self, candidate_client, mock_explain_service
    ):
        mock_explain_service.explain_match.return_value = (
            _explain_response_payload()
        )

        resp = candidate_client.post(
            "/api/v1/ai/explain-match",
            json={"match_result": _match_result_payload()},
        )

        assert resp.status_code == 200

    def test_explain_match_accepts_recruiter_role(
        self, recruiter_client, mock_explain_service
    ):
        mock_explain_service.explain_match.return_value = (
            _explain_response_payload()
        )

        resp = recruiter_client.post(
            "/api/v1/ai/explain-match",
            json={"match_result": _match_result_payload()},
        )

        assert resp.status_code == 200


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
        "reply": "Dựa trên dữ kiện được cung cấp, bạn nên tập trung vào Python.",
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
        assert body["reply"].startswith("Dựa trên dữ kiện")
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


def _interview_question_payload():
    return {
        "question": "Explain how you handle React state.",
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