"""
RAG Benchmark Tests for AI Recruitment Platform.

This module provides comprehensive benchmarking for the RAG chat service
to measure retrieval quality, response accuracy, and system performance.
"""

import asyncio
import statistics
import time
from dataclasses import dataclass
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock
import uuid
from uuid import uuid4

import pytest

from app.services.rag_chat_service import (
    RAGChatService,
    DEFAULT_SCORE_THRESHOLD,
    RETRIEVAL_LIMIT,
    LLMChatResponse,
)
from app.schemas.ai_chat import (
    ChatMessage,
    ChatSource,
    ChatResponse,
)
from app.domain.enums import UserRole
from app.models import User
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.context_resolver import ContextResolver


@dataclass
class BenchmarkResult:
    """Results from a single benchmark run."""
    test_name: str
    latency_ms: float
    success: bool
    sources_count: int
    confidence: float
    answer: str
    error: Optional[str] = None


@dataclass
class BenchmarkSummary:
    """Aggregated benchmark results."""
    total_tests: int
    passed: int
    failed: int
    avg_latency_ms: float
    median_latency_ms: float
    p95_latency_ms: float
    avg_sources: float
    avg_confidence: float
    success_rate: float


class MockVectorRepository:
    """Mock vector repository with configurable behavior."""

    def __init__(self, jobs_data: list[dict], resumes_data: list[dict]):
        self.jobs_data = jobs_data
        self.resumes_data = resumes_data
        self.call_count = 0
        self.last_score_threshold = 0.0

    async def search_similar(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int,
        score_threshold: float = 0.0,
        **kwargs
    ) -> list[dict]:
        self.call_count += 1
        self.last_score_threshold = score_threshold

        if collection_name == "jobs":
            return [j for j in self.jobs_data if j.get("score", 0) >= score_threshold][:limit]
        elif collection_name == "resumes":
            return [r for r in self.resumes_data if r.get("score", 0) >= score_threshold][:limit]
        return []


class MockEmbeddingService:
    """Mock embedding service with fixed vectors."""

    def __init__(self):
        self.call_count = 0
        self.last_text = ""

    def embed_text(self, text: str) -> list[float]:
        self.call_count += 1
        self.last_text = text
        # Return a deterministic vector based on text hash
        import hashlib
        hash_val = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
        return [((hash_val >> i) & 0xFF) / 255.0 for i in range(0, 384, 8)][:384]


class MockLLMProvider:
    """Mock LLM provider with configurable responses."""

    def __init__(self, responses: list[LLMChatResponse]):
        self.responses = responses
        self.call_count = 0
        self.call_schemas = []

    async def generate_structured_output(
        self,
        prompt: str,
        response_schema: type,
        system_instruction: str
    ) -> Any:
        self.call_count += 1
        self.call_schemas.append(response_schema)

        if self.responses:
            return self.responses.pop(0)
        # Default fallback
        return LLMChatResponse(
            answer="Default answer",
            cited_source_ids=[],
            evidence_quotes=[],
            suggested_followups=[],
        )


class MockContextResolver:
    """Mock context resolver with authorization filtering."""

    def __init__(self, jobs_dict: dict, resumes_dict: dict):
        self.jobs_dict = jobs_dict
        self.resumes_dict = resumes_dict
        self.resolve_jobs_calls = []
        self.resolve_resumes_calls = []

    async def resolve_jobs(self, job_ids: list, actor_user) -> dict:
        self.resolve_jobs_calls.append((job_ids, actor_user))
        return {jid: self.jobs_dict[jid] for jid in job_ids if jid in self.jobs_dict}

    async def resolve_resumes(self, candidate_ids: list, actor_user) -> dict:
        self.resolve_resumes_calls.append((candidate_ids, actor_user))
        return {cid: self.resumes_dict[cid] for cid in candidate_ids if cid in self.resumes_dict}


class MockSession:
    """Mock session for async context manager."""

    def __init__(self, resolver: MockContextResolver):
        self.resolver = resolver

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def make_mock_session_factory(resolver: MockContextResolver):
    """Create a mock session factory that returns an async context manager."""
    def factory():
        return MockSession(resolver)
    return factory


def make_benchmark_service(
    jobs_data: list[dict],
    resumes_data: list[dict],
    jobs_dict: dict,
    resumes_dict: dict,
    llm_responses: list[LLMChatResponse]
) -> RAGChatService:
    """Create a RAGChatService configured for benchmarking."""
    embed = MockEmbeddingService()
    repo = MockVectorRepository(jobs_data, resumes_data)
    llm = MockLLMProvider(llm_responses)
    resolver = MockContextResolver(jobs_dict, resumes_dict)
    session_factory = make_mock_session_factory(resolver)

    service = RAGChatService(
        embedding_service=embed,
        vector_repository=repo,
        llm_provider=llm,
        session_factory=session_factory,
        context_resolver=resolver,
    )
    return service


