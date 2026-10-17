import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.repositories import NotificationRepository
from app.services.notification_service import (
    SUBSCRIPTION_ACTIVATED_TITLE,
    NotificationService,
    _format_expiry_date,
)


def make_service() -> NotificationService:
    session = MagicMock()
    service = NotificationService(session)
    service.notifications = AsyncMock(spec=NotificationRepository)
    service.create_notification = AsyncMock(return_value="created")
    return service


class TestFormatExpiryDate:
    def test_converts_utc_to_vietnam_local_date(self):
        # 2026-10-17 20:00 UTC == 2026-10-18 03:00 +07:00
        dt = datetime(2026, 10, 17, 20, 0, tzinfo=timezone.utc)
        assert _format_expiry_date(dt) == "18/10/2026"

    def test_treats_naive_datetime_as_utc(self):
        dt = datetime(2026, 10, 17, 20, 0)
        assert _format_expiry_date(dt) == "18/10/2026"

    def test_returns_placeholder_for_missing_date(self):
        assert _format_expiry_date(None) == "không xác định"


class TestNotifySubscriptionActivated:
    def test_builds_exact_payload_when_absent(self):
        service = make_service()
        service.notifications.exists_by_entity = AsyncMock(return_value=False)
        user_id = uuid.uuid4()
        sub_id = uuid.uuid4()
        expires_at = datetime(2026, 12, 31, 10, 0, tzinfo=timezone.utc)

        result = asyncio.run(
            service.notify_subscription_activated(
                user_id=user_id,
                subscription_id=sub_id,
                plan_name="Professional",
                expires_at=expires_at,
            )
        )

        assert result == "created"
        service.notifications.exists_by_entity.assert_awaited_once_with(
            user_id=user_id,
            entity_type="subscription",
            entity_id=sub_id,
            notification_type="subscription_activated",
        )
        service.create_notification.assert_awaited_once()
        kwargs = service.create_notification.await_args.kwargs
        assert kwargs["user_id"] == user_id
        assert kwargs["title"] == SUBSCRIPTION_ACTIVATED_TITLE
        assert kwargs["title"] == "Kích hoạt gói dịch vụ thành công"
        assert kwargs["notification_type"] == "subscription_activated"
        assert kwargs["entity_type"] == "subscription"
        assert kwargs["entity_id"] == sub_id
        assert "Professional" in kwargs["content"]
        assert "31/12/2026" in kwargs["content"]

    def test_skips_when_notification_already_exists(self):
        service = make_service()
        service.notifications.exists_by_entity = AsyncMock(return_value=True)

        result = asyncio.run(
            service.notify_subscription_activated(
                user_id=uuid.uuid4(),
                subscription_id=uuid.uuid4(),
                plan_name="Professional",
                expires_at=datetime(2026, 12, 31, tzinfo=timezone.utc),
            )
        )

        assert result is None
        service.create_notification.assert_not_awaited()
