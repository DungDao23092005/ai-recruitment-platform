from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.domain.enums import (
    PaymentOrderStatus,
    PaymentProvider,
    SubscriptionScope,
)
from app.models import User
from app.schemas.admin_payment import AdminPaymentOrderList
from app.services.admin_payment_service import AdminPaymentOrderService

router = APIRouter(
    prefix="/admin/payment-orders",
    tags=["Admin - Payment Orders"],
    dependencies=[Depends(require_admin)],
)


def _get_service(db: AsyncSession = Depends(get_db)) -> AdminPaymentOrderService:
    return AdminPaymentOrderService(db)


@router.get("", response_model=AdminPaymentOrderList)
async def list_admin_payment_orders(
    current_user: User = Depends(require_admin),
    service: AdminPaymentOrderService = Depends(_get_service),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    status: Optional[PaymentOrderStatus] = Query(default=None),
    scope: Optional[SubscriptionScope] = Query(default=None),
    provider: Optional[PaymentProvider] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=255),
) -> AdminPaymentOrderList:
    """List payment orders for reconciliation and support (admin only)."""
    items, total = await service.list_payment_orders(
        skip=skip,
        limit=limit,
        status_filter=status,
        scope_filter=scope,
        provider=provider,
        search=search,
    )
    return AdminPaymentOrderList(items=items, total=total, skip=skip, limit=limit)
