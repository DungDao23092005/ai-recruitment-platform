import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.enums import MembershipRole, MembershipStatus
from app.models import CompanyMembership, Notification, User
from app.repositories import NotificationRepository
from app.schemas.notification import NotificationRead
from app.services.notification_service import (
    ACCOUNT_UNLOCKED_TITLE,
    ACCOUNT_UNLOCKED_TYPE,
    APPLICATION_STATUS_VIETNAMESE_LABELS,
    COMPANY_RETURNED_TO_FREE_TITLE,
    COMPANY_RETURNED_TO_FREE_TYPE,
    SUBSCRIPTION_ACTIVATED_TITLE,
    NotificationService,
    _format_expiry_date,
    application_status_notification_id,
    candidate_interview_response_notification_id,
    evaluation_submission_notification_id,
    get_application_status_label,
    interview_assignment_notification_id,
    interview_schedule_notification_id,
    offer_response_notification_id,
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
        assert kwargs["notification_id"] == uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"subscription_activated:{user_id}:{sub_id}",
        )
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


class TestNotifyCompanyReturnedToFree:
    def test_builds_payload_with_expired_subscription_identity(self):
        service = make_service()
        service.notifications.exists_by_entity = AsyncMock(return_value=False)
        user_id = uuid.uuid4()
        sub_id = uuid.uuid4()

        result = asyncio.run(
            service.notify_company_returned_to_free(
                user_id=user_id,
                paid_subscription_id=sub_id,
                plan_name="Professional",
            )
        )

        assert result == "created"
        service.notifications.exists_by_entity.assert_awaited_once_with(
            user_id=user_id,
            entity_type="subscription",
            entity_id=sub_id,
            notification_type=COMPANY_RETURNED_TO_FREE_TYPE,
        )
        kwargs = service.create_notification.await_args.kwargs
        assert kwargs["user_id"] == user_id
        assert kwargs["title"] == COMPANY_RETURNED_TO_FREE_TITLE
        assert kwargs["notification_type"] == "company_returned_to_free"
        assert kwargs["entity_type"] == "subscription"
        assert kwargs["entity_id"] == sub_id
        assert kwargs["notification_id"] == uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"company_returned_to_free:{user_id}:{sub_id}",
        )
        assert "Professional" in kwargs["content"]
        assert "đã hết hạn" in kwargs["content"]
        assert "gói miễn phí" in kwargs["content"]
        # No quota figures are invented for an expiration event.
        assert "hạn mức" not in kwargs["content"]

    def test_skips_when_already_notified(self):
        service = make_service()
        service.notifications.exists_by_entity = AsyncMock(return_value=True)

        result = asyncio.run(
            service.notify_company_returned_to_free(
                user_id=uuid.uuid4(),
                paid_subscription_id=uuid.uuid4(),
            )
        )

        assert result is None
        service.create_notification.assert_not_awaited()

    def test_distinct_subscriptions_get_distinct_ids(self):
        service = make_service()
        service.notifications.exists_by_entity = AsyncMock(return_value=False)
        user_id = uuid.uuid4()
        first_sub_id = uuid.uuid4()
        second_sub_id = uuid.uuid4()

        asyncio.run(
            service.notify_company_returned_to_free(
                user_id=user_id,
                paid_subscription_id=first_sub_id,
            )
        )
        first_id = service.create_notification.await_args.kwargs["notification_id"]
        asyncio.run(
            service.notify_company_returned_to_free(
                user_id=user_id,
                paid_subscription_id=second_sub_id,
            )
        )
        second_id = service.create_notification.await_args.kwargs["notification_id"]

        assert first_id != second_id


class TestCreateNotificationDeterministicId:
    def test_explicit_notification_id_is_persisted(self):
        session = MagicMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        explicit_id = uuid.uuid4()

        async def _mock_refresh(instance):
            instance.created_at = datetime.now(timezone.utc)
            instance.is_read = False

        session.refresh = AsyncMock(side_effect=_mock_refresh)
        service = NotificationService(session)

        with patch(
            "app.services.notification_service.TransactionActionManager"
        ):
            result = asyncio.run(
                service.create_notification(
                    user_id=uuid.uuid4(),
                    title="Tiêu đề",
                    content="Nội dung",
                    notification_type="test_type",
                    notification_id=explicit_id,
                )
            )

        added = session.add.call_args.args[0]
        assert added.id == explicit_id
        assert result.id == explicit_id


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


