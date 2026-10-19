from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApplicationActivityRead(BaseModel):
    """Recruiter/admin projection of an application-history entry.

    Exposes actor identity, the event type, any status change, the optional
    short internal note and structured metadata. Never serialised to
    candidates.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    actor_id: uuid.UUID
    action_type: str
    from_status: str | None = None
    to_status: str | None = None
    note: str | None = None
    metadata_json: str | None = None
    created_at: datetime


class CandidateApplicationActivityRead(BaseModel):
    """Candidate-facing timeline entry.

    Deliberately minimal: the candidate only sees *what* changed and *when*,
    never the actor's identity, the internal note, or the free-form metadata
    (which may reference private evaluation/note ids).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action_type: str
    from_status: str | None = None
    to_status: str | None = None
    created_at: datetime
