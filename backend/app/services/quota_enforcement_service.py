from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException, ForbiddenException
from app.domain.enums import SubscriptionStatus, SubscriptionUsageFeatureType, SubscriptionUsageStatus
from app.domain.models.base import utc_now
from app.models import Subscription, SubscriptionUsage
from app.repositories import SubscriptionRepository


@dataclass
class QuotaCheckResult:
    allowed: bool
    remaining: int
    limit: int
    used: int
    message: str | None = None


@dataclass
class ReservationResult:
    usage_id: uuid.UUID | None
    remaining: int
    limit: int
    used: int
    bypassed: bool = False


class QuotaEnforcementService:
    """
    Central service for subscription quota enforcement.

    Handles:
    - Job post quota: atomic check-and-consume within transaction
    - Candidate search / AI feature quota: reserve -> execute -> finalize pattern
    - Idempotency for search/AI operations
    - Admin bypass
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.subscriptions = SubscriptionRepository(session)

    async def get_active_subscription_or_raise(
        self,
        user_id: uuid.UUID,
        require_quota: bool = True,
    ) -> Subscription:
        """Get active subscription or raise ForbiddenException with Vietnamese message."""
        now = utc_now()
        subscription = await self.subscriptions.get_active_by_user_id(user_id, now)

        if subscription is None:
            raise ForbiddenException(
                "Bạn chưa có gói đăng ký hợp lệ. Vui lòng đăng ký gói tuyển dụng để sử dụng tính năng này."
            )

        if require_quota and not self._has_any_quota(subscription):
            raise ForbiddenException(
                "Gói đăng ký của bạn không bao gồm quyền sử dụng tính năng này. Vui lòng liên hệ quản trị viên để nâng cấp gói."
            )

        return subscription

    def _has_any_quota(self, subscription: Subscription) -> bool:
        return (
            subscription.max_job_posts > 0
            or subscription.max_candidate_searches > 0
            or subscription.max_ai_features > 0
        )

    def _get_quota_info(
        self,
        subscription: Subscription,
        feature_type: SubscriptionUsageFeatureType,
    ) -> tuple[int, int, int]:
        """Return (limit, used, remaining) for a feature type."""
        if feature_type == SubscriptionUsageFeatureType.JOB_POST:
            limit = subscription.max_job_posts
            used = subscription.job_posts_used
        elif feature_type == SubscriptionUsageFeatureType.CANDIDATE_SEARCH:
            limit = subscription.max_candidate_searches
            used = subscription.candidate_searches_used
        elif feature_type == SubscriptionUsageFeatureType.AI_FEATURE:
            limit = subscription.max_ai_features
            used = subscription.ai_features_used
        else:
            raise ValueError(f"Unknown feature type: {feature_type}")

        remaining = max(0, limit - used)
        return limit, used, remaining

    def _get_counter_column(self, feature_type: SubscriptionUsageFeatureType) -> str:
        if feature_type == SubscriptionUsageFeatureType.JOB_POST:
            return "job_posts_used"
        elif feature_type == SubscriptionUsageFeatureType.CANDIDATE_SEARCH:
            return "candidate_searches_used"
        elif feature_type == SubscriptionUsageFeatureType.AI_FEATURE:
            return "ai_features_used"
        raise ValueError(f"Unknown feature type: {feature_type}")

    def _get_max_column(self, feature_type: SubscriptionUsageFeatureType) -> str:
        if feature_type == SubscriptionUsageFeatureType.JOB_POST:
            return "max_job_posts"
        elif feature_type == SubscriptionUsageFeatureType.CANDIDATE_SEARCH:
            return "max_candidate_searches"
        elif feature_type == SubscriptionUsageFeatureType.AI_FEATURE:
            return "max_ai_features"
        raise ValueError(f"Unknown feature type: {feature_type}")

    async def check_job_post_quota(self, user_id: uuid.UUID) -> QuotaCheckResult:
        """Check if user can publish a job (for preflight UI). Does not consume quota."""
        subscription = await self.get_active_subscription_or_raise(user_id)
        limit, used, remaining = self._get_quota_info(
            subscription, SubscriptionUsageFeatureType.JOB_POST
        )

        if limit == 0:
            return QuotaCheckResult(
                allowed=False,
                remaining=0,
                limit=limit,
                used=used,
                message="Gói đăng ký của bạn không bao gồm quyền đăng tin tuyển dụng.",
            )

        if remaining <= 0:
            return QuotaCheckResult(
                allowed=False,
                remaining=0,
                limit=limit,
                used=used,
                message=f"Đã hết lượt đăng tin (đã dùng {used}/{limit}). Vui lòng nâng cấp gói hoặc chờ gia hạn.",
            )

        return QuotaCheckResult(
            allowed=True,
            remaining=remaining,
            limit=limit,
            used=used,
        )

    async def check_search_quota(self, user_id: uuid.UUID) -> QuotaCheckResult:
        """Check if user can perform candidate search (for preflight UI). Does not consume quota."""
        subscription = await self.get_active_subscription_or_raise(user_id)
        limit, used, remaining = self._get_quota_info(
            subscription, SubscriptionUsageFeatureType.CANDIDATE_SEARCH
        )

        if limit == 0:
            return QuotaCheckResult(
                allowed=False,
                remaining=0,
                limit=limit,
                used=used,
                message="Gói đăng ký của bạn không bao gồm quyền tìm kiếm ứng viên.",
            )

        if remaining <= 0:
            return QuotaCheckResult(
                allowed=False,
                remaining=0,
                limit=limit,
                used=used,
                message=f"Đã hết lượt tìm kiếm ứng viên (đã dùng {used}/{limit}). Vui lòng nâng cấp gói hoặc chờ gia hạn.",
            )

        return QuotaCheckResult(
            allowed=True,
            remaining=remaining,
            limit=limit,
            used=used,
        )

    async def check_ai_quota(self, user_id: uuid.UUID) -> QuotaCheckResult:
        """Check if user can use AI features (for preflight UI). Does not consume quota."""
        subscription = await self.get_active_subscription_or_raise(user_id)
        limit, used, remaining = self._get_quota_info(
            subscription, SubscriptionUsageFeatureType.AI_FEATURE
        )

        if limit == 0:
            return QuotaCheckResult(
                allowed=False,
                remaining=0,
                limit=limit,
                used=used,
                message="Gói đăng ký của bạn không bao gồm quyền sử dụng tính năng AI.",
            )

        if remaining <= 0:
            return QuotaCheckResult(
                allowed=False,
                remaining=0,
                limit=limit,
                used=used,
                message=f"Đã hết lượt sử dụng AI (đã dùng {used}/{limit}). Vui lòng nâng cấp gói hoặc chờ gia hạn.",
            )

        return QuotaCheckResult(
            allowed=True,
            remaining=remaining,
            limit=limit,
            used=used,
        )

    async def consume_job_post_quota(
        self,
        user_id: uuid.UUID,
        job_id: uuid.UUID,
        is_admin: bool = False,
    ) -> QuotaCheckResult:
        """
        Atomically consume one job post quota.
        Must be called within the same transaction as job creation/publication.
        """
        if is_admin:
            return QuotaCheckResult(allowed=True, remaining=-1, limit=-1, used=-1)

        subscription = await self.get_active_subscription_or_raise(user_id)
        limit, used, remaining = self._get_quota_info(
            subscription, SubscriptionUsageFeatureType.JOB_POST
        )

        if limit == 0:
            raise ForbiddenException(
                "Gói đăng ký của bạn không bao gồm quyền đăng tin tuyển dụng."
            )

        if remaining <= 0:
            raise ForbiddenException(
                f"Đã hết lượt đăng tin (đã dùng {used}/{limit}). Vui lòng nâng cấp gói hoặc chờ gia hạn."
            )

        # Atomic increment with check
        counter_col = self._get_counter_column(SubscriptionUsageFeatureType.JOB_POST)
        max_col = self._get_max_column(SubscriptionUsageFeatureType.JOB_POST)

        stmt = (
            update(Subscription)
            .where(
                Subscription.id == subscription.id,
                getattr(Subscription, counter_col) < getattr(Subscription, max_col),
            )
            .values({counter_col: getattr(Subscription, counter_col) + 1})
        )
        result = await self.session.execute(stmt)

        if result.rowcount == 0:
            # Race condition: quota exhausted between check and update
            raise ForbiddenException(
                f"Đã hết lượt đăng tin (đã dùng {used}/{limit}). Vui lòng nâng cấp gói hoặc chờ gia hạn."
            )

        # Create usage ledger entry (completed immediately for job posts)
        usage = SubscriptionUsage(
            subscription_id=subscription.id,
            user_id=user_id,
            feature_type=SubscriptionUsageFeatureType.JOB_POST,
            status=SubscriptionUsageStatus.COMPLETED,
            reference_id=job_id,
            amount=1,
            finalized_at=utc_now(),
        )
        self.session.add(usage)

        return QuotaCheckResult(
            allowed=True,
            remaining=remaining - 1,
            limit=limit,
            used=used + 1,
        )

    async def _get_completed_job_post_usage(
        self,
        subscription_id: uuid.UUID,
        job_id: uuid.UUID,
        idempotency_key: str,
    ) -> SubscriptionUsage | None:
        """Return a COMPLETED job-post usage record for this job under the subscription, if any."""
        stmt = select(SubscriptionUsage).where(
            SubscriptionUsage.subscription_id == subscription_id,
            SubscriptionUsage.feature_type == SubscriptionUsageFeatureType.JOB_POST,
            SubscriptionUsage.status == SubscriptionUsageStatus.COMPLETED,
            SubscriptionUsage.idempotency_key == idempotency_key,
            SubscriptionUsage.reference_id == job_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def consume_job_post_quota_idempotent(
        self,
        user_id: uuid.UUID,
        job_id: uuid.UUID,
        is_admin: bool = False,
    ) -> QuotaCheckResult:
        """
        Consume one job-post quota, idempotent by (subscription, job).

        Uses a deterministic idempotency key ``job_post_{job_id}`` scoped to the
        current subscription. Concurrency is serialized with a SQL Server
        ``SELECT ... WITH (UPDLOCK, HOLDLOCK)`` range lock on the idempotency
        key: the lock is taken before any existence check and held until the
        caller's transaction commits, so two concurrent transactions cannot both
        observe "no row" and both insert. The loser blocks on the lock, then
        observes the winner's committed row and returns an idempotent allowed
        result without double-charging.

        The database uniqueness scope is ``(subscription_id, feature_type,
        idempotency_key)`` via the existing filtered unique index
        ``uq_subscription_usage_idempotency``, so:
        - the same job under the same subscription consumes at most one unit;
        - the same job under a different subscription consumes that
          subscription's quota once;
        - other feature types and unrelated job IDs are unaffected.
        No savepoint is used (aioodbc / SQL Server does not roll back counter
        increments reliably on savepoint failure).
        """
        if is_admin:
            return QuotaCheckResult(allowed=True, remaining=-1, limit=-1, used=-1)

        subscription = await self.get_active_subscription_or_raise(user_id)
        limit, used, remaining = self._get_quota_info(
            subscription, SubscriptionUsageFeatureType.JOB_POST
        )

        if limit == 0:
            raise ForbiddenException(
                "Gói đăng ký của bạn không bao gồm quyền đăng tin tuyển dụng."
            )
        if remaining <= 0:
            raise ForbiddenException(
                f"Đã hết lượt đăng tin (đã dùng {used}/{limit}). Vui lòng nâng cấp gói hoặc chờ gia hạn."
            )

        idempotency_key = f"job_post_{job_id}"

        # Serialize claiming of this idempotency key with SQL Server range locks.
        # UPDLOCK takes update locks on matched rows/ranges; HOLDLOCK holds them
        # until transaction commit (SERIALIZABLE semantics for this table
        # access), preventing the phantom/duplicate-key race under READ COMMITTED.
        lock_sql = text(
            """
            SELECT id FROM subscription_usages WITH (UPDLOCK, HOLDLOCK)
            WHERE subscription_id = :subscription_id
              AND feature_type = :feature_type
              AND idempotency_key = :idempotency_key
            """
        )
        await self.session.execute(
            lock_sql,
            {
                "subscription_id": subscription.id,
                "feature_type": SubscriptionUsageFeatureType.JOB_POST.value,
                "idempotency_key": idempotency_key,
            },
        )

        # Within the same transaction, the range lock serializes us against other
        # claimants of the same key. Check whether this job was already consumed.
        existing = await self._get_completed_job_post_usage(
            subscription.id, job_id, idempotency_key
        )
        if existing is not None:
            # Re-fetch the subscription so counter values reflect the winner's
            # committed increment rather than our stale snapshot.
            subscription = await self.get_active_subscription_or_raise(user_id)
            limit_w, used_w, remaining_w = self._get_quota_info(
                subscription, SubscriptionUsageFeatureType.JOB_POST
            )
            return QuotaCheckResult(
                allowed=True,
                remaining=remaining_w,
                limit=limit_w,
                used=used_w,
            )

        # Claim the usage row while holding the range lock.
        now = utc_now()
        insert_sql = text(
            """
            INSERT INTO subscription_usages
                (id, subscription_id, user_id, feature_type, status,
                 reference_id, idempotency_key, amount, finalized_at,
                 created_at, updated_at)
            VALUES (:id, :subscription_id, :user_id, :feature_type, :status,
                    :reference_id, :idempotency_key, :amount, :finalized_at,
                    :created_at, :updated_at)
            """
        )
        await self.session.execute(
            insert_sql,
            {
                "id": uuid.uuid4(),
                "subscription_id": subscription.id,
                "user_id": user_id,
                "feature_type": SubscriptionUsageFeatureType.JOB_POST.value,
                "status": SubscriptionUsageStatus.COMPLETED.value,
                "reference_id": job_id,
                "idempotency_key": idempotency_key,
                "amount": 1,
                "finalized_at": now,
                "created_at": now,
                "updated_at": now,
            },
        )

        # Increment the counter atomically.
        counter_col = self._get_counter_column(SubscriptionUsageFeatureType.JOB_POST)
        max_col = self._get_max_column(SubscriptionUsageFeatureType.JOB_POST)
        stmt = (
            update(Subscription)
            .where(
                Subscription.id == subscription.id,
                getattr(Subscription, counter_col)
                < getattr(Subscription, max_col),
            )
            .values({counter_col: getattr(Subscription, counter_col) + 1})
        )
        increment_result = await self.session.execute(stmt)
        if increment_result.rowcount == 0:
            # Quota exhausted between claim and increment: remove our claimed
            # row so the ledger stays consistent with the counter.
            await self.session.execute(
                delete(SubscriptionUsage).where(
                    SubscriptionUsage.subscription_id == subscription.id,
                    SubscriptionUsage.idempotency_key == idempotency_key,
                )
            )
            raise ForbiddenException(
                f"Đã hết lượt đăng tin (đã dùng {used}/{limit}). Vui lòng nâng cấp gói hoặc chờ gia hạn."
            )

        return QuotaCheckResult(
            allowed=True,
            remaining=remaining - 1,
            limit=limit,
            used=used + 1,
        )

    async def reserve_search_quota(
        self,
        user_id: uuid.UUID,
        idempotency_key: str | None,
        reference_id: uuid.UUID | None = None,
        is_admin: bool = False,
    ) -> ReservationResult:
        """
        Reserve one candidate search quota.
        Returns reservation ID for later finalize/release.
        If is_admin=True, bypasses quota check and returns a bypassed result.
        """
        if is_admin:
            return ReservationResult(
                usage_id=None,
                remaining=-1,
                limit=-1,
                used=-1,
                bypassed=True,
            )

        subscription = await self.get_active_subscription_or_raise(user_id)
        limit, used, remaining = self._get_quota_info(
            subscription, SubscriptionUsageFeatureType.CANDIDATE_SEARCH
        )

        if limit == 0:
            raise ForbiddenException(
                "Gói đăng ký của bạn không bao gồm quyền tìm kiếm ứng viên."
            )

        if remaining <= 0:
            raise ForbiddenException(
                f"Đã hết lượt tìm kiếm ứng viên (đã dùng {used}/{limit}). Vui lòng nâng cấp gói hoặc chờ gia hạn."
            )

        # Check idempotency
        if idempotency_key:
            existing = await self._get_usage_by_idempotency(
                subscription.id,
                SubscriptionUsageFeatureType.CANDIDATE_SEARCH,
                idempotency_key,
            )
            if existing:
                if existing.status == SubscriptionUsageStatus.COMPLETED:
                    # Already completed, return current state
                    return ReservationResult(
                        usage_id=existing.id,
                        remaining=max(0, limit - subscription.candidate_searches_used),
                        limit=limit,
                        used=subscription.candidate_searches_used,
                    )
                elif existing.status == SubscriptionUsageStatus.RESERVED:
                    # Reserved but not finalized, return existing reservation
                    return ReservationResult(
                        usage_id=existing.id,
                        remaining=remaining,
                        limit=limit,
                        used=used,
                    )
                elif existing.status == SubscriptionUsageStatus.FAILED:
                    # Previous attempt failed, allow new reservation
                    pass

        # Atomic increment with check
        counter_col = self._get_counter_column(SubscriptionUsageFeatureType.CANDIDATE_SEARCH)
        max_col = self._get_max_column(SubscriptionUsageFeatureType.CANDIDATE_SEARCH)

        stmt = (
            update(Subscription)
            .where(
                Subscription.id == subscription.id,
                getattr(Subscription, counter_col) < getattr(Subscription, max_col),
            )
            .values({counter_col: getattr(Subscription, counter_col) + 1})
        )
        result = await self.session.execute(stmt)

        if result.rowcount == 0:
            raise ForbiddenException(
                f"Đã hết lượt tìm kiếm ứng viên (đã dùng {used}/{limit}). Vui lòng nâng cấp gói hoặc chờ gia hạn."
            )

        # Create reservation ledger entry
        usage = SubscriptionUsage(
            subscription_id=subscription.id,
            user_id=user_id,
            feature_type=SubscriptionUsageFeatureType.CANDIDATE_SEARCH,
            status=SubscriptionUsageStatus.RESERVED,
            reference_id=reference_id,
            idempotency_key=idempotency_key,
            amount=1,
        )
        self.session.add(usage)
        await self.session.flush()

        return ReservationResult(
            usage_id=usage.id,
            remaining=remaining - 1,
            limit=limit,
            used=used + 1,
        )

    async def reserve_ai_quota(
        self,
        user_id: uuid.UUID,
        idempotency_key: str | None,
        reference_id: uuid.UUID | None = None,
        is_admin: bool = False,
    ) -> ReservationResult:
        """
        Reserve one AI feature quota.
        Returns reservation ID for later finalize/release.
        If is_admin=True, bypasses quota check and returns a bypassed result.
        """
        if is_admin:
            return ReservationResult(
                usage_id=None,
                remaining=-1,
                limit=-1,
                used=-1,
                bypassed=True,
            )

        subscription = await self.get_active_subscription_or_raise(user_id)
        limit, used, remaining = self._get_quota_info(
            subscription, SubscriptionUsageFeatureType.AI_FEATURE
        )

        if limit == 0:
            raise ForbiddenException(
                "Gói đăng ký của bạn không bao gồm quyền sử dụng tính năng AI."
            )

        if remaining <= 0:
            raise ForbiddenException(
                f"Đã hết lượt sử dụng AI (đã dùng {used}/{limit}). Vui lòng nâng cấp gói hoặc chờ gia hạn."
            )

        # Check idempotency
        if idempotency_key:
            existing = await self._get_usage_by_idempotency(
                subscription.id,
                SubscriptionUsageFeatureType.AI_FEATURE,
                idempotency_key,
            )
            if existing:
                if existing.status == SubscriptionUsageStatus.COMPLETED:
                    return ReservationResult(
                        usage_id=existing.id,
                        remaining=max(0, limit - subscription.ai_features_used),
                        limit=limit,
                        used=subscription.ai_features_used,
                    )
                elif existing.status == SubscriptionUsageStatus.RESERVED:
                    return ReservationResult(
                        usage_id=existing.id,
                        remaining=remaining,
                        limit=limit,
                        used=used,
                    )
                elif existing.status == SubscriptionUsageStatus.FAILED:
                    pass

        # Atomic increment with check
        counter_col = self._get_counter_column(SubscriptionUsageFeatureType.AI_FEATURE)
        max_col = self._get_max_column(SubscriptionUsageFeatureType.AI_FEATURE)

        stmt = (
            update(Subscription)
            .where(
                Subscription.id == subscription.id,
                getattr(Subscription, counter_col) < getattr(Subscription, max_col),
            )
            .values({counter_col: getattr(Subscription, counter_col) + 1})
        )
        result = await self.session.execute(stmt)

        if result.rowcount == 0:
            raise ForbiddenException(
                f"Đã hết lượt sử dụng AI (đã dùng {used}/{limit}). Vui lòng nâng cấp gói hoặc chờ gia hạn."
            )

        # Create reservation ledger entry
        usage = SubscriptionUsage(
            subscription_id=subscription.id,
            user_id=user_id,
            feature_type=SubscriptionUsageFeatureType.AI_FEATURE,
            status=SubscriptionUsageStatus.RESERVED,
            reference_id=reference_id,
            idempotency_key=idempotency_key,
            amount=1,
        )
        self.session.add(usage)
        await self.session.flush()

        return ReservationResult(
            usage_id=usage.id,
            remaining=remaining - 1,
            limit=limit,
            used=used + 1,
        )

    async def finalize_reservation(
        self,
        usage_id: uuid.UUID | None,
        success: bool = True,
    ) -> None:
        """Finalize a reservation as completed or failed."""
        if usage_id is None:
            # Bypassed reservation - nothing to do
            return

        usage = await self.session.get(SubscriptionUsage, usage_id)
        if usage is None:
            # Log warning but don't raise - idempotent finalize
            return

        if usage.status != SubscriptionUsageStatus.RESERVED:
            # Already finalized, idempotent
            return

        if success:
            usage.status = SubscriptionUsageStatus.COMPLETED
            usage.finalized_at = utc_now()
        else:
            usage.status = SubscriptionUsageStatus.FAILED
            usage.finalized_at = utc_now()
            # Release the counter
            await self._release_counter(usage)

    async def release_reservation(self, usage_id: uuid.UUID | None) -> None:
        """Release a reservation (mark as failed and decrement counter)."""
        if usage_id is None:
            # Bypassed reservation - nothing to do
            return

        usage = await self.session.get(SubscriptionUsage, usage_id)
        if usage is None:
            return

        if usage.status != SubscriptionUsageStatus.RESERVED:
            return

        usage.status = SubscriptionUsageStatus.FAILED
        usage.finalized_at = utc_now()
        await self._release_counter(usage)

    async def reconcile_stale_reservations(
        self,
        max_age_minutes: int = 60,
        limit: int = 100,
    ) -> int:
        """Reconcile RESERVED reservations older than ``max_age_minutes``.

        Marks them FAILED and releases their counters. Idempotent: only
        ``RESERVED`` rows are touched, so COMPLETED reservations are never
        refunded and already-finalized rows are skipped. Bounded by ``limit``.
        Does not hold a transaction open while waiting on external providers.
        """
        cutoff = utc_now() - timedelta(minutes=max_age_minutes)
        stmt = (
            select(SubscriptionUsage)
            .where(
                SubscriptionUsage.status == SubscriptionUsageStatus.RESERVED,
                SubscriptionUsage.created_at < cutoff,
            )
            .order_by(SubscriptionUsage.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        stale = result.scalars().all()

        reconciled = 0
        for usage in stale:
            usage.status = SubscriptionUsageStatus.FAILED
            usage.finalized_at = utc_now()
            await self._release_counter(usage)
            reconciled += 1
        return reconciled

    async def _release_counter(self, usage: SubscriptionUsage) -> None:
        """Atomically decrement the usage counter."""
        counter_col = self._get_counter_column(usage.feature_type)
        stmt = (
            update(Subscription)
            .where(
                Subscription.id == usage.subscription_id,
                getattr(Subscription, counter_col) > 0,
            )
            .values({counter_col: getattr(Subscription, counter_col) - 1})
        )
        await self.session.execute(stmt)

    async def _get_usage_by_idempotency(
        self,
        subscription_id: uuid.UUID,
        feature_type: SubscriptionUsageFeatureType,
        idempotency_key: str,
    ) -> SubscriptionUsage | None:
        stmt = select(SubscriptionUsage).where(
            SubscriptionUsage.subscription_id == subscription_id,
            SubscriptionUsage.feature_type == feature_type,
            SubscriptionUsage.idempotency_key == idempotency_key,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_usage_summary(self, user_id: uuid.UUID) -> dict:
        """Get usage summary for all features for the user's active subscription."""
        subscription = await self.subscriptions.get_active_by_user_id(user_id, utc_now())
        if subscription is None:
            return {
                "has_subscription": False,
                "job_posts": {"limit": 0, "used": 0, "remaining": 0},
                "candidate_searches": {"limit": 0, "used": 0, "remaining": 0},
                "ai_features": {"limit": 0, "used": 0, "remaining": 0},
            }

        job_limit, job_used, job_remaining = self._get_quota_info(
            subscription, SubscriptionUsageFeatureType.JOB_POST
        )
        search_limit, search_used, search_remaining = self._get_quota_info(
            subscription, SubscriptionUsageFeatureType.CANDIDATE_SEARCH
        )
        ai_limit, ai_used, ai_remaining = self._get_quota_info(
            subscription, SubscriptionUsageFeatureType.AI_FEATURE
        )

        return {
            "has_subscription": True,
            "subscription_id": str(subscription.id),
            "job_posts": {"limit": job_limit, "used": job_used, "remaining": job_remaining},
            "candidate_searches": {"limit": search_limit, "used": search_used, "remaining": search_remaining},
            "ai_features": {"limit": ai_limit, "used": ai_used, "remaining": ai_remaining},
        }