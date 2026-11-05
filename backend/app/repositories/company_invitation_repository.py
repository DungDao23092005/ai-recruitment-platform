from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import joinedload

from app.domain.enums import InvitationStatus
from app.models import Company, CompanyInvitation
from app.repositories.base import BaseRepository


class CompanyInvitationRepository(BaseRepository[CompanyInvitation]):
    async def get_by_token_hash(
        self,
        token_hash: str,
    ) -> CompanyInvitation | None:
        stmt = (
            select(CompanyInvitation)
            .options(joinedload(CompanyInvitation.company))
            .where(
                CompanyInvitation.token_hash == token_hash,
                CompanyInvitation.is_deleted == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_token_hash_for_update(
        self,
        token_hash: str,
    ) -> CompanyInvitation | None:
        stmt = (
            select(CompanyInvitation)
            .where(
                CompanyInvitation.token_hash == token_hash,
                CompanyInvitation.is_deleted == False,  # noqa: E712
            )
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_company(
        self,
        invitation_id: Any,
        company_id: Any,
    ) -> CompanyInvitation | None:
        stmt = select(CompanyInvitation).where(
            CompanyInvitation.id == invitation_id,
            CompanyInvitation.company_id == company_id,
            CompanyInvitation.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_by_company_email(
        self,
        company_id: Any,
        email: str,
    ) -> CompanyInvitation | None:
        stmt = select(CompanyInvitation).where(
            CompanyInvitation.company_id == company_id,
            CompanyInvitation.email == email,
            CompanyInvitation.status == InvitationStatus.PENDING,
            CompanyInvitation.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_company(
        self,
        company_id: Any,
        *,
        status: InvitationStatus | None = None,
    ) -> list[CompanyInvitation]:
        stmt = select(CompanyInvitation).where(
            CompanyInvitation.company_id == company_id,
            CompanyInvitation.is_deleted == False,  # noqa: E712
        )
        if status is not None:
            stmt = stmt.where(CompanyInvitation.status == status)
        stmt = stmt.order_by(CompanyInvitation.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def expire_stale(
        self,
        *,
        company_id: Any | None = None,
        now: datetime,
    ) -> int:
        stmt = (
            update(CompanyInvitation)
            .where(
                CompanyInvitation.status == InvitationStatus.PENDING,
                CompanyInvitation.expires_at <= now,
                CompanyInvitation.is_deleted == False,  # noqa: E712
            )
            .values(
                status=InvitationStatus.EXPIRED,
                updated_at=now,
            )
        )
        if company_id is not None:
            stmt = stmt.where(CompanyInvitation.company_id == company_id)
        result = await self.session.execute(stmt)
        return result.rowcount or 0
