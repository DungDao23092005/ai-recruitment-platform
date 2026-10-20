from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema


class ExplainMatchRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    match_result: MatchResultSchema = Field(
        ...,
        description="Match score details and explanation produced by the matching engine",
    )
    candidate: ParsedResumeSchema | None = Field(
        default=None, description="Parsed candidate resume details"
    )
    job: ParsedJobSchema | None = Field(
        default=None, description="Parsed job description details"
    )


class EvidenceItem(BaseModel):
    source: str = Field(..., description="Source of the evidence, e.g., 'candidate_cv', 'job_description'")
    section: str = Field(..., description="Section the evidence was found in, e.g., 'work_experience', 'skills'")
    content: str = Field(..., description="The actual evidence text or description")


class ExplainMatchResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    match_score: float = Field(
        ...,
        description="The overall match score (from match_result)"
    )
    summary: str = Field(
        ...,
        description="High-level explanation of why the candidate matches (or not)",
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="Specific candidate strengths grounded in the provided facts",
    )
    missing_skills: list[str] = Field(
        default_factory=list,
        description="Skills the candidate is missing according to the provided facts",
    )
    experience_analysis: str = Field(
        ...,
        description="Analysis of the candidate's experience versus the job requirement",
    )
    education_analysis: str = Field(
        ...,
        description="Analysis of the candidate's education versus the job requirement",
    )
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="Specific pieces of evidence extracted from CV and JD to support the analysis",
    )
    recommendation: str = Field(
        ...,
        description="Actionable recommendation for the recruiter or candidate",
    )
    confidence: float = Field(
        ...,
        description="Confidence score in the explanation (0.0 to 1.0)",
    )


# ---------------------------------------------------------------------------
# Feature 5 - Explainable AI Matching (Phase 1)
#
# The models below are the canonical, backward-compatible evolution of the
# prototype explanation contract. The legacy ``ExplainMatchResponse`` /
# ``EvidenceItem`` pair above is preserved untouched for existing consumers.
# The canonical evidence field is now ``EvidenceExcerpt.quote``: unlike the
# free-form ``EvidenceItem.content`` (which the LLM may paraphrase), a
# ``quote`` is guaranteed to be a verbatim substring of the candidate's
# ``Resume.parsed_data`` after passing through the deterministic
# ``EvidenceVerifier``. Evidence that cannot be verified is dropped and the
# associated claim is downgraded - never fabricated.
#
# The free-form ``summary`` prose is NOT quote-verified: it is either an
# LLM-generated narrative (``summary_source == "ai_generated"``) or a local
# deterministic fallback ("deterministic"). Only ``evidence`` and the
# per-skill/per-experience evaluations are produced by the deterministic
# verifier.
# ---------------------------------------------------------------------------

SkillMatchStatus = Literal[
    "matched_evidenced",
    "partially_matched",
    "not_evidenced_in_cv",
    "insufficient_data",
]
RequirementType = Literal["required", "preferred"]
SummarySource = Literal["deterministic", "ai_generated"]


class EvidenceExcerpt(BaseModel):
    """A single, verifiable piece of evidence drawn from the candidate CV.

    ``quote`` must be a verbatim substring of the referenced resume field; the
    deterministic ``EvidenceVerifier`` is the only producer of this model.
    """

    model_config = ConfigDict(extra="forbid")

    section: str = Field(
        ...,
        description=(
            "Resume section the excerpt was taken from, e.g. 'skills', "
            "'experiences', 'projects', 'summary', 'education'."
        ),
    )
    field_name: str | None = Field(
        default=None,
        description="Specific field within the section, e.g. 'description'.",
    )
    item_index: int | None = Field(
        default=None,
        description="Zero-based index of the item within a list section.",
    )
    item_title: str | None = Field(
        default=None,
        description="Human-readable item label, e.g. a role title or project name.",
    )
    quote: str = Field(
        ...,
        description="Verbatim text from the resume that supports the claim.",
    )


class SkillEvaluation(BaseModel):
    """How a single job skill requirement relates to the candidate CV."""

    model_config = ConfigDict(extra="forbid")

    skill_name: str = Field(..., description="The skill being evaluated.")
    requirement_type: RequirementType = Field(
        ..., description="Whether the skill is a required or preferred skill."
    )
    status: SkillMatchStatus = Field(
        ...,
        description=(
            "matched_evidenced: found in the CV with evidence; "
            "partially_matched: implied by related CV content but not listed "
            "as a discrete skill; not_evidenced_in_cv: not found in the "
            "provided CV (never a claim that the candidate lacks it); "
            "insufficient_data: no parsed CV available to evaluate."
        ),
    )
    explanation: str = Field(
        ..., description="Human-readable, grounded explanation of the status."
    )
    evidence: list[EvidenceExcerpt] = Field(
        default_factory=list,
        description="Verified excerpts supporting the status (may be empty).",
    )


