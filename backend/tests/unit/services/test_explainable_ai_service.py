from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import InvalidDocumentError
from app.schemas.ai_explanation import ExplainMatchResponse
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.explainable_ai_service import ExplainableAIService


def make_match_result(
    overall_score: float = 82.0,
    cosine_similarity: float = 0.85,
    skill_coverage_score: float = 0.8,
    experience_match_score: float = 0.75,
) -> MatchResultSchema:
    return MatchResultSchema(
        overall_score=overall_score,
        cosine_similarity=cosine_similarity,
        skill_coverage_score=skill_coverage_score,
        experience_match_score=experience_match_score,
        matching_skills=["React", "TypeScript"],
        skill_gap=["GraphQL"],
        match_reasons=["Strong skill overlap"],
    )


def make_candidate() -> ParsedResumeSchema:
    return ParsedResumeSchema(
        full_name="John Doe",
        email="john@example.com",
        phone="+84123456789",
        title="Frontend Engineer",
        summary="React specialist with 5 years of experience.",
        total_years_experience=5,
        skills=["React", "TypeScript", "Node.js"],
    )


def make_job() -> ParsedJobSchema:
    return ParsedJobSchema(
        title="Senior Frontend Engineer",
        summary="Build modern web applications with React.",
        required_skills=["React", "TypeScript", "GraphQL"],
        preferred_skills=["Next.js"],
        minimum_years_experience=4,
        education_level="Bachelor",
    )


def make_response() -> ExplainMatchResponse:
    return ExplainMatchResponse(
        summary="The candidate matches the role well.",
        strengths=["Strong overlap in React and TypeScript"],
        skill_gaps=["GraphQL"],
        experience_analysis="Candidate has 5 years experience vs 4 required.",
        recommendation="Proceed to interview.",
    )


def make_service(provider=None) -> ExplainableAIService:
    service = ExplainableAIService(llm_provider=provider)
    return service


@pytest.fixture
def provider():
    provider = MagicMock()
    provider.generate_structured_output = AsyncMock(
        return_value=make_response()
    )
    return provider


class TestExplainMatchSuccess:
    def test_returns_structured_response(self, provider):
        service = make_service(provider)

        result = asyncio.run(
            service.explain_match(
                match_result=make_match_result(),
                candidate=make_candidate(),
                job=make_job(),
            )
        )

        assert result.summary == "The candidate matches the role well."
        assert result.strengths == ["Strong overlap in React and TypeScript"]
        assert result.skill_gaps == ["GraphQL"]
        assert result.experience_analysis == (
            "Candidate has 5 years experience vs 4 required."
        )
        assert result.recommendation == "Proceed to interview."

    def test_provider_called_exactly_once(self, provider):
        service = make_service(provider)

        asyncio.run(
            service.explain_match(
                match_result=make_match_result(),
                candidate=make_candidate(),
                job=make_job(),
            )
        )

        provider.generate_structured_output.assert_awaited_once()

    def test_prompt_contains_overall_score(self, provider):
        service = make_service(provider)

        asyncio.run(
            service.explain_match(match_result=make_match_result())
        )

        prompt = provider.generate_structured_output.await_args.kwargs["prompt"]
        assert "overall_score: 82.0" in prompt

    def test_prompt_contains_matching_skills(self, provider):
        service = make_service(provider)

        asyncio.run(
            service.explain_match(match_result=make_match_result())
        )

        prompt = provider.generate_structured_output.await_args.kwargs["prompt"]
        assert "React" in prompt
        assert "TypeScript" in prompt

    def test_prompt_contains_skill_gap(self, provider):
        service = make_service(provider)

        asyncio.run(
            service.explain_match(match_result=make_match_result())
        )

        prompt = provider.generate_structured_output.await_args.kwargs["prompt"]
        assert "GraphQL" in prompt

    def test_prompt_contains_cosine_similarity(self, provider):
        service = make_service(provider)

        asyncio.run(
            service.explain_match(match_result=make_match_result())
        )

        prompt = provider.generate_structured_output.await_args.kwargs["prompt"]
        assert "cosine_similarity: 0.85" in prompt

    def test_prompt_contains_experience_information(self, provider):
        service = make_service(provider)

        asyncio.run(
            service.explain_match(
                match_result=make_match_result(),
                candidate=make_candidate(),
                job=make_job(),
            )
        )

        prompt = provider.generate_structured_output.await_args.kwargs["prompt"]
        assert "total_years_experience: 5" in prompt
        assert "minimum_years_experience: 4" in prompt

    def test_prompt_contains_candidate_and_job_summaries(self, provider):
        service = make_service(provider)

        asyncio.run(
            service.explain_match(
                match_result=make_match_result(),
                candidate=make_candidate(),
                job=make_job(),
            )
        )

        prompt = provider.generate_structured_output.await_args.kwargs["prompt"]
        assert "React specialist with 5 years of experience." in prompt
        assert "Build modern web applications with React." in prompt

    def test_prompt_handles_missing_candidate_and_job(self, provider):
        service = make_service(provider)

        asyncio.run(
            service.explain_match(match_result=make_match_result())
        )

        prompt = provider.generate_structured_output.await_args.kwargs["prompt"]
        assert "thông tin ứng viên không được cung cấp" in prompt
        assert "thông tin tin tuyển dụng không được cung cấp" in prompt

    def test_prompt_passes_system_instruction(self, provider):
        service = make_service(provider)

        asyncio.run(
            service.explain_match(match_result=make_match_result())
        )

        kwargs = provider.generate_structured_output.await_args.kwargs
        assert "Chỉ sử dụng dữ kiện được cung cấp" in kwargs[
            "system_instruction"
        ]