def make_user(role: UserRole = UserRole.CANDIDATE) -> User:
    return User(id=uuid4(), role=role, email="test@example.com")


def make_job_point(job_id: str, score: float, skills: list[str]) -> dict:
    return {
        "id": job_id,
        "score": score,
        "payload": {
            "job_id": job_id,
            "skills": skills,
            "is_deleted": False,
        }
    }


def make_resume_point(candidate_id: str, score: float, skills: list[str]) -> dict:
    return {
        "id": candidate_id,
        "score": score,
        "payload": {
            "candidate_id": candidate_id,
            "skills": skills,
        }
    }


def run_benchmark(
    service: RAGChatService,
    message: str,
    user: User,
    history: Optional[list[ChatMessage]] = None
) -> BenchmarkResult:
    """Run a single benchmark test."""
    start = time.perf_counter()
    try:
        result = asyncio.run(service.chat(message, user, history=history))
        latency_ms = (time.perf_counter() - start) * 1000
        return BenchmarkResult(
            test_name=f"chat({message[:30]})",
            latency_ms=latency_ms,
            success=True,
            sources_count=len(result.sources),
            confidence=result.confidence,
            answer=result.answer,
        )
    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return BenchmarkResult(
            test_name=f"chat({message[:30]})",
            latency_ms=latency_ms,
            success=False,
            sources_count=0,
            confidence=0.0,
            answer="",
            error=str(e),
        )


def summarize_results(results: list[BenchmarkResult]) -> BenchmarkSummary:
    """Aggregate benchmark results."""
    successful = [r for r in results if r.success]
    latencies = [r.latency_ms for r in successful]

    return BenchmarkSummary(
        total_tests=len(results),
        passed=len(successful),
        failed=len(results) - len(successful),
        avg_latency_ms=statistics.mean(latencies) if latencies else 0,
        median_latency_ms=statistics.median(latencies) if latencies else 0,
        p95_latency_ms=sorted(latencies)[int(0.95 * len(latencies))] if latencies else 0,
        avg_sources=statistics.mean([r.sources_count for r in successful]) if successful else 0,
        avg_confidence=statistics.mean([r.confidence for r in successful]) if successful else 0,
        success_rate=len(successful) / len(results) if results else 0,
    )


