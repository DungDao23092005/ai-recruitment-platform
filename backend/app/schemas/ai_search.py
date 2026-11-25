from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import ContactRequestStatus


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


class CandidatePreviewResponse(BaseModel):
    """Masked candidate profile and resume preview for discovery.

    Explicitly excludes email and phone numbers, and redacts PII in work experiences and education.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str | None = None
    title: str | None = None
    summary: str | None = None
    total_years_experience: float | int | None = None
    skills: list[str] = Field(default_factory=list)
    experiences: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    contact_request_status: ContactRequestStatus | None = None
    contact_request_id: uuid.UUID | None = None
    can_request_contact: bool = True
    cooldown_until: datetime | None = None
