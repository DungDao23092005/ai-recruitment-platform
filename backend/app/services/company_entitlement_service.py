from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import case, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConfigurationError
from app.domain.enums import (
    MembershipRole,
    MembershipStatus,
    SubscriptionScope,
    SubscriptionStatus,
)
from app.domain.models.base import utc_now
from app.models import CompanyMembership, RecruitmentPlan, Subscription
from app.repositories import RecruitmentPlanRepository, SubscriptionRepository

COMPANY_CALENDAR_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


class CompanyEntitlementService:
    """Provision and resolve the canonical Company Free entitlement.

    The service never commits. It composes inside the caller's transaction so
    workspace creation and the initial Company Free subscription are committed
    or rolled back together. Entitlements are always resolved by
    ``company_id``; ``user_id`` is only populated because the current schema
    requires it (the workspace owner is used, never for entitlement lookup).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.subscriptions = SubscriptionRepository(session)
        self.plans = RecruitmentPlanRepository(session)

    @staticmethod
    def company_period_key(now: datetime) -> str:
        """Return the Asia/Ho_Chi_Minh calendar month key (``YYYY-MM``)."""
        return now.astimezone(COMPANY_CALENDAR_TIMEZONE).strftime("%Y-%m")

    async def get_active_company_free_plan(self) -> RecruitmentPlan | None:
        return await self.plans.get_active_company_free_plan()

    async def _resolve_owner_user_id(self, company_id) -> uuid.UUID:
        stmt = (
            select(CompanyMembership)
            .where(
                CompanyMembership.company_id == company_id,
                CompanyMembership.is_deleted == False,  # noqa: E712
                CompanyMembership.status == MembershipStatus.ACTIVE,
            )
            .order_by(
                # ADMIN first, then the earliest joined member as a fallback.
                case(
                    (CompanyMembership.role == MembershipRole.ADMIN, 1),
                    else_=0,
                ).desc(),
                CompanyMembership.joined_at.asc(),
                CompanyMembership.created_at.asc(),
            )
        )
        result = await self.session.execute(stmt)
        membership = result.scalars().first()
        if membership is None:
            raise ConfigurationError(
                "Cannot provision Company Free entitlement: workspace has no "
                "active member to record as the subscription owner."
            )
        return membership.user_id

    async def provision_company_free_subscription(
        self,
        company_id,
        now: Optional[datetime] = None,
    ) -> Subscription:
        """Ensure the company has exactly one active Company subscription.

        If an active Company subscription already exists (Free or Paid), it is
        returned unchanged. Otherwise the canonical active Company Free plan is
        snapshotted into a new ACTIVE subscription with a full current-month
        quota (no proration, no carry-over, ``expires_at = NULL``).

        Raises ``ConfigurationError`` when the canonical Company Free plan is
        missing; no quota is ever invented.
        """
        now = now or utc_now()

        existing = await self.subscriptions.get_active_by_company_id(
            company_id, now
        )
        if existing is not None:
            return existing

        plan = await self.get_active_company_free_plan()
        if plan is None:
            raise ConfigurationError(
                "No active Company Free Plan configured. Provision the "
                "canonical Company Free plan before creating workspaces."
            )

        owner_user_id = await self._resolve_owner_user_id(company_id)

        subscription = Subscription(
            user_id=owner_user_id,
            company_id=company_id,
            plan_id=plan.id,
            scope=SubscriptionScope.COMPANY_RECRUITING,
            is_free=True,
            current_period_key=self.company_period_key(now),
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
            existing = await self.subscriptions.get_active_by_company_id(
                company_id, now
            )
            if existing is None:
                raise
            return existing

        return subscription
