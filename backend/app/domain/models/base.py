from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DomainException(ValueError):
    """Raised when a business domain rule is violated."""


@dataclass(kw_only=True)
class BaseDomainEntity:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    is_deleted: bool = False

    def mark_updated(self) -> None:
        self.updated_at = utc_now()

    def soft_delete(self) -> None:
        self.is_deleted = True
        self.mark_updated()
