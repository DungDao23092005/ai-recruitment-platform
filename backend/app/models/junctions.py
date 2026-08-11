from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base
from app.domain.enums import ProficiencyLevel
from app.models.user import StringEnum


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id"),
        primary_key=True,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skills.id"),
        primary_key=True,
    )
    experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    proficiency_level: Mapped[ProficiencyLevel] = mapped_column(
        StringEnum(ProficiencyLevel),
        nullable=False,
    )

    candidate: Mapped[CandidateProfile] = relationship(back_populates="candidate_skills")
    skill: Mapped[Skill] = relationship(back_populates="candidate_skills")


class JobSkill(Base):
    __tablename__ = "job_skills"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id"),
        primary_key=True,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skills.id"),
        primary_key=True,
    )
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    minimum_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    job: Mapped[Job] = relationship(back_populates="job_skills")
    skill: Mapped[Skill] = relationship(back_populates="job_skills")
