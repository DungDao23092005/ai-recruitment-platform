import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

from app.repositories import NotificationRepository
from app.services.notification_service import NotificationService


def make_service() -> NotificationService:
    session = MagicMock()
    service = NotificationService(session)
    service.notifications = AsyncMock(spec=NotificationRepository)
    service.create_notification = AsyncMock(return_value="created")
    return service


class TestCandidateQuotaNotifications:
    def test_paid_exhaustion_is_deduplicated_by_subscription(self):
        service = make_service()
        service.notifications.exists_by_entity = AsyncMock(return_value=False)
        user_id = uuid.uuid4()
        sub_id = uuid.uuid4()

        result = asyncio.run(
            service.notify_candidate_paid_quota_exhausted(
                user_id=user_id,
                subscription_id=sub_id,
                plan_name="Professional",
            )
        )

        assert result == "created"
        service.notifications.exists_by_entity.assert_awaited_once_with(
            user_id=user_id,
            entity_type="candidate_quota",
            entity_id=sub_id,
            notification_type="candidate_paid_quota_exhausted",
        )
        kwargs = service.create_notification.await_args.kwargs
        assert kwargs["entity_id"] == sub_id
        assert "Professional" in kwargs["content"]

    def test_free_exhaustion_entity_is_stable_per_subscription_and_period(self):
        service = make_service()
        service.notifications.exists_by_entity = AsyncMock(return_value=False)
        user_id = uuid.uuid4()
        sub_id = uuid.uuid4()

        asyncio.run(
            service.notify_candidate_free_quota_exhausted(
                user_id=user_id,
                subscription_id=sub_id,
                period_key="2026-06",
            )
        )
        first = service.create_notification.await_args.kwargs["entity_id"]
        first_guard = service.notifications.exists_by_entity.await_args.kwargs

        asyncio.run(
            service.notify_candidate_free_quota_exhausted(
                user_id=user_id,
                subscription_id=sub_id,
                period_key="2026-06",
            )
        )
        second = service.create_notification.await_args.kwargs["entity_id"]

        assert first == second
        assert first_guard["notification_type"] == (
            "candidate_free_quota_exhausted"
        )
        assert first_guard["entity_id"] == first

    def test_free_exhaustion_skips_existing_notification(self):
        service = make_service()
        service.notifications.exists_by_entity = AsyncMock(return_value=True)

        result = asyncio.run(
            service.notify_candidate_free_quota_exhausted(
                user_id=uuid.uuid4(),
                subscription_id=uuid.uuid4(),
                period_key="2026-06",
            )
        )

        assert result is None
        service.create_notification.assert_not_awaited()

    def test_returned_to_free_is_deduplicated_and_names_reason(self):
        service = make_service()
        service.notifications.exists_by_entity = AsyncMock(return_value=False)
        sub_id = uuid.uuid4()

        result = asyncio.run(
            service.notify_candidate_returned_to_free(
                user_id=uuid.uuid4(),
                paid_subscription_id=sub_id,
                reason="expired",
            )
        )

        assert result == "created"
        guard = service.notifications.exists_by_entity.await_args.kwargs
        assert guard["entity_id"] == sub_id
        assert guard["notification_type"] == "candidate_returned_to_free"
        content = service.create_notification.await_args.kwargs["content"]
        assert "hết hạn" in content
