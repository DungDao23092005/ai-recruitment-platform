from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ai_resume import ParsedResumeSchema


class ResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    candidate_id: uuid.UUID
    title: str | None = None
    is_primary: bool
    is_confirmed: bool
    confirmed_at: datetime | None = None
    parsed_data: ParsedResumeSchema | None = None
    created_at: datetime
    updated_at: datetime


class ResumeDraftUpdate(BaseModel):
    parsed_data: ParsedResumeSchema
    title: str | None = Field(default=None, max_length=255)


class ResumeConfirmationRead(BaseModel):
    resume: ResumeRead
    indexing_status: Literal["indexed", "failed"]
    message: str
