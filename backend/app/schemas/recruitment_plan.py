from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import RecruitmentPlanStatus


class RecruitmentPlanBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    price: int = Field(..., ge=0)
    currency: str = Field(default="VND", min_length=3, max_length=10)
    duration_days: int = Field(..., gt=0)
    max_job_posts: int = Field(..., ge=0)
    max_candidate_searches: Optional[int] = Field(None, ge=0)
    max_ai_features: Optional[int] = Field(None, ge=0)
    display_order: int = Field(default=0, ge=0)


class RecruitmentPlanCreate(RecruitmentPlanBase):
    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        return v.upper()


class RecruitmentPlanUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    price: Optional[int] = Field(None, ge=0)
    currency: Optional[str] = Field(None, min_length=3, max_length=10)
    duration_days: Optional[int] = Field(None, gt=0)
    max_job_posts: Optional[int] = Field(None, ge=0)
    max_candidate_searches: Optional[int] = Field(None, ge=0)
    max_ai_features: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    display_order: Optional[int] = Field(None, ge=0)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if v is not None else None


class RecruitmentPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str]
    price: int
    currency: str
    duration_days: int
    max_job_posts: int
    max_candidate_searches: Optional[int]
    max_ai_features: Optional[int]
    is_active: bool
    display_order: int
    created_at: datetime
    updated_at: datetime


class RecruitmentPlanAdminRead(RecruitmentPlanRead):
    is_deleted: bool


class PlanStatusUpdate(BaseModel):
    is_active: bool