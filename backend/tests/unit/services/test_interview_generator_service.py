from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import AIError, EmptyDocumentError, InvalidDocumentError
from app.schemas.ai_interview import (
    GenerateInterviewQuestionsRequest,
    GenerateInterviewQuestionsResponse,
    InterviewQuestion,
)
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.interview_generator_service import InterviewGeneratorService


def make_job() -> ParsedJobSchema:
    return ParsedJobSchema(
        title="Senior Frontend Engineer",
        summary="Build modern web applications with React.",
        required_skills=["React", "TypeScript", "GraphQL"],
        preferred_skills=["Next.js"],
        minimum_years_experience=4,
    )


def make_candidate() -> ParsedResumeSchema:
    return ParsedResumeSchema(
        full_name="John Doe",
        title="Frontend Engineer",
        total_years_experience=5,
        skills=["React", "TypeScript"],
        experiences=[
            {
                "company": "Acme Corp",
                "position": "Frontend Engineer",
                "start_date": "2020/01",
                "description": "Built React dashboards.",
                "skills_used": ["React"],
            }
        ],
    )


def make_match_result() -> MatchResultSchema:
    return MatchResultSchema(
        overall_score=80.0,
        cosine_similarity=0.8,
        skill_coverage_score=0.75,
        experience_match_score=0.7,
        matching_skills=["React", "TypeScript"],
        skill_gap=["GraphQL"],
        match_reasons=["Strong skill overlap"],
    )


def make_question(
    category: str = "technical",
    difficulty: str = "medium",
) -> InterviewQuestion:
    return InterviewQuestion(
        question="Explain how you handle React state.",
        category=category,
        difficulty=difficulty,
        target_skill_or_topic="React",
        evaluation_criteria="Demonstrates understanding of state management.",
        sample_answer_points=["Mentions hooks", "Explains trade-offs"],
    )


def make_response(questions=None) -> GenerateInterviewQuestionsResponse:
    if questions is None:
        questions = [make_question()]
    return GenerateInterviewQuestionsResponse(
        job_title="Senior Frontend Engineer",
        candidate_title="Frontend Engineer",
        total_questions=len(questions),
        questions=questions,
    )


def make_service(provider=None) -> InterviewGeneratorService:
    return InterviewGeneratorService(llm_provider=provider)


@pytest.fixture
def provider():
    provider = MagicMock()
    provider.generate_structured_output = AsyncMock(
        return_value=make_response()
    )
    return provider


@pytest.fixture
def job():
    return make_job()


@pytest.fixture
def candidate():
    return make_candidate()


@pytest.fixture
def match_result():
    return make_match_result()


def build_request(
    job,
    candidate=None,
    match_result=None,
    num_questions=5,
    difficulty="medium",
    focus_areas=None,
) -> GenerateInterviewQuestionsRequest:
    return GenerateInterviewQuestionsRequest(
        job=job,
        candidate=candidate,
        match_result=match_result,
        num_questions=num_questions,
        difficulty=difficulty,
        focus_areas=focus_areas or [],
    )


def run_generate(service, request):
    return asyncio.run(service.generate_questions(request))


class TestSuccessfulGeneration:
    def test_successful_generation(self, provider, job):
        service = make_service(provider)

        response = run_generate(service, build_request(job))

        assert response.job_title == "Senior Frontend Engineer"
        assert response.total_questions == 1
        assert response.questions[0].question.startswith("Explain")

    def test_returns_pydantic_response(self, provider, job):
        service = make_service(provider)

        response = run_generate(service, build_request(job))

        assert isinstance(response, GenerateInterviewQuestionsResponse)
        assert isinstance(response.questions[0], InterviewQuestion)

    def test_provider_called_exactly_once(self, provider, job):
        service = make_service(provider)

        run_generate(service, build_request(job))

        provider.generate_structured_output.assert_awaited_once()

    def test_prompt_contains_job_context(self, provider, job):
        service = make_service(provider)

        run_generate(service, build_request(job))

        prompt = provider.generate_structured_output.await_args.kwargs["prompt"]
        assert "Senior Frontend Engineer" in prompt
        assert "React" in prompt
        assert "GraphQL" in prompt
        assert "minimum_years_experience" in prompt

    def test_prompt_contains_candidate_context(self, provider, job, candidate):
        service = make_service(provider)

        run_generate(service, build_request(job, candidate=candidate))

        prompt = provider.generate_structured_output.await_args.kwargs["prompt"]
        assert "Acme Corp" in prompt
        assert "Frontend Engineer" in prompt
        assert "total_years_experience" in prompt

    def test_prompt_contains_skill_gap(self, provider, job, match_result):
        service = make_service(provider)

        run_generate(service, build_request(job, match_result=match_result))

        prompt = provider.generate_structured_output.await_args.kwargs["prompt"]
        assert "skill_gap" in prompt
        assert "GraphQL" in prompt

    def test_prompt_contains_focus_areas(self, provider, job):
        service = make_service(provider)

        run_generate(
            service,
            build_request(job, focus_areas=["Performance", "Testing"]),
        )

        prompt = provider.generate_structured_output.await_args.kwargs["prompt"]
        assert "focus_areas" in prompt
        assert "Performance" in prompt
        assert "Testing" in prompt

    def test_prompt_contains_difficulty(self, provider, job):
        service = make_service(provider)

        run_generate(service, build_request(job, difficulty="hard"))

        prompt = provider.generate_structured_output.await_args.kwargs["prompt"]
        assert "hard" in prompt

    def test_prompt_contains_num_questions(self, provider, job):
        service = make_service(provider)

        run_generate(service, build_request(job, num_questions=10))

        prompt = provider.generate_structured_output.await_args.kwargs["prompt"]
        assert "10" in prompt

    def test_provider_called_with_response_schema_and_system_instruction(
        self, provider, job
    ):
        service = make_service(provider)

        run_generate(service, build_request(job))

        kwargs = provider.generate_structured_output.await_args.kwargs
        assert kwargs["response_schema"] is GenerateInterviewQuestionsResponse
        assert "Interview Architect" in kwargs["system_instruction"]

    def test_validate_response_returns_response(self, provider, job):
        service = make_service(provider)

        response = run_generate(service, build_request(job))

        assert response is not None


