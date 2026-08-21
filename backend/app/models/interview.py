from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin
from app.domain.enums import InterviewStatus, InterviewType
from app.models.user import StringEnum


class Interview(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id"),
        nullable=False,
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    duration_minutes: Mapped[int] = mapped_column(default=60, nullable=False)
    interview_type: Mapped[InterviewType] = mapped_column(
        StringEnum(InterviewType),
        default=InterviewType.TECHNICAL,
        nullable=False,
    )
    meeting_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[InterviewStatus] = mapped_column(
        StringEnum(InterviewStatus),
        default=InterviewStatus.SCHEDULED,
        nullable=False,
    )

    application: Mapped["Application"] = relationship(back_populates="interviews")