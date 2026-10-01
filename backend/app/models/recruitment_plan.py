from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin
from app.domain.enums import RecruitmentPlanStatus
from app.models.user import StringEnum

if TYPE_CHECKING:
    from app.models.subscription import Subscription


class RecruitmentPlan(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "recruitment_plans"
    __table_args__ = (
        Index("ix_recruitment_plans_display_order", "display_order"),
        Index("ix_recruitment_plans_is_active", "is_active"),
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
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    subscriptions: Mapped[list[Subscription]] = relationship(
        back_populates="plan",
    )