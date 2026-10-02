from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    InvalidTransitionException,
    ValidationError,
)
from app.domain.enums import SubscriptionStatus
from app.domain.models.base import utc_now
from app.models import RecruitmentPlan, Subscription, User
from app.repositories import RecruitmentPlanRepository, SubscriptionRepository
from app.schemas.subscription import SubscriptionCreate


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.subscriptions = SubscriptionRepository(session)
        self.plans = RecruitmentPlanRepository(session)

    async def get_current_active_subscription(
        self,
        user_id: uuid.UUID,
        now: Optional[datetime] = None,
    ) -> Optional[Subscription]:
        if now is None:
            now = utc_now()
        return await self.subscriptions.get_active_by_user_id(user_id, now)

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
    ) -> Optional[Subscription]:
        """Check for existing valid active subscription for the user."""
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
        existing_active = await self._check_active_overlap(user_id, now)
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

        now = utc_now()

        # Check for existing active subscription BEFORE activating
        existing_active = await self._check_active_overlap(sub.user_id, now)
        if existing_active is not None and existing_active.id != sub.id:
            raise ConflictException(
                f"User already has an active subscription (id: {existing_active.id})"
            )

        plan = await self.plans.get_active_by_id(sub.plan_id)
        if plan is None:
            raise EntityNotFoundException(f"Plan {sub.plan_id} not found or inactive")

        sub.status = SubscriptionStatus.ACTIVE
        sub.started_at = now
        sub.expires_at = now + timedelta(days=plan.duration_days)

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
    ) -> int:
        """Check for expired subscriptions and update their status.
        This is a lazy expiration check - subscriptions are treated as expired
        when expires_at <= now, but this method can be called periodically
        to update the status in the database.
        """
        if now is None:
            now = utc_now()

        stmt = select(Subscription).where(
            Subscription.is_deleted == False,  # noqa: E712
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.expires_at <= now,
        )
        result = await self.session.execute(stmt)
        expired_subs = list(result.scalars().all())

        count = 0
        for sub in expired_subs:
            sub.status = SubscriptionStatus.EXPIRED
            count += 1

        if count > 0:
            try:
                await self.session.commit()
            except Exception:
                await self.session.rollback()
                raise

        return count