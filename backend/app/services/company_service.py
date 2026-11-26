from __future__ import annotations

import uuid
from datetime import datetime, timezone

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
from app.services.company_email_service import CompanyEmailService
from app.services.company_entitlement_service import CompanyEntitlementService
from app.services.job_service import JobService
from app.services.notification_service import NotificationService


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
        self.notifications = NotificationService(session)
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

        await self.session.flush()

        try:
            # Company Free is provisioned in the same transaction as the
            # workspace, owner membership and RecruiterProfile. A missing
            # canonical plan raises before commit, so no workspace is ever
            # created without an entitlement.
            entitlement_service = CompanyEntitlementService(self.session)
            await entitlement_service.provision_company_free_subscription(
                company.id
            )
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
        return await self.update_company(company_id, data, updated_by=user)

    async def update_company(
        self,
        company_id: uuid.UUID,
        data: CompanyUpdate,
        updated_by: User | None = None,
    ) -> Company:
        company = await self.companies.get_by_id(company_id)
        if company is None:
            raise EntityNotFoundException(f"Company {company_id} not found")

        changed_labels: list[str] = []
        if data.name is not None and data.name != company.name:
            company.name = data.name
            changed_labels.append("tên công ty")
        if data.slug is not None and data.slug != company.slug:
            existing = await self.companies.get_by_slug(data.slug)
            if existing is not None and existing.id != company.id:
                raise ConflictException(
                    f"Đường dẫn (slug) {data.slug!r} đã được sử dụng."
                )
            company.slug = data.slug
            changed_labels.append("đường dẫn (slug)")
        if data.tax_code is not None and data.tax_code != company.tax_code:
            existing = await self.companies.get_by_tax_code(data.tax_code)
            if existing is not None and existing.id != company.id:
                raise ConflictException(
                    f"Mã số thuế {data.tax_code!r} đã được sử dụng."
                )
            company.tax_code = data.tax_code
            changed_labels.append("mã số thuế")
        if data.size is not None and data.size != company.size:
            company.size = data.size
            changed_labels.append("quy mô")

        # PO-3 (Option A): No-Op Suppression
        if not changed_labels:
            try:
                await self.session.commit()
                await self.session.refresh(company)
            except Exception:
                await self.session.rollback()
                raise
            return company

        # Query all active members of the company (tenant isolation & PO-2 Option B)
        memberships = await self.memberships.list_by_company(
            company_id, include_revoked=False
        )

        # PO-4 (Option A): Platform Admin Attribution vs Member Name
        is_company_member = False
        updater_member = None
        if updated_by is not None:
            updater_member = next(
                (m for m in memberships if m.user_id == updated_by.id), None
            )
            if updater_member is not None:
                is_company_member = True

        if updated_by is None:
            updater_name = "Quản trị viên hệ thống"
        elif updated_by.role == UserRole.ADMIN and not is_company_member:
            updater_name = "Quản trị viên hệ thống"
        else:
            name: str | None = None
            if updater_member and updater_member.user:
                if (
                    updater_member.user.recruiter_profile
                    and updater_member.user.recruiter_profile.full_name
                ):
                    name = updater_member.user.recruiter_profile.full_name
                elif updater_member.user.email:
                    name = updater_member.user.email
            if not name:
                if (
                    getattr(updated_by, "recruiter_profile", None)
                    and updated_by.recruiter_profile.full_name
                ):
                    name = updated_by.recruiter_profile.full_name
                elif updated_by.email:
                    name = updated_by.email
                else:
                    name = "Quản trị viên hệ thống"
            updater_name = name

        # PO-1 (Option A): Exclude updater from in-app notifications and emails
        eligible_members = [
            m for m in memberships
            if updated_by is None or m.user_id != updated_by.id
        ]

        event_uuid = uuid.uuid4()
        changed_fields_summary = ", ".join(changed_labels)
        now = datetime.now(timezone.utc)

        for member in eligible_members:
            # In-App Notification
            await self.notifications.notify_company_profile_updated(
                user_id=member.user_id,
                company_id=company.id,
                company_name=company.name,
                updater_name=updater_name,
                changed_fields_summary=changed_fields_summary,
            )

            # Transactional Email
            recipient_email = member.user.email if member.user else None
            if recipient_email:
                await CompanyEmailService.schedule_company_profile_updated_email(
                    session=self.session,
                    company_id=company.id,
                    company_name=company.name,
                    updater_name=updater_name,
                    recipient_user_id=member.user_id,
                    recipient_email=recipient_email,
                    event_uuid=event_uuid,
                    updated_at=now,
                    changed_fields_summary=changed_fields_summary,
                )

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