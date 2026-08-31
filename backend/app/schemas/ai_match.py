from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MatchResultSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    overall_score: float = Field(
        description="Final match score from 0.0 to 100.0"
    )
    cosine_similarity: float = Field(
        description="Semantic/Cosine similarity from 0.0 to 1.0"
    )
    skill_coverage_score: float = Field(
        description="Required skill coverage from 0.0 to 1.0"
    )
    preferred_skill_coverage_score: float = Field(
        default=0.0,
        description="Preferred skill coverage from 0.0 to 1.0"
    )
    experience_match_score: float = Field(
        description="Experience compatibility from 0.0 to 1.0"
    )
    education_score: float = Field(
        default=0.0,
        description="Education compatibility from 0.0 to 1.0"
    )
    project_score: float = Field(
        default=0.0,
        description="Project relevance score from 0.0 to 1.0"
    )

    # Requirement presence flags
    has_required_skills: bool = Field(
        default=False,
        description="Whether the job has any required skills defined"
    )
    has_preferred_skills: bool = Field(
        default=False,
        description="Whether the job has any preferred skills defined"
    )
    has_experience_requirement: bool = Field(
        default=False,
        description="Whether the job has a minimum experience requirement"
    )
    has_education_requirement: bool = Field(
        default=False,
        description="Whether the job has an education level requirement"
    )

    matching_skills: list[str] = Field(
        default_factory=list,
        description="Skills the candidate shares with the job requirements",
    )
    skill_gap: list[str] = Field(
        default_factory=list,
        description="Required skills the candidate is missing",
    )
    match_reasons: list[str] = Field(
        default_factory=list,
        description="Deterministic human-readable matching reasons",
    )
