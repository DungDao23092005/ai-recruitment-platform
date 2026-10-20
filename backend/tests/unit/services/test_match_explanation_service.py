from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AIError
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import (
    ParsedResumeSchema,
    ProjectSchema,
    WorkExperienceSchema,
)
from app.services.match_explanation_service import MatchExplanationService


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
        match_reasons=["✓ Matching skills: Python"],
    )


def make_job() -> ParsedJobSchema:
    return ParsedJobSchema(
        title="Backend Engineer",
        summary="Build APIs",
        required_skills=["Python", "Docker"],
        preferred_skills=["GraphQL"],
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
        projects=[ProjectSchema(name="Tooling", skills_used=["GraphQL"])],
    )


def make_service(narrative_service=None) -> MatchExplanationService:
    return MatchExplanationService(narrative_service=narrative_service)


class TestSkillEvaluation:
    async def test_matched_skill_is_evidenced(self):
        service = make_service()

        result = await service.build_explanation(
            application_id=uuid.uuid4(),
            match_result=make_match_result(),
            parsed_resume=make_resume(),
            parsed_job=make_job(),
        )

        by_name = {e.skill_name: e for e in result.skill_evaluations}
        assert by_name["Python"].status == "matched_evidenced"
        assert by_name["Python"].requirement_type == "required"
        assert by_name["Python"].evidence[0].quote == "Python"

    async def test_missing_required_skill_is_not_evidenced(self):
        service = make_service()

        result = await service.build_explanation(
            application_id=uuid.uuid4(),
            match_result=make_match_result(),
            parsed_resume=make_resume(),
            parsed_job=make_job(),
        )

        by_name = {e.skill_name: e for e in result.skill_evaluations}
        assert by_name["Docker"].status == "not_evidenced_in_cv"
        assert by_name["Docker"].evidence == []

    async def test_skill_only_in_projects_is_partially_matched(self):
        service = make_service()

        result = await service.build_explanation(
            application_id=uuid.uuid4(),
            match_result=make_match_result(),
            parsed_resume=make_resume(),
            parsed_job=make_job(),
        )

        by_name = {e.skill_name: e for e in result.skill_evaluations}
        assert by_name["GraphQL"].status == "partially_matched"
        assert by_name["GraphQL"].requirement_type == "preferred"
        assert by_name["GraphQL"].evidence[0].section == "projects"

    async def test_no_resume_yields_insufficient_data(self):
        service = make_service()

        result = await service.build_explanation(
            application_id=uuid.uuid4(),
            match_result=make_match_result(),
            parsed_resume=None,
            parsed_job=make_job(),
        )

        assert all(
            e.status == "insufficient_data" for e in result.skill_evaluations
        )
        assert result.experience_evaluations == []
        assert result.data_limitations


class TestExperienceEvaluation:
    async def test_relevant_experience_detected_with_duration(self):
        service = make_service()

        result = await service.build_explanation(
            application_id=uuid.uuid4(),
            match_result=make_match_result(),
            parsed_resume=make_resume(),
            parsed_job=make_job(),
        )

        assert len(result.experience_evaluations) == 1
        evaluation = result.experience_evaluations[0]
        assert evaluation.role_title == "Backend Engineer"
        assert evaluation.company == "Acme"
        assert evaluation.relevance == "relevant_skills"
        assert evaluation.duration == "2019 - 2022"

    async def test_current_role_duration_uses_present(self):
        service = make_service()
        resume = make_resume()
        resume.experiences[0].is_current = True
        resume.experiences[0].end_date = None

        result = await service.build_explanation(
            application_id=uuid.uuid4(),
            match_result=make_match_result(),
            parsed_resume=resume,
            parsed_job=make_job(),
        )

        assert result.experience_evaluations[0].duration == "2019 - present"


