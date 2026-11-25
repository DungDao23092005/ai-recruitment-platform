from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import ContactRequestStatus


class ContactRequestCreate(BaseModel):
    candidate_id: uuid.UUID = Field(
        ..., description="Candidate profile ID to request contact authorization for"
    )


class ContactRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    candidate_id: uuid.UUID
    requester_user_id: uuid.UUID
    status: ContactRequestStatus
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    responded_at: datetime | None = None
    revoked_at: datetime | None = None

    # Extra enriched metadata for frontend display
    company_name: str | None = None
    candidate_name: str | None = None
    candidate_title: str | None = None


class ContactRequestStatusCheck(BaseModel):
    candidate_id: uuid.UUID
    status: ContactRequestStatus | None = None
    can_request: bool
    request_id: uuid.UUID | None = None
    cooldown_until: datetime | None = None
    reason: str | None = None


class CandidateContactResponse(BaseModel):
    """Authorized contact information disclosed only when an active ACCEPTED request exists."""

    candidate_id: uuid.UUID
    full_name: str | None = None
    email: str
    phone: str | None = None
    disclosed_at: datetime
