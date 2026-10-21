from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import (
    AIProviderQuotaExceededError,
    AIProviderUnavailableError,
)
from app.core.telemetry.explainability_telemetry import (
    TelemetryErrorCode,
    TelemetryOutcome,
)
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import (
    ParsedResumeSchema,
    WorkExperienceSchema,
)
from app.services.match_explanation_service import (
    MatchExplanationService,
    _narrative_contradicts_score,
)


def make_match_result() -> MatchResultSchema:
    return MatchResultSchema(
        overall_score=77.5,
        cosine_similarity=0.71,
        skill_coverage_score=0.5,
        preferred_skill_coverage_score=0.0,
        experience_match_score=1.0,
        education_score=0.5,
        project_score=0.4,
        matching_skills=["Python"],
        skill_gap=["Docker"],
        match_reasons=["Matching skills: Python"],
    )


def make_job() -> ParsedJobSchema:
    return ParsedJobSchema(
        title="Backend Engineer",
        summary="Build APIs",
        required_skills=["Python", "Docker"],
        minimum_years_experience=3,
    )


def make_resume() -> ParsedResumeSchema:
    return ParsedResumeSchema(
        full_name="Jane Doe",
        summary="Backend engineer.",
        total_years_experience=5,
        skills=["Python", "FastAPI"],
        experiences=[
            WorkExperienceSchema(
                company="Acme",
                position="Backend Engineer",
                start_date="2019",
                end_date="2022",
                description="Built Python services.",
                skills_used=["Python"],
            )
        ],
    )


def make_narrative(error: Exception | None = None) -> SimpleNamespace:
    explain = AsyncMock(
        return_value=SimpleNamespace(summary="Provider narrative."),
        side_effect=error,
    )
    return SimpleNamespace(
        explain_match=explain,
        llm_provider=SimpleNamespace(model_name="gemini-3.5-flash-lite"),
    )


async def build(
    narrative: SimpleNamespace, telemetry_sink=None
) -> object:
    service = MatchExplanationService(
        narrative_service=narrative, telemetry_sink=telemetry_sink
    )
    return await service.build_explanation(
        application_id=uuid.uuid4(),
        match_result=make_match_result(),
        parsed_resume=make_resume(),
        parsed_job=make_job(),
    )


@pytest.mark.parametrize(
    ("error", "error_code"),
    [
        (
            AIProviderQuotaExceededError("quota", retry_after=30),
            TelemetryErrorCode.PROVIDER_QUOTA_EXCEEDED,
        ),
        (
            AIProviderUnavailableError("down", retry_after=30),
            TelemetryErrorCode.PROVIDER_UNAVAILABLE,
        ),
        (TimeoutError("slow provider"), TelemetryErrorCode.PROVIDER_TIMEOUT),
    ],
)
async def test_provider_failure_degrades_to_verified_deterministic_response(
    error: Exception, error_code: TelemetryErrorCode
) -> None:
    events = []

    result = await build(make_narrative(error), telemetry_sink=events.append)

    assert result.summary_source == "deterministic"
    assert result.overall_score == 77.5
    assert result.model_version is None
    assert any(
        "deterministic summary" in limitation
        for limitation in result.data_limitations
    )
    assert events[0].outcome is TelemetryOutcome.FALLBACK
    assert events[0].error_code is error_code
    assert not _narrative_contradicts_score(
        SimpleNamespace(match_score=None),
        result.summary,
        result.overall_score,
    )


async def test_score_contradiction_is_replaced_by_deterministic_summary() -> None:
    events = []
    narrative = make_narrative()
    narrative.explain_match.return_value = SimpleNamespace(
        summary="Perfect match, 100/100.",
        match_score=100.0,
    )

    result = await build(narrative, telemetry_sink=events.append)

    assert result.summary_source == "deterministic"
    assert "100/100" not in result.summary
    assert events[0].error_code is TelemetryErrorCode.SCORE_CONTRADICTION
    assert not _narrative_contradicts_score(
        SimpleNamespace(match_score=None),
        result.summary,
        result.overall_score,
    )
