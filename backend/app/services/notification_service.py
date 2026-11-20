from __future__ import annotations

import inspect
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException
from app.core.pubsub import pubsub_manager
from app.models import CompanyMembership, Notification, User
from app.repositories import NotificationRepository
from app.schemas.notification import NotificationRead
from app.services.transaction_action_manager import TransactionActionManager

logger = logging.getLogger(__name__)

VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

ACCOUNT_UNLOCKED_TYPE = "account_unlocked"
ACCOUNT_UNLOCKED_TITLE = "Tài khoản đã được mở khóa"

SUBSCRIPTION_ACTIVATED_TYPE = "subscription_activated"
SUBSCRIPTION_ENTITY_TYPE = "subscription"
SUBSCRIPTION_ACTIVATED_TITLE = "Kích hoạt gói dịch vụ thành công"

COMPANY_RETURNED_TO_FREE_TYPE = "company_returned_to_free"
COMPANY_RETURNED_TO_FREE_TITLE = "Công ty đã quay lại gói miễn phí"

SUBSCRIPTION_PLAN_CHANGED_TYPE = "subscription_plan_changed"
SUBSCRIPTION_PLAN_CHANGED_TITLE = "Thay đổi gói dịch vụ"

SUBSCRIPTION_REVOKED_TYPE = "subscription_revoked"
SUBSCRIPTION_REVOKED_TITLE = "Thu hồi gói dịch vụ"

CANDIDATE_QUOTA_ENTITY_TYPE = "candidate_quota"
CANDIDATE_PAID_QUOTA_EXHAUSTED_TYPE = "candidate_paid_quota_exhausted"
CANDIDATE_PAID_QUOTA_EXHAUSTED_TITLE = "Đã hết hạn mức AI của gói trả phí"
CANDIDATE_FREE_QUOTA_EXHAUSTED_TYPE = "candidate_free_quota_exhausted"
CANDIDATE_FREE_QUOTA_EXHAUSTED_TITLE = "Đã hết hạn mức AI miễn phí"
CANDIDATE_RETURNED_TO_FREE_TYPE = "candidate_returned_to_free"
CANDIDATE_RETURNED_TO_FREE_TITLE = "Tài khoản đã quay lại gói miễn phí"

# Pipeline entity types
APPLICATION_ENTITY_TYPE = "application"
INTERVIEW_ENTITY_TYPE = "interview"

# Pipeline notification types and titles
NEW_APPLICATION_TYPE = "new_application"
NEW_APPLICATION_TITLE = "Đơn ứng tuyển mới"

APPLICATION_SUBMITTED_TYPE = "application_submitted"
APPLICATION_SUBMITTED_TITLE = "Nộp đơn ứng tuyển thành công"

APPLICATION_STATUS_CHANGED_TYPE = "application_status_changed"
APPLICATION_STATUS_CHANGED_TITLE = "Cập nhật trạng thái đơn ứng tuyển"

APPLICATION_WITHDRAWN_TYPE = "application_withdrawn"
APPLICATION_WITHDRAWN_TITLE = "Ứng viên rút đơn"

OFFER_ACCEPTED_TYPE = "offer_accepted"
OFFER_ACCEPTED_TITLE = "Ứng viên chấp nhận lời mời làm việc"

OFFER_DECLINED_TYPE = "offer_declined"
OFFER_DECLINED_TITLE = "Ứng viên từ chối lời mời làm việc"

INTERVIEW_SCHEDULED_TYPE = "interview_scheduled"
INTERVIEW_SCHEDULED_TITLE = "Lịch phỏng vấn mới"

INTERVIEW_UPDATED_TYPE = "interview_updated"
INTERVIEW_UPDATED_TITLE = "Cập nhật lịch phỏng vấn"

INTERVIEW_CANCELLED_TYPE = "interview_cancelled"
INTERVIEW_CANCELLED_TITLE = "Phỏng vấn bị hủy"

INTERVIEW_CONFIRMED_TYPE = "interview_confirmed"
INTERVIEW_CONFIRMED_TITLE = "Ứng viên xác nhận phỏng vấn"

INTERVIEW_DECLINED_TYPE = "interview_declined"
INTERVIEW_DECLINED_TITLE = "Ứng viên từ chối phỏng vấn"

