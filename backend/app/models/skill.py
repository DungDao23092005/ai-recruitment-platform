from __future__ import annotations

import uuid

from sqlalchemy import Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin


class Skill(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "skills"
    __table_args__ = (
        Index("uq_skills_name", "name", unique=True, mssql_where=text("is_deleted = 0")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    candidate_skills: Mapped[list[CandidateSkill]] = relationship(
        back_populates="skill",
        cascade="all, delete-orphan",
        overlaps="candidates,skills",
    )
    candidates: Mapped[list[CandidateProfile]] = relationship(
        secondary="candidate_skills",
        back_populates="skills",
        overlaps="candidate_skills,skill",
    )
    job_skills: Mapped[list[JobSkill]] = relationship(
        back_populates="skill",
        cascade="all, delete-orphan",
        overlaps="jobs,skills",
    )
    jobs: Mapped[list[Job]] = relationship(
        secondary="job_skills",
        back_populates="skills",
        overlaps="job_skills,skill",
    )
