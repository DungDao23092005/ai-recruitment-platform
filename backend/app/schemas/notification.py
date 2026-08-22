from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    content: str
    notification_type: str
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    is_read: bool = False


class NotificationRead(NotificationBase):
    id: uuid.UUID
    created_at: datetime


class UnreadCountResponse(BaseModel):
    unread_count: int