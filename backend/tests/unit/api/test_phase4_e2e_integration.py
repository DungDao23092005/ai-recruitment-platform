from __future__ import annotations

import hashlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.ai.embeddings.embedding_service import EmbeddingService
from app.ai.interfaces.base_provider import (
    BaseEmbeddingProvider,
    BaseLLMProvider,
    BaseVectorRepository,
)
from app.ai.matching.cosine_engine import compute_cosine_similarity
from app.ai.matching.matching_engine import MatchingEngine
from app.ai.parsers.job_parser import JobParser
from app.ai.parsers.resume_parser import ResumeParser
from app.api.deps import get_current_user, get_db
from app.api.v1.endpoints.ai import (
    _get_ai_service,
    _get_explainable_ai_service,
    _get_interview_generator_service,
    _get_rag_chat_service,
    _get_semantic_search_service,
)
from app.api.v1.endpoints.admin import _get_admin_service
from app.core.config import settings
from app.core.exceptions import EmptyDocumentError
from app.domain.enums import JobStatus, UserRole
from app.main import app
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.ai_matching_service import AIMatchingService

VECTOR_DIM = settings.VECTOR_DIMENSION

KNOWN_CANDIDATE_ID = uuid.uuid4()
KNOWN_JOB_ID = uuid.uuid4()
KNOWN_COMPANY_ID = uuid.uuid4()

MINIMAL_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n"
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
    b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\n"
    b"endobj\n"
    b"4 0 obj\n<< /Length 100 >>\nstream\n"
    b"BT\n/F1 12 Tf\n72 720 Td\n"
    b"(John Doe - Senior Python Developer) Tj\n"
    b"0 -14 Td\n(Skills: Python, FastAPI) Tj\n"
    b"ET\nendstream\nendobj\n"
    b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    b"trailer\n<< /Size 6 /Root 1 0 R >>\n%%EOF\n"
)

EXPECTED_RESUME = ParsedResumeSchema(
    full_name="John Doe",
    title="Senior Python Developer",
    summary="Experienced Python developer with FastAPI and SQL Server.",
    total_years_experience=5.0,
    skills=["Python", "FastAPI", "SQL Server"],
)

EXPECTED_JOB = ParsedJobSchema(
    title="Senior Python Developer",
    summary="Backend role focused on Python and FastAPI.",
    required_skills=["Python", "FastAPI", "Docker"],
    preferred_skills=["GraphQL"],
    minimum_years_experience=3.0,
)


class FakeLLMProvider(BaseLLMProvider):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate_structured_output(
        self,
        prompt: str,
        response_schema,
        system_instruction: str | None = None,
    ):
        self.prompts.append(prompt)
        if response_schema is ParsedResumeSchema:
            return EXPECTED_RESUME
        if response_schema is ParsedJobSchema:
            return EXPECTED_JOB
        raise EmptyDocumentError("Unsupported response schema")


class FakeEmbeddingProvider(BaseEmbeddingProvider):
    def embed_text(self, text: str) -> list[float]:
        return self._hash_vector(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_vector(text) for text in texts]

    @staticmethod
    def _hash_vector(text: str, dim: int = VECTOR_DIM) -> list[float]:
        vector = [0.0] * dim
        for token in text.lower().replace(",", " ").replace(":", " ").split():
            index = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % dim
            vector[index] += 1.0
        return vector


class FakeVectorRepository(BaseVectorRepository):
    def __init__(self) -> None:
        self.store: dict[tuple[str, str], tuple[list[float], dict]] = {}

    async def upsert_vector(self, collection_name, point_id, vector, payload) -> None:
        self.store[(collection_name, str(point_id))] = (vector, payload)

    async def delete_vector(self, collection_name, point_id) -> None:
        self.store.pop((collection_name, str(point_id)), None)

    async def retrieve_vector(self, collection_name, point_id) -> dict | None:
        entry = self.store.get((collection_name, str(point_id)))
        if entry is None:
            return None
        vector, payload = entry
        return {"id": str(point_id), "vector": vector, "payload": payload}

    async def search_similar(self, collection_name, query_vector, limit=10, filters=None):
        results = []
        for (col, pid), (vector, payload) in self.store.items():
            if col != collection_name:
                continue
            score = compute_cosine_similarity(query_vector, vector)
            results.append({"id": pid, "score": score, "payload": payload})
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:limit]


def build_pipeline_service() -> tuple[AIMatchingService, FakeVectorRepository]:
    llm = FakeLLMProvider()
    service = AIMatchingService(
        resume_parser=ResumeParser(llm_provider=llm),
        job_parser=JobParser(llm_provider=llm),
        embedding_service=EmbeddingService(FakeEmbeddingProvider()),
        vector_repository=FakeVectorRepository(),
        matching_engine=MatchingEngine(),
    )
    return service, service.vector_repository


