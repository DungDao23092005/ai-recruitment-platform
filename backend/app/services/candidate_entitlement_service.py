from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConfigurationError, EntityNotFoundException, ValidationError
from app.domain.enums import SubscriptionScope, SubscriptionStatus, UserRole
from app.domain.models.base import utc_now
from app.models import Subscription, User
from app.repositories import RecruitmentPlanRepository, SubscriptionRepository

CANDIDATE_CALENDAR_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


class CandidateEntitlementService:
    """Provision and resolve Candidate Free entitlements.

    The service never commits. It composes inside the caller's transaction so
    registration can persist the candidate and their Free entitlement atomically,
    while lazy provisioning can commit immediately afterwards.

    Idempotency is enforced twice: an explicit lookup before insert, and the
    partial unique index ``uq_subscriptions_candidate_free`` as the final
    concurrency boundary. A losing concurrent insert is contained in a
    savepoint, rolled back, and re-read instead of aborting the caller's
    transaction.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.subscriptions = SubscriptionRepository(session)
        self.plans = RecruitmentPlanRepository(session)

    @staticmethod
    def candidate_period_key(now: datetime) -> str:
        """Return the Asia/Ho_Chi_Minh calendar month key (``YYYY-MM``)."""
        return now.astimezone(CANDIDATE_CALENDAR_TIMEZONE).strftime("%Y-%m")

    async def get_active_free_subscription(
        self,
        user_id,
        now: Optional[datetime] = None,
    ) -> Subscription | None:
        return await self.subscriptions.get_active_candidate_free_by_user_id(
            user_id, now
        )

    async def get_active_paid_subscription(
        self,
        user_id,
        now: Optional[datetime] = None,
    ) -> Subscription | None:
        return await self.subscriptions.get_active_candidate_paid_by_user_id(
            user_id, now
        )

    async def provision_free_entitlement(
        self,
        user_id,
        now: Optional[datetime] = None,
    ) -> Subscription:
        """Ensure the candidate has exactly one active Free entitlement.

        Returns the existing row when present, otherwise creates it from the
        active Candidate Free plan. Raises ``ConfigurationError`` when no such
        plan exists; no fallback plan, price, or quota is invented.
        """
        now = now or utc_now()

        existing = await self.subscriptions.get_active_candidate_free_by_user_id(
            user_id, now
        )
        if existing is not None:
            return existing

        user = await self.session.get(User, user_id)
        if user is None:
            raise EntityNotFoundException(f"User {user_id} not found")
        if user.role != UserRole.CANDIDATE:
            raise ValidationError(
                "Candidate Free entitlement can only be provisioned for "
                "candidate accounts"
            )

        plan = await self.plans.get_active_candidate_free_plan()
        if plan is None:
            raise ConfigurationError(
                "No active Candidate Free Plan configured"
            )

        subscription = Subscription(
            user_id=user_id,
            company_id=None,
            plan_id=plan.id,
            scope=SubscriptionScope.CANDIDATE_PERSONAL,
            is_free=True,
            current_period_key=self.candidate_period_key(now),
            status=SubscriptionStatus.ACTIVE,
            started_at=now,
            expires_at=None,
            max_job_posts=plan.max_job_posts,
            max_candidate_searches=plan.max_candidate_searches or 0,
            max_ai_features=plan.max_ai_features or 0,
            job_posts_used=0,
            candidate_searches_used=0,
            ai_features_used=0,
        )

        savepoint = await self.session.begin_nested()
        try:
            self.session.add(subscription)
            await self.session.flush()
            await savepoint.commit()
        except IntegrityError:
            await savepoint.rollback()
            existing = await self.subscriptions.get_active_candidate_free_by_user_id(
                user_id, now
            )
            if existing is None:
                raise
            return existing

        return subscription
