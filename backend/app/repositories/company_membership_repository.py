from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload, selectinload

from app.domain.enums import MembershipRole, MembershipStatus
from app.models import Company, CompanyMembership, User
from app.repositories.base import BaseRepository


class CompanyMembershipRepository(BaseRepository[CompanyMembership]):
    async def get_active(
        self,
        user_id: Any,
        company_id: Any,
    ) -> CompanyMembership | None:
        stmt = (
            select(CompanyMembership)
            .options(joinedload(CompanyMembership.company))
            .join(Company, CompanyMembership.company_id == Company.id)
            .where(
                CompanyMembership.user_id == user_id,
                CompanyMembership.company_id == company_id,
                CompanyMembership.status == MembershipStatus.ACTIVE,
                CompanyMembership.is_deleted == False,  # noqa: E712
                Company.is_deleted == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_for_update(
        self,
        user_id: Any,
        company_id: Any,
    ) -> CompanyMembership | None:
        stmt = (
            select(CompanyMembership)
            .options(joinedload(CompanyMembership.company))
            .join(Company, CompanyMembership.company_id == Company.id)
            .where(
                CompanyMembership.user_id == user_id,
                CompanyMembership.company_id == company_id,
                CompanyMembership.status == MembershipStatus.ACTIVE,
                CompanyMembership.is_deleted == False,  # noqa: E712
                Company.is_deleted == False,  # noqa: E712
            )
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active_for_user(
        self,
        user_id: Any,
    ) -> list[CompanyMembership]:
        stmt = (
            select(CompanyMembership)
            .options(joinedload(CompanyMembership.company))
            .join(Company, CompanyMembership.company_id == Company.id)
            .where(
                CompanyMembership.user_id == user_id,
                CompanyMembership.status == MembershipStatus.ACTIVE,
                CompanyMembership.is_deleted == False,  # noqa: E712
                Company.is_deleted == False,  # noqa: E712
            )
            .order_by(CompanyMembership.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def list_by_company(
        self,
        company_id: Any,
        *,
        include_revoked: bool = True,
    ) -> list[CompanyMembership]:
        stmt = (
            select(CompanyMembership)
            .options(
                selectinload(CompanyMembership.user).selectinload(
                    User.recruiter_profile
                )
            )
            .where(
                CompanyMembership.company_id == company_id,
                CompanyMembership.is_deleted == False,  # noqa: E712
            )
            .order_by(CompanyMembership.created_at.asc())
        )
        if not include_revoked:
            stmt = stmt.where(
                CompanyMembership.status == MembershipStatus.ACTIVE
            )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def get_by_id_with_user(
        self,
        membership_id: Any,
    ) -> CompanyMembership | None:
        stmt = (
            select(CompanyMembership)
            .options(
                selectinload(CompanyMembership.user).selectinload(
                    User.recruiter_profile
                ),
                joinedload(CompanyMembership.company),
            )
            .where(
                CompanyMembership.id == membership_id,
                CompanyMembership.is_deleted == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_company_and_user(
        self,
        company_id: Any,
        user_id: Any,
    ) -> CompanyMembership | None:
        stmt = (
            select(CompanyMembership)
            .where(
                CompanyMembership.company_id == company_id,
                CompanyMembership.user_id == user_id,
                CompanyMembership.is_deleted == False,  # noqa: E712
            )
            .order_by(CompanyMembership.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_active_admins(self, company_id: Any) -> int:
        stmt = select(func.count(CompanyMembership.id)).where(
            CompanyMembership.company_id == company_id,
            CompanyMembership.role == MembershipRole.ADMIN,
            CompanyMembership.status == MembershipStatus.ACTIVE,
            CompanyMembership.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())