class _FakeAttrs:
    def __init__(self, profile, recruiter_profile=None):
        self._profile = profile
        self._recruiter_profile = recruiter_profile

    @property
    def candidate_profile(self):
        async def _resolve():
            return self._profile

        return _resolve()

    @property
    def recruiter_profile(self):
        async def _resolve():
            return self._recruiter_profile

        return _resolve()


def make_user(
    role: UserRole, has_profile: bool = True, profile_id: uuid.UUID | None = None
) -> SimpleNamespace:
    profile = (
        SimpleNamespace(id=profile_id or KNOWN_CANDIDATE_ID)
        if has_profile
        else None
    )
    recruiter_profile = (
        SimpleNamespace(company_id=KNOWN_COMPANY_ID) if role == UserRole.RECRUITER else None
    )
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        is_active=True,
        awaitable_attrs=_FakeAttrs(profile, recruiter_profile),
    )


def override_user(user):
    async def _override():
        return user

    return _override


@pytest.fixture
def vector_repository():
    return FakeVectorRepository()


@pytest.fixture
def pipeline_service(vector_repository):
    llm = FakeLLMProvider()
    return AIMatchingService(
        resume_parser=ResumeParser(llm_provider=llm),
        job_parser=JobParser(llm_provider=llm),
        embedding_service=EmbeddingService(FakeEmbeddingProvider()),
        vector_repository=vector_repository,
        matching_engine=MatchingEngine(),
    )


def _mock_explain_service():
    service = MagicMock()
    service.explain_match = AsyncMock(
        return_value={
            "summary": "Good match.",
            "strengths": ["Python"],
            "skill_gaps": ["Docker"],
            "experience_analysis": "5 years vs 3 required.",
            "recommendation": "Proceed.",
        }
    )
    return service


def _mock_search_service():
    service = MagicMock()
    payload = [
        {
            "id": "point-1",
            "score": 0.9,
            "skills": ["Python"],
            "created_at": None,
        }
    ]
    service.search_jobs = AsyncMock(return_value=payload)
    service.search_candidates = AsyncMock(return_value=payload)
    return service


def _mock_rag_chat_service():
    service = MagicMock()
    service.chat = AsyncMock(
        return_value={
            "reply": "Dựa trên dữ kiện, hãy học Python.",
            "sources": [],
            "suggested_followups": [],
        }
    )
    return service


def _mock_interview_generator_service():
    service = MagicMock()
    service.generate_questions = AsyncMock(
        return_value={
            "job_title": "Senior Python Developer",
            "candidate_title": None,
            "total_questions": 1,
            "questions": [
                {
                    "question": "Explain Python async.",
                    "category": "technical",
                    "difficulty": "medium",
                    "target_skill_or_topic": "Python",
                    "evaluation_criteria": "Shows async understanding.",
                    "sample_answer_points": ["asyncio", "event loop"],
                }
            ],
        }
    )
    return service


def _mock_admin_service():
    service = MagicMock()
    service.get_stats = AsyncMock(
        return_value={
            "total_users": 5,
            "total_candidates": 2,
            "total_recruiters": 2,
            "total_admins": 1,
            "total_companies": 1,
            "total_jobs": 2,
            "total_applications": 3,
            "applications_by_status": {
                "applied": 1,
                "under_review": 1,
                "shortlisted": 1,
                "interviewing": 0,
                "accepted": 0,
                "rejected": 0,
                "withdrawn": 0,
            },
        }
    )
    return service


def _make_db_job() -> MagicMock:
    job = MagicMock()
    job.id = KNOWN_JOB_ID
    job.company_id = KNOWN_COMPANY_ID
    job.title = "Senior Python Developer"
    job.description = "Backend role focused on Python and FastAPI."
    job.status = JobStatus.PUBLISHED
    job.is_deleted = False
    job.company = SimpleNamespace(id=KNOWN_COMPANY_ID, name="TechNova AI")
    job.skills = []
    return job


