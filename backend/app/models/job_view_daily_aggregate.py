from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base_class import Base, TimestampMixin, utc_now


class JobViewDailyAggregate(Base, TimestampMixin):
    """Durable per-job, per-Vietnam-day view rollup.

    ``view_date`` is the local date in ``Asia/Ho_Chi_Minh`` (UTC+7, no DST).
    ``raw_pruned`` records that the raw events backing this row have been
    deleted by retention; such a row must never be recomputed from raw events
    (that would overwrite real history with zero).
    """

    __tablename__ = "job_view_daily_aggregates"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "view_date", name="uq_job_view_daily_aggregates_job_date"
        ),
        Index(
            "ix_job_view_daily_aggregates_company_view_date",
            "company_id",
            "view_date",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False
    )
    view_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unverified_views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    raw_pruned: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    aggregated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
