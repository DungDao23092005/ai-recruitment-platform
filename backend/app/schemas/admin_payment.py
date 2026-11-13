from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.domain.enums import (
    PaymentOrderStatus,
    PaymentProvider,
    PlanAudience,
    SubscriptionScope,
)


class AdminPaymentOrderItem(BaseModel):
    """Admin-facing payment order read model.

    Deliberately excludes provider secrets, signatures and raw callback
    payloads. Only fields needed to reconcile and support an order are exposed.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    user_email: Optional[str] = None
    user_full_name: Optional[str] = None
    company_id: Optional[uuid.UUID] = None
    company_name: Optional[str] = None
    plan_id: uuid.UUID
    plan_name: Optional[str] = None
    plan_audience: Optional[PlanAudience] = None
    subscription_id: Optional[uuid.UUID] = None
    scope: SubscriptionScope
    amount: int
    currency: str
    provider: PaymentProvider
    internal_order_id: str
    status: PaymentOrderStatus
    paid_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    created_at: datetime


class AdminPaymentOrderList(BaseModel):
    items: list[AdminPaymentOrderItem]
    total: int
    skip: int
    limit: int
