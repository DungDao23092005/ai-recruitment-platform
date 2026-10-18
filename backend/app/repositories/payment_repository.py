from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import PaymentOrderStatus, PaymentProvider, SubscriptionStatus
from app.models import PaymentOrder, PaymentTransaction, Subscription
from app.repositories.base import BaseRepository


class PaymentOrderRepository(BaseRepository[PaymentOrder]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PaymentOrder)

    async def get_by_internal_order_id(
        self,
        internal_order_id: str,
    ) -> PaymentOrder | None:
        stmt = select(PaymentOrder).where(
            PaymentOrder.internal_order_id == internal_order_id,
            PaymentOrder.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_and_plan(
        self,
        user_id: Any,
        plan_id: Any,
        provider: PaymentProvider = PaymentProvider.VNPAY,
    ) -> PaymentOrder | None:
        stmt = select(PaymentOrder).where(
            PaymentOrder.user_id == user_id,
            PaymentOrder.plan_id == plan_id,
            PaymentOrder.provider == provider,
            PaymentOrder.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_id(
        self,
        user_id: Any,
    ) -> list[PaymentOrder]:
        stmt = (
            select(PaymentOrder)
            .where(
                PaymentOrder.user_id == user_id,
                PaymentOrder.is_deleted == False,  # noqa: E712
            )
            .order_by(PaymentOrder.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_pending_for_user(
        self,
        user_id: Any,
        now: datetime,
        provider: PaymentProvider = PaymentProvider.VNPAY,
    ) -> list[PaymentOrder]:
        """Unpaid checkout orders that are still valid (PENDING and not expired).

        A previously abandoned/expired PENDING order must never lock a user out
        of checkout forever, so only orders whose ``expired_at`` is present and
        strictly in the future are returned. PAID orders are intentionally
        excluded: a paid order awaiting activation is an entitlement incident,
        not an unpaid checkout.
        """
        stmt = (
            select(PaymentOrder)
            .where(
                PaymentOrder.user_id == user_id,
                PaymentOrder.status == PaymentOrderStatus.PENDING,
                PaymentOrder.provider == provider,
                PaymentOrder.is_deleted == False,  # noqa: E712
                PaymentOrder.expired_at.is_not(None),
                PaymentOrder.expired_at > now,
            )
            .order_by(PaymentOrder.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def has_paid_order_with_pending_subscription(
        self,
        user_id: Any,
    ) -> bool:
        """Whether the user has a PAID order whose bound subscription is PENDING.

        This is the entitlement-incident signal: the money was taken but the
        subscription was never activated. It must not be mistaken for an unpaid
        checkout, so it is surfaced separately and blocks new checkouts.
        """
        stmt = (
            select(func.count())
            .select_from(PaymentOrder)
            .join(Subscription, PaymentOrder.subscription_id == Subscription.id)
            .where(
                PaymentOrder.user_id == user_id,
                PaymentOrder.status == PaymentOrderStatus.PAID,
                PaymentOrder.is_deleted == False,  # noqa: E712
                Subscription.status == SubscriptionStatus.PENDING,
                Subscription.is_deleted == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return bool(result.scalar_one())

    async def list_active_pending_user_ids(
        self,
        user_ids: list[Any],
        now: datetime,
        provider: PaymentProvider = PaymentProvider.VNPAY,
    ) -> set[Any]:
        """Batch: users with at least one live PENDING VNPAY checkout order.

        Uses the exact predicate of ``get_active_pending_for_user`` so the
        admin list flag stays consistent with the guard that raises 409.
        """
        if not user_ids:
            return set()
        stmt = (
            select(PaymentOrder.user_id)
            .where(
                PaymentOrder.user_id.in_(user_ids),
                PaymentOrder.status == PaymentOrderStatus.PENDING,
                PaymentOrder.provider == provider,
                PaymentOrder.is_deleted == False,  # noqa: E712
                PaymentOrder.expired_at.is_not(None),
                PaymentOrder.expired_at > now,
            )
            .distinct()
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

    async def list_entitlement_incidents(
        self,
        user_ids: list[Any],
    ) -> list[PaymentOrder]:
        """Batch: PAID orders bound to still-PENDING subscriptions.

        Mirrors ``has_paid_order_with_pending_subscription`` so incident flags in
        the admin list match the fail-closed guard. Ordered deterministically
        (newest per user first) so a single incident can be summarised while the
        rest stay visible in the detail history.
        """
        if not user_ids:
            return []
        stmt = (
            select(PaymentOrder)
            .join(Subscription, PaymentOrder.subscription_id == Subscription.id)
            .where(
                PaymentOrder.user_id.in_(user_ids),
                PaymentOrder.status == PaymentOrderStatus.PAID,
                PaymentOrder.is_deleted == False,  # noqa: E712
                Subscription.status == SubscriptionStatus.PENDING,
                Subscription.is_deleted == False,  # noqa: E712
            )
            .order_by(
                PaymentOrder.user_id,
                PaymentOrder.created_at.desc(),
                PaymentOrder.id.desc(),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_subscription_ids(
        self,
        subscription_ids: list[Any],
    ) -> list[PaymentOrder]:
        """All non-deleted orders bound to the given subscriptions."""
        if not subscription_ids:
            return []
        stmt = (
            select(PaymentOrder)
            .where(
                PaymentOrder.subscription_id.in_(subscription_ids),
                PaymentOrder.is_deleted == False,  # noqa: E712
            )
            .order_by(PaymentOrder.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_including_deleted(
        self,
        payment_order_id: Any,
    ) -> PaymentOrder | None:
        stmt = select(PaymentOrder).where(PaymentOrder.id == payment_order_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_admin(
        self,
        skip: int,
        limit: int,
        user_id: Optional[Any] = None,
        status_filter: Optional[PaymentOrderStatus] = None,
        provider: Optional[PaymentProvider] = None,
    ) -> tuple[list[PaymentOrder], int]:
        filters = [
            PaymentOrder.is_deleted == False,  # noqa: E712
        ]
        if user_id is not None:
            filters.append(PaymentOrder.user_id == user_id)
        if status_filter is not None:
            filters.append(PaymentOrder.status == status_filter)
        if provider is not None:
            filters.append(PaymentOrder.provider == provider)

        count_stmt = select(func.count()).select_from(PaymentOrder)
        list_stmt = select(PaymentOrder).order_by(PaymentOrder.created_at.desc())

        if filters:
            count_stmt = count_stmt.where(*filters)
            list_stmt = list_stmt.where(*filters)

        total = (await self.session.execute(count_stmt)).scalar_one()
        list_stmt = list_stmt.offset(skip).limit(limit)
        rows = (await self.session.execute(list_stmt)).scalars().all()
        return list(rows), total


class PaymentTransactionRepository(BaseRepository[PaymentTransaction]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PaymentTransaction)

    async def get_by_provider_transaction_id(
        self,
        provider_transaction_id: str,
    ) -> PaymentTransaction | None:
        stmt = select(PaymentTransaction).where(
            PaymentTransaction.provider_transaction_id == provider_transaction_id,
            PaymentTransaction.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_payment_order_id(
        self,
        payment_order_id: Any,
    ) -> list[PaymentTransaction]:
        stmt = (
            select(PaymentTransaction)
            .where(
                PaymentTransaction.payment_order_id == payment_order_id,
                PaymentTransaction.is_deleted == False,  # noqa: E712
            )
            .order_by(PaymentTransaction.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_by_payment_order_id(
        self,
        payment_order_id: Any,
    ) -> PaymentTransaction | None:
        stmt = (
            select(PaymentTransaction)
            .where(
                PaymentTransaction.payment_order_id == payment_order_id,
                PaymentTransaction.is_deleted == False,  # noqa: E712
            )
            .order_by(PaymentTransaction.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def exists_by_provider_transaction_id(
        self,
        provider_transaction_id: str,
    ) -> bool:
        stmt = select(PaymentTransaction.id).where(
            PaymentTransaction.provider_transaction_id == provider_transaction_id,
            PaymentTransaction.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None