INTERVIEW_ASSIGNED_TYPE = "interview_assigned"
INTERVIEW_ASSIGNED_TITLE = "Phân công phỏng vấn"

INTERVIEW_UNASSIGNED_TYPE = "interview_unassigned"
INTERVIEW_UNASSIGNED_TITLE = "Hủy phân công phỏng vấn"

EVALUATION_SUBMITTED_TYPE = "evaluation_submitted"
EVALUATION_SUBMITTED_TITLE = "Đánh giá phỏng vấn mới"

APPLICATION_STATUS_VIETNAMESE_LABELS: dict[str, str] = {
    "applied": "Đã nộp",
    "under_review": "Đang xem xét",
    "shortlisted": "Lọt vòng ngắn",
    "interviewing": "Đang phỏng vấn",
    "offered": "Đã gửi đề nghị",
    "accepted": "Đã chấp nhận",
    "rejected": "Từ chối",
    "withdrawn": "Đã rút đơn",
}


def get_application_status_label(status: object) -> str:
    """Return the Vietnamese localized label for an application status."""
    val = status.value if hasattr(status, "value") else str(status)
    return APPLICATION_STATUS_VIETNAMESE_LABELS.get(val, val)


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


def application_status_notification_id(
    user_id: uuid.UUID,
    activity_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Deterministic identity for an application status change notification."""
    suffix = f":{activity_id}" if activity_id is not None else ""
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"application_status_changed:{user_id}{suffix}",
    )


def interview_schedule_notification_id(
    event: str,
    user_id: uuid.UUID,
    activity_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Occurrence-aware identity for interview reschedule or cancellation."""
    suffix = f":{activity_id}" if activity_id is not None else ""
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"interview_{event}:{user_id}{suffix}",
    )


def interview_assignment_notification_id(
    event: str,
    user_id: uuid.UUID,
    assignment_id: uuid.UUID,
) -> uuid.UUID:
    """Lifecycle identity for interviewer assignment or unassignment."""
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"interview_{event}:{user_id}:{assignment_id}",
    )


def evaluation_submission_notification_id(
    user_id: uuid.UUID,
    evaluation_id: uuid.UUID,
) -> uuid.UUID:
    """Deterministic identity for interview evaluation submission notification."""
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"evaluation_submitted:{user_id}:{evaluation_id}",
    )


def offer_response_notification_id(
    action: str,
    user_id: uuid.UUID,
    application_id: uuid.UUID,
    activity_id: uuid.UUID | None = None,
) -> uuid.UUID:
    suffix = f":{activity_id}" if activity_id is not None else ""
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"offer_{action}:{user_id}:{application_id}{suffix}",
    )


