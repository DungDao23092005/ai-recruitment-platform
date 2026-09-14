from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin
from app.domain.enums import JobStatus, JobType, WorkplaceType
from app.models.user import StringEnum


class Job(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255).with_variant(NVARCHAR(255), "mssql"), nullable=False
    )
    description: Mapped[str] = mapped_column(
        Text().with_variant(NVARCHAR(), "mssql"),
        nullable=False,
    )
    status: Mapped[JobStatus] = mapped_column(
        StringEnum(JobStatus),
        default=JobStatus.DRAFT,
        nullable=False,
    )
    job_type: Mapped[JobType] = mapped_column(StringEnum(JobType), nullable=False)
    workplace_type: Mapped[WorkplaceType] = mapped_column(
        StringEnum(WorkplaceType),
        nullable=False,
    )
    location: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    minimum_years_experience: Mapped[float | None] = mapped_column(Float, nullable=True)
    education_level: Mapped[str | None] = mapped_column(
        String(255).with_variant(NVARCHAR(255), "mssql"), nullable=True
    )

    company: Mapped[Company] = relationship(back_populates="jobs")
    job_skills: Mapped[list[JobSkill]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        overlaps="skills,jobs",
    )
    # Required skills (is_mandatory=True)
    required_skills: Mapped[list[Skill]] = relationship(
        secondary="job_skills",
        primaryjoin="and_(Job.id==JobSkill.job_id, JobSkill.is_mandatory==True)",
        secondaryjoin="Skill.id==JobSkill.skill_id",
        back_populates="jobs",
        overlaps="job_skills,skills",
        viewonly=True,
    )
    # Preferred skills (is_mandatory=False)
    preferred_skills: Mapped[list[Skill]] = relationship(
        secondary="job_skills",
        primaryjoin="and_(Job.id==JobSkill.job_id, JobSkill.is_mandatory==False)",
        secondaryjoin="Skill.id==JobSkill.skill_id",
        back_populates="jobs",
        overlaps="job_skills,skills",
        viewonly=True,
    )
    skills: Mapped[list[Skill]] = relationship(
        secondary="job_skills",
        back_populates="jobs",
        overlaps="job_skills,job",
    )
    applications: Mapped[list[Application]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )
