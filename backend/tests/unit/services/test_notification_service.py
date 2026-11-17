import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.repositories import NotificationRepository
from app.services.notification_service import (
    ACCOUNT_UNLOCKED_TITLE,
    ACCOUNT_UNLOCKED_TYPE,
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


class TestNotifySubscriptionPlanChanged:
    def test_builds_payload_with_both_plan_names(self):
        service = make_service()
        user_id = uuid.uuid4()
        sub_id = uuid.uuid4()

        result = asyncio.run(
            service.notify_subscription_plan_changed(
                user_id=user_id,
                subscription_id=sub_id,
                old_plan_name="Basic",
                new_plan_name="Professional",
                expires_at=datetime(2026, 12, 31, tzinfo=timezone.utc),
            )
        )

        assert result == "created"
        kwargs = service.create_notification.await_args.kwargs
        assert kwargs["title"] == "Thay đổi gói dịch vụ"
        assert kwargs["notification_type"] == "subscription_plan_changed"
        assert kwargs["entity_type"] == "subscription"
        assert kwargs["entity_id"] == sub_id
        assert "Basic" in kwargs["content"]
        assert "Professional" in kwargs["content"]
        # No dedupe guard: every admin action is its own notification.
        service.notifications.exists_by_entity.assert_not_called()

    def test_falls_back_when_old_plan_name_missing(self):
        service = make_service()

        asyncio.run(
            service.notify_subscription_plan_changed(
                user_id=uuid.uuid4(),
                subscription_id=uuid.uuid4(),
                old_plan_name=None,
                new_plan_name="Professional",
                expires_at=None,
            )
        )

        kwargs = service.create_notification.await_args.kwargs
        assert "gói hiện tại" in kwargs["content"]


class TestNotifySubscriptionRevoked:
    def test_builds_payload_with_reason(self):
        service = make_service()
        sub_id = uuid.uuid4()

        result = asyncio.run(
            service.notify_subscription_revoked(
                user_id=uuid.uuid4(),
                subscription_id=sub_id,
                plan_name="Professional",
                reason="Vi phạm điều khoản",
            )
        )

        assert result == "created"
        kwargs = service.create_notification.await_args.kwargs
        assert kwargs["title"] == "Thu hồi gói dịch vụ"
        assert kwargs["notification_type"] == "subscription_revoked"
        assert kwargs["entity_type"] == "subscription"
        assert kwargs["entity_id"] == sub_id
        assert "Professional" in kwargs["content"]
        assert "Vi phạm điều khoản" in kwargs["content"]

    def test_falls_back_when_plan_name_missing(self):
        service = make_service()

        asyncio.run(
            service.notify_subscription_revoked(
                user_id=uuid.uuid4(),
                subscription_id=uuid.uuid4(),
                plan_name=None,
                reason="Lý do nào đó",
            )
        )

        kwargs = service.create_notification.await_args.kwargs
        assert "Gói dịch vụ của bạn" in kwargs["content"]


class TestNotifyAccountUnlocked:
    """Tests 25-26: Account unlock in-app notification and action delegation."""

    def test_notify_account_unlocked_payload(self):
        """25. notify_account_unlocked constructs the correct payload and entity bindings."""
        service = make_service()
        user_id = uuid.uuid4()

        result = asyncio.run(service.notify_account_unlocked(user_id=user_id))

        assert result == "created"
        service.create_notification.assert_awaited_once()
        kwargs = service.create_notification.await_args.kwargs
        assert kwargs["user_id"] == user_id
        assert kwargs["title"] == ACCOUNT_UNLOCKED_TITLE
        assert kwargs["title"] == "Tài khoản đã được mở khóa"
        assert kwargs["notification_type"] == ACCOUNT_UNLOCKED_TYPE
        assert kwargs["entity_type"] == "user"
        assert kwargs["entity_id"] == user_id
        assert "mở khóa thành công" in kwargs["content"]

    def test_create_notification_delegates_to_transaction_action_manager(self):
        """26. create_notification registers realtime publish action with TransactionActionManager."""
        session = MagicMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        async def _mock_refresh(instance):
            instance.id = uuid.uuid4()
            instance.created_at = datetime.now(timezone.utc)
            instance.is_read = False

        session.refresh = AsyncMock(side_effect=_mock_refresh)
        service = NotificationService(session)

        user_id = uuid.uuid4()
        with patch(
            "app.services.notification_service.TransactionActionManager"
        ) as tam_mock:
            result = asyncio.run(
                service.create_notification(
                    user_id=user_id,
                    title="Tiêu đề",
                    content="Nội dung",
                    notification_type="test_type",
                )
            )

        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        tam_mock.register_action.assert_called_once()
        args, kwargs = tam_mock.register_action.call_args
        assert args[0] is session
        assert callable(args[1])
        assert result.title == "Tiêu đề"
        assert result.notification_type == "test_type"
