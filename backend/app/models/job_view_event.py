from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base_class import Base, utc_now


class JobViewEvent(Base):
    """Append-only raw job-view telemetry.

    ``is_unique`` is deliberately nullable: uniqueness depends on a bounded
    Redis dedup check, and ``None`` records that the check could not be
    performed (for example during a Redis outage). Such views are still real
    views and are reported as "unverified" rather than silently dropped or
    guessed.

    Events are never rewritten. They are pruned only after a matching
    Vietnam-local daily aggregate has been durably recorded (see the analytics
    rollup worker).
    """

    __tablename__ = "job_view_events"
    __table_args__ = (
        Index(
            "ix_job_view_events_company_viewed_at",
            "company_id",
            "viewed_at",
        ),
        Index(
            "ix_job_view_events_job_viewed_at",
            "job_id",
            "viewed_at",
        ),
        Index("ix_job_view_events_viewed_at", "viewed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False
    )
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    is_unique: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
