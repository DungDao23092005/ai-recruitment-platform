from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SemanticSearchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(
        ..., description="Vector point id (job id or candidate id)"
    )
    score: float = Field(
        ..., description="Semantic similarity score from the vector store"
    )
    skills: list[str] = Field(
        default_factory=list,
        description="Skills stored in the vector point payload",
    )
    created_at: str | None = Field(
        default=None, description="Creation timestamp stored in payload"
    )
    full_name: str | None = Field(
        default=None, description="Candidate full name (enriched from profile)"
    )
    title: str | None = Field(
        default=None,
        description="Candidate professional title or Job title (enriched from profile)",
    )
    company_name: str | None = Field(
        default=None, description="Company name for job results (enriched from database)"
    )
    location: str | None = Field(
        default=None, description="Job location (enriched from database)"
    )
