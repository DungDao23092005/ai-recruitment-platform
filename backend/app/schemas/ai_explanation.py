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


class ExplainMatchResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: str = Field(
        ...,
        description="High-level explanation of why the candidate matches (or not)",
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="Specific candidate strengths grounded in the provided facts",
    )
    skill_gaps: list[str] = Field(
        default_factory=list,
        description="Skills the candidate is missing according to the provided facts",
    )
    experience_analysis: str = Field(
        ...,
        description="Analysis of the candidate's experience versus the job requirement",
    )
    recommendation: str = Field(
        ...,
        description="Actionable recommendation for the recruiter or candidate",
    )
