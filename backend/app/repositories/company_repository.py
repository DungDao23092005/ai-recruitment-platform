from __future__ import annotations

from sqlalchemy import select

from app.models import Company
from app.repositories.base import BaseRepository


class CompanyRepository(BaseRepository[Company]):
    async def get_by_slug(self, slug: str) -> Company | None:
        stmt = select(Company).where(
            Company.slug == slug,
            Company.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_tax_code(self, tax_code: str) -> Company | None:
        stmt = select(Company).where(
            Company.tax_code == tax_code,
            Company.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
