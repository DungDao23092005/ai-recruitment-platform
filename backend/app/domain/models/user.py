from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import UserRole
from app.domain.models.base import BaseDomainEntity


@dataclass(kw_only=True)
class User(BaseDomainEntity):
    email: str
    password_hash: str
    role: UserRole
    is_active: bool = True