class ExperienceEvaluation(BaseModel):
    """Deterministic evaluation of one work experience versus the job."""

    model_config = ConfigDict(extra="forbid")

    role_title: str | None = Field(default=None, description="Role title held.")
    company: str | None = Field(default=None, description="Employer name.")
    duration: str | None = Field(
        default=None,
        description=(
            "Human-readable duration, only populated when reliably derivable "
            "from structured start/end dates; otherwise null."
        ),
    )
    relevance: str = Field(
        ...,
        description=(
            "Deterministic relevance label, e.g. 'relevant_skills' or "
            "'no_overlap_with_requirements'."
        ),
    )
    explanation: str = Field(
        ..., description="Grounded explanation of the relevance assessment."
    )
    evidence: list[EvidenceExcerpt] = Field(
        default_factory=list,
        description="Verified excerpts supporting the assessment.",
    )


class ScoreBreakdown(BaseModel):
    """The existing deterministic score components, surfaced unchanged."""

    model_config = ConfigDict(extra="forbid")

    overall_score: float
    cosine_similarity: float
    skill_coverage_score: float
    preferred_skill_coverage_score: float
    experience_match_score: float
    education_score: float
    project_score: float


class ApplicationMatchExplanationResponse(BaseModel):
    """Explainable, evidence-grounded explanation for an application match.

    Scores are copied verbatim from the existing deterministic matching engine
    (``MatchResultSchema``) and are never recalculated or rounded here.
    """

    model_config = ConfigDict(extra="forbid")

    application_id: uuid.UUID = Field(
        ..., description="The application this explanation belongs to."
    )
    overall_score: float = Field(
        ..., description="Overall match score, copied from the matching engine."
    )
    score_breakdown: ScoreBreakdown = Field(
        ..., description="Existing score components, copied unchanged."
    )
    summary: str = Field(
        ...,
        description=(
            "High-level narrative of the match. This prose is NOT "
            "quote-verified: when ``summary_source`` is 'ai_generated' it is "
            "LLM-generated; when 'deterministic' it is built locally from the "
            "engine result. Verified facts live in ``evidence`` and the "
            "per-skill/per-experience evaluations."
        ),
    )
    summary_source: SummarySource = Field(
        default="deterministic",
        description=(
            "Where ``summary`` came from. 'ai_generated' means LLM prose that "
            "is not quote-verified; 'deterministic' means the local fallback. "
            "In both cases ``evidence`` is produced by the deterministic "
            "EvidenceVerifier."
        ),
    )
    skill_evaluations: list[SkillEvaluation] = Field(
        default_factory=list,
        description="Per-skill evaluation grounded in the candidate CV.",
    )
    experience_evaluations: list[ExperienceEvaluation] = Field(
        default_factory=list,
        description="Per-experience evaluation grounded in the candidate CV.",
    )
    key_strengths: list[str] = Field(
        default_factory=list,
        description="Grounded strengths derived from verified evidence.",
    )
    areas_for_inquiry: list[str] = Field(
        default_factory=list,
        description=(
            "Topics a recruiter should probe in an interview; these are "
            "open questions, never assertions of absence."
        ),
    )
    evidence: list[EvidenceExcerpt] = Field(
        default_factory=list,
        description=(
            "All candidate excerpts referenced above. Every quote is a "
            "verbatim substring of the parsed CV, produced by the "
            "deterministic EvidenceVerifier - unlike the AI narrative summary."
        ),
    )
    data_limitations: list[str] = Field(
        default_factory=list,
        description="Honest notes about missing or unverifiable source data.",
    )
    confidence: float | None = Field(
        default=None,
        description=(
            "Reserved for a future supported signal. Left null in Phase 1: no "
            "confidence value is invented."
        ),
    )
    model_version: str | None = Field(
        default=None,
        description=(
            "Identifier of the configured model that produced the AI "
            "narrative (for example the provider's real ``model_name``), when "
            "one was used; null for a purely deterministic explanation or "
            "when the provider exposes no reliable identifier. Never a "
            "guessed class name."
        ),
    )
    generated_at: datetime = Field(
        ..., description="UTC timestamp the explanation was generated."
    )
    cache_state: Literal["not_cached"] = Field(
        default="not_cached",
        description=(
            "Honest cache indicator. Phase 1 performs no caching, so this is "
            "always 'not_cached'."
        ),
    )