class TestVietnameseStatusLabels:
    def test_all_standard_statuses_have_vietnamese_labels(self):
        assert get_application_status_label("applied") == "Đã nộp"
        assert get_application_status_label("under_review") == "Đang xem xét"
        assert get_application_status_label("shortlisted") == "Lọt vòng ngắn"
        assert get_application_status_label("interviewing") == "Đang phỏng vấn"
        assert get_application_status_label("offered") == "Đã gửi đề nghị"
        assert get_application_status_label("accepted") == "Đã chấp nhận"
        assert get_application_status_label("rejected") == "Từ chối"
        assert get_application_status_label("withdrawn") == "Đã rút đơn"

    def test_unknown_status_fallback(self):
        assert get_application_status_label("non_existent_status") == "non_existent_status"


class TestDeterministicNotificationIDs:
    def test_application_status_notification_id_deterministic(self):
        user_id = uuid.uuid4()
        activity_id = uuid.uuid4()
        id1 = application_status_notification_id(user_id, activity_id)
        id2 = application_status_notification_id(user_id, activity_id)
        assert id1 == id2
        assert isinstance(id1, uuid.UUID)

        # Different activity creates distinct notification ID
        other_activity = uuid.uuid4()
        id3 = application_status_notification_id(user_id, other_activity)
        assert id1 != id3

    def test_interview_schedule_notification_id_deterministic(self):
        user_id = uuid.uuid4()
        activity_id = uuid.uuid4()
        id1 = interview_schedule_notification_id("rescheduled", user_id, activity_id)
        id2 = interview_schedule_notification_id("rescheduled", user_id, activity_id)
        assert id1 == id2

        # Rescheduled vs cancelled creates distinct IDs
        id_cancelled = interview_schedule_notification_id("cancelled", user_id, activity_id)
        assert id1 != id_cancelled

        # Repeated reschedule cycle T1 -> T2 -> T1 creates distinct ID per activity
        act1 = uuid.uuid4()
        act2 = uuid.uuid4()
        assert (
            interview_schedule_notification_id("rescheduled", user_id, act1)
            != interview_schedule_notification_id("rescheduled", user_id, act2)
        )

    def test_interview_assignment_notification_id_lifecycle(self):
        user_id = uuid.uuid4()
        assignment_id_1 = uuid.uuid4()
        assignment_id_2 = uuid.uuid4()

        assign_1 = interview_assignment_notification_id("assigned", user_id, assignment_id_1)
        unassign_1 = interview_assignment_notification_id("unassigned", user_id, assignment_id_1)
        assert assign_1 != unassign_1

        # Reassignment produces a new assignment ID, hence a distinct notification ID
        assign_2 = interview_assignment_notification_id("assigned", user_id, assignment_id_2)
        assert assign_1 != assign_2

    def test_evaluation_submission_notification_id_deterministic(self):
        user_id = uuid.uuid4()
        eval_id = uuid.uuid4()
        id1 = evaluation_submission_notification_id(user_id, eval_id)
        id2 = evaluation_submission_notification_id(user_id, eval_id)
        assert id1 == id2
        assert id1 != evaluation_submission_notification_id(uuid.uuid4(), eval_id)

    def test_offer_response_notification_id_deterministic(self):
        user_id = uuid.uuid4()
        app_id = uuid.uuid4()
        act_id = uuid.uuid4()

        id_acc = offer_response_notification_id("accepted", user_id, app_id, act_id)
        id_dec = offer_response_notification_id("declined", user_id, app_id, act_id)
        assert id_acc != id_dec

    def test_candidate_interview_response_notification_id_deterministic(self):
        user_id = uuid.uuid4()
        int_id = uuid.uuid4()
        act_id = uuid.uuid4()

        id_conf = candidate_interview_response_notification_id("confirmed", user_id, int_id, act_id)
        id_dec = candidate_interview_response_notification_id("declined", user_id, int_id, act_id)
        assert id_conf != id_dec


