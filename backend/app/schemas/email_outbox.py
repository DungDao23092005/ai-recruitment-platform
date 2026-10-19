from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import OutboxStatus


class EmailOutboxRead(BaseModel):
    """Admin-facing view of a queued notification email.

    Deliberately excludes ``html_body``/``text_body`` (raw, potentially
    PII-bearing content) and any provider configuration. Only delivery metadata
    is exposed so an operator can diagnose stuck messages.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    to_email: str
    subject: str
    status: OutboxStatus
    attempts: int
    max_attempts: int
    next_attempt_at: datetime
    processing_started_at: datetime | None = None
    sent_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class EmailOutboxListResponse(BaseModel):
    items: list[EmailOutboxRead]
    total: int
    skip: int
    limit: int


class EmailOutboxStatsResponse(BaseModel):
    pending: int
    processing: int
    sent: int
    failed: int
    total: int
    oldest_pending_created_at: datetime | None = None
