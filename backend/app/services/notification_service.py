from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException
from app.core.pubsub import pubsub_manager
from app.models import Notification, User
from app.repositories import NotificationRepository
from app.schemas.notification import NotificationRead

VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

SUBSCRIPTION_ACTIVATED_TYPE = "subscription_activated"
SUBSCRIPTION_ENTITY_TYPE = "subscription"
SUBSCRIPTION_ACTIVATED_TITLE = "Kích hoạt gói dịch vụ thành công"

SUBSCRIPTION_PLAN_CHANGED_TYPE = "subscription_plan_changed"
SUBSCRIPTION_PLAN_CHANGED_TITLE = "Thay đổi gói dịch vụ"

SUBSCRIPTION_REVOKED_TYPE = "subscription_revoked"
SUBSCRIPTION_REVOKED_TITLE = "Thu hồi gói dịch vụ"


def _format_expiry_date(expires_at: datetime | None) -> str:
    """Render an activation expiry date in Vietnam local time (dd/mm/yyyy).

    Stored boundaries are UTC-aware; SQL Server may hand back a naive value, so
    a naive datetime is treated as UTC before conversion. This keeps the date
    the user sees consistent with the +07:00 business timezone.
    """
    if expires_at is None:
        return "không xác định"
    aware = (
        expires_at
        if expires_at.tzinfo is not None
        else expires_at.replace(tzinfo=timezone.utc)
    )
    return aware.astimezone(VIETNAM_TZ).strftime("%d/%m/%Y")


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

        # Schedule publish after commit using SQLAlchemy event listener
        def _publish_after_commit(session):
            try:
                channel = f"notifications:user:{notification.user_id}"
                message = {
                    "type": "notification.created",
                    "notification_id": str(notification.id),
                    "title": notification.title,
                    "content": notification.content,
                    "notification_type": notification.notification_type,
                    "entity_type": notification.entity_type,
                    "entity_id": str(notification.entity_id) if notification.entity_id else None,
                    "created_at": notification.created_at.isoformat() if notification.created_at else None,
                    "unread_count": 0,
                }
                import asyncio
                asyncio.create_task(
                    pubsub_manager.publish(channel=channel, message=message)
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to publish notification event: {e}")

        # Register the event listener to fire after commit
        event.listen(self.session.sync_session, "after_commit", _publish_after_commit, once=True)

        return NotificationRead.model_validate(notification)

    async def notify_subscription_activated(
        self,
        user_id: uuid.UUID,
        subscription_id: uuid.UUID,
        plan_name: str,
        expires_at: datetime | None,
    ) -> NotificationRead | None:
        """Create the one-time "subscription activated" notification.

        Returns ``None`` when a notification for this subscription already
        exists (see ``NotificationRepository.exists_by_entity``), so a re-entrant
        activation handler cannot produce a duplicate. The caller is responsible
        for invoking this inside the activation transaction, before commit.
        """
        already_notified = await self.notifications.exists_by_entity(
            user_id=user_id,
            entity_type=SUBSCRIPTION_ENTITY_TYPE,
            entity_id=subscription_id,
            notification_type=SUBSCRIPTION_ACTIVATED_TYPE,
        )
        if already_notified:
            return None

        return await self.create_notification(
            user_id=user_id,
            title=SUBSCRIPTION_ACTIVATED_TITLE,
            content=(
                f'Gói "{plan_name}" đã được kích hoạt thành công. '
                f"Thời hạn sử dụng đến {_format_expiry_date(expires_at)}."
            ),
            notification_type=SUBSCRIPTION_ACTIVATED_TYPE,
            entity_type=SUBSCRIPTION_ENTITY_TYPE,
            entity_id=subscription_id,
        )

    async def notify_subscription_plan_changed(
        self,
        user_id: uuid.UUID,
        subscription_id: uuid.UUID,
        old_plan_name: str | None,
        new_plan_name: str,
        expires_at: datetime | None,
    ) -> NotificationRead:
        """Notify the buyer that an admin changed their subscription plan.

        No dedupe guard: every admin mutation is a distinct, auditable event and
        must produce its own notification.
        """
        previous = old_plan_name or "gói hiện tại"
        return await self.create_notification(
            user_id=user_id,
            title=SUBSCRIPTION_PLAN_CHANGED_TITLE,
            content=(
                f'Gói dịch vụ của bạn đã được thay đổi từ "{previous}" '
                f'sang "{new_plan_name}". '
                f"Thời hạn sử dụng đến {_format_expiry_date(expires_at)}."
            ),
            notification_type=SUBSCRIPTION_PLAN_CHANGED_TYPE,
            entity_type=SUBSCRIPTION_ENTITY_TYPE,
            entity_id=subscription_id,
        )

    async def notify_subscription_revoked(
        self,
        user_id: uuid.UUID,
        subscription_id: uuid.UUID,
        plan_name: str | None,
        reason: str,
    ) -> NotificationRead:
        """Notify the buyer that an admin revoked their subscription."""
        subject = f'Gói "{plan_name}"' if plan_name else "Gói dịch vụ của bạn"
        return await self.create_notification(
            user_id=user_id,
            title=SUBSCRIPTION_REVOKED_TITLE,
            content=f"{subject} đã bị thu hồi. Lý do: {reason}.",
            notification_type=SUBSCRIPTION_REVOKED_TYPE,
            entity_type=SUBSCRIPTION_ENTITY_TYPE,
            entity_id=subscription_id,
        )

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
