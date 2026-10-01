from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin
from app.domain.enums import PaymentOrderStatus, PaymentProvider
from app.models.user import StringEnum

if TYPE_CHECKING:
    from app.models.payment_transaction import PaymentTransaction
    from app.models.recruitment_plan import RecruitmentPlan
    from app.models.subscription import Subscription
    from app.models.user import User


class PaymentOrder(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "payment_orders"
    __table_args__ = (
        Index("ix_payment_orders_provider_order_id_unique", "provider_order_id", unique=True, mssql_where=text("provider_order_id IS NOT NULL")),
        Index("ix_payment_orders_provider_request_id_unique", "provider_request_id", unique=True, mssql_where=text("provider_request_id IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recruitment_plans.id"), nullable=False
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="VND", nullable=False)
    provider: Mapped[PaymentProvider] = mapped_column(
        StringEnum(PaymentProvider),
        default=PaymentProvider.MOMO,
        nullable=False,
    )
    internal_order_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )
    provider_order_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    provider_request_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    status: Mapped[PaymentOrderStatus] = mapped_column(
        StringEnum(PaymentOrderStatus),
        default=PaymentOrderStatus.PENDING,
        nullable=False,
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship()
    plan: Mapped[RecruitmentPlan] = relationship()
    subscription: Mapped[Subscription | None] = relationship(back_populates="payment_orders")
    transactions: Mapped[list[PaymentTransaction]] = relationship(
        back_populates="payment_order",
    )