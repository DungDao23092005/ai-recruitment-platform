from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
)
from app.domain.enums import MembershipRole, MembershipStatus, UserRole
from app.models import Company, CompanyMembership, RecruiterProfile, User
from app.repositories import (
    CompanyMembershipRepository,
    CompanyRepository,
    UserRepository,
)
from app.schemas.company import CompanyCreate, CompanyUpdate
from app.services.job_service import JobService


class CompanyService:
    def __init__(
        self,
        session: AsyncSession,
        job_service: JobService | None = None,
    ) -> None:
        self.session = session
        self.companies = CompanyRepository(session, Company)
        self.users = UserRepository(session, User)
        self.memberships = CompanyMembershipRepository(
            session, CompanyMembership
        )
        self.job_service = job_service

    async def create_company(self, data: CompanyCreate) -> Company:
        if await self.companies.get_by_slug(data.slug) is not None:
            raise ConflictException(
                f"Đường dẫn (slug) {data.slug!r} đã được sử dụng."
            )
        if await self.companies.get_by_tax_code(data.tax_code) is not None:
            raise ConflictException(
                f"Mã số thuế {data.tax_code!r} đã được sử dụng."
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

    async def create_company_for_owner(
        self,
        data: CompanyCreate,
        owner: User,
    ) -> Company:
        """Create a company and its first Admin membership atomically."""
        loaded_owner = await self.users.get_with_profile(owner.id)
        if loaded_owner is not None:
            owner = loaded_owner
        if await self.companies.get_by_slug(data.slug) is not None:
            raise ConflictException(
                f"Đường dẫn (slug) {data.slug!r} đã được sử dụng."
            )
        if await self.companies.get_by_tax_code(data.tax_code) is not None:
            raise ConflictException(
                f"Mã số thuế {data.tax_code!r} đã được sử dụng."
            )

        company = Company(
            name=data.name,
            slug=data.slug,
            tax_code=data.tax_code,
            size=data.size,
        )
        self.session.add(company)
        await self.session.flush()

        membership = CompanyMembership(
            company_id=company.id,
            user_id=owner.id,
            role=MembershipRole.ADMIN,
            status=MembershipStatus.ACTIVE,
            joined_at=company.created_at,
        )
        self.session.add(membership)

        if owner.recruiter_profile is None:
            self.session.add(
                RecruiterProfile(
                    user_id=owner.id,
                    company_id=company.id,
                )
            )
        elif owner.recruiter_profile.company_id is None:
            owner.recruiter_profile.company_id = company.id

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

    async def list_companies_for_user(self, user: User) -> list[Company]:
        if user.role == UserRole.ADMIN:
            return await self.companies.list_all()
        memberships = await self.memberships.list_active_for_user(user.id)
        return [
            membership.company
            for membership in memberships
            if membership.company is not None
        ]

    async def update_owned_company(
        self,
        user: User,
        company_id: uuid.UUID,
        data: CompanyUpdate,
        workspace_company_id: uuid.UUID | None = None,
    ) -> Company:
        """Update a company using the caller's active workspace membership."""
        if user.role != UserRole.ADMIN:
            company = await self.companies.get_by_id(company_id)
            if company is None:
                raise EntityNotFoundException(
                    f"Company {company_id} not found"
                )
            if workspace_company_id != company_id:
                raise ForbiddenException(
                    f"Not allowed to update company {company_id}"
                )
        return await self.update_company(company_id, data)

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
                    f"Đường dẫn (slug) {data.slug!r} đã được sử dụng."
                )
            company.slug = data.slug
        if data.tax_code is not None and data.tax_code != company.tax_code:
            existing = await self.companies.get_by_tax_code(data.tax_code)
            if existing is not None and existing.id != company.id:
                raise ConflictException(
                    f"Mã số thuế {data.tax_code!r} đã được sử dụng."
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

    async def delete_company(
        self,
        user: User,
        company_id: uuid.UUID,
        job_service: JobService | None = None,
    ) -> Company:
        """Soft-delete a company and cascade-delete its active jobs.

        Admin-only operation enforced by the API layer. The company is soft
        deleted (``is_deleted = True``); no rows are hard deleted. Every
        active job owned by the company is first removed through the existing
        ``JobService.delete_job`` (soft delete + Qdrant vector removal), so
        no duplicate job-deletion logic exists. Applications attached to those
        jobs are preserved.

        If a Qdrant failure occurs mid-cascade, the jobs deleted so far remain
        soft-deleted while the company stays active (the safe direction: the
        remaining jobs stay visible and searchable). Re-running the operation
        deletes the rest.
        """
        company = await self.companies.get_by_id(company_id)
        if company is None:
            raise EntityNotFoundException(f"Company {company_id} not found")

        cascade = job_service or self.job_service or JobService(self.session)
        jobs = await cascade.jobs.list_jobs_by_company(company_id)
        for job in jobs:
            await cascade.delete_job(user, job.id)

        await self.companies.soft_delete(company)
        try:
            await self.session.commit()
            await self.session.refresh(company)
        except Exception:
            await self.session.rollback()
            raise
        return company