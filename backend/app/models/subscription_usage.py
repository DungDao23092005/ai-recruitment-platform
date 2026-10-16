from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, TimestampMixin
from app.domain.enums import SubscriptionUsageFeatureType, SubscriptionUsageStatus
from app.models.user import StringEnum

if TYPE_CHECKING:
    from app.models.subscription import Subscription
    from app.models.user import User


class SubscriptionUsage(Base, TimestampMixin):
    __tablename__ = "subscription_usages"
    __table_args__ = (
        Index(
            "ix_subscription_usages_subscription_feature_status",
            "subscription_id",
            "feature_type",
            "status",
        ),
        Index(
            "ix_subscription_usages_user_feature_status",
            "user_id",
            "feature_type",
            "status",
        ),
        Index(
            "ix_subscription_usages_reference",
            "reference_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    feature_type: Mapped[SubscriptionUsageFeatureType] = mapped_column(
        StringEnum(SubscriptionUsageFeatureType), nullable=False
    )
    status: Mapped[SubscriptionUsageStatus] = mapped_column(
        StringEnum(SubscriptionUsageStatus), default=SubscriptionUsageStatus.RESERVED, nullable=False
    )
    reference_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    subscription: Mapped[Subscription] = relationship(back_populates="usages")
    user: Mapped[User] = relationship()