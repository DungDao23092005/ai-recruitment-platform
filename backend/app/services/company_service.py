from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, EntityNotFoundException
from app.models import Company
from app.repositories import CompanyRepository
from app.schemas.company import CompanyCreate, CompanyUpdate


class CompanyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.companies = CompanyRepository(session, Company)

    async def create_company(self, data: CompanyCreate) -> Company:
        if await self.companies.get_by_slug(data.slug) is not None:
            raise ConflictException(
                f"Company with slug {data.slug!r} already exists"
            )
        if await self.companies.get_by_tax_code(data.tax_code) is not None:
            raise ConflictException(
                f"Company with tax_code {data.tax_code!r} already exists"
            )

        company = Company(
            name=data.name,
            slug=data.slug,
            tax_code=data.tax_code,
            size=data.size,
        )
        self.session.add(company)
        try:
            await self.session.commit()
            await self.session.refresh(company)
        except Exception:
            await self.session.rollback()
            raise
        return company

    async def get_company_by_id(self, company_id: uuid.UUID) -> Company | None:
        return await self.companies.get_by_id(company_id)

    async def list_companies(self) -> list[Company]:
        return await self.companies.list_all()

    async def update_company(
        self,
        company_id: uuid.UUID,
        data: CompanyUpdate,
    ) -> Company:
        company = await self.companies.get_by_id(company_id)
        if company is None:
            raise EntityNotFoundException(f"Company {company_id} not found")

        if data.name is not None:
            company.name = data.name
        if data.slug is not None and data.slug != company.slug:
            existing = await self.companies.get_by_slug(data.slug)
            if existing is not None and existing.id != company.id:
                raise ConflictException(
                    f"Company with slug {data.slug!r} already exists"
                )
            company.slug = data.slug
        if data.tax_code is not None and data.tax_code != company.tax_code:
            existing = await self.companies.get_by_tax_code(data.tax_code)
            if existing is not None and existing.id != company.id:
                raise ConflictException(
                    f"Company with tax_code {data.tax_code!r} already exists"
                )
            company.tax_code = data.tax_code
        if data.size is not None:
            company.size = data.size

        try:
            await self.session.commit()
            await self.session.refresh(company)
        except Exception:
            await self.session.rollback()
            raise
        return company