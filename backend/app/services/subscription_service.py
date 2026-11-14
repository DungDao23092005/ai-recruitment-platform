from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    InvalidTransitionException,
    ValidationError,
)
from app.domain.enums import (
    PlanAudience,
    SubscriptionScope,
    SubscriptionStatus,
    SubscriptionUsageFeatureType,
    SubscriptionUsageStatus,
    UserRole,
)
from app.domain.models.base import utc_now
from app.models import (
    PaymentOrder,
    RecruitmentPlan,
    RecruiterProfile,
    Subscription,
    SubscriptionUsage,
    User,
)
from app.repositories import (
    PaymentOrderRepository,
    RecruitmentPlanRepository,
    SubscriptionRepository,
)
from app.schemas.subscription import (
    CandidateUsageHistoryResponse,
    CandidateUsageItem,
    CompanyUsageHistoryResponse,
    CompanyUsageItem,
    SubscriptionCreate,
)
from app.services.notification_service import NotificationService
from app.services.recruiter_access import ensure_recruiter_access
from app.services.subscription_email_service import schedule_activation_email
from app.services.subscription_realtime import (
    ACTION_ACTIVATED,
    schedule_admin_subscription_event,
)

_VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
_MAX_USAGE_RANGE_DAYS = 366

_USAGE_FEATURE_LABELS: dict[SubscriptionUsageFeatureType, str] = {
    SubscriptionUsageFeatureType.JOB_POST: "Tin tuyển dụng",
    SubscriptionUsageFeatureType.CANDIDATE_SEARCH: "Tìm kiếm ứng viên",
    SubscriptionUsageFeatureType.AI_FEATURE: "AI tuyển dụng",
    SubscriptionUsageFeatureType.RECRUITING_AI: "AI tuyển dụng",
    SubscriptionUsageFeatureType.CANDIDATE_PARSE_RESUME: "Phân tích CV",
    SubscriptionUsageFeatureType.CANDIDATE_JOB_RECOMMENDATIONS: "Gợi ý việc làm",
    SubscriptionUsageFeatureType.CANDIDATE_CHAT: "Trò chuyện AI",
}

_USAGE_STATUS_LABELS: dict[SubscriptionUsageStatus, str] = {
    SubscriptionUsageStatus.RESERVED: "Đang xử lý",
    SubscriptionUsageStatus.COMPLETED: "Hoàn tất",
    SubscriptionUsageStatus.FAILED: "Thất bại",
}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _local_day_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=_VN_TZ)


