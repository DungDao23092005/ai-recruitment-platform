from __future__ import annotations

import hashlib
import inspect
import uuid

import pytest

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
from app.ai.extractors.pdf_extractor import PDFTextExtractor
from app.core.config import settings
from app.core.exceptions import (
    EmptyDocumentError,
    EntityNotFoundException,
    InvalidDocumentError,
)
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.ai_matching_service import AIMatchingService

VECTOR_DIM = settings.VECTOR_DIMENSION

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
    """Deterministic LLM stub that records every prompt it receives."""

    def __init__(
        self,
        resume_schema: ParsedResumeSchema,
        job_schema: ParsedJobSchema,
    ) -> None:
        self.resume_schema = resume_schema
        self.job_schema = job_schema
        self.prompts: list[str] = []

    async def generate_structured_output(
        self,
        prompt: str,
        response_schema,
        system_instruction: str | None = None,
    ):
        self.prompts.append(prompt)
        if response_schema is ParsedResumeSchema:
            return self.resume_schema
        if response_schema is ParsedJobSchema:
            return self.job_schema
        raise InvalidDocumentError("Unsupported response schema")


class FakeEmbeddingProvider(BaseEmbeddingProvider):
    """Deterministic embedding stub producing VECTOR_DIM vectors."""

    async def embed_text(self, text: str) -> list[float]:
        return self._hash_vector(text)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_vector(text) for text in texts]

    @staticmethod
    def _hash_vector(text: str, dim: int = VECTOR_DIM) -> list[float]:
        vector = [0.0] * dim
        for token in text.lower().replace(",", " ").replace(":", " ").split():
            index = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % dim
            vector[index] += 1.0
        return vector


