from __future__ import annotations

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
