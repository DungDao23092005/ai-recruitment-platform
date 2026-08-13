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
        description="Required education degree/level",
    )