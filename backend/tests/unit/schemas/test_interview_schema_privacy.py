"""Unit tests for the candidate/recruiter interview projection split."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import get_args
from types import SimpleNamespace

from app.schemas.application import ApplicationDetailRead, ApplicationWithJobRead
from app.schemas.interview import (
    CandidateInterviewRead,
    InterviewRead,
    RecruiterInterviewRead,
)

RECRUITER_NOTES = "INTERNAL ONLY: do not leak"


def _interview_source():
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid.uuid4(),
        application_id=uuid.uuid4(),
        scheduled_at=now,
        duration_minutes=60,
        interview_type="technical",
        meeting_url="https://meet.example.com/x",
        location="Room 1",
        notes=RECRUITER_NOTES,
        candidate_notes=None,
        status="scheduled",
        created_at=now,
        updated_at=now,
    )


class TestCandidateInterviewRead:
    def test_excludes_recruiter_notes_field(self):
        assert "notes" not in CandidateInterviewRead.model_fields

    def test_serialization_drops_recruiter_notes(self):
        schema = CandidateInterviewRead.model_validate(_interview_source())
        dumped = schema.model_dump()
        assert "notes" not in dumped
        assert RECRUITER_NOTES not in schema.model_dump_json()

    def test_keeps_candidate_visible_fields(self):
        source = _interview_source()
        schema = CandidateInterviewRead.model_validate(source)
        assert schema.id == source.id
        assert schema.application_id == source.application_id
        assert schema.location == source.location
        assert schema.meeting_url == source.meeting_url
        assert schema.duration_minutes == 60


class TestRecruiterInterviewRead:
    def test_exposes_recruiter_notes(self):
        assert "notes" in RecruiterInterviewRead.model_fields

    def test_serialization_includes_recruiter_notes(self):
        schema = RecruiterInterviewRead.model_validate(_interview_source())
        assert schema.model_dump()["notes"] == RECRUITER_NOTES

    def test_interview_read_alias_is_recruiter_projection(self):
        assert InterviewRead is RecruiterInterviewRead


class TestApplicationSchemaWiring:
    def test_candidate_list_uses_candidate_projection(self):
        annotation = ApplicationWithJobRead.model_fields["interviews"].annotation
        assert get_args(annotation) == (CandidateInterviewRead,)

    def test_recruiter_detail_uses_recruiter_projection(self):
        annotation = ApplicationDetailRead.model_fields["interviews"].annotation
        assert get_args(annotation) == (RecruiterInterviewRead,)