class TestExplainMatchEmptyInvalid:
    def test_none_match_result_raises(self, provider):
        service = make_service(provider)

        with pytest.raises(InvalidDocumentError):
            asyncio.run(
                service.explain_match(match_result=None)  # type: ignore[arg-type]
            )

    def test_empty_prompt_not_sent_when_match_result_missing(self, provider):
        service = make_service(provider)

        with pytest.raises(InvalidDocumentError):
            asyncio.run(service.explain_match(match_result=None))  # type: ignore[arg-type]

        provider.generate_structured_output.assert_not_awaited()


class TestExplainMatchProviderFailure:
    def test_provider_failure_propagates_ai_error(self, provider):
        from app.core.exceptions import InvalidDocumentError as AIInvalidError

        provider.generate_structured_output.side_effect = AIInvalidError(
            "Gemini API request failed"
        )
        service = make_service(provider)

        with pytest.raises(InvalidDocumentError):
            asyncio.run(
                service.explain_match(match_result=make_match_result())
            )

    def test_unexpected_provider_failure_maps_to_invalid_document(self, provider):
        provider.generate_structured_output.side_effect = RuntimeError(
            "boom"
        )
        service = make_service(provider)

        with pytest.raises(InvalidDocumentError) as exc_info:
            asyncio.run(
                service.explain_match(match_result=make_match_result())
            )

        assert "AI explanation provider failed" in str(exc_info.value)


class TestExplainMatchValidation:
    def test_empty_summary_rejected(self, provider):
        provider.generate_structured_output.return_value = ExplainMatchResponse(
            summary="",
            strengths=[],
            skill_gaps=[],
            experience_analysis="Experience analysis",
            recommendation="Recommendation",
        )
        service = make_service(provider)

        with pytest.raises(InvalidDocumentError):
            asyncio.run(
                service.explain_match(match_result=make_match_result())
            )

    def test_empty_experience_analysis_rejected(self, provider):
        provider.generate_structured_output.return_value = ExplainMatchResponse(
            summary="Summary",
            strengths=[],
            skill_gaps=[],
            experience_analysis=" ",
            recommendation="Recommendation",
        )
        service = make_service(provider)

        with pytest.raises(InvalidDocumentError):
            asyncio.run(
                service.explain_match(match_result=make_match_result())
            )

    def test_none_response_rejected(self, provider):
        provider.generate_structured_output.return_value = None  # type: ignore[assignment]
        service = make_service(provider)

        with pytest.raises(InvalidDocumentError):
            asyncio.run(
                service.explain_match(match_result=make_match_result())
            )


class TestNoScoreRecalculation:
    def test_prompt_does_not_contain_weight_formula(self, provider):
        service = make_service(provider)

        asyncio.run(
            service.explain_match(match_result=make_match_result())
        )

        prompt = provider.generate_structured_output.await_args.kwargs["prompt"]
        assert "0.6" not in prompt
        assert "0.3" not in prompt
        assert "0.1" not in prompt

    def test_no_secret_leakage_in_prompt(self, provider):
        service = make_service(provider)
        candidate = make_candidate()
        candidate.email = "private@example.com"
        candidate.phone = "0000000000"

        asyncio.run(
            service.explain_match(
                match_result=make_match_result(),
                candidate=candidate,
                job=make_job(),
            )
        )

        prompt = provider.generate_structured_output.await_args.kwargs["prompt"]
        assert "GEMINI_API_KEY" not in prompt
        assert "private@example.com" not in prompt
        assert "0000000000" not in prompt
        assert "api_key" not in prompt.lower()
