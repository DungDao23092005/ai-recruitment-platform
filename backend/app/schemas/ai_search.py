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
