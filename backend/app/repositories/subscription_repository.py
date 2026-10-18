from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import PaymentOrderStatus, PaymentProvider, SubscriptionStatus
from app.models import PaymentOrder, Subscription
from app.repositories.base import BaseRepository


@dataclass(frozen=True)
class AdminSubscriptionRepresentative:
    """One representative subscription per user for the admin list.

    ``total_subscriptions`` and ``active_count`` are computed across ALL of the
    user's non-deleted subscriptions, so multi-subscription and multi-active
    users can be surfaced without loading the whole table into Python.
    """

    subscription: Subscription
    total_subscriptions: int
    active_count: int


class SubscriptionRepository(BaseRepository[Subscription]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Subscription)

    async def get_active_by_user_id(
        self,
        user_id: Any,
        now: Optional[datetime] = None,
    ) -> Subscription | None:
        if now is None:
            from app.domain.models.base import utc_now
            now = utc_now()

        stmt = (
            select(Subscription)
            .options(selectinload(Subscription.plan))
            .where(
                Subscription.user_id == user_id,
                Subscription.is_deleted == False,  # noqa: E712
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at > now,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_and_plan(
        self,
        user_id: Any,
        plan_id: Any,
    ) -> Subscription | None:
        stmt = select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.plan_id == plan_id,
            Subscription.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_id(
        self,
        user_id: Any,
    ) -> list[Subscription]:
        stmt = (
            select(Subscription)
            .options(selectinload(Subscription.plan))
            .where(
                Subscription.user_id == user_id,
                Subscription.is_deleted == False,  # noqa: E712
            )
            .order_by(Subscription.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_including_deleted(self, subscription_id: Any) -> Subscription | None:
        stmt = (
            select(Subscription)
            .options(selectinload(Subscription.plan))
            .where(Subscription.id == subscription_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # --------------------------------------------------- admin list ranking

    def _effective_active_condition(self, now: datetime):
        """``status = ACTIVE`` and not yet expired (``expires_at`` may be null)."""
        return and_(
            Subscription.status == SubscriptionStatus.ACTIVE,
            or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
        )

    def _expired_active_condition(self, now: datetime):
        """``status = ACTIVE`` in the DB but already past ``expires_at``."""
        return and_(
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.expires_at.is_not(None),
            Subscription.expires_at <= now,
        )

    def _rank_tier_expression(self, now: datetime):
        """Ranking priority for picking a user's representative subscription.

        1. effective ACTIVE              -> live entitlement
        2. PENDING + PAID order          -> entitlement incident
        3. PENDING + live VNPAY checkout -> checkout in flight
        4. cancelled / expired / stale ACTIVE -> most recent history
        5. any other PENDING             -> abandoned checkout

        Payment linkage uses correlated ``EXISTS`` so a subscription with many
        orders is never duplicated by a join.
        """
        incident_exists = (
            select(PaymentOrder.id)
            .where(
                PaymentOrder.subscription_id == Subscription.id,
                PaymentOrder.status == PaymentOrderStatus.PAID,
                PaymentOrder.is_deleted == False,  # noqa: E712
            )
            .exists()
        )
        pending_vnpay_exists = (
            select(PaymentOrder.id)
            .where(
                PaymentOrder.subscription_id == Subscription.id,
                PaymentOrder.status == PaymentOrderStatus.PENDING,
                PaymentOrder.provider == PaymentProvider.VNPAY,
                PaymentOrder.is_deleted == False,  # noqa: E712
                PaymentOrder.expired_at.is_not(None),
                PaymentOrder.expired_at > now,
            )
            .exists()
        )
        return case(
            (self._effective_active_condition(now), 1),
            (
                and_(
                    Subscription.status == SubscriptionStatus.PENDING,
                    incident_exists,
                ),
                2,
            ),
            (
                and_(
                    Subscription.status == SubscriptionStatus.PENDING,
                    pending_vnpay_exists,
                ),
                3,
            ),
            (
                or_(
                    Subscription.status == SubscriptionStatus.CANCELLED,
                    Subscription.status == SubscriptionStatus.EXPIRED,
                    self._expired_active_condition(now),
                ),
                4,
            ),
            else_=5,
        )

    def _representative_subquery(self, now: datetime):
        """Subquery selecting exactly one ``rank_num = 1`` row per user.

        Ranking runs over each user's whole subscription set BEFORE search,
        status filter and pagination, so history rows can never displace a live
        subscription as the representative.
        """
        rank_tier = self._rank_tier_expression(now)
        rank_num = func.row_number().over(
            partition_by=Subscription.user_id,
            order_by=(
                rank_tier,
                Subscription.created_at.desc(),
                Subscription.id.desc(),
            ),
        ).label("rank_num")

        ranked = (
            select(
                Subscription.id.label("subscription_id"),
                Subscription.user_id.label("user_id"),
                Subscription.plan_id.label("plan_id"),
                Subscription.status.label("status"),
                Subscription.expires_at.label("expires_at"),
                Subscription.created_at.label("created_at"),
                rank_num,
            )
            .where(Subscription.is_deleted == False)  # noqa: E712
            .subquery()
        )
        return (
            select(
                ranked.c.subscription_id,
                ranked.c.user_id,
                ranked.c.plan_id,
                ranked.c.status,
                ranked.c.expires_at,
                ranked.c.created_at,
            )
            .where(ranked.c.rank_num == 1)
            .subquery()
        )

    @staticmethod
    def _representative_filters(rep, now: datetime, status_filter, plan_id, user_id, search):
        from app.models import User

        filters = []
        if user_id is not None:
            filters.append(rep.c.user_id == user_id)
        if plan_id is not None:
            filters.append(rep.c.plan_id == plan_id)
        if status_filter is not None:
            if status_filter == SubscriptionStatus.ACTIVE:
                filters.append(
                    and_(
                        rep.c.status == SubscriptionStatus.ACTIVE,
                        or_(rep.c.expires_at.is_(None), rep.c.expires_at > now),
                    )
                )
            elif status_filter == SubscriptionStatus.EXPIRED:
                filters.append(
                    or_(
                        rep.c.status == SubscriptionStatus.EXPIRED,
                        and_(
                            rep.c.status == SubscriptionStatus.ACTIVE,
                            rep.c.expires_at.is_not(None),
                            rep.c.expires_at <= now,
                        ),
                    )
                )
            else:
                filters.append(rep.c.status == status_filter)
        if search:
            term = f"%{search.strip()}%"
            filters.append(
                rep.c.user_id.in_(select(User.id).where(User.email.ilike(term)))
            )
        return filters

    async def list_admin(
        self,
        skip: int,
        limit: int,
        user_id: Optional[Any] = None,
        status_filter: Optional[SubscriptionStatus] = None,
        plan_id: Optional[Any] = None,
        search: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> tuple[list[AdminSubscriptionRepresentative], int]:
        """Return one representative subscription per user, ranked and paged.

        Only ``rank_num = 1`` rows are searched, filtered, counted and paged, so
        ``total`` is the number of distinct matching users, not subscriptions.
        """
        if now is None:
            from app.domain.models.base import utc_now

            now = utc_now()

        rep = self._representative_subquery(now)
        filters = self._representative_filters(
            rep, now, status_filter, plan_id, user_id, search
        )

        count_stmt = select(func.count()).select_from(rep)
        list_stmt = select(rep.c.subscription_id, rep.c.user_id).select_from(rep)
        if filters:
            count_stmt = count_stmt.where(*filters)
            list_stmt = list_stmt.where(*filters)

        # Stable ordering: newest representative first, user_id as tie-breaker.
        list_stmt = (
            list_stmt.order_by(rep.c.created_at.desc(), rep.c.user_id.asc())
            .offset(skip)
            .limit(limit)
        )

        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = (await self.session.execute(list_stmt)).all()
        if not rows:
            return [], total

        sub_ids = [row[0] for row in rows]
        user_ids = [row[1] for row in rows]

        subs_result = await self.session.execute(
            select(Subscription)
            .options(selectinload(Subscription.plan), selectinload(Subscription.user))
            .where(Subscription.id.in_(sub_ids))
        )
        subs_by_id = {sub.id: sub for sub in subs_result.scalars().all()}
        diagnostics = await self.count_by_user_ids(user_ids, now)

        representatives: list[AdminSubscriptionRepresentative] = []
        for subscription_id, uid in rows:
            subscription = subs_by_id.get(subscription_id)
            if subscription is None:
                continue
            total_subscriptions, active_count = diagnostics.get(uid, (0, 0))
            representatives.append(
                AdminSubscriptionRepresentative(
                    subscription=subscription,
                    total_subscriptions=total_subscriptions,
                    active_count=active_count,
                )
            )
        return representatives, total

    async def count_by_user_ids(
        self,
        user_ids: list[Any],
        now: Optional[datetime] = None,
    ) -> dict[Any, tuple[int, int]]:
        """Batch ``{user_id: (total_subscriptions, active_count)}`` for users.

        ``active_count`` counts effective ACTIVE subscriptions (live
        entitlement). One grouped query avoids N+1 and never duplicates rows.
        """
        if not user_ids:
            return {}
        if now is None:
            from app.domain.models.base import utc_now

            now = utc_now()

        active_flag = case(
            (self._effective_active_condition(now), 1),
            else_=0,
        )
        stmt = (
            select(
                Subscription.user_id,
                func.count().label("total"),
                func.sum(active_flag).label("active"),
            )
            .where(
                Subscription.is_deleted == False,  # noqa: E712
                Subscription.user_id.in_(user_ids),
            )
            .group_by(Subscription.user_id)
        )
        result = await self.session.execute(stmt)
        return {
            row[0]: (int(row[1]), int(row[2] or 0))
            for row in result.all()
        }

    async def get_representative_for_user(
        self,
        user_id: Any,
        now: Optional[datetime] = None,
    ) -> Subscription | None:
        """Return the same representative row the admin list would show."""
        if now is None:
            from app.domain.models.base import utc_now

            now = utc_now()

        rep = self._representative_subquery(now)
        stmt = select(rep.c.subscription_id).where(rep.c.user_id == user_id)
        subscription_id = (await self.session.execute(stmt)).scalar_one_or_none()
        if subscription_id is None:
            return None
        return await self.get_by_id_including_deleted(subscription_id)

    async def get_pending_by_user_and_plan(
        self,
        user_id: Any,
        plan_id: Any,
    ) -> Subscription | None:
        stmt = select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.plan_id == plan_id,
            Subscription.is_deleted == False,  # noqa: E712
            Subscription.status == SubscriptionStatus.PENDING,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()