class TestCreateIdempotentNotification:
    def test_returns_existing_without_creating_new(self):
        service = make_service()
        user_id = uuid.uuid4()
        notif_id = uuid.uuid4()

        existing_row = Notification(
            id=notif_id,
            user_id=user_id,
            title="Existing",
            content="Already there",
            notification_type="existing_type",
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )
        service.notifications.get_by_id_and_user = AsyncMock(return_value=existing_row)

        result = asyncio.run(
            service.create_idempotent_notification(
                user_id=user_id,
                title="New title",
                content="New content",
                notification_type="existing_type",
                notification_id=notif_id,
            )
        )

        assert result is not None
        assert result.id == notif_id
        service.notifications.get_by_id_and_user.assert_awaited_once_with(
            notification_id=notif_id,
            user_id=user_id,
        )
        service.create_notification.assert_not_awaited()

    def test_creates_when_not_existing(self):
        service = make_service()
        user_id = uuid.uuid4()
        notif_id = uuid.uuid4()

        service.notifications.get_by_id_and_user = AsyncMock(return_value=None)
        created_read = NotificationRead(
            id=notif_id,
            user_id=user_id,
            title="New title",
            content="New content",
            notification_type="type_x",
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )
        service.create_notification = AsyncMock(return_value=created_read)

        result = asyncio.run(
            service.create_idempotent_notification(
                user_id=user_id,
                title="New title",
                content="New content",
                notification_type="type_x",
                notification_id=notif_id,
            )
        )

        assert result == created_read
        service.create_notification.assert_awaited_once()


class TestGetActiveRecruiterAndAdminUsers:
    def test_filters_authoritative_company_memberships(self):
        session = MagicMock()
        service = NotificationService(session)
        company_id = uuid.uuid4()

        active_admin = User(id=uuid.uuid4(), email="admin@corp.com", is_active=True)
        active_recruiter = User(id=uuid.uuid4(), email="recruiter@corp.com", is_active=True)
        inactive_user = User(id=uuid.uuid4(), email="inactive@corp.com", is_active=False)
        deleted_user = User(id=uuid.uuid4(), email="deleted@corp.com", is_active=True, is_deleted=True)
        interviewer_user = User(id=uuid.uuid4(), email="interviewer@corp.com", is_active=True)

        m_admin = CompanyMembership(
            id=uuid.uuid4(),
            company_id=company_id,
            user_id=active_admin.id,
            role=MembershipRole.ADMIN,
            status=MembershipStatus.ACTIVE,
            user=active_admin,
        )
        m_recruiter = CompanyMembership(
            id=uuid.uuid4(),
            company_id=company_id,
            user_id=active_recruiter.id,
            role=MembershipRole.RECRUITER,
            status=MembershipStatus.ACTIVE,
            user=active_recruiter,
        )
        m_revoked = CompanyMembership(
            id=uuid.uuid4(),
            company_id=company_id,
            user_id=uuid.uuid4(),
            role=MembershipRole.ADMIN,
            status=MembershipStatus.REVOKED,
            user=None,
        )
        m_revoked_recruiter = CompanyMembership(
            id=uuid.uuid4(),
            company_id=company_id,
            user_id=uuid.uuid4(),
            role=MembershipRole.RECRUITER,
            status=MembershipStatus.REVOKED,
            user=None,
        )
        m_inactive_user = CompanyMembership(
            id=uuid.uuid4(),
            company_id=company_id,
            user_id=inactive_user.id,
            role=MembershipRole.ADMIN,
            status=MembershipStatus.ACTIVE,
            user=inactive_user,
        )
        m_deleted_user = CompanyMembership(
            id=uuid.uuid4(),
            company_id=company_id,
            user_id=deleted_user.id,
            role=MembershipRole.RECRUITER,
            status=MembershipStatus.ACTIVE,
            user=deleted_user,
        )
        m_interviewer = CompanyMembership(
            id=uuid.uuid4(),
            company_id=company_id,
            user_id=interviewer_user.id,
            role=MembershipRole.INTERVIEWER,
            status=MembershipStatus.ACTIVE,
            user=interviewer_user,
        )

        all_memberships = [
            m_admin,
            m_recruiter,
            m_revoked,
            m_revoked_recruiter,
            m_inactive_user,
            m_deleted_user,
            m_interviewer,
        ]

        with patch("app.repositories.company_membership_repository.CompanyMembershipRepository") as MockMemRepo, \
             patch("app.repositories.user_repository.UserRepository") as MockUserRepo:
            MockMemRepo.return_value.list_by_company = AsyncMock(return_value=all_memberships)

            recipients = asyncio.run(service.get_active_recruiter_and_admin_users(company_id))

        assert len(recipients) == 2
        recipient_ids = {r.id for r in recipients}
        assert recipient_ids == {active_admin.id, active_recruiter.id}