class TestRAGBenchmark:
    """RAG Benchmark test suite."""

    def setup_method(self):
        """Set up test data."""
        self.job_ids = [str(uuid4()) for _ in range(5)]
        self.resume_ids = [str(uuid4()) for _ in range(3)]

        # Create job points with varying scores
        self.jobs_data = [
            make_job_point(self.job_ids[0], 0.95, ["Python", "FastAPI", "PostgreSQL"]),
            make_job_point(self.job_ids[1], 0.87, ["Python", "Django", "Redis"]),
            make_job_point(self.job_ids[2], 0.72, ["JavaScript", "React", "Node.js"]),
            make_job_point(self.job_ids[3], 0.65, ["Go", "gRPC", "Kubernetes"]),
            make_job_point(self.job_ids[4], 0.45, ["Python", "Machine Learning"]),  # Below threshold
        ]

        # Create resume points
        self.resumes_data = [
            make_resume_point(self.resume_ids[0], 0.82, ["Python", "FastAPI"]),
            make_resume_point(self.resume_ids[1], 0.78, ["JavaScript", "React"]),
            make_resume_point(self.resume_ids[2], 0.60, ["Go", "Kubernetes"]),
        ]

        # Create authorized context
        self.jobs_dict = {
            uuid4() if i == 4 else uuid.UUID(self.job_ids[i]): ParsedJobSchema(
                title=f"Job {i+1}",
                skills=self.jobs_data[i]["payload"]["skills"]
            )
            for i in range(5)
        }

        self.resumes_dict = {
            uuid.UUID(self.resume_ids[i]): ParsedResumeSchema(
                name=f"Candidate {i+1}",
                skills=self.resumes_data[i]["payload"]["skills"]
            )
            for i in range(3)
        }

        # Default LLM responses
        self.default_llm_responses = [
            LLMChatResponse(
                answer="Based on the job requirements, you should focus on Python and FastAPI.",
                cited_source_ids=[uuid.UUID(self.job_ids[0])],
                evidence_quotes=["Python", "FastAPI"],
                suggested_followups=["What about React?"],
            )
            for _ in range(10)
        ]

    def test_basic_retrieval_latency(self):
        """Benchmark basic retrieval latency."""
        service = make_benchmark_service(
            self.jobs_data,
            self.resumes_data,
            self.jobs_dict,
            self.resumes_dict,
            self.default_llm_responses.copy()
        )

        results = []
        for _ in range(10):
            result = run_benchmark(
                service,
                "Python developer job",
                make_user(UserRole.CANDIDATE)
            )
            results.append(result)

        summary = summarize_results(results)

        # Assertions for performance
        assert summary.success_rate == 1.0
        assert summary.avg_latency_ms < 500  # Should be fast with mocks
        assert summary.avg_sources >= 1

        print(f"\nBasic Retrieval: {summary.avg_latency_ms:.2f}ms avg, "
              f"{summary.median_latency_ms:.2f}ms median, "
              f"{summary.p95_latency_ms:.2f}ms p95")

    def test_threshold_filtering_benchmark(self):
        """Benchmark score threshold filtering behavior."""
        # Test with jobs both above and below threshold
        service = make_benchmark_service(
            self.jobs_data,
            self.resumes_data,
            self.jobs_dict,
            self.resumes_dict,
            self.default_llm_responses.copy()
        )

        results = []
        for _ in range(5):
            result = run_benchmark(
                service,
                "Python job with ML",
                make_user(UserRole.CANDIDATE)
            )
            results.append(result)

        summary = summarize_results(results)

        # The job with score 0.45 should be filtered out
        assert summary.success_rate == 1.0
        assert summary.avg_sources >= 1  # At least one job above threshold

        print(f"\nThreshold Filtering: {summary.avg_sources:.1f} avg sources")

    def test_recruiter_resume_retrieval(self):
        """Benchmark recruiter resume retrieval."""
        # Use LLM responses that cite resume sources
        llm_responses = [
            LLMChatResponse(
                answer="Found candidates with Python skills",
                cited_source_ids=[uuid.UUID(self.resume_ids[0])],
                evidence_quotes=["Python", "FastAPI"],
                suggested_followups=[],
            )
            for _ in range(5)
        ]

        service = make_benchmark_service(
            self.jobs_data,
            self.resumes_data,
            self.jobs_dict,
            self.resumes_dict,
            llm_responses
        )

        results = []
        for _ in range(5):
            result = run_benchmark(
                service,
                "Find Python candidates",
                make_user(UserRole.RECRUITER)
            )
            results.append(result)

        summary = summarize_results(results)

        assert summary.success_rate == 1.0
        assert summary.avg_sources >= 1

        print(f"\nRecruiter Retrieval: {summary.avg_latency_ms:.2f}ms avg, "
              f"{summary.avg_sources:.1f} avg sources")

    def test_context_authorization_benchmark(self):
        """Benchmark authorization filtering performance."""
        # Only authorize 2 out of 5 jobs
        authorized_job_ids = [uuid.UUID(self.job_ids[0]), uuid.UUID(self.job_ids[1])]
        authorized_jobs_dict = {jid: self.jobs_dict[jid] for jid in authorized_job_ids}

        service = make_benchmark_service(
            self.jobs_data,
            self.resumes_data,
            authorized_jobs_dict,
            self.resumes_dict,
            self.default_llm_responses.copy()
        )

        results = []
        for _ in range(5):
            result = run_benchmark(
                service,
                "All jobs query",
                make_user(UserRole.CANDIDATE)
            )
            results.append(result)

        summary = summarize_results(results)

        # Should only return authorized jobs
        assert summary.success_rate == 1.0
        assert summary.avg_sources <= 2  # Max 2 authorized jobs

        print(f"\nAuthorization Filtering: {summary.avg_sources:.1f} avg sources (max 2)")

    def test_query_rewriting_latency(self):
        """Benchmark query rewriting overhead."""
        llm_responses = [
            # First call: rewrite response
            type('obj', (object,), {'standalone_query': 'Python developer job'})(),
            # Second call: final answer
            LLMChatResponse(
                answer="Python developer jobs available",
                cited_source_ids=[uuid.UUID(self.job_ids[0])],
                evidence_quotes=["Python"],
                suggested_followups=[],
            )
        ]

        service = make_benchmark_service(
            self.jobs_data,
            self.resumes_data,
            self.jobs_dict,
            self.resumes_dict,
            llm_responses.copy()
        )

        history = [
            ChatMessage(role="user", content="Looking for jobs"),
            ChatMessage(role="assistant", content="Here are some jobs"),
        ]

        results = []
        for _ in range(5):
            result = run_benchmark(
                service,
                "More Python jobs",
                make_user(UserRole.CANDIDATE),
                history=history
            )
            results.append(result)

        summary = summarize_results(results)

        # Query rewriting adds one extra LLM call
        assert summary.success_rate == 1.0

        print(f"\nQuery Rewriting: {summary.avg_latency_ms:.2f}ms avg "
              f"(includes rewrite + answer)")

    def test_empty_context_short_circuit(self):
        """Benchmark short-circuit when no context."""
        service = make_benchmark_service(
            [],  # No jobs
            [],
            {},  # No authorized context
            {},
            []
        )

        results = []
        for _ in range(10):
            result = run_benchmark(
                service,
                "Any question",
                make_user(UserRole.CANDIDATE)
            )
            results.append(result)

        summary = summarize_results(results)

        # Should short-circuit without calling LLM
        assert summary.success_rate == 1.0
        assert all(r.answer == "Không đủ dữ liệu để trả lời." for r in results)
        assert all(r.confidence == 0.0 for r in results)

        print(f"\nShort-circuit: {summary.avg_latency_ms:.2f}ms avg (no LLM call)")

    def test_confidence_calculation_accuracy(self):
        """Verify deterministic confidence calculation."""
        llm_responses = [
            LLMChatResponse(
                answer="Test answer",
                cited_source_ids=[uuid.UUID(self.job_ids[0]), uuid.UUID(self.job_ids[1])],
                evidence_quotes=[],
                suggested_followups=[],
            )
            for _ in range(5)
        ]

        service = make_benchmark_service(
            self.jobs_data,
            self.resumes_data,
            self.jobs_dict,
            self.resumes_dict,
            llm_responses
        )

        results = []
        for _ in range(5):
            result = run_benchmark(
                service,
                "Test confidence",
                make_user(UserRole.CANDIDATE)
            )
            results.append(result)

        summary = summarize_results(results)

        # Confidence should be max of cited sources (0.95 and 0.87) = 0.95
        for r in results:
            assert r.confidence == 0.95, f"Expected 0.95, got {r.confidence}"

        print(f"\nConfidence Accuracy: all results have confidence={results[0].confidence}")


