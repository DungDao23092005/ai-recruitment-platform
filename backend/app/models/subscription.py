from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin
from app.domain.enums import SubscriptionStatus
from app.models.user import StringEnum

if TYPE_CHECKING:
    from app.models.payment_order import PaymentOrder
    from app.models.recruitment_plan import RecruitmentPlan
    from app.models.user import User


class Subscription(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recruitment_plans.id"), nullable=False
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        StringEnum(SubscriptionStatus),
        default=SubscriptionStatus.PENDING,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="subscriptions")
    plan: Mapped[RecruitmentPlan] = relationship(back_populates="subscriptions")
    payment_orders: Mapped[list[PaymentOrder]] = relationship(
        back_populates="subscription",
    )