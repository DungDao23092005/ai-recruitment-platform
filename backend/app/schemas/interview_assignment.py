from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InterviewAssignmentCreate(BaseModel):
    user_id: uuid.UUID


class InterviewAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    interview_id: uuid.UUID
    user_id: uuid.UUID
    assigned_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