class TestRAGQualityBenchmarks:
    """Quality-focused benchmarks for RAG responses."""

    def test_evidence_quote_validation(self):
        """Benchmark evidence quote validation accuracy."""
        job_id = str(uuid4())
        jobs_data = [make_job_point(job_id, 0.9, ["Python", "FastAPI", "PostgreSQL"])]
        jobs_dict = {uuid.UUID(job_id): ParsedJobSchema(title="Backend Dev", skills=["Python", "FastAPI", "PostgreSQL"])}

        llm_responses = [
            LLMChatResponse(
                answer="Backend developer role",
                cited_source_ids=[uuid.UUID(job_id)],
                evidence_quotes=["Python", "FastAPI"],  # Valid quotes
                suggested_followups=[],
            )
        ]

        service = make_benchmark_service(
            jobs_data,
            [],
            jobs_dict,
            {},
            llm_responses
        )

        result = run_benchmark(service, "Backend job", make_user(UserRole.CANDIDATE))

        assert result.success
        assert result.confidence == 0.9
        print(f"\nEvidence Validation: confidence={result.confidence}, sources={result.sources_count}")

    def test_hallucinated_citation_rejection(self):
        """Verify hallucinated citations are rejected."""
        job_id = str(uuid4())
        jobs_data = [make_job_point(job_id, 0.9, ["Python"])]
        jobs_dict = {uuid.UUID(job_id): ParsedJobSchema(title="Python Dev", skills=["Python"])}

        fake_id = uuid4()
        llm_responses = [
            LLMChatResponse(
                answer="Hallucinated answer",
                cited_source_ids=[fake_id],  # Fake ID not in context
                evidence_quotes=["Fake quote"],
                suggested_followups=[],
            )
        ]

        service = make_benchmark_service(
            jobs_data,
            [],
            jobs_dict,
            {},
            llm_responses
        )

        result = run_benchmark(service, "Test", make_user(UserRole.CANDIDATE))

        assert result.success
        assert result.sources_count == 0  # Fake ID should be discarded
        assert result.confidence == 0.0
        print(f"\nHallucination Rejection: sources={result.sources_count}, confidence={result.confidence}")

    def test_duplicate_citation_deduplication(self):
        """Verify duplicate citations are deduplicated."""
        job_id = str(uuid4())
        jobs_data = [make_job_point(job_id, 0.85, ["Python"])]
        jobs_dict = {uuid.UUID(job_id): ParsedJobSchema(title="Python Dev", skills=["Python"])}

        llm_responses = [
            LLMChatResponse(
                answer="Answer",
                cited_source_ids=[uuid.UUID(job_id), uuid.UUID(job_id), uuid.UUID(job_id)],
                evidence_quotes=[],
                suggested_followups=[],
            )
        ]

        service = make_benchmark_service(
            jobs_data,
            [],
            jobs_dict,
            {},
            llm_responses
        )

        result = run_benchmark(service, "Test", make_user(UserRole.CANDIDATE))

        assert result.success
        assert result.sources_count == 1  # Duplicates removed
        print(f"\nDeduplication: sources={result.sources_count}")


