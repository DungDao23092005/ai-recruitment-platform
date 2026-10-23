from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import AdminAuditAction


class AdminAuditLogRead(BaseModel):
    """Read-only projection of an admin audit record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    admin_id: uuid.UUID
    admin_email: str | None = None
    target_user_id: uuid.UUID
    target_user_email: str | None = None
    action: AdminAuditAction
    reason: str | None = None
    details: dict[str, Any] | None = None
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def _normalize_created_at(cls, value: Any) -> Any:
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class AdminAuditLogListParams(BaseModel):
    """Filters for the admin audit ledger.

    ``created_from`` and ``created_to`` are inclusive UTC instants. Naive
    datetimes are interpreted as UTC. ``search`` is a literal substring match
    over the reason and current actor/target email addresses.
    """

    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    action: AdminAuditAction | None = None
    admin_id: uuid.UUID | None = None
    target_user_id: uuid.UUID | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    search: str | None = Field(default=None, max_length=100)

    @field_validator("created_from", "created_to")
    @classmethod
    def _normalize_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @field_validator("search")
    @classmethod
    def _normalize_search(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @model_validator(mode="after")
    def _validate_time_window(self) -> AdminAuditLogListParams:
        if (
            self.created_from is not None
            and self.created_to is not None
            and self.created_from > self.created_to
        ):
            raise ValueError("created_from must be earlier than or equal to created_to")
        return self


class AdminAuditLogListResponse(BaseModel):
    items: list[AdminAuditLogRead]
    total: int
    skip: int
    limit: int
