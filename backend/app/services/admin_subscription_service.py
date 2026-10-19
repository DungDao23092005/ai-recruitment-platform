from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    InvalidTransitionException,
)
from app.domain.enums import SubscriptionAuditAction, SubscriptionStatus
from app.domain.models.base import utc_now
from app.models import PaymentOrder, Subscription, SubscriptionAuditLog, User
from app.repositories import (
    PaymentOrderRepository,
    RecruitmentPlanRepository,
    SubscriptionAuditLogRepository,
    SubscriptionRepository,
)
from app.schemas.subscription import (
    AdminSubscriptionDetail,
    AdminSubscriptionListItem,
    SubscriptionAuditLogRead,
    SubscriptionPaymentSummary,
    SubscriptionSummary,
)
from app.services.notification_service import NotificationService
from app.services.recruiter_access import ensure_recruiter_access
from app.services.subscription_email_service import (
    schedule_activation_email,
    schedule_plan_changed_email,
    schedule_revoked_email,
)
from app.services.subscription_realtime import (
    ACTION_ACTIVATED,
    ACTION_PLAN_CHANGED,
    ACTION_REVOKED,
    schedule_admin_subscription_event,
)

# Reason recorded when an admin provisions a subscription through the support
# endpoint. The endpoint does not require an operator-supplied reason, so this
# keeps the audit trail non-null and human-readable.
_PROVISION_REASON = "Khởi tạo gói bởi quản trị viên"


