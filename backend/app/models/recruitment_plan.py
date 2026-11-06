from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin
from app.domain.enums import PlanAudience, RecruitmentPlanStatus
from app.models.user import StringEnum

if TYPE_CHECKING:
    from app.models.subscription import Subscription


class RecruitmentPlan(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "recruitment_plans"
    __table_args__ = (
        CheckConstraint(
            "plan_audience IN ('company', 'candidate')",
            name="ck_recruitment_plans_audience",
        ),
        CheckConstraint(
            "is_free = 0 OR plan_audience = 'candidate'",
            name="ck_recruitment_plans_free_candidate",
        ),
        Index("ix_recruitment_plans_display_order", "display_order"),
        Index("ix_recruitment_plans_is_active", "is_active"),
        Index(
            "ix_recruitment_plans_audience_active",
            "plan_audience",
            "is_active",
            "display_order",
            mssql_where=text("is_deleted = 0"),
        ),
        Index(
            "uq_recruitment_plans_active_candidate_free",
            "plan_audience",
            "is_free",
            unique=True,
            mssql_where=text(
                "is_active = 1 AND is_deleted = 0 AND plan_audience = 'candidate' AND is_free = 1"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(
        String(255).with_variant(NVARCHAR(255), "mssql"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(
        Text().with_variant(NVARCHAR(), "mssql"), nullable=True
    )
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="VND", nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    max_job_posts: Mapped[int] = mapped_column(Integer, nullable=False)
    max_candidate_searches: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_ai_features: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plan_audience: Mapped[PlanAudience] = mapped_column(
        StringEnum(PlanAudience),
        default=PlanAudience.COMPANY,
        server_default="company",
        nullable=False,
    )
    is_free: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("0"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    subscriptions: Mapped[list[Subscription]] = relationship(
        back_populates="plan",
    )