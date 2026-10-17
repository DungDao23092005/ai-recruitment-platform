from __future__ import annotations

from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Notification)

    async def list_by_user(
        self, user_id: Any, skip: int = 0, limit: int = 20
    ) -> list[Notification]:
        stmt = (
            select(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_deleted == False,  # noqa: E712
            )
            .order_by(Notification.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_unread_by_user(self, user_id: Any) -> int:
        stmt = select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.is_read == False,  # noqa: E712
            Notification.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    async def exists_by_entity(
        self,
        user_id: Any,
        entity_type: str,
        entity_id: Any,
        notification_type: str | None = None,
    ) -> bool:
        """Return True if a matching (non-deleted) notification already exists.

        Used as a defense-in-depth guard before inserting an idempotent
        domain-event notification (for example ``subscription_activated`` for a
        given subscription). It is NOT the primary concurrency guarantee: the
        scheduling of the activation itself is serialized by the per-user /
        per-order row locks, so only the single transaction that performs the
        ``PENDING -> ACTIVE`` transition ever reaches the insert. This check
        additionally suppresses a duplicate if a handler is somehow re-entered
        after that transition has already been recorded.
        """
        stmt = select(Notification.id).where(
            Notification.user_id == user_id,
            Notification.entity_type == entity_type,
            Notification.entity_id == entity_id,
            Notification.is_deleted == False,  # noqa: E712
        )
        if notification_type is not None:
            stmt = stmt.where(Notification.notification_type == notification_type)
        stmt = stmt.limit(1)
        result = await self.session.execute(stmt)
        return result.first() is not None

    async def get_by_id_and_user(
        self, notification_id: Any, user_id: Any
    ) -> Notification | None:
        stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
            Notification.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_as_read(
        self, notification: Notification
    ) -> Notification:
        notification.is_read = True
        await self.session.flush()
        await self.session.refresh(notification)
        return notification

    async def mark_all_as_read(self, user_id: Any) -> int:
        stmt = (
            select(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read == False,  # noqa: E712
                Notification.is_deleted == False,  # noqa: E712
            )
            .execution_options(synchronize_session="fetch")
        )
        result = await self.session.execute(stmt)
        notifications = list(result.scalars().all())
        for notification in notifications:
            notification.is_read = True
        await self.session.flush()
        return len(notifications)