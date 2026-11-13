from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    PaymentOrderStatus,
    PaymentProvider,
    SubscriptionScope,
)
from app.models import PaymentOrder
from app.repositories import PaymentOrderRepository
from app.schemas.admin_payment import AdminPaymentOrderItem


class AdminPaymentOrderService:
    """Read-only, admin-facing payment order listing."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.payment_orders = PaymentOrderRepository(session)

    async def list_payment_orders(
        self,
        *,
        skip: int,
        limit: int,
        status_filter: Optional[PaymentOrderStatus] = None,
        scope_filter: Optional[SubscriptionScope] = None,
        provider: Optional[PaymentProvider] = None,
        search: Optional[str] = None,
    ) -> tuple[list[AdminPaymentOrderItem], int]:
        orders, total = await self.payment_orders.list_admin(
            skip=skip,
            limit=limit,
            status_filter=status_filter,
            provider=provider,
            scope_filter=scope_filter,
            search=search,
        )
        return [self._to_item(order) for order in orders], total

    @staticmethod
    def _to_item(order: PaymentOrder) -> AdminPaymentOrderItem:
        user = getattr(order, "user", None)
        company = getattr(order, "company", None)
        plan = getattr(order, "plan", None)

        user_full_name: Optional[str] = None
        if user is not None:
            candidate_profile = getattr(user, "candidate_profile", None)
            recruiter_profile = getattr(user, "recruiter_profile", None)
            user_full_name = (
                getattr(candidate_profile, "full_name", None)
                or getattr(recruiter_profile, "full_name", None)
            )

        return AdminPaymentOrderItem(
            id=order.id,
            user_id=order.user_id,
            user_email=user.email if user is not None else None,
            user_full_name=user_full_name,
            company_id=order.company_id,
            company_name=company.name if company is not None else None,
            plan_id=order.plan_id,
            plan_name=plan.name if plan is not None else None,
            plan_audience=plan.plan_audience if plan is not None else None,
            subscription_id=order.subscription_id,
            scope=order.scope,
            amount=order.amount,
            currency=order.currency,
            provider=order.provider,
            internal_order_id=order.internal_order_id,
            status=order.status,
            paid_at=order.paid_at,
            expired_at=order.expired_at,
            created_at=order.created_at,
        )
