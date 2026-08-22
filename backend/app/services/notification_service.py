from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException
from app.models import Notification, User
from app.repositories import NotificationRepository
from app.schemas.notification import NotificationRead


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.notifications = NotificationRepository(session)

    async def create_notification(
        self,
        user_id: uuid.UUID,
        title: str,
        content: str,
        notification_type: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[uuid.UUID] = None,
    ) -> NotificationRead:
        notification = Notification(
            user_id=user_id,
            title=title,
            content=content,
            notification_type=notification_type,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        self.session.add(notification)
        await self.session.flush()
        await self.session.refresh(notification)
        return NotificationRead.model_validate(notification)

    async def list_notifications(
        self,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> list[NotificationRead]:
        notifications = await self.notifications.list_by_user(
            user_id=user_id, skip=skip, limit=limit
        )
        return [NotificationRead.model_validate(n) for n in notifications]

    async def get_unread_count(self, user_id: uuid.UUID) -> int:
        return await self.notifications.count_unread_by_user(user_id=user_id)

    async def mark_as_read(
        self,
        current_user: User,
        notification_id: uuid.UUID,
    ) -> NotificationRead:
        notification = await self.notifications.get_by_id_and_user(
            notification_id=notification_id, user_id=current_user.id
        )
        if notification is None:
            raise EntityNotFoundException(
                f"Notification {notification_id} not found"
            )
        updated = await self.notifications.mark_as_read(notification)
        return NotificationRead.model_validate(updated)

    async def mark_all_as_read(self, user_id: uuid.UUID) -> int:
        return await self.notifications.mark_all_as_read(user_id=user_id)