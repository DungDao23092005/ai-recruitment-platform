from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.domain.enums import InvitationStatus, MembershipRole, MembershipStatus


def normalize_email(value: str) -> str:
    return value.strip().lower()


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    user_id: uuid.UUID
    role: MembershipRole
    status: MembershipStatus
    joined_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class MemberRead(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str | None = None
    role: MembershipRole
    status: MembershipStatus
    joined_at: datetime | None = None
    revoked_at: datetime | None = None


class WorkspaceRead(BaseModel):
    company_id: uuid.UUID
    company_name: str
    company_slug: str
    membership_id: uuid.UUID | None = None
    role: MembershipRole | None = None
    is_platform_admin: bool = False


class InvitationCreate(BaseModel):
    email: EmailStr
    role: Literal[MembershipRole.ADMIN, MembershipRole.RECRUITER] = (
        MembershipRole.RECRUITER
    )

    @field_validator("email")
    @classmethod
    def normalize_invitation_email(cls, value: str) -> str:
        return normalize_email(value)


class InvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    email: str
    role: MembershipRole
    status: InvitationStatus
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class InvitationPreviewRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class InvitationPreviewRead(BaseModel):
    company_name: str
    company_slug: str
    email_masked: str
    role: MembershipRole
    status: InvitationStatus
    expires_at: datetime
    can_accept: bool


class InvitationAcceptRead(BaseModel):
    workspace: WorkspaceRead
    membership_id: uuid.UUID


class InvitationRevokeRead(BaseModel):
    invitation_id: uuid.UUID
    status: InvitationStatus
