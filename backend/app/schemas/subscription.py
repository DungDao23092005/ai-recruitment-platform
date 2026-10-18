from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import (
    PaymentOrderStatus,
    PaymentProvider,
    SubscriptionAuditAction,
    SubscriptionStatus,
)
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


class SubscriptionPaymentSummary(BaseModel):
    """A payment order attached to a subscription, for admin drill-down."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_id: uuid.UUID
    subscription_id: Optional[uuid.UUID]
    internal_order_id: str
    provider: PaymentProvider
    status: PaymentOrderStatus
    amount: int
    currency: str
    paid_at: Optional[datetime]
    expired_at: Optional[datetime]
    created_at: datetime


class SubscriptionSummary(BaseModel):
    """One subscription in a user's history, with plan, quota and payments."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_id: uuid.UUID
    plan_name: Optional[str] = None
    status: SubscriptionStatus
    started_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime
    max_job_posts: int
    max_candidate_searches: int
    max_ai_features: int
    job_posts_used: int
    candidate_searches_used: int
    ai_features_used: int
    payments: list[SubscriptionPaymentSummary] = Field(default_factory=list)


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


def _validate_reason(value: str) -> str:
    """Require a meaningful, non-blank justification of at least 5 chars."""
    stripped = value.strip()
    if len(stripped) < 5:
        raise ValueError("Lý do phải có ít nhất 5 ký tự.")
    return stripped


class AdminSubscriptionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    user_email: Optional[str] = None
    plan_id: uuid.UUID
    plan_name: Optional[str] = None
    status: SubscriptionStatus
    # Effective status for display: a DB-ACTIVE row past ``expires_at`` is shown
    # as EXPIRED without mutating the stored status.
    effective_status: SubscriptionStatus
    started_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    max_job_posts: int
    max_candidate_searches: int
    max_ai_features: int
    job_posts_used: int
    candidate_searches_used: int
    ai_features_used: int
    # Per-user diagnostics (computed across ALL the user's subscriptions).
    total_subscriptions: int = 1
    has_multiple_active: bool = False
    has_unresolved_payment: bool = False
    is_entitlement_incident: bool = False
    incident_subscription_id: Optional[uuid.UUID] = None
    incident_internal_order_id: Optional[str] = None
    incident_amount: Optional[int] = None


class AdminSubscriptionList(BaseModel):
    items: list[AdminSubscriptionListItem]
    total: int
    skip: int
    limit: int


class AdminSubscriptionChangePlan(BaseModel):
    target_plan_id: uuid.UUID
    reason: str = Field(..., min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def _check_reason(cls, value: str) -> str:
        return _validate_reason(value)


class AdminSubscriptionRevoke(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def _check_reason(cls, value: str) -> str:
        return _validate_reason(value)


class SubscriptionAuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    admin_id: uuid.UUID
    admin_email: Optional[str] = None
    user_id: uuid.UUID
    subscription_id: uuid.UUID
    action: SubscriptionAuditAction
    old_plan_id: Optional[uuid.UUID]
    new_plan_id: Optional[uuid.UUID]
    reason: str
    created_at: datetime


class AdminSubscriptionDetail(BaseModel):
    subscription: AdminSubscriptionListItem
    history: list[SubscriptionSummary]
    audit_logs: list[SubscriptionAuditLogRead]