class TestScoreIntegrity:
    async def test_scores_copied_verbatim_never_recalculated(self):
        service = make_service()
        match_result = make_match_result()

        result = await service.build_explanation(
            application_id=uuid.uuid4(),
            match_result=match_result,
            parsed_resume=make_resume(),
            parsed_job=make_job(),
        )

        assert result.overall_score == match_result.overall_score
        assert result.score_breakdown.overall_score == match_result.overall_score
        assert (
            result.score_breakdown.cosine_similarity
            == match_result.cosine_similarity
        )
        assert (
            result.score_breakdown.skill_coverage_score
            == match_result.skill_coverage_score
        )

    async def test_no_invented_confidence(self):
        service = make_service()

        result = await service.build_explanation(
            application_id=uuid.uuid4(),
            match_result=make_match_result(),
            parsed_resume=make_resume(),
            parsed_job=make_job(),
        )

        assert result.confidence is None
        assert result.model_version is None
        assert result.summary_source == "deterministic"
        assert result.cache_state == "not_cached"

    async def test_areas_for_inquiry_never_claim_absence(self):
        service = make_service()

        result = await service.build_explanation(
            application_id=uuid.uuid4(),
            match_result=make_match_result(),
            parsed_resume=make_resume(),
            parsed_job=make_job(),
        )

        assert any("Docker" in area for area in result.areas_for_inquiry)
        assert all(
            "lacks" not in area for area in result.areas_for_inquiry
        )


class TestNarrativeReuse:
    async def test_narrative_summary_is_used_when_available(self):
        narrative = SimpleNamespace(
            explain_match=AsyncMock(
                return_value=SimpleNamespace(summary="Narrative summary text.")
            ),
            llm_provider=SimpleNamespace(model_name="gemini-test-model"),
        )
        service = make_service(narrative)

        result = await service.build_explanation(
            application_id=uuid.uuid4(),
            match_result=make_match_result(),
            parsed_resume=make_resume(),
            parsed_job=make_job(),
        )

        assert result.summary == "Narrative summary text."
        assert result.summary_source == "ai_generated"
        # Real configured model identifier, not a class name.
        assert result.model_version == "gemini-test-model"
        assert any(
            "not quote-verified" in limitation.lower()
            for limitation in result.data_limitations
        )
        # Evidence remains deterministically verified even when narrative is AI.
        assert all(excerpt.quote.strip() for excerpt in result.evidence)
        narrative.explain_match.assert_awaited_once()

    async def test_narrative_without_model_identifier_reports_none(self):
        narrative = SimpleNamespace(
            explain_match=AsyncMock(
                return_value=SimpleNamespace(summary="Narrative summary text.")
            ),
            llm_provider=SimpleNamespace(),
        )
        service = make_service(narrative)

        result = await service.build_explanation(
            application_id=uuid.uuid4(),
            match_result=make_match_result(),
            parsed_resume=make_resume(),
            parsed_job=make_job(),
        )

        assert result.summary == "Narrative summary text."
        assert result.summary_source == "ai_generated"
        assert result.model_version is None

    async def test_narrative_failure_degrades_gracefully(self):
        narrative = SimpleNamespace(
            explain_match=AsyncMock(side_effect=AIError("provider down")),
        )
        service = make_service(narrative)

        result = await service.build_explanation(
            application_id=uuid.uuid4(),
            match_result=make_match_result(),
            parsed_resume=make_resume(),
            parsed_job=make_job(),
        )

        assert "Deterministic match score" in result.summary
        assert result.summary_source == "deterministic"
        assert result.model_version is None
        assert any(
            "narrative" in limitation.lower()
            for limitation in result.data_limitations
        )

    async def test_empty_narrative_falls_back(self):
        narrative = SimpleNamespace(
            explain_match=AsyncMock(return_value=SimpleNamespace(summary="  ")),
        )
        service = make_service(narrative)

        result = await service.build_explanation(
            application_id=uuid.uuid4(),
            match_result=make_match_result(),
            parsed_resume=make_resume(),
            parsed_job=make_job(),
        )

        assert "Deterministic match score" in result.summary
        assert result.summary_source == "deterministic"


class TestEvidenceAggregation:
    async def test_evidence_list_is_deduplicated_and_verified(self):
        service = make_service()

        result = await service.build_explanation(
            application_id=uuid.uuid4(),
            match_result=make_match_result(),
            parsed_resume=make_resume(),
            parsed_job=make_job(),
        )

        keys = [
            (e.section, e.field_name, e.item_index, e.quote)
            for e in result.evidence
        ]
        assert len(keys) == len(set(keys))
        assert all(e.quote.strip() for e in result.evidence)

    async def test_application_id_is_preserved(self):
        service = make_service()
        application_id = uuid.uuid4()

        result = await service.build_explanation(
            application_id=application_id,
            match_result=make_match_result(),
            parsed_resume=make_resume(),
            parsed_job=make_job(),
        )

        assert result.application_id == application_id
