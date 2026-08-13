from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema


class JobMatchRecommendation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    job_id: uuid.UUID = Field(..., description="Target Job UUID")
    parsed_job: ParsedJobSchema | None = Field(
        default=None, description="Parsed Job Description details"
    )
    match_result: MatchResultSchema = Field(
        ..., description="Match score details and explanation"
    )


class CandidateMatchRecommendation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: uuid.UUID = Field(..., description="Candidate Profile UUID")
    parsed_resume: ParsedResumeSchema | None = Field(
        default=None, description="Parsed Candidate Resume details"
    )
    match_result: MatchResultSchema = Field(
        ..., description="Match score details and explanation"
    )
