from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, TimestampMixin
from app.domain.enums import (
    SubscriptionScope,
    SubscriptionUsageFeatureType,
    SubscriptionUsageStatus,
)
from app.models.user import StringEnum

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.subscription import Subscription
    from app.models.user import User


class SubscriptionUsage(Base, TimestampMixin):
    __tablename__ = "subscription_usages"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('company_recruiting', 'candidate_personal', 'legacy_recruiter_personal')",
            name="ck_subscription_usages_scope_valid",
        ),
        CheckConstraint(
            "(scope = 'company_recruiting' AND company_id IS NOT NULL) OR "
            "(scope IN ('candidate_personal', 'legacy_recruiter_personal') AND company_id IS NULL)",
            name="ck_subscription_usages_scope_company_pairing",
        ),
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
        Index(
            "ix_subscription_usages_company_period",
            "company_id",
            "period_key",
            "feature_type",
            "status",
            mssql_where=text("company_id IS NOT NULL"),
        ),
        Index(
            "ix_subscription_usages_user_period",
            "user_id",
            "period_key",
            "feature_type",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", name="fk_subscription_usages_company_id_companies"),
        nullable=True,
    )
    scope: Mapped[SubscriptionScope] = mapped_column(
        StringEnum(SubscriptionScope),
        default=SubscriptionScope.LEGACY_RECRUITER_PERSONAL,
        server_default="legacy_recruiter_personal",
        nullable=False,
    )
    period_key: Mapped[str | None] = mapped_column(
        String(7), nullable=True
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
    company: Mapped[Company | None] = relationship(back_populates="subscription_usages")