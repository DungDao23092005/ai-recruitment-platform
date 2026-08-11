from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import CompanySize
from app.domain.models.base import BaseDomainEntity


@dataclass(kw_only=True)
class Company(BaseDomainEntity):
    name: str
    slug: str
    tax_code: str
    size: CompanySize