def candidate_interview_response_notification_id(
    action: str,
    user_id: uuid.UUID,
    interview_id: uuid.UUID,
    activity_id: uuid.UUID | None = None,
) -> uuid.UUID:
    suffix = f":{activity_id}" if activity_id is not None else ""
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"interview_{action}:{user_id}:{interview_id}{suffix}",
    )


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
        notification_id: Optional[uuid.UUID] = None,
    ) -> NotificationRead:
        notification = Notification(
            id=notification_id,
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

        # Schedule publish after commit using TransactionActionManager
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

        async def _publish() -> None:
            try:
                await pubsub_manager.publish(channel=channel, message=message)
            except Exception as e:
                logger.warning(f"Failed to publish notification event: {e}")

        TransactionActionManager.register_action(self.session, _publish)

        return NotificationRead.model_validate(notification)

    async def notify_account_unlocked(
        self,
        user_id: uuid.UUID,
    ) -> NotificationRead:
        """Create the notification when an account is unlocked by an administrator."""
        return await self.create_notification(
            user_id=user_id,
            title=ACCOUNT_UNLOCKED_TITLE,
            content="Tài khoản của bạn đã được quản trị viên mở khóa thành công. Bạn đã có thể đăng nhập và tiếp tục sử dụng dịch vụ.",
            notification_type=ACCOUNT_UNLOCKED_TYPE,
            entity_type="user",
            entity_id=user_id,
        )

    @staticmethod
    def _subscription_notification_id(
        event: str,
        user_id: uuid.UUID,
        subscription_id: uuid.UUID,
    ) -> uuid.UUID:
        """Stable identity for a per-user, per-subscription lifecycle event."""
        return uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{event}:{user_id}:{subscription_id}",
        )

    application_status_notification_id = staticmethod(application_status_notification_id)
    interview_schedule_notification_id = staticmethod(interview_schedule_notification_id)
    interview_assignment_notification_id = staticmethod(interview_assignment_notification_id)
    evaluation_submission_notification_id = staticmethod(evaluation_submission_notification_id)
    offer_response_notification_id = staticmethod(offer_response_notification_id)
    candidate_interview_response_notification_id = staticmethod(candidate_interview_response_notification_id)

    async def get_active_recruiter_and_admin_users(
        self,
        company_id: uuid.UUID,
    ) -> list[User]:
        """Resolve active company recruiters and admins strictly via CompanyMembership."""
        from app.domain.enums import MembershipRole, MembershipStatus
        from app.repositories.company_membership_repository import (
            CompanyMembershipRepository,
        )
        from app.repositories.user_repository import UserRepository

        membership_repo = CompanyMembershipRepository(self.session, CompanyMembership)
        memberships = await membership_repo.list_by_company(
            company_id, include_revoked=False
        )
        seen_user_ids: set[uuid.UUID] = set()
        recipients: list[User] = []
        user_repo: UserRepository | None = None

        for m in memberships:
            if m.role not in {MembershipRole.ADMIN, MembershipRole.RECRUITER}:
                continue
            if m.status != MembershipStatus.ACTIVE:
                continue
            if not m.user_id:
                continue
            user = m.user
            if user is None:
                if user_repo is None:
                    user_repo = UserRepository(self.session, User)
                user = await user_repo.get_by_id(m.user_id)
            if user is None or not user.is_active or getattr(user, "is_deleted", False):
                continue
            if user.id in seen_user_ids:
                continue
            seen_user_ids.add(user.id)
            recipients.append(user)
        return recipients

    async def create_idempotent_notification(
        self,
        *,
        user_id: uuid.UUID,
        title: str,
        content: str,
        notification_type: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[uuid.UUID] = None,
        notification_id: Optional[uuid.UUID] = None,
    ) -> NotificationRead | None:
        """Create notification with exact identity deduplication via get_by_id_and_user."""
        if notification_id is not None:
            res = self.notifications.get_by_id_and_user(
                notification_id=notification_id,
                user_id=user_id,
            )
            existing = await res if inspect.isawaitable(res) else None
            if existing is not None:
                return NotificationRead.model_validate(existing)

        return await self.create_notification(
            user_id=user_id,
            title=title,
            content=content,
            notification_type=notification_type,
            entity_type=entity_type,
            entity_id=entity_id,
            notification_id=notification_id,
        )

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
            notification_id=self._subscription_notification_id(
                SUBSCRIPTION_ACTIVATED_TYPE, user_id, subscription_id
            ),
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

    async def notify_company_returned_to_free(
        self,
        user_id: uuid.UUID,
        paid_subscription_id: uuid.UUID,
        plan_name: str | None = None,
    ) -> NotificationRead | None:
        """Notify an active Workspace Admin that a Paid subscription expired.

        The expired subscription id is the entity id, so every distinct plan
        period produces its own notification while retries for the same period
        are suppressed. The message only states what the persisted transition
        proves: the Paid plan ended and the Workspace is back on Free.
        """
        already_notified = await self.notifications.exists_by_entity(
            user_id=user_id,
            entity_type=SUBSCRIPTION_ENTITY_TYPE,
            entity_id=paid_subscription_id,
            notification_type=COMPANY_RETURNED_TO_FREE_TYPE,
        )
        if already_notified:
            return None

        subject = (
            f'Gói "{plan_name}" của công ty'
            if plan_name
            else "Gói trả phí của công ty"
        )
        return await self.create_notification(
            user_id=user_id,
            title=COMPANY_RETURNED_TO_FREE_TITLE,
            content=(
                f"{subject} đã hết hạn. "
                "Không gian làm việc đã quay lại gói miễn phí."
            ),
            notification_type=COMPANY_RETURNED_TO_FREE_TYPE,
            entity_type=SUBSCRIPTION_ENTITY_TYPE,
            entity_id=paid_subscription_id,
            notification_id=self._subscription_notification_id(
                COMPANY_RETURNED_TO_FREE_TYPE, user_id, paid_subscription_id
            ),
        )

    @staticmethod
    def _candidate_free_period_entity_id(
        subscription_id: uuid.UUID,
        period_key: str,
    ) -> uuid.UUID:
        """Stable entity id so a Free exhaustion notice is unique per period."""
        return uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"candidate-free-quota:{subscription_id}:{period_key}",
        )

    async def notify_candidate_paid_quota_exhausted(
        self,
        user_id: uuid.UUID,
        subscription_id: uuid.UUID,
        plan_name: str | None = None,
    ) -> NotificationRead | None:
        """Notify once that an active Paid entitlement has no AI quota left.

        Paid stays active, so this is a fixed-period exhaustion notice. Repeated
        rejected requests for the same subscription are suppressed.
        """
        already_notified = await self.notifications.exists_by_entity(
            user_id=user_id,
            entity_type=CANDIDATE_QUOTA_ENTITY_TYPE,
            entity_id=subscription_id,
            notification_type=CANDIDATE_PAID_QUOTA_EXHAUSTED_TYPE,
        )
        if already_notified:
            return None

        subject = f'Gói "{plan_name}"' if plan_name else "Gói trả phí của bạn"
        return await self.create_notification(
            user_id=user_id,
            title=CANDIDATE_PAID_QUOTA_EXHAUSTED_TITLE,
            content=(
                f"{subject} đã sử dụng hết hạn mức AI. "
                "Gói vẫn còn hiệu lực nhưng bạn không thể dùng thêm tính năng AI "
                "cho đến khi gói được gia hạn."
            ),
            notification_type=CANDIDATE_PAID_QUOTA_EXHAUSTED_TYPE,
            entity_type=CANDIDATE_QUOTA_ENTITY_TYPE,
            entity_id=subscription_id,
        )

    async def notify_candidate_free_quota_exhausted(
        self,
        user_id: uuid.UUID,
        subscription_id: uuid.UUID,
        period_key: str,
    ) -> NotificationRead | None:
        """Notify once per Vietnam calendar month for Free exhaustion."""
        entity_id = self._candidate_free_period_entity_id(
            subscription_id, period_key
        )
        already_notified = await self.notifications.exists_by_entity(
            user_id=user_id,
            entity_type=CANDIDATE_QUOTA_ENTITY_TYPE,
            entity_id=entity_id,
            notification_type=CANDIDATE_FREE_QUOTA_EXHAUSTED_TYPE,
        )
        if already_notified:
            return None

        return await self.create_notification(
            user_id=user_id,
            title=CANDIDATE_FREE_QUOTA_EXHAUSTED_TITLE,
            content=(
                f"Bạn đã sử dụng hết hạn mức AI miễn phí trong tháng {period_key}. "
                "Hạn mức sẽ được làm mới vào tháng sau."
            ),
            notification_type=CANDIDATE_FREE_QUOTA_EXHAUSTED_TYPE,
            entity_type=CANDIDATE_QUOTA_ENTITY_TYPE,
            entity_id=entity_id,
        )

    async def notify_candidate_returned_to_free(
        self,
        user_id: uuid.UUID,
        paid_subscription_id: uuid.UUID,
        reason: str,
    ) -> NotificationRead | None:
        """Notify once that a Candidate Paid entitlement ended.

        ``reason`` is only used in the message. Deduplication is keyed on the
        Paid subscription id so expiration/cancellation retries do not flood the
        candidate.
        """
        already_notified = await self.notifications.exists_by_entity(
            user_id=user_id,
            entity_type=CANDIDATE_QUOTA_ENTITY_TYPE,
            entity_id=paid_subscription_id,
            notification_type=CANDIDATE_RETURNED_TO_FREE_TYPE,
        )
        if already_notified:
            return None

        reason_text = (
            "đã hết hạn" if reason == "expired" else "đã bị hủy"
        )
        return await self.create_notification(
            user_id=user_id,
            title=CANDIDATE_RETURNED_TO_FREE_TITLE,
            content=(
                f"Gói trả phí của bạn {reason_text}. "
                "Tài khoản đã tự động quay lại gói miễn phí."
            ),
            notification_type=CANDIDATE_RETURNED_TO_FREE_TYPE,
            entity_type=CANDIDATE_QUOTA_ENTITY_TYPE,
            entity_id=paid_subscription_id,
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