def _make_db_user(role: UserRole = UserRole.RECRUITER) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.recruiter_profile = SimpleNamespace(company_id=KNOWN_COMPANY_ID)
    user.candidate_profile = SimpleNamespace(id=KNOWN_CANDIDATE_ID)
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
def client(pipeline_service):
    store = pipeline_service.vector_repository.store
    store[("resumes", str(KNOWN_CANDIDATE_ID))] = (
        FakeEmbeddingProvider._hash_vector("Python FastAPI SQL Server"),
        {
            "candidate_id": str(KNOWN_CANDIDATE_ID),
            "skills": ["Python", "FastAPI", "SQL Server"],
            "is_deleted": False,
        },
    )
    store[("jobs", str(KNOWN_JOB_ID))] = (
        FakeEmbeddingProvider._hash_vector("Python FastAPI Docker"),
        {
            "job_id": str(KNOWN_JOB_ID),
            "skills": ["Python", "FastAPI", "Docker"],
            "is_deleted": False,
        },
    )
    app.dependency_overrides[_get_ai_service] = lambda: pipeline_service
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_get_explainable_ai_service] = (
        lambda: _mock_explain_service()
    )
    app.dependency_overrides[_get_semantic_search_service] = (
        lambda: _mock_search_service()
    )
    app.dependency_overrides[_get_rag_chat_service] = (
        lambda: _mock_rag_chat_service()
    )
    app.dependency_overrides[_get_interview_generator_service] = (
        lambda: _mock_interview_generator_service()
    )
    app.dependency_overrides[_get_admin_service] = lambda: _mock_admin_service()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _set_user(client, user):
    app.dependency_overrides[get_current_user] = override_user(user)


def _set_anonymous(client):
    async def _raise():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    app.dependency_overrides[get_current_user] = _raise


@pytest.fixture
def candidate_client(client):
    _set_user(client, make_user(UserRole.CANDIDATE))
    yield client


@pytest.fixture
def recruiter_client(client):
    _set_user(client, make_user(UserRole.RECRUITER))
    yield client


@pytest.fixture
def admin_client(client):
    _set_user(client, make_user(UserRole.ADMIN))
    yield client


@pytest.fixture
def anonymous_client(client):
    _set_anonymous(client)
    yield client


def _resume_payload() -> dict:
    return {
        "full_name": "Jane Doe",
        "title": "Backend Engineer",
        "skills": ["Python", "FastAPI"],
        "total_years_experience": 4.0,
    }


def _job_payload() -> dict:
    return {
        "title": "Backend Engineer",
        "summary": "Build robust APIs.",
        "required_skills": ["Python", "FastAPI"],
        "preferred_skills": ["GraphQL"],
        "minimum_years_experience": 3.0,
    }


def _match_result_payload() -> dict:
    return {
        "overall_score": 80.0,
        "cosine_similarity": 0.8,
        "skill_coverage_score": 0.8,
        "experience_match_score": 0.75,
        "matching_skills": ["Python"],
        "skill_gap": ["Docker"],
        "match_reasons": ["Strong overlap"],
    }


def _interview_request() -> dict:
    return {
        "job": _job_payload(),
        "num_questions": 5,
        "difficulty": "medium",
        "focus_areas": [],
    }


