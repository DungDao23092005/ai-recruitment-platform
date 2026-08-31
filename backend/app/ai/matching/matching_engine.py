from __future__ import annotations

from typing import TypeVar

from app.ai.matching.cosine_engine import compute_cosine_similarity
from app.ai.matching.rules_engine import RulesEngine
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema

T = TypeVar("T")

# Configuration weights as specified in Phase C architecture
SEMANTIC_WEIGHT = 0.40
SKILL_WEIGHT = 0.30
EXPERIENCE_WEIGHT = 0.15
EDUCATION_WEIGHT = 0.10
PROJECT_WEIGHT = 0.05


class MatchingEngine:
    """Hybrid Matching Engine combining semantic, rule-based, and profile features."""

    def __init__(self, rules_engine: RulesEngine | None = None) -> None:
        self.rules_engine = rules_engine or RulesEngine()

    def match_resume_to_job(
        self,
        resume: ParsedResumeSchema | None,
        job: ParsedJobSchema | None,
        resume_vector: list[float] | None = None,
        job_vector: list[float] | None = None,
    ) -> MatchResultSchema:
        semantic_score = compute_cosine_similarity(
            resume_vector, job_vector
        )

        candidate_skills = resume.skills if resume else []
        required_skills = job.required_skills if job else []
        preferred_skills = job.preferred_skills if job else []

        candidate_exp = resume.total_years_experience if resume else None
        minimum_exp = job.minimum_years_experience if job else None

        candidate_education = resume.education if resume else []
        required_education = job.education_level if job else None

        candidate_projects = resume.projects if resume else []

        matching_required = self.rules_engine.match_skills(
            candidate_skills, required_skills
        )
        matching_preferred = self.rules_engine.match_skills(
            candidate_skills, preferred_skills
        )

        skill_gap = self.rules_engine.skill_gap(
            required_skills, matching_required
        )

        required_coverage = self.rules_engine.skill_coverage(
            required_skills, matching_required
        )
        preferred_coverage = self.rules_engine.skill_coverage(
            preferred_skills, matching_preferred
        )

        # Skill score prioritizes required skills (80%) but gives bonus for preferred (20%)
        skill_score = (required_coverage * 0.8) + (preferred_coverage * 0.2)

        experience_score = self.rules_engine.experience_match(
            candidate_exp, minimum_exp
        )

        education_score = self.rules_engine.education_match(
            candidate_education, required_education
        )

        project_score = self.rules_engine.project_relevance(
            candidate_projects, required_skills
        )

        # Determine requirement presence flags
        has_required_skills = len(required_skills) > 0
        has_preferred_skills = len(preferred_skills) > 0
        has_experience_requirement = minimum_exp is not None and minimum_exp > 0
        has_education_requirement = required_education is not None and len(required_education.strip()) > 0

# Dynamic weight calculation
        # Semantic is always active (weight 40)
        active_weight_sum = SEMANTIC_WEIGHT

        # Required skills weight (30) + Project weight (5) - they activate together
        if has_required_skills:
            active_weight_sum += SKILL_WEIGHT + PROJECT_WEIGHT

        # Experience weight (15) - only when there's a real requirement
        if has_experience_requirement:
            active_weight_sum += EXPERIENCE_WEIGHT

        # Education weight (10) - only when there's a real requirement
        if has_education_requirement:
            active_weight_sum += EDUCATION_WEIGHT

        # Calculate weighted score
        weighted_sum = (
            semantic_score * SEMANTIC_WEIGHT
        )

        if has_required_skills:
            weighted_sum += skill_score * SKILL_WEIGHT
            weighted_sum += project_score * PROJECT_WEIGHT

        if has_experience_requirement:
            weighted_sum += experience_score * EXPERIENCE_WEIGHT

        if has_education_requirement:
            weighted_sum += education_score * EDUCATION_WEIGHT

        overall_score = round(
            (weighted_sum / active_weight_sum) * 100,
            2,
        )

        match_reasons = self._build_reasons(
            matching_skills=matching_required + matching_preferred,
            skill_gap=skill_gap,
            candidate_exp=candidate_exp,
            minimum_exp=minimum_exp,
            education_score=education_score,
            project_score=project_score,
            has_required_skills=has_required_skills,
            has_preferred_skills=has_preferred_skills,
            has_experience_requirement=has_experience_requirement,
            has_education_requirement=has_education_requirement,
        )

        return MatchResultSchema(
            overall_score=overall_score,
            cosine_similarity=semantic_score,
            skill_coverage_score=skill_score,
            preferred_skill_coverage_score=preferred_coverage,
            experience_match_score=experience_score,
            education_score=education_score,
            project_score=project_score,
            matching_skills=list(set(matching_required + matching_preferred)),
            skill_gap=skill_gap,
            match_reasons=match_reasons,
            has_required_skills=has_required_skills,
            has_preferred_skills=has_preferred_skills,
            has_experience_requirement=has_experience_requirement,
            has_education_requirement=has_education_requirement,
        )

    @staticmethod
    def _build_reasons(
        matching_skills: list[str],
        skill_gap: list[str],
        candidate_exp: float | None,
        minimum_exp: float | None,
        education_score: float,
        project_score: float,
        has_required_skills: bool,
        has_preferred_skills: bool,
        has_experience_requirement: bool,
        has_education_requirement: bool,
    ) -> list[str]:
        reasons: list[str] = []

        if matching_skills:
            reasons.append(
                "✓ Matching skills: " + ", ".join(set(matching_skills))
            )

        if skill_gap:
            reasons.append(
                "✗ Missing required skills: " + ", ".join(skill_gap)
            )

        if has_experience_requirement:
            if candidate_exp is None:
                reasons.append(
                    "✗ Candidate experience unknown; defaulted to 0.5"
                )
            elif candidate_exp >= minimum_exp:
                reasons.append(
                    f"✓ Candidate experience ({candidate_exp} yrs) "
                    f"satisfies minimum requirement ({minimum_exp} yrs)"
                )
            else:
                reasons.append(
                    f"✗ Candidate experience ({candidate_exp} yrs) "
                    f"below minimum requirement ({minimum_exp} yrs)"
                )

        if has_education_requirement:
            if education_score >= 1.0:
                reasons.append("✓ Education meets requirements")
            elif education_score > 0.0:
                reasons.append("⚠ Education partially meets requirements")

        if has_required_skills and project_score >= 0.5:
            reasons.append("✓ Relevant project experience found")

        return reasons


def rank_matches(
    items: list[tuple[T, MatchResultSchema]],
) -> list[tuple[T, MatchResultSchema]]:
    """Sort matches descending by overall_score (stable)."""
    return sorted(
        items,
        key=lambda item: item[1].overall_score,
        reverse=True,
    )
