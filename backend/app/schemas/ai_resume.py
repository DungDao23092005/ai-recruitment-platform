from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WorkExperienceSchema(BaseModel):
    company: str | None = Field(
        default=None, description="Name of company or organization"
    )
    position: str | None = Field(
        default=None, description="Job title or position"
    )
    start_date: str | None = Field(
        default=None, description="Start date (e.g. MM/YYYY or YYYY)"
    )
    end_date: str | None = Field(
        default=None, description="End date (e.g. MM/YYYY or 'Present')"
    )
    is_current: bool = Field(
        default=False, description="True if candidate currently works here"
    )
    description: str | None = Field(
        default=None, description="Summary of responsibilities and achievements"
    )
    skills_used: list[str] = Field(
        default_factory=list, description="Skills or technologies used"
    )


class EducationSchema(BaseModel):
    institution: str | None = Field(
        default=None, description="Name of university or school"
    )
    degree: str | None = Field(
        default=None, description="Degree name (e.g. Bachelor of Science)"
    )
    field_of_study: str | None = Field(
        default=None, description="Major or field of study"
    )
    start_year: int | None = Field(default=None, description="Start year")
    end_year: int | None = Field(
        default=None, description="Graduation or end year"
    )


class ProjectSchema(BaseModel):
    name: str | None = Field(default=None, description="Name of the project")
    description: str | None = Field(default=None, description="Description of the project")
    skills_used: list[str] = Field(default_factory=list, description="Skills or technologies used in the project")


class ParsedResumeSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    full_name: str | None = Field(default=None, description="Full candidate name")
    email: str | None = Field(default=None, description="Email address")
    phone: str | None = Field(default=None, description="Phone number")
    title: str | None = Field(
        default=None, description="Professional headline or job title"
    )
    summary: str | None = Field(
        default=None, description="Professional summary or bio"
    )
    total_years_experience: float | None = Field(
        default=None,
        description="Total years of work experience computed from experience timeline (float, null if insufficient data)",
    )
    skills: list[str] = Field(
        default_factory=list,
        description="List of all skills (combined)",
    )
    technical_skills: list[str] = Field(
        default_factory=list,
        description="List of technical/hard skills",
    )
    soft_skills: list[str] = Field(
        default_factory=list,
        description="List of soft/interpersonal skills",
    )
    job_titles: list[str] = Field(
        default_factory=list,
        description="List of job titles the candidate has held",
    )
    projects: list[ProjectSchema] = Field(
        default_factory=list, description="List of projects"
    )
    experiences: list[WorkExperienceSchema] = Field(
        default_factory=list, description="List of work experiences"
    )
    education: list[EducationSchema] = Field(
        default_factory=list, description="List of education history"
    )
    certifications: list[str] = Field(
        default_factory=list, description="List of certifications or licenses"
    )
    languages: list[str] = Field(
        default_factory=list, description="List of languages spoken"
    )
