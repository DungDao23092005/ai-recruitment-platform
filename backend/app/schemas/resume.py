from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.ai_resume import ParsedResumeSchema


class ResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    candidate_id: uuid.UUID
    title: str | None = None
    is_primary: bool
    parsed_data: ParsedResumeSchema | None = None
    created_at: datetime
    updated_at: datetime