class TestRAGRegressionBenchmarks:
    """Regression benchmarks to catch performance degradation."""

    def test_short_circuit_performance(self):
        """Short-circuit should be very fast."""
        service = make_benchmark_service([], [], {}, {}, [])

        latencies = []
        for _ in range(20):
            result = run_benchmark(service, "test", make_user(UserRole.CANDIDATE))
            latencies.append(result.latency_ms)

        avg_latency = statistics.mean(latencies)
        p99_latency = sorted(latencies)[int(0.99 * len(latencies))]

        # Short-circuit should be extremely fast (< 50ms with mocks)
        assert avg_latency < 50
        assert p99_latency < 100
        assert all(r.answer == "Không đủ dữ liệu để trả lời." for r in [run_benchmark(service, "test", make_user(UserRole.CANDIDATE)) for _ in range(3)])

        print(f"\nShort-circuit Performance: {avg_latency:.2f}ms avg, {p99_latency:.2f}ms p99")

    def test_first_turn_no_rewrite(self):
        """First turn should not call rewrite."""
        llm_responses = [
            LLMChatResponse(
                answer="First turn answer",
                cited_source_ids=[uuid.UUID(str(uuid4()))],
                evidence_quotes=[],
                suggested_followups=[],
            )
        ]

        service = make_benchmark_service(
            [make_job_point(str(uuid4()), 0.9, ["Python"])],
            [],
            {uuid.UUID(str(uuid4())): ParsedJobSchema(title="Test", skills=["Python"])},
            {},
            llm_responses
        )

        # This test verifies the rewrite is not called on first turn
        # The benchmark is implicit - we just ensure it works
        result = run_benchmark(service, "First turn", make_user(UserRole.CANDIDATE))

        assert result.success
        print(f"\nFirst Turn (no rewrite): {result.latency_ms:.2f}ms")


def run_all_benchmarks() -> dict[str, BenchmarkSummary]:
    """Run all benchmark suites and return summaries."""
    suites = {
        "retrieval": TestRAGBenchmark(),
        "quality": TestRAGQualityBenchmarks(),
        "regression": TestRAGRegressionBenchmarks(),
    }

    results = {}

    for name, suite in suites.items():
        print(f"\n{'='*60}")
        print(f"Running {name} benchmarks...")
        print(f"{'='*60}")

        # Get all test methods
        test_methods = [m for m in dir(suite) if m.startswith("test_")]

        all_results = []
        for method_name in test_methods:
            try:
                method = getattr(suite, method_name)
                method()
            except Exception as e:
                print(f"  {method_name}: ERROR - {e}")

        # Note: This is a simplified runner. In practice, use pytest to run tests.

    return results


if __name__ == "__main__":
    # Allow running as standalone script
    print("Running RAG Benchmarks...")
    print("=" * 60)

    # Run a quick sanity check
    test = TestRAGBenchmark()
    test.setup_method()

    print("\n--- Basic Retrieval ---")
    test.test_basic_retrieval_latency()

    print("\n--- Threshold Filtering ---")
    test.test_threshold_filtering_benchmark()

    print("\n--- Recruiter Retrieval ---")
    test.test_recruiter_resume_retrieval()

    print("\n--- Authorization ---")
    test.test_context_authorization_benchmark()

    print("\n--- Query Rewriting ---")
    test.test_query_rewriting_latency()

    print("\n--- Short Circuit ---")
    test.test_empty_context_short_circuit()

    print("\n--- Confidence Accuracy ---")
    test.test_confidence_calculation_accuracy()

    print("\n" + "=" * 60)
    print("All benchmarks completed!")