def _normalize_usage_window(
    start_date: date | None,
    end_date: date | None,
    now: datetime | None,
) -> tuple[datetime, datetime]:
    """Resolve the Company usage window to a half-open UTC interval.

    Defaults follow the current calendar month in Asia/Ho_Chi_Minh. The end
    bound is exclusive: an explicit ``end_date`` includes that whole local day,
    while an omitted end uses the actual current instant.
    """
    current = _as_utc(now or utc_now())
    local_now = current.astimezone(_VN_TZ)

    if start_date is None:
        start_local = _local_day_start(local_now.date().replace(day=1))
    else:
        start_local = _local_day_start(start_date)

    if end_date is None:
        end_exclusive = current
        effective_end_date = local_now.date()
    else:
        end_exclusive = _local_day_start(end_date + timedelta(days=1))
        effective_end_date = end_date

    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_exclusive.astimezone(timezone.utc)

    if start_date is not None:
        span_days = (effective_end_date - start_date).days + 1
        if span_days > _MAX_USAGE_RANGE_DAYS:
            raise ValidationError(
                f"Date range must not exceed {_MAX_USAGE_RANGE_DAYS} days"
            )
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValidationError("start_date must be on or before end_date")
    if start_utc > end_utc:
        raise ValidationError("start_date must be on or before end_date")

    return start_utc, end_utc


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.subscriptions = SubscriptionRepository(session)
        self.plans = RecruitmentPlanRepository(session)
        self.payment_orders = PaymentOrderRepository(session)

    async def get_current_active_subscription(
        self,
        user_id: uuid.UUID,
        now: Optional[datetime] = None,
    ) -> Optional[Subscription]:
        if now is None:
            now = utc_now()
        return await self.subscriptions.get_active_by_user_id(user_id, now)

    async def get_current_active_company_subscription(
        self,
        company_id: uuid.UUID,
        now: Optional[datetime] = None,
    ) -> Optional[Subscription]:
        if now is None:
            now = utc_now()
        return await self.subscriptions.get_active_by_company_id(
            company_id, now
        )

    async def list_company_payment_orders(
        self,
        company_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> list[PaymentOrder]:
        return await self.payment_orders.get_by_company_id(
            company_id=company_id,
            user_id=user_id,
        )

    async def list_company_usages(
        self,
        *,
        company_id: uuid.UUID,
        page: int,
        page_size: int,
        start_date: date | None = None,
        end_date: date | None = None,
        feature_type: SubscriptionUsageFeatureType | None = None,
        user_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> CompanyUsageHistoryResponse:
        start_at, end_at = _normalize_usage_window(
            start_date, end_date, now
        )
        usages, total = await self.subscriptions.list_company_usages(
            company_id=company_id,
            start_at=start_at,
            end_at=end_at,
            page=page,
            page_size=page_size,
            feature_type=feature_type,
            user_id=user_id,
        )
        total_pages = (total + page_size - 1) // page_size if total else 0
        return CompanyUsageHistoryResponse(
            items=[
                self._serialize_company_usage(usage) for usage in usages
            ],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    @staticmethod
    def _serialize_company_usage(usage: SubscriptionUsage) -> CompanyUsageItem:
        recruiter_profile = usage.user.recruiter_profile
        return CompanyUsageItem(
            id=usage.id,
            subscription_id=usage.subscription_id,
            user_id=usage.user_id,
            user_email=usage.user.email,
            user_full_name=(
                recruiter_profile.full_name
                if recruiter_profile is not None
                else None
            ),
            feature_type=usage.feature_type,
            feature_label=_USAGE_FEATURE_LABELS.get(
                usage.feature_type, usage.feature_type.value
            ),
            amount=usage.amount,
            status=usage.status,
            status_label=_USAGE_STATUS_LABELS.get(
                usage.status, usage.status.value
            ),
            reference_id=usage.reference_id,
            created_at=_as_utc(usage.created_at),
            finalized_at=(
                _as_utc(usage.finalized_at)
                if usage.finalized_at is not None
                else None
            ),
        )

    async def list_candidate_usages(
        self,
        *,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
        start_date: date | None = None,
        end_date: date | None = None,
        feature_type: SubscriptionUsageFeatureType | None = None,
        status: SubscriptionUsageStatus | None = None,
        now: datetime | None = None,
    ) -> CandidateUsageHistoryResponse:
        start_at, end_at = _normalize_usage_window(
            start_date, end_date, now
        )
        usages, total = await self.subscriptions.list_candidate_usages(
            user_id=user_id,
            start_at=start_at,
            end_at=end_at,
            page=page,
            page_size=page_size,
            feature_type=feature_type,
            status=status,
        )
        total_pages = (total + page_size - 1) // page_size if total else 0
        return CandidateUsageHistoryResponse(
            items=[
                self._serialize_candidate_usage(usage)
                for usage in usages
            ],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    @staticmethod
    def _serialize_candidate_usage(
        usage: SubscriptionUsage,
    ) -> CandidateUsageItem:
        return CandidateUsageItem(
            id=usage.id,
            subscription_id=usage.subscription_id,
            feature_type=usage.feature_type,
            feature_label=_USAGE_FEATURE_LABELS.get(
                usage.feature_type, usage.feature_type.value
            ),
            amount=usage.amount,
            status=usage.status,
            status_label=_USAGE_STATUS_LABELS.get(
                usage.status, usage.status.value
            ),
            reference_id=usage.reference_id,
            created_at=_as_utc(usage.created_at),
            finalized_at=(
                _as_utc(usage.finalized_at)
                if usage.finalized_at is not None
                else None
            ),
        )

    async def get_subscription_by_id(
        self,
        subscription_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> Subscription:
        sub = await self.subscriptions.get_by_id_including_deleted(subscription_id)
        if sub is None:
            raise EntityNotFoundException(f"Subscription {subscription_id} not found")
        if user_id is not None and sub.user_id != user_id:
            raise EntityNotFoundException(f"Subscription {subscription_id} not found")
        return sub

    async def list_user_subscriptions(self, user_id: uuid.UUID) -> list[Subscription]:
        return await self.subscriptions.get_by_user_id(user_id)

    async def _lock_user_for_subscription(
        self,
        user_id: uuid.UUID,
    ) -> User:
        """
        Lock the user row to serialize subscription creation/activation.
        The user row always exists, so FOR UPDATE will always have a target.
        Uses explicit SQL Server UPDLOCK table hint for proper serialization.
        """
        stmt = (
            select(User)
            .where(User.id == user_id)
            .with_hint(User, "WITH (UPDLOCK, ROWLOCK)")
        )
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            raise EntityNotFoundException(f"User {user_id} not found")
        return user

    async def _check_active_overlap(
        self,
        user_id: uuid.UUID,
        now: datetime,
        plan: Optional[RecruitmentPlan] = None,
    ) -> Optional[Subscription]:
        """Return the active subscription that blocks the requested plan.

        Candidate tiers are independent entitlements: an active Free row blocks
        only another Free row and an active Paid row blocks only another Paid
        row, which lets Free and Paid coexist. Legacy recruiter plans keep their
        existing single-active invariant. Company subscriptions never enter this
        check, so candidate entitlements cannot interfere with company billing.
        """
        if plan is not None and plan.plan_audience == PlanAudience.CANDIDATE:
            if plan.is_free:
                return await self.subscriptions.get_active_candidate_free_by_user_id(
                    user_id, now
                )
            return await self.subscriptions.get_active_candidate_paid_by_user_id(
                user_id, now
            )

        stmt = (
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.is_deleted == False,  # noqa: E712
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at > now,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_pending_subscription(
        self,
        user_id: uuid.UUID,
        plan_id: uuid.UUID,
    ) -> Subscription:
        plan = await self.plans.get_active_by_id(plan_id)
        if plan is None:
            raise EntityNotFoundException(f"Plan {plan_id} not found or inactive")

        # Lock user row first to serialize subscription creation for this user
        await self._lock_user_for_subscription(user_id)

        now = utc_now()

        # Check for existing active subscription
        existing_active = await self._check_active_overlap(user_id, now, plan=plan)
        if existing_active is not None:
            raise ConflictException(
                f"User already has an active subscription (id: {existing_active.id})"
            )

        # Check for pending subscription for the same plan
        stmt_pending = (
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.plan_id == plan_id,
                Subscription.is_deleted == False,  # noqa: E712
                Subscription.status == SubscriptionStatus.PENDING,
            )
        )
        result_pending = await self.session.execute(stmt_pending)
        existing_pending = result_pending.scalar_one_or_none()

        if existing_pending is not None:
            return existing_pending

        # Create new pending subscription
        subscription = Subscription(
            user_id=user_id,
            plan_id=plan_id,
            status=SubscriptionStatus.PENDING,
        )
        self.session.add(subscription)
        try:
            await self.session.commit()
            await self.session.refresh(subscription)
        except Exception:
            await self.session.rollback()
            raise
        return subscription

    async def activate_subscription(
        self,
        subscription_id: uuid.UUID,
        payment_order_id: Optional[uuid.UUID] = None,
    ) -> Subscription:
        sub = await self.subscriptions.get_by_id_including_deleted(subscription_id)
        if sub is None:
            raise EntityNotFoundException(f"Subscription {subscription_id} not found")

        if sub.status != SubscriptionStatus.PENDING:
            raise InvalidTransitionException(
                f"Cannot activate subscription in status {sub.status.value}"
            )

        # Lock user row to serialize activation for this user
        await self._lock_user_for_subscription(sub.user_id)

        # Re-read the subscription under the per-user lock. The PENDING check
        # above ran before serialization, so a concurrent activation of the same
        # subscription may have completed while we waited for the lock. Refreshing
        # here makes PENDING -> ACTIVE a single-winner transition, which in turn
        # guarantees the activation notification is emitted exactly once per
        # transition (a loser raises instead of re-notifying).
        await self.session.refresh(sub)
        if sub.status != SubscriptionStatus.PENDING:
            raise InvalidTransitionException(
                f"Cannot activate subscription in status {sub.status.value}"
            )

        is_candidate_subscription = (
            sub.scope == SubscriptionScope.CANDIDATE_PERSONAL
        )

        now = utc_now()

        # Retire stale ACTIVE rows first so they cannot be mistaken for a live
        # overlap. This runs under the same per-user lock and transaction as the
        # activation, so the status change and new activation commit together.
        await self.subscriptions.expire_stale_active_for_user(sub.user_id, now)

        plan = await self.plans.get_active_by_id(sub.plan_id)
        if plan is None:
            raise EntityNotFoundException(f"Plan {sub.plan_id} not found or inactive")

        if is_candidate_subscription:
            if (
                plan.plan_audience != PlanAudience.CANDIDATE
                or bool(getattr(plan, "is_free", False))
                or sub.is_free
                or sub.company_id is not None
            ):
                raise ConflictException(
                    "Candidate paid activation requires an active paid Candidate plan"
                )

        # Check for existing active subscription BEFORE activating. The plan
        # determines which candidate tier (Free/Paid) is allowed to coexist.
        existing_active = await self._check_active_overlap(
            sub.user_id, now, plan=plan
        )
        if existing_active is not None and existing_active.id != sub.id:
            raise ConflictException(
                f"User already has an active subscription (id: {existing_active.id})"
            )

        # Get the user (already locked by _lock_user_for_subscription)
        stmt = select(User).where(User.id == sub.user_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            raise EntityNotFoundException(f"User {sub.user_id} not found")

        if is_candidate_subscription:
            if user.role != UserRole.CANDIDATE:
                raise ConflictException(
                    "Candidate subscription owner is no longer a candidate"
                )
        else:
            # Ensure recruiter access (role transition + profile creation) only
            # for the preserved legacy personal checkout domain.
            await ensure_recruiter_access(self.session, user)

        sub.status = SubscriptionStatus.ACTIVE
        sub.started_at = now
        sub.expires_at = now + timedelta(days=plan.duration_days)

        # Snapshot quota from plan at activation time
        sub.max_job_posts = plan.max_job_posts
        sub.max_candidate_searches = plan.max_candidate_searches or 0
        sub.max_ai_features = plan.max_ai_features or 0
        # Initialize usage counters to 0 (grandfathered jobs not counted)
        sub.job_posts_used = 0
        sub.candidate_searches_used = 0
        sub.ai_features_used = 0
        if is_candidate_subscription:
            # Candidate Paid has a fixed period and must not carry the Candidate
            # Free monthly period key.
            sub.current_period_key = None

        # Create the activation notification in the SAME session/transaction as
        # the PENDING -> ACTIVE transition so the two commit or roll back
        # together. Publishing to Redis/SSE is scheduled for after commit and a
        # publish failure cannot invalidate the committed activation.
        notification = await NotificationService(
            self.session
        ).notify_subscription_activated(
            user_id=sub.user_id,
            subscription_id=sub.id,
            plan_name=plan.name,
            expires_at=sub.expires_at,
        )

        # Durable lifecycle email + admin invalidation. Email is enqueued in the
        # SAME transaction (gated on a freshly created notification) so a
        # re-entrant caller cannot resend it.
        if notification is not None:
            await schedule_activation_email(
                self.session,
                to_email=user.email,
                plan_name=plan.name,
                expires_at=sub.expires_at,
                idempotency_key=f"subscription_activated:{sub.id}",
            )
        schedule_admin_subscription_event(
            self.session,
            user_id=sub.user_id,
            subscription_id=sub.id,
            action=ACTION_ACTIVATED,
        )

        try:
            await self.session.commit()
            await self.session.refresh(sub)
        except Exception:
            await self.session.rollback()
            raise
        return sub

    async def cancel_subscription(
        self,
        subscription_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> Subscription:
        sub = await self.subscriptions.get_by_id_including_deleted(subscription_id)
        if sub is None:
            raise EntityNotFoundException(f"Subscription {subscription_id} not found")

        if user_id is not None and sub.user_id != user_id:
            raise EntityNotFoundException(f"Subscription {subscription_id} not found")

        if sub.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.PENDING):
            raise InvalidTransitionException(
                f"Cannot cancel subscription in status {sub.status.value}"
            )

        sub.status = SubscriptionStatus.CANCELLED
        if (
            sub.scope == SubscriptionScope.CANDIDATE_PERSONAL
            and not sub.is_free
        ):
            await NotificationService(
                self.session
            ).notify_candidate_returned_to_free(
                user_id=sub.user_id,
                paid_subscription_id=sub.id,
                reason="cancelled",
            )
        try:
            await self.session.commit()
            await self.session.refresh(sub)
        except Exception:
            await self.session.rollback()
            raise
        return sub

    async def check_and_expire_subscriptions(
        self,
        now: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> int:
        """Check for expired subscriptions and persist their status.

        Expiration is a lazy, database-level conditional update: rows are
        selected oldest-first for the batch, then the UPDATE re-checks status,
        soft-delete and ``expires_at <= now`` at write time so a concurrent
        renewal cannot be overwritten with EXPIRED.
        """
        if now is None:
            now = utc_now()

        expiring_candidate_paid = await self.subscriptions.get_stale_candidate_paid(
            now, limit=limit
        )
        count = await self.subscriptions.expire_stale_active(now, limit=limit)

        if count > 0:
            if expiring_candidate_paid:
                notifications = NotificationService(self.session)
                for candidate_paid in expiring_candidate_paid:
                    await self.session.refresh(candidate_paid)
                    if candidate_paid.status != SubscriptionStatus.EXPIRED:
                        continue
                    await notifications.notify_candidate_returned_to_free(
                        user_id=candidate_paid.user_id,
                        paid_subscription_id=candidate_paid.id,
                        reason="expired",
                    )
            try:
                await self.session.commit()
            except Exception:
                await self.session.rollback()
                raise

        return count