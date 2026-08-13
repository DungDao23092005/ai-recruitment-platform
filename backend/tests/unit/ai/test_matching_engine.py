from __future__ import annotations

import pytest

from app.ai.matching.cosine_engine import compute_cosine_similarity
from app.ai.matching.matching_engine import MatchingEngine, rank_matches
from app.ai.matching.rules_engine import RulesEngine
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema

A = compute_cosine_similarity


def make_resume(
    skills: list[str] | None = None,
    years: float | None = None,
) -> ParsedResumeSchema:
    return ParsedResumeSchema(
        skills=skills or [],
        total_years_experience=years,
    )


def make_job(
    required_skills: list[str] | None = None,
    minimum_years: float | None = None,
) -> ParsedJobSchema:
    return ParsedJobSchema(
        required_skills=required_skills or [],
        minimum_years_experience=minimum_years,
    )


class TestCosineSimilarity:
    def test_identical_vectors_returns_1(self):
        assert A([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0

    def test_orthogonal_vectors_returns_0(self):
        assert A([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_empty_vector_returns_0(self):
        assert A([], [1.0, 2.0]) == 0.0
        assert A([1.0, 2.0], []) == 0.0
        assert A([], []) == 0.0

    def test_different_dimensions_returns_0(self):
        assert A([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0

    def test_zero_vector_returns_0(self):
        assert A([0.0, 0.0], [1.0, 2.0]) == 0.0
        assert A([1.0, 2.0], [0.0, 0.0]) == 0.0

    def test_negative_cosine_clamped_to_0(self):
        assert A([1.0, 0.0], [-1.0, 0.0]) == 0.0

    def test_none_vector_returns_0(self):
        assert A(None, [1.0, 2.0]) == 0.0
        assert A([1.0, 2.0], None) == 0.0
        assert A(None, None) == 0.0

    def test_partial_similarity_value(self):
        assert A([1.0, 0.0], [1.0, 1.0]) == pytest.approx(
            1.0 / (2 ** 0.5)
        )


class TestRulesEngineSkills:
    def setup_method(self):
        self.engine = RulesEngine()

    def test_full_required_skill_match(self):
        matching = self.engine.match_skills(
            ["Python", "FastAPI"], ["Python", "FastAPI"]
        )
        coverage = self.engine.required_skill_coverage(
            ["Python", "FastAPI"], matching
        )
        assert matching == ["Python", "FastAPI"]
        assert coverage == 1.0
        assert self.engine.skill_gap(["Python", "FastAPI"], matching) == []

    def test_partial_required_skill_match(self):
        matching = self.engine.match_skills(
            ["Python", "Docker"], ["Python", "FastAPI", "PostgreSQL"]
        )
        coverage = self.engine.required_skill_coverage(
            ["Python", "FastAPI", "PostgreSQL"], matching
        )
        assert matching == ["Python"]
        assert coverage == pytest.approx(1 / 3)

    def test_missing_required_skills_produce_gap(self):
        matching = self.engine.match_skills(
            ["Python"], ["FastAPI", "PostgreSQL"]
        )
        gap = self.engine.skill_gap(["FastAPI", "PostgreSQL"], matching)
        assert matching == []
        assert gap == ["FastAPI", "PostgreSQL"]

    def test_case_insensitive_matching(self):
        matching = self.engine.match_skills(
            ["Python", "FastAPI", "Docker"],
            ["python", "fastapi", "PostgreSQL"],
        )
        gap = self.engine.skill_gap(
            ["python", "fastapi", "PostgreSQL"], matching
        )
        assert matching == ["Python", "FastAPI"]
        assert gap == ["PostgreSQL"]

    def test_no_required_skills_returns_coverage_1(self):
        coverage = self.engine.required_skill_coverage([], [])
        assert coverage == 1.0

    def test_empty_candidate_skills_does_not_crash(self):
        matching = self.engine.match_skills([], ["Python", "SQL"])
        assert matching == []
        coverage = self.engine.required_skill_coverage(
            ["Python", "SQL"], matching
        )
        assert coverage == 0.0


class TestRulesEngineExperience:
    def setup_method(self):
        self.engine = RulesEngine()

    def test_candidate_meets_or_exceeds_minimum(self):
        assert self.engine.experience_match(5.0, 3.0) == 1.0
        assert self.engine.experience_match(3.0, 3.0) == 1.0

    def test_candidate_below_minimum_uses_ratio(self):
        assert self.engine.experience_match(1.0, 3.0) == pytest.approx(
            1 / 3
        )

    def test_missing_candidate_experience_returns_0_5(self):
        assert self.engine.experience_match(None, 3.0) == 0.5

    def test_missing_minimum_experience_returns_1(self):
        assert self.engine.experience_match(5.0, None) == 1.0
        assert self.engine.experience_match(None, None) == 1.0


class TestMatchingEngine:
    def setup_method(self):
        self.engine = MatchingEngine()

    def test_perfect_match_scores_100(self):
        resume = make_resume(
            skills=["Python", "FastAPI", "Docker"], years=5.0
        )
        job = make_job(
            required_skills=["Python", "FastAPI", "Docker"],
            minimum_years=3.0,
        )
        vector = [1.0, 0.0, 0.0, 0.0]

        result = self.engine.match_resume_to_job(
            resume, job, resume_vector=vector, job_vector=vector
        )

        assert result.overall_score == 100.0
        assert result.cosine_similarity == 1.0
        assert result.skill_coverage_score == 1.0
        assert result.experience_match_score == 1.0
        assert result.matching_skills == ["Python", "FastAPI", "Docker"]
        assert result.skill_gap == []

    def test_partial_match_formula(self):
        resume = make_resume(skills=["Python"], years=1.0)
        job = make_job(
            required_skills=["Python", "FastAPI", "PostgreSQL"],
            minimum_years=3.0,
        )
        resume_vector = [1.0, 0.0, 0.0, 0.0]
        job_vector = [1.0, 1.0, 0.0, 0.0]

        result = self.engine.match_resume_to_job(
            resume, job,
            resume_vector=resume_vector, job_vector=job_vector,
        )

        expected_overall = round(
            (
                A(resume_vector, job_vector) * 0.6
                + (1 / 3) * 0.3
                + (1.0 / 3.0) * 0.1
            )
            * 100,
            2,
        )
        assert result.overall_score == expected_overall
        assert result.skill_coverage_score == pytest.approx(1 / 3)
        assert result.experience_match_score == pytest.approx(1 / 3)

    def test_missing_vectors_use_zero_cosine(self):
        resume = make_resume(skills=["Python"], years=5.0)
        job = make_job(required_skills=["Python"], minimum_years=3.0)

        result = self.engine.match_resume_to_job(resume, job)

        assert result.cosine_similarity == 0.0
        assert result.overall_score == pytest.approx(40.0)

    def test_missing_data_does_not_crash(self):
        result = self.engine.match_resume_to_job(
            make_resume(), make_job()
        )
        assert isinstance(result, MatchResultSchema)
        assert result.skill_coverage_score == 1.0
        assert result.experience_match_score == 1.0

        result = self.engine.match_resume_to_job(None, None)
        assert isinstance(result, MatchResultSchema)
        assert result.overall_score == 0.0

    def test_match_reasons_generated(self):
        resume = make_resume(skills=["Python", "SQL"], years=5.0)
        job = make_job(
            required_skills=["Python", "PostgreSQL"], minimum_years=3.0
        )

        result = self.engine.match_resume_to_job(resume, job)

        joined = " ".join(result.match_reasons)
        assert "Python" in joined
        assert "PostgreSQL" in joined
        assert "experience" in joined
        assert any("5" in reason for reason in result.match_reasons)

    def test_matching_skills_correct(self):
        resume = make_resume(skills=["Python", "Kubernetes", "SQL"])
        job = make_job(required_skills=["python", "SQL", "Docker"])

        result = self.engine.match_resume_to_job(resume, job)

        assert result.matching_skills == ["Python", "SQL"]

    def test_skill_gap_correct(self):
        resume = make_resume(skills=["Python"])
        job = make_job(
            required_skills=["Python", "Docker", "Kubernetes"]
        )

        result = self.engine.match_resume_to_job(resume, job)

        assert result.skill_gap == ["Docker", "Kubernetes"]

    def test_resume_direction_and_job_direction_same_engine(self):
        resume = make_resume(skills=["Python"], years=2.0)
        job = make_job(required_skills=["Python"], minimum_years=3.0)

        from_resume = self.engine.match_resume_to_job(
            resume, job, [1.0, 0.0], [1.0, 0.0]
        )
        from_job = self.engine.match_resume_to_job(
            resume, job, [1.0, 0.0], [1.0, 0.0]
        )

        assert from_resume.overall_score == from_job.overall_score


class TestRankMatches:
    def test_rank_descending_by_overall_score(self):
        item1 = (1, MatchResultSchema(
            overall_score=50.0, cosine_similarity=0.5,
            skill_coverage_score=0.5, experience_match_score=0.5,
        ))
        item2 = (2, MatchResultSchema(
            overall_score=90.0, cosine_similarity=0.9,
            skill_coverage_score=0.9, experience_match_score=0.9,
        ))
        item3 = (3, MatchResultSchema(
            overall_score=30.0, cosine_similarity=0.3,
            skill_coverage_score=0.3, experience_match_score=0.3,
        ))

        ranked = rank_matches([item1, item2, item3])

        assert [item[0] for item in ranked] == [2, 1, 3]

    def test_equal_scores_preserve_deterministic_order(self):
        item1 = (1, MatchResultSchema(
            overall_score=70.0, cosine_similarity=0.7,
            skill_coverage_score=0.7, experience_match_score=0.7,
        ))
        item2 = (2, MatchResultSchema(
            overall_score=70.0, cosine_similarity=0.7,
            skill_coverage_score=0.7, experience_match_score=0.7,
        ))
        item3 = (3, MatchResultSchema(
            overall_score=70.0, cosine_similarity=0.7,
            skill_coverage_score=0.7, experience_match_score=0.7,
        ))

        ranked = rank_matches([item1, item2, item3])

        assert [item[0] for item in ranked] == [1, 2, 3]

    def test_does_not_mutate_original_list(self):
        item1 = (1, MatchResultSchema(
            overall_score=50.0, cosine_similarity=0.5,
            skill_coverage_score=0.5, experience_match_score=0.5,
        ))
        item2 = (2, MatchResultSchema(
            overall_score=90.0, cosine_similarity=0.9,
            skill_coverage_score=0.9, experience_match_score=0.9,
        ))
        original = [item1, item2]

        rank_matches(original)

        assert original == [item1, item2]
