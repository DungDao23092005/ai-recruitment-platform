from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin


class CandidateProfile(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "candidate_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
    )
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship(back_populates="candidate_profile")
    resumes: Mapped[list[Resume]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    applications: Mapped[list[Application]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    candidate_skills: Mapped[list[CandidateSkill]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    skills: Mapped[list[Skill]] = relationship(
        secondary="candidate_skills",
        back_populates="candidates",
    )