class TestApiRegression:
    def test_ai_routes_registered(self):
        from app.api.v1.endpoints.ai import router

        routes = {(r.path, tuple(sorted(r.methods or []))) for r in router.routes}
        expected = {
            ("/parse-resume", ("POST",)),
            ("/parse-jd", ("POST",)),
            ("/match", ("POST",)),
            ("/explain-match", ("POST",)),
            ("/recommendations/jobs", ("GET",)),
            ("/chat", ("POST",)),
            ("/generate-interview-questions", ("POST",)),
            ("/search/jobs", ("GET",)),
            ("/search/candidates", ("GET",)),
            ("/recommendations/candidates", ("GET",)),
        }
        assert expected.issubset(routes)

    def test_health_endpoint_is_healthy(self, client):
        resp = client.get("/api/v1/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["service"] == "AI Recruitment Platform API"


ACCESS_MATRIX = [
    # (method, path, request kwargs, candidate, recruiter, admin, anonymous)
    (
        "post",
        "/api/v1/ai/parse-resume",
        {"files": {"file": ("resume.pdf", MINIMAL_PDF_BYTES, "application/pdf")}},
        200,
        403,
        200,
        401,
    ),
    (
        "post",
        "/api/v1/ai/parse-jd",
        {"json": {"job_title": "Backend", "job_description": "Python APIs"}},
        403,
        200,
        200,
        401,
    ),
    (
        "post",
        "/api/v1/ai/match",
        {
            "json": {
                "parsed_resume": _resume_payload(),
                "parsed_job": _job_payload(),
            }
        },
        200,
        200,
        200,
        401,
    ),
    (
        "post",
        "/api/v1/ai/explain-match",
        {
            "json": {
                "match_result": _match_result_payload(),
                "candidate": _resume_payload(),
                "job": _job_payload(),
            }
        },
        200,
        200,
        200,
        401,
    ),
    ("post", "/api/v1/ai/chat", {"json": {"message": "Xin chào"}}, 200, 200, 200, 401),
    (
        "post",
        "/api/v1/ai/generate-interview-questions",
        {"json": _interview_request()},
        403,
        200,
        200,
        401,
    ),
    ("get", "/api/v1/ai/search/jobs", {"params": {"q": "python"}}, 200, 200, 200, 401),
    (
        "get",
        "/api/v1/ai/search/candidates",
        {"params": {"q": "python"}},
        403,
        200,
        200,
        401,
    ),
    (
        "get",
        "/api/v1/ai/recommendations/jobs",
        {"params": {"limit": 5}},
        200,
        403,
        200,
        401,
    ),
    (
        "get",
        "/api/v1/ai/recommendations/candidates",
        {"params": {"job_id": str(KNOWN_JOB_ID), "limit": 5}},
        403,
        200,
        200,
        401,
    ),
]

ACCESS_FIXTURES = {
    "candidate": "candidate_client",
    "recruiter": "recruiter_client",
    "admin": "admin_client",
    "anonymous": "anonymous_client",
}


class TestAccessMatrix:
    @pytest.mark.parametrize("method,path,kwargs,c,s,r,a", ACCESS_MATRIX)
    def test_role_access_matrix(
        self, request, client, method, path, kwargs, c, s, r, a
    ):
        expected = {"candidate": c, "recruiter": s, "admin": r, "anonymous": a}
        for role, expected_status in expected.items():
            if role == "anonymous":
                _set_anonymous(client)
            else:
                _set_user(client, make_user(getattr(UserRole, role.upper())))
            resp = getattr(client, method)(path, **kwargs)
            assert resp.status_code == expected_status, (
                f"{method.upper()} {path} as {role}: expected "
                f"{expected_status}, got {resp.status_code}"
            )


class TestCandidateFlow:
    def test_candidate_full_pipeline(self, candidate_client, vector_repository):
        resp = candidate_client.post(
            "/api/v1/ai/parse-resume",
            files={"file": ("resume.pdf", MINIMAL_PDF_BYTES, "application/pdf")},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["full_name"] == "John Doe"
        assert "Python" in body["skills"]

        resume_keys = [k for k in vector_repository.store.keys() if k[0] == "resumes"]
        assert len(resume_keys) == 1
        stored_vector, stored_payload = vector_repository.store[resume_keys[0]]
        assert len(stored_vector) == VECTOR_DIM
        assert stored_payload["skills"] == ["Python", "FastAPI", "SQL Server"]

    def test_candidate_match_uses_real_engine(self, candidate_client):
        resp = candidate_client.post(
            "/api/v1/ai/match",
            json={
                "parsed_resume": _resume_payload(),
                "parsed_job": _job_payload(),
                "resume_vector": FakeEmbeddingProvider._hash_vector(
                    "Python FastAPI"
                ),
                "job_vector": FakeEmbeddingProvider._hash_vector("Python FastAPI"),
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert 0.0 <= body["overall_score"] <= 100.0
        assert "Python" in body["matching_skills"]

    def test_candidate_explain_match(self, candidate_client):
        resp = candidate_client.post(
            "/api/v1/ai/explain-match",
            json={
                "match_result": _match_result_payload(),
                "candidate": _resume_payload(),
                "job": _job_payload(),
            },
        )

        assert resp.status_code == 200
        assert resp.json()["recommendation"] == "Proceed."

    def test_candidate_chat(self, candidate_client):
        resp = candidate_client.post(
            "/api/v1/ai/chat", json={"message": "Tư vấn lộ trình"}
        )

        assert resp.status_code == 200
        assert resp.json()["reply"].startswith("Dựa trên dữ kiện")

    def test_candidate_search_jobs(self, candidate_client):
        resp = candidate_client.get("/api/v1/ai/search/jobs", params={"q": "python"})

        assert resp.status_code == 200
        assert resp.json()[0]["id"] == "point-1"

    def test_candidate_job_recommendations_require_parsed_resume(
        self, candidate_client
    ):
        resp = candidate_client.get(
            "/api/v1/ai/recommendations/jobs", params={"limit": 5}
        )

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert body[0]["job_id"] == str(KNOWN_JOB_ID)


class TestRecruiterFlow:
    def test_recruiter_parse_jd_indexes_vector(
        self, recruiter_client, vector_repository
    ):
        job_keys_before = [
            k for k in vector_repository.store.keys() if k[0] == "jobs"
        ]

        resp = recruiter_client.post(
            "/api/v1/ai/parse-jd",
            json={
                "job_title": "Senior Python Developer",
                "job_description": (
                    "We are hiring a Senior Python Developer with FastAPI and "
                    "SQL Server experience. 3+ years required."
                ),
            },
        )

        assert resp.status_code == 200
        assert resp.json()["title"] == "Senior Python Developer"

        job_keys_after = [
            k for k in vector_repository.store.keys() if k[0] == "jobs"
        ]
        assert len(job_keys_after) == len(job_keys_before) + 1
        added = [k for k in job_keys_after if k not in job_keys_before]
        stored_vector, stored_payload = vector_repository.store[added[0]]
        assert len(stored_vector) == VECTOR_DIM
        assert stored_payload["job_id"] == added[0][1]
        assert "Python" in stored_payload["skills"]

    def test_recruiter_search_candidates(self, recruiter_client):
        resp = recruiter_client.get(
            "/api/v1/ai/search/candidates", params={"q": "python"}
        )

        assert resp.status_code == 200
        assert resp.json()[0]["id"] == "point-1"

    def test_recruiter_candidate_recommendations(self, recruiter_client):
        resp = recruiter_client.get(
            "/api/v1/ai/recommendations/candidates",
            params={"job_id": str(KNOWN_JOB_ID), "limit": 5},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert body[0]["candidate_id"] == str(KNOWN_CANDIDATE_ID)

    def test_recruiter_generate_interview_questions(self, recruiter_client):
        resp = recruiter_client.post(
            "/api/v1/ai/generate-interview-questions",
            json=_interview_request(),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["job_title"] == "Senior Python Developer"
        assert body["questions"][0]["category"] == "technical"


class TestAdminFlow:
    def test_admin_stats(self, admin_client):
        resp = admin_client.get("/api/v1/admin/stats")

        assert resp.status_code == 200
        assert resp.json()["total_users"] == 5

    def test_admin_can_use_recruiter_endpoints(self, admin_client):
        resp = admin_client.post(
            "/api/v1/ai/parse-jd",
            json={"job_title": "Backend", "job_description": "Python APIs"},
        )

        assert resp.status_code == 200
        assert resp.json()["title"] == "Senior Python Developer"

    def test_admin_can_use_candidate_endpoints(self, admin_client):
        resp = admin_client.post(
            "/api/v1/ai/parse-resume",
            files={"file": ("resume.pdf", MINIMAL_PDF_BYTES, "application/pdf")},
        )

        assert resp.status_code == 200
        assert resp.json()["full_name"] == "John Doe"


class TestAiPipelineIntegration:
    def test_indexed_resume_can_be_matched(self, vector_repository):
        resume = ParsedResumeSchema(
            full_name="Alice",
            skills=["Python", "FastAPI"],
            total_years_experience=4.0,
        )
        job = ParsedJobSchema(
            title="Python Backend",
            required_skills=["Python", "FastAPI"],
            preferred_skills=["GraphQL"],
            minimum_years_experience=3.0,
        )
        vector = FakeEmbeddingProvider._hash_vector("Python FastAPI")

        service = AIMatchingService(
            resume_parser=ResumeParser(llm_provider=FakeLLMProvider()),
            job_parser=JobParser(llm_provider=FakeLLMProvider()),
            embedding_service=EmbeddingService(FakeEmbeddingProvider()),
            vector_repository=vector_repository,
            matching_engine=MatchingEngine(),
        )
        result = service.match_candidate_with_job(
            parsed_resume=resume,
            parsed_job=job,
            resume_vector=vector,
            job_vector=vector,
        )

        assert isinstance(result, MatchResultSchema)
        assert 0.0 <= result.overall_score <= 100.0
        assert set(result.matching_skills) == {"Python", "FastAPI"}

    def test_search_similar_returns_ranked_results(self, vector_repository):
        for label in ["Python Developer", "Java Developer"]:
            vector_repository.store[("jobs", label)] = (
                FakeEmbeddingProvider._hash_vector(label),
                {"job_id": label, "skills": [label.split()[0]], "is_deleted": False},
            )

        results = asyncio_run(
            vector_repository.search_similar(
                "jobs", FakeEmbeddingProvider._hash_vector("Python"), limit=5
            )
        )

        assert len(results) == 2
        assert results[0]["score"] >= results[1]["score"]

    def test_malformed_pdf_maps_to_422(self, candidate_client):
        resp = candidate_client.post(
            "/api/v1/ai/parse-resume",
            files={"file": ("blank.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )

        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_empty_job_description_maps_to_400(self, recruiter_client):
        resp = recruiter_client.post(
            "/api/v1/ai/parse-jd",
            json={"job_title": "Backend", "job_description": "   "},
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
