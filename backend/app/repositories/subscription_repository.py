from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import SubscriptionStatus
from app.models import Subscription
from app.repositories.base import BaseRepository


class SubscriptionRepository(BaseRepository[Subscription]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Subscription)

    async def get_active_by_user_id(
        self,
        user_id: Any,
        now: Optional[datetime] = None,
    ) -> Subscription | None:
        if now is None:
            from app.domain.models.base import utc_now
            now = utc_now()

        stmt = select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.is_deleted == False,  # noqa: E712
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.expires_at > now,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_and_plan(
        self,
        user_id: Any,
        plan_id: Any,
    ) -> Subscription | None:
        stmt = select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.plan_id == plan_id,
            Subscription.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_id(
        self,
        user_id: Any,
    ) -> list[Subscription]:
        stmt = (
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.is_deleted == False,  # noqa: E712
            )
            .order_by(Subscription.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_including_deleted(self, subscription_id: Any) -> Subscription | None:
        stmt = select(Subscription).where(Subscription.id == subscription_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_admin(
        self,
        skip: int,
        limit: int,
        user_id: Optional[Any] = None,
        status_filter: Optional[SubscriptionStatus] = None,
    ) -> tuple[list[Subscription], int]:
        filters = [
            Subscription.is_deleted == False,  # noqa: E712
        ]
        if user_id is not None:
            filters.append(Subscription.user_id == user_id)
        if status_filter is not None:
            filters.append(Subscription.status == status_filter)

        count_stmt = select(func.count()).select_from(Subscription)
        list_stmt = select(Subscription).order_by(Subscription.created_at.desc())

        if filters:
            count_stmt = count_stmt.where(*filters)
            list_stmt = list_stmt.where(*filters)

        total = (await self.session.execute(count_stmt)).scalar_one()
        list_stmt = list_stmt.offset(skip).limit(limit)
        rows = (await self.session.execute(list_stmt)).scalars().all()
        return list(rows), total