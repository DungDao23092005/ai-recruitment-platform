from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Mirrors ``app.models.application_note.CONTENT_MAX_LENGTH`` (asserted by the
# unit tests so the two can never drift). Recruiter notes are bounded so the
# column stays indexable and predictable.
NOTE_CONTENT_MAX_LENGTH = 2000


class ApplicationNoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=NOTE_CONTENT_MAX_LENGTH)

    @field_validator("content")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Note content must not be blank")
        return stripped


class ApplicationNoteUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=NOTE_CONTENT_MAX_LENGTH)

    @field_validator("content")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Note content must not be blank")
        return stripped


class ApplicationNoteRead(BaseModel):
    """Recruiter-only view of an internal note.

    Notes are never serialised to candidates; this schema is only used by
    recruiter/admin endpoints.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    author_id: uuid.UUID
    content: str
    created_at: datetime
    updated_at: datetime
