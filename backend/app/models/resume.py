from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin


class Resume(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    parsed_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    candidate: Mapped[CandidateProfile] = relationship(back_populates="resumes")
