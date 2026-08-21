from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin
from app.domain.enums import ApplicationStatus
from app.models.user import StringEnum


class Application(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_applications_candidate_job"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id"),
        nullable=False,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id"),
        nullable=False,
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        StringEnum(ApplicationStatus),
        default=ApplicationStatus.APPLIED,
        nullable=False,
    )

    candidate: Mapped[CandidateProfile] = relationship(back_populates="applications")
    job: Mapped[Job] = relationship(back_populates="applications")
    interviews: Mapped[list["Interview"]] = relationship(
        back_populates="application",
        primaryjoin="and_(Application.id==Interview.application_id, Interview.is_deleted==False)",
    )