class FakeVectorRepository(BaseVectorRepository):
    """In-memory vector repository storing (vector, payload) by point ID."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], tuple[list[float], dict]] = {}

    async def upsert_vector(
        self,
        collection_name: str,
        point_id: str | uuid.UUID,
        vector: list[float],
        payload: dict,
    ) -> None:
        self.store[(collection_name, str(point_id))] = (vector, payload)

    async def delete_vector(
        self,
        collection_name: str,
        point_id: str | uuid.UUID,
    ) -> None:
        self.store.pop((collection_name, str(point_id)), None)

    async def delete_vectors_by_filter(
        self,
        collection_name: str,
        filter_key: str,
        filter_value: Any,
    ) -> None:
        keys_to_delete = [
            (col, pid)
            for (col, pid), (_, payload) in self.store.items()
            if col == collection_name and payload.get(filter_key) == filter_value
        ]
        for key in keys_to_delete:
            self.store.pop(key, None)

    async def retrieve_vector(
        self,
        collection_name: str,
        point_id: str | uuid.UUID,
    ) -> dict | None:
        entry = self.store.get((collection_name, str(point_id)))
        if entry is None:
            return None
        vector, payload = entry
        return {"id": str(point_id), "vector": vector, "payload": payload}

    async def search_similar(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        filters: dict | None = None,
    ) -> list[dict]:
        results = []
        for (col, pid), (vector, payload) in self.store.items():
            if col != collection_name:
                continue
            score = compute_cosine_similarity(query_vector, vector)
            results.append(
                {"id": pid, "score": score, "vector": vector, "payload": payload}
            )
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:limit]


@pytest.fixture
def pipeline() -> dict:
    llm = FakeLLMProvider(
        resume_schema=EXPECTED_RESUME,
        job_schema=EXPECTED_JOB,
    )
    embeddings = EmbeddingService(FakeEmbeddingProvider())
    vector_repository = FakeVectorRepository()
    service = AIMatchingService(
        resume_parser=ResumeParser(llm_provider=llm),
        job_parser=JobParser(llm_provider=llm),
        embedding_service=embeddings,
        vector_repository=vector_repository,
        matching_engine=MatchingEngine(),
    )
    return {
        "llm": llm,
        "service": service,
        "vector_repository": vector_repository,
        "resume_parser": service.resume_parser,
        "job_parser": service.job_parser,
    }


class TestResumePipeline:
    @pytest.mark.asyncio
    async def test_resume_pipeline_indexes_pdf(self, pipeline):
        candidate_id = uuid.uuid4()
        service = pipeline["service"]
        llm = pipeline["llm"]
        vector_repository = pipeline["vector_repository"]

        result = await service.process_and_index_resume(
            candidate_id=candidate_id,
            pdf_source=MINIMAL_PDF_BYTES,
        )

        assert result == EXPECTED_RESUME
        assert result.full_name == "John Doe"
        assert result.skills == ["Python", "FastAPI", "SQL Server"]

        assert llm.prompts, "ResumeParser should have received a prompt"
        assert "John Doe" in llm.prompts[0], (
            "ResumeParser should receive extracted PDF text"
        )

        key = ("resumes", str(candidate_id))
        assert key in vector_repository.store
        stored_vector, stored_payload = vector_repository.store[key]
        assert len(stored_vector) == VECTOR_DIM == 384
        assert stored_payload["candidate_id"] == str(candidate_id)
        assert stored_payload["skills"] == ["Python", "FastAPI", "SQL Server"]
        assert stored_payload["is_deleted"] is False


class TestJobPipeline:
    @pytest.mark.asyncio
    async def test_job_pipeline_indexes_jd(self, pipeline):
        job_id = uuid.uuid4()
        service = pipeline["service"]
        llm = pipeline["llm"]
        vector_repository = pipeline["vector_repository"]

        result = await service.process_and_index_job(
            job_id=job_id,
            job_title="Senior Python Developer",
            job_description=(
                "We are hiring a Senior Python Developer with FastAPI and "
                "SQL Server experience. 3+ years required."
            ),
        )

        assert result == EXPECTED_JOB
        assert result.title == "Senior Python Developer"
        assert result.required_skills == ["Python", "FastAPI", "Docker"]

        assert llm.prompts, "JobParser should have received a prompt"
        assert "JOB DESCRIPTION TEXT" in llm.prompts[-1]

        key = ("jobs", str(job_id))
        assert key in vector_repository.store
        stored_vector, stored_payload = vector_repository.store[key]
        assert len(stored_vector) == VECTOR_DIM == 384
        assert stored_payload["job_id"] == str(job_id)
        assert "Python" in stored_payload["skills"]
        assert stored_payload["is_deleted"] is False


class TestMatchingPipeline:
    @pytest.mark.asyncio
    async def test_full_matching_uses_real_engine(self, pipeline):
        resume = ParsedResumeSchema(
            full_name="Alice",
            skills=["Python", "FastAPI", "Docker"],
            total_years_experience=4.0,
        )
        job = ParsedJobSchema(
            title="Python Backend",
            required_skills=["Python", "FastAPI", "Docker"],
            preferred_skills=["GraphQL"],
            minimum_years_experience=3.0,
        )
        resume_vector = FakeEmbeddingProvider._hash_vector("Python FastAPI Docker")
        job_vector = FakeEmbeddingProvider._hash_vector("Python FastAPI Docker")

        result = await pipeline["service"].match_candidate_with_job(
            parsed_resume=resume,
            parsed_job=job,
            resume_vector=resume_vector,
            job_vector=job_vector,
        )

        assert isinstance(result, MatchResultSchema)
        assert 0.0 <= result.overall_score <= 100.0
        assert 0.0 <= result.cosine_similarity <= 1.0
        assert 0.0 <= result.skill_coverage_score <= 1.0
        assert 0.0 <= result.experience_match_score <= 1.0
        assert set(result.matching_skills) == {"Python", "FastAPI", "Docker"}
        assert result.skill_gap == []
        assert result.match_reasons, "match_reasons should be populated"


class TestRecommendJobs:
    @pytest.mark.asyncio
    async def test_recommend_jobs_ranked_descending(self, pipeline):
        service = pipeline["service"]
        candidate_id = uuid.uuid4()
        parsed_resume = ParsedResumeSchema(
            full_name="Bob",
            skills=["Python"],
            total_years_experience=5.0,
        )
        candidate_vector = FakeEmbeddingProvider._hash_vector("Python")

        job_ids = [uuid.uuid4() for _ in range(3)]
        jobs_data = [
            (
                job_ids[0],
                ParsedJobSchema(title="Job A", required_skills=["Python"]),
                None,
            ),
            (
                job_ids[1],
                ParsedJobSchema(title="Job B", required_skills=["Java"]),
                None,
            ),
            (
                job_ids[2],
                ParsedJobSchema(title="Job C", required_skills=["Python", "SQL"]),
                None,
            ),
        ]

        recommendations = await service.recommend_jobs_for_candidate(
            candidate_id=candidate_id,
            parsed_resume=parsed_resume,
            candidate_vector=candidate_vector,
            jobs_data=jobs_data,
            limit=10,
        )

        assert len(recommendations) == 3
        scores = [rec.match_result.overall_score for rec in recommendations]
        assert scores == sorted(scores, reverse=True), (
            "recommendations must be ranked by overall_score descending"
        )
        assert recommendations[0].job_id == job_ids[0]
        assert recommendations[0].match_result.overall_score >= 50.0


class TestRecommendCandidates:
    @pytest.mark.asyncio
    async def test_recommend_candidates_ranked_descending(self, pipeline):
        service = pipeline["service"]
        job_id = uuid.uuid4()
        parsed_job = ParsedJobSchema(
            title="Python Dev",
            required_skills=["Python", "FastAPI"],
        )
        job_vector = FakeEmbeddingProvider._hash_vector("Python FastAPI")

        candidate_ids = [uuid.uuid4() for _ in range(3)]
        candidates_data = [
            (
                candidate_ids[0],
                ParsedResumeSchema(full_name="C1", skills=["Python", "FastAPI"]),
                None,
            ),
            (
                candidate_ids[1],
                ParsedResumeSchema(full_name="C2", skills=["Java"]),
                None,
            ),
            (
                candidate_ids[2],
                ParsedResumeSchema(full_name="C3", skills=["Python"]),
                None,
            ),
        ]

        recommendations = await service.recommend_candidates_for_job(
            job_id=job_id,
            parsed_job=parsed_job,
            job_vector=job_vector,
            candidates_data=candidates_data,
            limit=10,
        )

        assert len(recommendations) == 3
        scores = [rec.match_result.overall_score for rec in recommendations]
        assert scores == sorted(scores, reverse=True)
        assert recommendations[0].candidate_id == candidate_ids[0]
        assert recommendations[0].match_result.overall_score >= 50.0


class TestErrorPropagation:
    @pytest.mark.asyncio
    async def test_empty_resume_raises_empty_document_error(self, pipeline):
        service = pipeline["service"]
        with pytest.raises(EmptyDocumentError):
            await service.resume_parser.parse("   \n  ")

    @pytest.mark.asyncio
    async def test_empty_job_raises_empty_document_error(self, pipeline):
        service = pipeline["service"]
        with pytest.raises(EmptyDocumentError):
            await service.process_and_index_job(
                job_id=uuid.uuid4(),
                job_title="Dev",
                job_description="   ",
            )

    @pytest.mark.asyncio
    async def test_llm_failure_raises_invalid_document_error(self):
        llm = FakeLLMProvider(
            resume_schema=EXPECTED_RESUME,
            job_schema=EXPECTED_JOB,
        )
        llm.generate_structured_output = _fail_with_invalid_document

        service = AIMatchingService(
            resume_parser=ResumeParser(llm_provider=llm),
            job_parser=JobParser(llm_provider=llm),
            embedding_service=EmbeddingService(FakeEmbeddingProvider()),
            vector_repository=FakeVectorRepository(),
            matching_engine=MatchingEngine(),
        )

        with pytest.raises(InvalidDocumentError):
            await service.resume_parser.parse("Valid CV text")

    @pytest.mark.asyncio
    async def test_missing_vector_raises_entity_not_found(self, pipeline):
        service = pipeline["service"]
        with pytest.raises(EntityNotFoundException):
            await service.recommend_jobs_for_candidate(
                candidate_id=uuid.uuid4(),
                limit=5,
            )


class TestVectorContract:
    def test_vector_dimension_is_384(self):
        assert VECTOR_DIM == 384

    def test_all_pipeline_vectors_are_384_dim(self):
        vector = FakeEmbeddingProvider._hash_vector("Python FastAPI")
        assert len(vector) == 384
        assert vector != [0.0] * 384


class TestProviderBoundary:
    def test_matching_engine_has_no_external_dependencies(self):
        source = inspect.getsource(MatchingEngine)
        forbidden = ["fastapi", "sqlalchemy", "qdrant", "gemini"]
        lower = source.lower()
        assert not any(token in lower for token in forbidden), (
            "MatchingEngine must stay pure business logic"
        )

    def test_pipeline_uses_provider_abstractions(self, pipeline):
        service = pipeline["service"]
        assert isinstance(service.resume_parser.llm_provider, BaseLLMProvider)
        assert isinstance(service.job_parser.llm_provider, BaseLLMProvider)
        assert isinstance(service.embedding_service.provider, BaseEmbeddingProvider)
        assert isinstance(service.vector_repository, BaseVectorRepository)


class TestDeterminism:
    @pytest.mark.asyncio
    async def test_resume_pipeline_deterministic(self):
        first = await self._run_resume_pipeline()
        second = await self._run_resume_pipeline()

        assert first["parsed"] == second["parsed"]
        assert first["vector"] == second["vector"]

    @pytest.mark.asyncio
    async def test_matching_deterministic(self):
        resume = ParsedResumeSchema(skills=["Python", "FastAPI"])
        job = ParsedJobSchema(required_skills=["Python", "FastAPI"])
        vector = FakeEmbeddingProvider._hash_vector("Python FastAPI")

        first = self._score(resume, job, vector)
        second = self._score(resume, job, vector)

        assert first == second
        assert first.overall_score == second.overall_score
        assert first.match_reasons == second.match_reasons

    async def _run_resume_pipeline(self) -> dict:
        service = AIMatchingService(
            resume_parser=ResumeParser(
                llm_provider=FakeLLMProvider(
                    resume_schema=EXPECTED_RESUME,
                    job_schema=EXPECTED_JOB,
                )
            ),
            job_parser=JobParser(
                llm_provider=FakeLLMProvider(
                    resume_schema=EXPECTED_RESUME,
                    job_schema=EXPECTED_JOB,
                )
            ),
            embedding_service=EmbeddingService(FakeEmbeddingProvider()),
            vector_repository=FakeVectorRepository(),
            matching_engine=MatchingEngine(),
        )
        parsed = await service.process_and_index_resume(
            candidate_id=uuid.uuid4(),
            pdf_source=MINIMAL_PDF_BYTES,
        )
        vector = FakeEmbeddingProvider._hash_vector(
            f"{parsed.title} {' '.join(parsed.skills)}"
        )
        return {"parsed": parsed, "vector": vector}

    def _score(
        self,
        resume: ParsedResumeSchema,
        job: ParsedJobSchema,
        vector: list[float],
    ) -> MatchResultSchema:
        engine = MatchingEngine()
        return engine.match_resume_to_job(
            resume=resume,
            job=job,
            resume_vector=vector,
            job_vector=vector,
        )


async def _fail_with_invalid_document(*args, **kwargs):
    raise InvalidDocumentError("LLM generation failed")
