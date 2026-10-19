"""Unit tests for the Phase 2 hiring-pipeline schemas and activity vocabulary.

These assert the validation bounds and the recruiter/candidate projection split
without a database, and pin the schema constants to their model counterparts so
they can never silently drift.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain import hiring
from app.models.application_activity import ACTION_TYPE_MAX_LENGTH
from app.models.application_note import CONTENT_MAX_LENGTH
from app.models.interview_evaluation import (
    MAX_RATING,
    MIN_RATING,
    RECOMMENDATION_VALUES,
)
from app.schemas.application_activity import (
    ApplicationActivityRead,
    CandidateApplicationActivityRead,
)
from app.schemas.application_note import (
    NOTE_CONTENT_MAX_LENGTH,
    ApplicationNoteCreate,
    ApplicationNoteRead,
    ApplicationNoteUpdate,
)
from app.schemas.interview_evaluation import (
    EVALUATION_MAX_RATING,
    EVALUATION_MIN_RATING,
    EVALUATION_RECOMMENDATION_VALUES,
    InterviewEvaluationCreate,
    InterviewEvaluationUpdate,
)


class TestSchemaConstantAlignment:
    def test_note_length_matches_model(self):
        assert NOTE_CONTENT_MAX_LENGTH == CONTENT_MAX_LENGTH

    def test_rating_bounds_match_model(self):
        assert EVALUATION_MIN_RATING == MIN_RATING
        assert EVALUATION_MAX_RATING == MAX_RATING

    def test_recommendation_values_match_model(self):
        assert EVALUATION_RECOMMENDATION_VALUES == RECOMMENDATION_VALUES


class TestApplicationNoteCreate:
    def test_accepts_normal_content(self):
        note = ApplicationNoteCreate(content="Ứng viên rất phù hợp")
        assert note.content == "Ứng viên rất phù hợp"

    def test_strips_surrounding_whitespace(self):
        note = ApplicationNoteCreate(content="  hello  ")
        assert note.content == "hello"

    @pytest.mark.parametrize("value", ["", "   ", "\n\t"])
    def test_rejects_blank(self, value):
        with pytest.raises(ValidationError):
            ApplicationNoteCreate(content=value)

    def test_rejects_too_long(self):
        with pytest.raises(ValidationError):
            ApplicationNoteCreate(content="a" * (NOTE_CONTENT_MAX_LENGTH + 1))

    def test_accepts_max_length_unicode(self):
        content = "ữ" * NOTE_CONTENT_MAX_LENGTH
        assert ApplicationNoteCreate(content=content).content == content

    def test_update_schema_requires_content(self):
        with pytest.raises(ValidationError):
            ApplicationNoteUpdate(content="   ")


class TestInterviewEvaluationCreate:
    @pytest.mark.parametrize("rating", [1, 3, 5])
    def test_accepts_rating_in_range(self, rating):
        assert InterviewEvaluationCreate(rating=rating).rating == rating

    @pytest.mark.parametrize("rating", [0, 6, -1])
    def test_rejects_rating_out_of_range(self, rating):
        with pytest.raises(ValidationError):
            InterviewEvaluationCreate(rating=rating)

    def test_rejects_unknown_recommendation(self):
        with pytest.raises(ValidationError):
            InterviewEvaluationCreate(rating=4, recommendation="maybe")

    def test_accepts_known_recommendation(self):
        evaluation = InterviewEvaluationCreate(
            rating=4, recommendation="strong_hire"
        )
        assert evaluation.recommendation == "strong_hire"

    def test_accepts_null_recommendation(self):
        assert InterviewEvaluationCreate(rating=4).recommendation is None

    def test_update_all_fields_optional(self):
        assert InterviewEvaluationUpdate().rating is None

    def test_update_rejects_bad_recommendation(self):
        with pytest.raises(ValidationError):
            InterviewEvaluationUpdate(recommendation="nope")


class TestActivityProjections:
    def test_recruiter_projection_exposes_internal_fields(self):
        assert {
            "id",
            "application_id",
            "actor_id",
            "action_type",
            "from_status",
            "to_status",
            "note",
            "metadata_json",
            "created_at",
        } == set(ApplicationActivityRead.model_fields)

    def test_candidate_projection_hides_internal_fields(self):
        fields = set(CandidateApplicationActivityRead.model_fields)
        assert fields == {
            "id",
            "action_type",
            "from_status",
            "to_status",
            "created_at",
        }
        assert "actor_id" not in fields
        assert "note" not in fields
        assert "metadata_json" not in fields
        assert "application_id" not in fields

    def test_note_and_evaluation_events_are_not_candidate_visible(self):
        internal = {
            hiring.NOTE_ADDED,
            hiring.NOTE_UPDATED,
            hiring.NOTE_DELETED,
            hiring.EVALUATION_ADDED,
            hiring.EVALUATION_UPDATED,
            hiring.EVALUATION_DELETED,
        }
        assert internal.isdisjoint(hiring.CANDIDATE_VISIBLE_ACTIVITY_TYPES)

    def test_candidate_visible_is_subset_of_recruiter_vocabulary(self):
        assert (
            hiring.CANDIDATE_VISIBLE_ACTIVITY_TYPES
            <= hiring.RECRUITER_VISIBLE_ACTIVITY_TYPES
        )

    def test_action_types_fit_column(self):
        for action_type in hiring.RECRUITER_VISIBLE_ACTIVITY_TYPES:
            assert len(action_type) <= ACTION_TYPE_MAX_LENGTH

    def test_application_note_read_has_no_candidate_variant(self):
        # Notes are recruiter-only; the read schema intentionally carries the
        # author so the UI can enforce edit rights.
        assert "author_id" in ApplicationNoteRead.model_fields
