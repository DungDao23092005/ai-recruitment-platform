from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.domain.enums import ApplicationStatus
from app.schemas.ai_resume import ParsedResumeSchema


class InterviewType(str):
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    HR = "hr"
    CASE_STUDY = "case_study"


class InterviewStatus(str):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    CANDIDATE_CONFIRMED = "candidate_confirmed"
    CANDIDATE_DECLINED = "candidate_declined"


class InterviewBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scheduled_at: datetime
    duration_minutes: int = Field(default=60, ge=15, le=480)
    interview_type: str = Field(default="technical")
    meeting_url: HttpUrl | None = None
    location: str | None = None
    notes: str | None = None
    candidate_notes: str | None = None
    status: str = Field(default="scheduled")


class InterviewCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scheduled_at: datetime
    duration_minutes: int = Field(default=60, ge=15, le=480)
    interview_type: str = Field(default="technical")
    meeting_url: HttpUrl | None = None
    location: str | None = None
    notes: str | None = None


class InterviewUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=480)
    interview_type: str | None = None
    meeting_url: HttpUrl | None = None
    location: str | None = None
    notes: str | None = None


class RecruiterInterviewRead(BaseModel):
    """Recruiter/admin view of an interview.

    Includes ``notes`` (internal recruiter notes). Only recruiter-authorised
    endpoints may serialise this schema; candidate-facing responses must use
    :class:`CandidateInterviewRead` so internal notes are never leaked.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    scheduled_at: datetime
    duration_minutes: int
    interview_type: str
    meeting_url: str | None = None
    location: str | None = None
    notes: str | None = None
    candidate_notes: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class CandidateInterviewRead(BaseModel):
    """Candidate-facing view of an interview.

    Deliberately excludes the recruiter-only ``notes`` field (and any future
    internal scorecards). ``candidate_notes`` is the candidate's own input and
    remains visible to them.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    scheduled_at: datetime
    duration_minutes: int
    interview_type: str
    meeting_url: str | None = None
    location: str | None = None
    candidate_notes: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class CandidateScheduledInterviewRead(CandidateInterviewRead):
    """Aggregated interview item for the authenticated candidate's schedule.

    Extends :class:`CandidateInterviewRead` with application-scoped job and
    company context so the candidate portal schedule page needs only a single
    request to render the complete session history. Deliberately excludes
    internal recruiter notes, evaluations, scorecards, and interviewer assignments.
    """

    job_id: uuid.UUID
    job_title: str
    company_name: str


class InterviewerInterviewRead(BaseModel):
    """Interviewer-facing view that never exposes internal recruiter notes."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    scheduled_at: datetime
    duration_minutes: int
    interview_type: str
    meeting_url: str | None = None
    location: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class AssignedInterviewRead(InterviewerInterviewRead):
    job_id: uuid.UUID
    job_title: str
    company_name: str
    candidate_name: str | None = None
    application_status: str


class InterviewerCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str | None = None
    title: str | None = None
    email: str | None = None
    phone: str | None = None


class InterviewerResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None = None
    is_primary: bool
    is_confirmed: bool
    parsed_data: ParsedResumeSchema | None = None


class InterviewerApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    job_title: str
    company_name: str | None = None
    status: ApplicationStatus
    created_at: datetime
    updated_at: datetime
    candidate: InterviewerCandidateRead | None = None
    resume: InterviewerResumeRead | None = None


# Backward-compatible alias: existing recruiter-facing code paths import
# ``InterviewRead`` and must keep the full (recruiter) projection.
InterviewRead = RecruiterInterviewRead


class InterviewActionRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    action: str  # "confirm" | "decline"
    candidate_notes: str | None = None