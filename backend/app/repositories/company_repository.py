from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select

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

    async def get_admin_company(self, company_id: Any) -> Company | None:
        """Fetch a company for admin views, including soft-deleted companies."""
        stmt = select(Company).where(Company.id == company_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_admin_companies(
        self,
        skip: int,
        limit: int,
        search: str | None = None,
    ) -> tuple[list[Company], int]:
        """List companies for the admin console.

        Unlike the default repository queries, soft-deleted companies are
        included so locked companies remain visible to administrators.
        Supports an optional case-insensitive search across the company
        name, slug, and tax code.
        """
        filters = []
        if search:
            term = f"%{search.strip()}%"
            filters.append(
                or_(
                    Company.name.ilike(term),
                    Company.slug.ilike(term),
                    Company.tax_code.ilike(term),
                )
            )

        count_stmt = select(func.count()).select_from(Company)
        list_stmt = select(Company).order_by(Company.created_at.desc())

        if filters:
            count_stmt = count_stmt.where(*filters)
            list_stmt = list_stmt.where(*filters)

        total = (await self.session.execute(count_stmt)).scalar_one()
        list_stmt = list_stmt.offset(skip).limit(limit)
        rows = (await self.session.execute(list_stmt)).scalars().all()
        return list(rows), total
