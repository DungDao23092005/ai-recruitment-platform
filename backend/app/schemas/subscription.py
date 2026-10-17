from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.domain.enums import SubscriptionStatus
from app.schemas.recruitment_plan import RecruitmentPlanRead


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    plan_id: uuid.UUID
    status: SubscriptionStatus
    started_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    # Quota snapshot from plan at activation
    max_job_posts: int
    max_candidate_searches: int
    max_ai_features: int
    # Usage counters
    job_posts_used: int
    candidate_searches_used: int
    ai_features_used: int
    # Linked plan (eager-loaded). Optional so serialization stays safe if the
    # plan row is genuinely absent.
    plan: Optional[RecruitmentPlanRead] = None


class SubscriptionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_id: uuid.UUID
    status: SubscriptionStatus
    started_at: Optional[datetime]
    expires_at: Optional[datetime]


class SubscriptionCreate(BaseModel):
    user_id: uuid.UUID
    plan_id: uuid.UUID
    status: SubscriptionStatus = SubscriptionStatus.PENDING
    started_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class SubscriptionAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    plan_id: uuid.UUID
    status: SubscriptionStatus
    started_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    is_deleted: bool
    # Quota snapshot and usage
    max_job_posts: int
    max_candidate_searches: int
    max_ai_features: int
    job_posts_used: int
    candidate_searches_used: int
    ai_features_used: int


class SubscriptionAdminProvision(BaseModel):
    user_id: uuid.UUID
    plan_id: uuid.UUID