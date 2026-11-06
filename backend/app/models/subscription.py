from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin
from app.domain.enums import SubscriptionScope, SubscriptionStatus
from app.models.user import StringEnum

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.payment_order import PaymentOrder
    from app.models.recruitment_plan import RecruitmentPlan
    from app.models.subscription_usage import SubscriptionUsage
    from app.models.user import User


class Subscription(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('company_recruiting', 'candidate_personal', 'legacy_recruiter_personal')",
            name="ck_subscriptions_scope_valid",
        ),
        CheckConstraint(
            "(scope = 'company_recruiting' AND company_id IS NOT NULL) OR "
            "(scope IN ('candidate_personal', 'legacy_recruiter_personal') AND company_id IS NULL)",
            name="ck_subscriptions_scope_company_pairing",
        ),
        CheckConstraint(
            "is_free = 0 OR scope = 'candidate_personal'",
            name="ck_subscriptions_free_candidate",
        ),
        Index(
            "uq_subscriptions_active_company",
            "company_id",
            unique=True,
            mssql_where=text(
                "status = 'active' AND is_deleted = 0 AND scope = 'company_recruiting'"
            ),
        ),
        Index(
            "uq_subscriptions_candidate_paid",
            "user_id",
            unique=True,
            mssql_where=text(
                "status = 'active' AND is_deleted = 0 AND scope = 'candidate_personal' AND is_free = 0"
            ),
        ),
        Index(
            "uq_subscriptions_candidate_free",
            "user_id",
            unique=True,
            mssql_where=text(
                "status = 'active' AND is_deleted = 0 AND scope = 'candidate_personal' AND is_free = 1"
            ),
        ),
        Index(
            "uq_subscriptions_legacy_user",
            "user_id",
            unique=True,
            mssql_where=text(
                "status = 'active' AND is_deleted = 0 AND scope = 'legacy_recruiter_personal'"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", name="fk_subscriptions_company_id_companies"),
        nullable=True,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recruitment_plans.id"), nullable=False
    )
    scope: Mapped[SubscriptionScope] = mapped_column(
        StringEnum(SubscriptionScope),
        default=SubscriptionScope.LEGACY_RECRUITER_PERSONAL,
        server_default="legacy_recruiter_personal",
        nullable=False,
    )
    is_free: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("0"),
        nullable=False,
    )
    current_period_key: Mapped[str | None] = mapped_column(
        String(7), nullable=True
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
    # Quota snapshot from plan at activation time
    max_job_posts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_candidate_searches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_ai_features: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Usage counters
    job_posts_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidate_searches_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_features_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped[User] = relationship(back_populates="subscriptions")
    company: Mapped[Company | None] = relationship(back_populates="subscriptions")
    plan: Mapped[RecruitmentPlan] = relationship(back_populates="subscriptions")
    payment_orders: Mapped[list[PaymentOrder]] = relationship(
        back_populates="subscription",
    )
    usages: Mapped[list[SubscriptionUsage]] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
    )