from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SubscriptionAuditLog
from app.repositories.base import BaseRepository


class SubscriptionAuditLogRepository(BaseRepository[SubscriptionAuditLog]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SubscriptionAuditLog)

    async def list_by_subscription(
        self,
        subscription_id: Any,
    ) -> list[SubscriptionAuditLog]:
        stmt = (
            select(SubscriptionAuditLog)
            .where(SubscriptionAuditLog.subscription_id == subscription_id)
            .order_by(SubscriptionAuditLog.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_user(self, user_id: Any) -> list[SubscriptionAuditLog]:
        stmt = (
            select(SubscriptionAuditLog)
            .where(SubscriptionAuditLog.user_id == user_id)
            .order_by(SubscriptionAuditLog.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
