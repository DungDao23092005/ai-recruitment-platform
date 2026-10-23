from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

ANALYTICS_TIMEZONE = "Asia/Ho_Chi_Minh"


class AnalyticsQuotaLine(BaseModel):
    """One quota counter. ``limit``/``remaining`` are null when unlimited."""

    limit: int | None = None
    used: int = 0
    remaining: int | None = None


class AnalyticsQuotaStatus(BaseModel):
    """Transparent subscription/quota state for the authenticated recruiter."""

    subscription_status: Literal["active", "none"] = "none"
    plan_name: str | None = None
    expires_at: datetime | None = None
    job_posts: AnalyticsQuotaLine = Field(default_factory=AnalyticsQuotaLine)
    candidate_searches: AnalyticsQuotaLine = Field(
        default_factory=AnalyticsQuotaLine
    )
    ai_features: AnalyticsQuotaLine = Field(default_factory=AnalyticsQuotaLine)


class AnalyticsKpis(BaseModel):
    total_views: int = 0
    unique_views: int = 0
    unverified_views: int = 0
    total_applications: int = 0
    hires: int = 0
    conversion_rate: float = 0.0
    avg_time_to_hire_days: float | None = None


class AnalyticsFunnelStage(BaseModel):
    stage: Literal[
        "applied", "under_review", "interviewing", "offered", "accepted"
    ]
    count: int


class AnalyticsDailyPoint(BaseModel):
    date: date
    total_views: int
    unique_views: int
    unverified_views: int


class AnalyticsJobRow(BaseModel):
    job_id: uuid.UUID
    job_title: str
    job_status: str
    total_views: int = 0
    unique_views: int = 0
    unverified_views: int = 0
    applications: int = 0
    hires: int = 0


class AnalyticsDataQuality(BaseModel):
    unique_views_reliable: bool
    raw_fallback_dates: list[date] = Field(default_factory=list)
    note: str


class RecruiterAnalyticsResponse(BaseModel):
    timezone: str = ANALYTICS_TIMEZONE
    start_date: date
    end_date: date
    generated_at: datetime
    kpis: AnalyticsKpis
    funnel: list[AnalyticsFunnelStage]
    daily_views: list[AnalyticsDailyPoint]
    jobs: list[AnalyticsJobRow]
    quota: AnalyticsQuotaStatus
    data_quality: AnalyticsDataQuality