def _as_utc(value: datetime) -> datetime:
    """Interpret a naive SQL Server datetime as UTC for comparison."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _effective_status(sub: Subscription, now: datetime) -> SubscriptionStatus:
    """Display status without mutating the DB.

    A row stored as ACTIVE but already past ``expires_at`` is surfaced as
    EXPIRED (lazy expiry), matching the read-time entitlement checks elsewhere.
    """
    if sub.status == SubscriptionStatus.ACTIVE and sub.expires_at is not None:
        if _as_utc(sub.expires_at) <= _as_utc(now):
            return SubscriptionStatus.EXPIRED
    return sub.status


class AdminSubscriptionService:
    """Administrator-facing subscription operations.

    All mutating operations:
      * take the per-user row lock so they serialize against VNPAY IPN/QueryDr
        activation (which uses the same lock),
      * fail closed with a 409-mapped ``ConflictException`` while the user has an
        unresolved VNPAY checkout (an unexpired PENDING order or a PAID order
        whose subscription is still PENDING),
      * write both the subscription mutation and its audit log, plus the buyer
        notification, in the SAME transaction, so they commit or roll back
        together.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.subscriptions = SubscriptionRepository(session)
        self.plans = RecruitmentPlanRepository(session)
        self.payment_orders = PaymentOrderRepository(session)
        self.audit = SubscriptionAuditLogRepository(session)

    # ------------------------------------------------------------------ reads

    async def list_subscriptions(
        self,
        *,
        skip: int,
        limit: int,
        search: Optional[str] = None,
        status_filter: Optional[SubscriptionStatus] = None,
        plan_id: Optional[uuid.UUID] = None,
    ) -> tuple[list[AdminSubscriptionListItem], int]:
        """One representative row per user, ranked before filter/pagination."""
        now = utc_now()
        representatives, total = await self.subscriptions.list_admin(
            skip=skip,
            limit=limit,
            status_filter=status_filter,
            plan_id=plan_id,
            search=search,
            now=now,
        )
        user_ids = [rep.subscription.user_id for rep in representatives]
        payments = await self._payment_diagnostics(user_ids, now)
        items = []
        for rep in representatives:
            uid = rep.subscription.user_id
            has_unresolved, incident = payments.get(uid, (False, None))
            items.append(
                self._to_list_item(
                    rep.subscription,
                    total_subscriptions=rep.total_subscriptions,
                    active_count=rep.active_count,
                    has_unresolved_payment=has_unresolved,
                    incident=incident,
                    now=now,
                )
            )
        return items, total

    async def get_detail(self, subscription_id: uuid.UUID) -> AdminSubscriptionDetail:
        """Detail of the user owning ``subscription_id``: representative row
        plus the whole user's subscription history, payments and audit trail."""
        sub = await self.subscriptions.get_by_id_including_deleted(subscription_id)
        if sub is None:
            raise EntityNotFoundException(f"Subscription {subscription_id} not found")

        now = utc_now()
        user_id = sub.user_id
        user_email = await self._user_email(user_id)

        representative = await self.subscriptions.get_representative_for_user(
            user_id, now
        )
        if representative is None:
            representative = sub

        counts = await self.subscriptions.count_by_user_ids([user_id], now)
        total_subscriptions, active_count = counts.get(user_id, (0, 0))
        payments_diag = await self._payment_diagnostics([user_id], now)
        has_unresolved, incident = payments_diag.get(user_id, (False, None))

        history_subs = await self.subscriptions.get_by_user_id(user_id)
        payments_by_sub: dict[uuid.UUID, list[PaymentOrder]] = defaultdict(list)
        for order in await self.payment_orders.list_by_subscription_ids(
            [item.id for item in history_subs]
        ):
            payments_by_sub[order.subscription_id].append(order)

        audit_logs = await self.audit.list_by_user(user_id)

        return AdminSubscriptionDetail(
            subscription=self._to_list_item(
                representative,
                total_subscriptions=total_subscriptions,
                active_count=active_count,
                has_unresolved_payment=has_unresolved,
                incident=incident,
                now=now,
                user_email=user_email,
            ),
            history=[
                self._to_history_item(item, payments_by_sub.get(item.id, []))
                for item in history_subs
            ],
            audit_logs=[self._to_audit_read(log) for log in audit_logs],
        )

    # ------------------------------------------------------------- mutations

    async def provision(
        self,
        *,
        admin_id: uuid.UUID,
        user_id: uuid.UUID,
        plan_id: uuid.UUID,
    ) -> Subscription:
        plan = await self.plans.get_active_by_id(plan_id)
        if plan is None:
            raise EntityNotFoundException(f"Plan {plan_id} not found or inactive")

        await self._lock_user(user_id)
        now = utc_now()

        existing_active = await self._check_active_overlap(user_id, now)
        if existing_active is not None:
            raise ConflictException(
                f"User already has an active subscription (id: {existing_active.id})"
            )

        await self._assert_no_unresolved_payment(user_id)

        user = await self._load_user(user_id)

        # Reuse a matching pending subscription if one exists so a repeated
        # support call is idempotent instead of creating a second pending row.
        sub = await self.subscriptions.get_pending_by_user_and_plan(user_id, plan_id)
        if sub is None:
            sub = Subscription(
                user_id=user_id,
                plan_id=plan_id,
                status=SubscriptionStatus.PENDING,
            )
            self.session.add(sub)
            await self.session.flush()

        await ensure_recruiter_access(self.session, user)

        self._apply_plan_snapshot(sub, plan, now, reset_usage=True)

        self._add_audit(
            admin_id=admin_id,
            subscription=sub,
            action=SubscriptionAuditAction.PROVISION,
            old_plan_id=None,
            new_plan_id=plan.id,
            reason=_PROVISION_REASON,
        )
        notification = await NotificationService(
            self.session
        ).notify_subscription_activated(
            user_id=sub.user_id,
            subscription_id=sub.id,
            plan_name=plan.name,
            expires_at=sub.expires_at,
        )
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

        await self._commit_and_refresh(sub)
        return sub

    async def change_plan(
        self,
        *,
        admin_id: uuid.UUID,
        subscription_id: uuid.UUID,
        target_plan_id: uuid.UUID,
        reason: str,
    ) -> Subscription:
        sub = await self.subscriptions.get_by_id_including_deleted(subscription_id)
        if sub is None:
            raise EntityNotFoundException(f"Subscription {subscription_id} not found")
        if sub.status != SubscriptionStatus.ACTIVE:
            raise InvalidTransitionException(
                f"Cannot change plan of subscription in status {sub.status.value}"
            )

        await self._lock_user(sub.user_id)
        # Re-read under the lock so the ACTIVE check is a single-winner guard.
        await self.session.refresh(sub)
        if sub.status != SubscriptionStatus.ACTIVE:
            raise InvalidTransitionException(
                f"Cannot change plan of subscription in status {sub.status.value}"
            )

        await self._assert_no_unresolved_payment(sub.user_id)

        target = await self.plans.get_active_by_id(target_plan_id)
        if target is None:
            raise EntityNotFoundException(f"Plan {target_plan_id} not found or inactive")
        if target.id == sub.plan_id:
            raise ConflictException(
                "Gói mới trùng với gói hiện tại của người dùng."
            )

        old_plan = await self.plans.get_active_by_id_admin(sub.plan_id)
        old_plan_id = sub.plan_id
        old_plan_name = old_plan.name if old_plan else None

        now = utc_now()
        # Mutate in place: the subscription row id, counters and usage ledger
        # are preserved so there is never a counter/ledger mismatch, and
        # ``_reserve`` clamps remaining quota at zero when usage already meets
        # or exceeds the new plan's limit.
        self._apply_plan_snapshot(sub, target, now, reset_usage=False)

        self._add_audit(
            admin_id=admin_id,
            subscription=sub,
            action=SubscriptionAuditAction.CHANGE_PLAN,
            old_plan_id=old_plan_id,
            new_plan_id=target.id,
            reason=reason,
        )
        await NotificationService(self.session).notify_subscription_plan_changed(
            user_id=sub.user_id,
            subscription_id=sub.id,
            old_plan_name=old_plan_name,
            new_plan_name=target.name,
            expires_at=sub.expires_at,
        )

        await schedule_plan_changed_email(
            self.session,
            to_email=await self._user_email(sub.user_id),
            previous_plan_name=old_plan_name,
            new_plan_name=target.name,
            expires_at=sub.expires_at,
            reason=reason,
            idempotency_key=f"subscription_plan_changed:{sub.id}:{now.isoformat()}",
        )
        schedule_admin_subscription_event(
            self.session,
            user_id=sub.user_id,
            subscription_id=sub.id,
            action=ACTION_PLAN_CHANGED,
        )

        await self._commit_and_refresh(sub)
        return sub

    async def revoke(
        self,
        *,
        admin_id: uuid.UUID,
        subscription_id: uuid.UUID,
        reason: str,
    ) -> Subscription:
        sub = await self.subscriptions.get_by_id_including_deleted(subscription_id)
        if sub is None:
            raise EntityNotFoundException(f"Subscription {subscription_id} not found")
        if sub.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.PENDING):
            raise InvalidTransitionException(
                f"Cannot revoke subscription in status {sub.status.value}"
            )

        await self._lock_user(sub.user_id)
        await self.session.refresh(sub)
        if sub.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.PENDING):
            raise InvalidTransitionException(
                f"Cannot revoke subscription in status {sub.status.value}"
            )

        await self._assert_no_unresolved_payment(sub.user_id)

        old_plan_id = sub.plan_id
        plan = await self.plans.get_active_by_id_admin(sub.plan_id)
        plan_name = plan.name if plan else None

        # Revocation is immediate. RECRUITER role and recruiter profile are
        # intentionally left intact (data is preserved, entitlement is gone).
        sub.status = SubscriptionStatus.CANCELLED

        self._add_audit(
            admin_id=admin_id,
            subscription=sub,
            action=SubscriptionAuditAction.REVOKE,
            old_plan_id=old_plan_id,
            new_plan_id=None,
            reason=reason,
        )
        await NotificationService(self.session).notify_subscription_revoked(
            user_id=sub.user_id,
            subscription_id=sub.id,
            plan_name=plan_name,
            reason=reason,
        )

        revoked_at = utc_now()
        await schedule_revoked_email(
            self.session,
            to_email=await self._user_email(sub.user_id),
            plan_name=plan_name or "Gói dịch vụ",
            reason=reason,
            effective_at=revoked_at,
            idempotency_key=f"subscription_revoked:{sub.id}",
        )
        schedule_admin_subscription_event(
            self.session,
            user_id=sub.user_id,
            subscription_id=sub.id,
            action=ACTION_REVOKED,
        )

        await self._commit_and_refresh(sub)
        return sub

    # -------------------------------------------------------------- internals

    def _apply_plan_snapshot(
        self,
        sub: Subscription,
        plan,
        now: datetime,
        *,
        reset_usage: bool,
    ) -> None:
        sub.plan_id = plan.id
        sub.status = SubscriptionStatus.ACTIVE
        sub.started_at = now
        sub.expires_at = now + timedelta(days=plan.duration_days)
        sub.max_job_posts = plan.max_job_posts
        sub.max_candidate_searches = plan.max_candidate_searches or 0
        sub.max_ai_features = plan.max_ai_features or 0
        if reset_usage:
            sub.job_posts_used = 0
            sub.candidate_searches_used = 0
            sub.ai_features_used = 0

    def _add_audit(
        self,
        *,
        admin_id: uuid.UUID,
        subscription: Subscription,
        action: SubscriptionAuditAction,
        old_plan_id: Optional[uuid.UUID],
        new_plan_id: Optional[uuid.UUID],
        reason: str,
    ) -> SubscriptionAuditLog:
        log = SubscriptionAuditLog(
            admin_id=admin_id,
            user_id=subscription.user_id,
            subscription_id=subscription.id,
            action=action,
            old_plan_id=old_plan_id,
            new_plan_id=new_plan_id,
            reason=reason.strip(),
        )
        self.session.add(log)
        return log

    async def _assert_no_unresolved_payment(self, user_id: uuid.UUID) -> None:
        """Fail closed while the user has an unresolved VNPAY payment.

        Covers both an unexpired PENDING checkout order and a PAID order whose
        bound subscription never activated (entitlement incident). Mutating the
        subscription in either case risks double entitlement or leaving a paid
        order without a matching active subscription.
        """
        pending = await self.payment_orders.get_active_pending_for_user(
            user_id, utc_now()
        )
        if pending:
            raise ConflictException(
                "Người dùng đang có giao dịch VNPAY chờ xử lý. "
                "Vui lòng hoàn tất hoặc hủy giao dịch trước khi thay đổi gói."
            )
        incident = await self.payment_orders.has_paid_order_with_pending_subscription(
            user_id
        )
        if incident:
            raise ConflictException(
                "Người dùng có giao dịch đã thanh toán nhưng gói chưa được kích hoạt. "
                "Vui lòng xử lý trước khi thay đổi gói."
            )

    async def _lock_user(self, user_id: uuid.UUID) -> User:
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

    async def _load_user(self, user_id: uuid.UUID) -> User:
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            raise EntityNotFoundException(f"User {user_id} not found")
        return user

    async def _user_email(self, user_id: uuid.UUID) -> Optional[str]:
        user = await self._load_user(user_id)
        return user.email

    async def _check_active_overlap(
        self,
        user_id: uuid.UUID,
        now: datetime,
    ) -> Optional[Subscription]:
        stmt = select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.is_deleted == False,  # noqa: E712
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.expires_at > now,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _commit_and_refresh(self, sub: Subscription) -> None:
        try:
            await self.session.commit()
            await self.session.refresh(sub)
        except Exception:
            await self.session.rollback()
            raise

    def _to_list_item(
        self,
        sub: Subscription,
        *,
        total_subscriptions: int = 1,
        active_count: int = 0,
        has_unresolved_payment: bool = False,
        incident: Optional[PaymentOrder] = None,
        now: Optional[datetime] = None,
        user_email: Optional[str] = None,
    ) -> AdminSubscriptionListItem:
        if now is None:
            now = utc_now()
        if user_email is None and getattr(sub, "user", None) is not None:
            user_email = sub.user.email
        plan = getattr(sub, "plan", None)
        return AdminSubscriptionListItem(
            id=sub.id,
            user_id=sub.user_id,
            user_email=user_email,
            plan_id=sub.plan_id,
            plan_name=plan.name if plan is not None else None,
            status=sub.status,
            effective_status=_effective_status(sub, now),
            started_at=sub.started_at,
            expires_at=sub.expires_at,
            created_at=sub.created_at,
            updated_at=sub.updated_at,
            max_job_posts=sub.max_job_posts,
            max_candidate_searches=sub.max_candidate_searches,
            max_ai_features=sub.max_ai_features,
            job_posts_used=sub.job_posts_used,
            candidate_searches_used=sub.candidate_searches_used,
            ai_features_used=sub.ai_features_used,
            total_subscriptions=total_subscriptions,
            has_multiple_active=active_count >= 2,
            has_unresolved_payment=has_unresolved_payment,
            is_entitlement_incident=incident is not None,
            incident_subscription_id=(
                incident.subscription_id if incident is not None else None
            ),
            incident_internal_order_id=(
                incident.internal_order_id if incident is not None else None
            ),
            incident_amount=incident.amount if incident is not None else None,
        )

    def _to_history_item(
        self,
        sub: Subscription,
        payments: list[PaymentOrder],
    ) -> SubscriptionSummary:
        plan = getattr(sub, "plan", None)
        return SubscriptionSummary(
            id=sub.id,
            plan_id=sub.plan_id,
            plan_name=plan.name if plan is not None else None,
            status=sub.status,
            started_at=sub.started_at,
            expires_at=sub.expires_at,
            created_at=sub.created_at,
            max_job_posts=sub.max_job_posts,
            max_candidate_searches=sub.max_candidate_searches,
            max_ai_features=sub.max_ai_features,
            job_posts_used=sub.job_posts_used,
            candidate_searches_used=sub.candidate_searches_used,
            ai_features_used=sub.ai_features_used,
            payments=[self._to_payment_summary(order) for order in payments],
        )

    def _to_payment_summary(self, order: PaymentOrder) -> SubscriptionPaymentSummary:
        return SubscriptionPaymentSummary(
            id=order.id,
            plan_id=order.plan_id,
            subscription_id=order.subscription_id,
            internal_order_id=order.internal_order_id,
            provider=order.provider,
            status=order.status,
            amount=order.amount,
            currency=order.currency,
            paid_at=order.paid_at,
            expired_at=order.expired_at,
            created_at=order.created_at,
        )

    async def _payment_diagnostics(
        self,
        user_ids: list[uuid.UUID],
        now: datetime,
    ) -> dict[uuid.UUID, tuple[bool, Optional[PaymentOrder]]]:
        """Batch ``{user_id: (has_unresolved_payment, incident_order)}``.

        ``has_unresolved_payment`` mirrors ``_assert_no_unresolved_payment``:
        an unexpired PENDING VNPAY order OR a PAID order bound to a PENDING
        subscription. The incident is the newest per user (deterministic).
        """
        if not user_ids:
            return {}
        pending_user_ids = await self.payment_orders.list_active_pending_user_ids(
            user_ids, now
        )
        incident_by_user: dict[uuid.UUID, PaymentOrder] = {}
        for order in await self.payment_orders.list_entitlement_incidents(user_ids):
            incident_by_user.setdefault(order.user_id, order)
        return {
            uid: (
                (uid in pending_user_ids) or (uid in incident_by_user),
                incident_by_user.get(uid),
            )
            for uid in user_ids
        }

    def _to_audit_read(self, log: SubscriptionAuditLog) -> SubscriptionAuditLogRead:
        return SubscriptionAuditLogRead(
            id=log.id,
            admin_id=log.admin_id,
            admin_email=log.admin.email if log.admin is not None else None,
            user_id=log.user_id,
            subscription_id=log.subscription_id,
            action=log.action,
            old_plan_id=log.old_plan_id,
            new_plan_id=log.new_plan_id,
            reason=log.reason,
            created_at=log.created_at,
        )
