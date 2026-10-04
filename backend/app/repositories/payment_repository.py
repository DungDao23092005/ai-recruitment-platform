from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import PaymentOrderStatus, PaymentProvider
from app.models import PaymentOrder, PaymentTransaction
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