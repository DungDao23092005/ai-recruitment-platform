from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ParsedJobSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = Field(
        default=None,
        description="Job title or role name",
    )
    summary: str | None = Field(
        default=None,
        description="Brief summary of job role and responsibilities",
    )
    seniority: str | None = Field(
        default=None,
        description="Seniority level (e.g. Junior, Mid, Senior, Lead, Manager)",
    )
    responsibilities: list[str] = Field(
        default_factory=list,
        description="List of key responsibilities and duties",
    )
    required_skills: list[str] = Field(
        default_factory=list,
        description="List of mandatory/required technical and professional skills",
    )
    preferred_skills: list[str] = Field(
        default_factory=list,
        description="List of nice-to-have or preferred skills",
    )
    minimum_years_experience: float | None = Field(
        default=None,
        description="Minimum required years of experience (float, null if unspecified)",
    )
    education_level: str | None = Field(
        default=None,
        description="Required education degree/level (e.g. Bachelor, Master)",
    )
    certifications: list[str] = Field(
        default_factory=list,
        description="List of required or preferred certifications",
    )
    languages: list[str] = Field(
        default_factory=list,
        description="List of required or preferred languages",
    )
    location: str | None = Field(
        default=None,
        description="Job location (city, region, or remote)",
    )
    city: str | None = Field(
        default=None,
        description="City where the job is located",
    )
    salary_min: float | None = Field(
        default=None,
        description="Minimum salary offered",
    )
    salary_max: float | None = Field(
        default=None,
        description="Maximum salary offered",
    )
    currency: str | None = Field(
        default=None,
        description="Currency for salary (e.g. VND, USD)",
    )
    employment_type: str | None = Field(
        default=None,
        description="Employment type (e.g. Full-time, Part-time, Contract)",
    )
    workplace_type: str | None = Field(
        default=None,
        description="Workplace type (e.g. On-site, Hybrid, Remote)",
    )