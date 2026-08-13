from __future__ import annotations

from typing import TypeVar

from app.ai.matching.cosine_engine import compute_cosine_similarity
from app.ai.matching.rules_engine import RulesEngine
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema

T = TypeVar("T")

COSINE_WEIGHT = 0.6
SKILL_WEIGHT = 0.3
EXPERIENCE_WEIGHT = 0.1


class MatchingEngine:
    """Combine cosine similarity, skill coverage and experience match."""

    def __init__(self, rules_engine: RulesEngine | None = None) -> None:
        self.rules_engine = rules_engine or RulesEngine()

    def match_resume_to_job(
        self,
        resume: ParsedResumeSchema | None,
        job: ParsedJobSchema | None,
        resume_vector: list[float] | None = None,
        job_vector: list[float] | None = None,
    ) -> MatchResultSchema:
        cosine_similarity = compute_cosine_similarity(
            resume_vector, job_vector
        )

        candidate_skills = resume.skills if resume else []
        required_skills = job.required_skills if job else []
        candidate_exp = (
            resume.total_years_experience if resume else None
        )
        minimum_exp = (
            job.minimum_years_experience if job else None
        )

        matching_skills = self.rules_engine.match_skills(
            candidate_skills, required_skills
        )
        skill_gap = self.rules_engine.skill_gap(
            required_skills, matching_skills
        )
        skill_coverage = self.rules_engine.required_skill_coverage(
            required_skills, matching_skills
        )
        experience_match = self.rules_engine.experience_match(
            candidate_exp, minimum_exp
        )

        has_any_input = bool(
            resume is not None
            or job is not None
            or resume_vector
            or job_vector
        )

        if not has_any_input:
            return MatchResultSchema(
                overall_score=0.0,
                cosine_similarity=0.0,
                skill_coverage_score=0.0,
                experience_match_score=0.0,
            )

        overall_score = round(
            (
                cosine_similarity * COSINE_WEIGHT
                + skill_coverage * SKILL_WEIGHT
                + experience_match * EXPERIENCE_WEIGHT
            )
            * 100,
            2,
        )

        match_reasons = self._build_reasons(
            matching_skills=matching_skills,
            skill_gap=skill_gap,
            candidate_exp=candidate_exp,
            minimum_exp=minimum_exp,
        )

        return MatchResultSchema(
            overall_score=overall_score,
            cosine_similarity=cosine_similarity,
            skill_coverage_score=skill_coverage,
            experience_match_score=experience_match,
            matching_skills=matching_skills,
            skill_gap=skill_gap,
            match_reasons=match_reasons,
        )

    @staticmethod
    def _build_reasons(
        matching_skills: list[str],
        skill_gap: list[str],
        candidate_exp: float | None,
        minimum_exp: float | None,
    ) -> list[str]:
        reasons: list[str] = []

        if matching_skills:
            reasons.append(
                "✓ Matching skills: " + ", ".join(matching_skills)
            )

        if skill_gap:
            reasons.append(
                "⚠ Missing required skills: " + ", ".join(skill_gap)
            )

        if minimum_exp is not None and minimum_exp > 0:
            if candidate_exp is None:
                reasons.append(
                    "⚠ Candidate experience unknown; defaulted to 0.5"
                )
            elif candidate_exp >= minimum_exp:
                reasons.append(
                    f"✓ Candidate experience ({candidate_exp} yrs) "
                    f"satisfies minimum requirement ({minimum_exp} yrs)"
                )
            else:
                reasons.append(
                    f"⚠ Candidate experience ({candidate_exp} yrs) "
                    f"below minimum requirement ({minimum_exp} yrs)"
                )

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