class TestJobValidation:
    def test_missing_job_raises_empty_document_error(self, provider):
        service = make_service(provider)
        request = GenerateInterviewQuestionsRequest.model_construct(
            job=None,
            num_questions=5,
            difficulty="medium",
            focus_areas=[],
        )

        with pytest.raises(EmptyDocumentError):
            run_generate(service, request)

    def test_empty_job_raises_empty_document_error(self, provider):
        service = make_service(provider)
        empty_job = ParsedJobSchema()

        with pytest.raises(EmptyDocumentError):
            run_generate(service, build_request(empty_job))


class TestInvalidLlmResponse:
    def test_none_response_raises_invalid_document(self, job):
        provider = MagicMock()
        provider.generate_structured_output = AsyncMock(return_value=None)
        service = make_service(provider)

        with pytest.raises(InvalidDocumentError):
            run_generate(service, build_request(job))

    def test_empty_questions_raises_invalid_document(self, job):
        response = make_response(questions=[])
        provider = MagicMock()
        provider.generate_structured_output = AsyncMock(return_value=response)
        service = make_service(provider)

        with pytest.raises(InvalidDocumentError):
            run_generate(service, build_request(job))

    def test_empty_question_text_raises_invalid_document(self, job):
        question = make_question()
        question.question = "   "
        response = make_response(questions=[question])
        provider = MagicMock()
        provider.generate_structured_output = AsyncMock(return_value=response)
        service = make_service(provider)

        with pytest.raises(InvalidDocumentError):
            run_generate(service, build_request(job))

    def test_missing_evaluation_criteria_raises_invalid_document(self, job):
        question = make_question()
        question.evaluation_criteria = ""
        response = make_response(questions=[question])
        provider = MagicMock()
        provider.generate_structured_output = AsyncMock(return_value=response)
        service = make_service(provider)

        with pytest.raises(InvalidDocumentError):
            run_generate(service, build_request(job))


class TestProviderFailure:
    def test_ai_error_is_rethrown(self, job):
        provider = MagicMock()
        provider.generate_structured_output = AsyncMock(
            side_effect=AIError("gemini down")
        )
        service = make_service(provider)

        with pytest.raises(AIError):
            run_generate(service, build_request(job))

    def test_unexpected_provider_exception_maps_to_invalid_document(self, job):
        provider = MagicMock()
        provider.generate_structured_output = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        service = make_service(provider)

        with pytest.raises(InvalidDocumentError):
            run_generate(service, build_request(job))


class TestAntiFabrication:
    def test_experience_questions_kept_when_candidate_provided(
        self, provider, job, candidate
    ):
        experience_question = make_question(category="experience")
        response = make_response(questions=[experience_question])
        provider.generate_structured_output = AsyncMock(return_value=response)
        service = make_service(provider)

        result = run_generate(service, build_request(job, candidate=candidate))

        assert result.questions[0].category == "experience"

    def test_experience_questions_dropped_when_no_candidate(
        self, provider, job
    ):
        experience_question = make_question(category="experience")
        technical_question = make_question(category="technical")
        response = make_response(
            questions=[experience_question, technical_question]
        )
        provider.generate_structured_output = AsyncMock(return_value=response)
        service = make_service(provider)

        result = run_generate(service, build_request(job))

        assert result.total_questions == 1
        assert result.questions[0].category == "technical"

    def test_all_experience_questions_without_candidate_raises(self, provider, job):
        experience_question = make_question(category="experience")
        response = make_response(questions=[experience_question])
        provider.generate_structured_output = AsyncMock(return_value=response)
        service = make_service(provider)

        with pytest.raises(InvalidDocumentError):
            run_generate(service, build_request(job))


class TestPromptCandidateAbsent:
    def test_prompt_marks_candidate_absent(self, provider, job):
        service = make_service(provider)

        run_generate(service, build_request(job))

        prompt = provider.generate_structured_output.await_args.kwargs["prompt"]
        assert "thông tin ứng viên không được cung cấp" in prompt

    def test_prompt_grounds_skill_gap_from_match_result(
        self, provider, job, match_result
    ):
        service = make_service(provider)

        run_generate(service, build_request(job, match_result=match_result))

        prompt = provider.generate_structured_output.await_args.kwargs["prompt"]
        assert "skill_gap" in prompt
