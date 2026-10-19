from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Mirror the column/constraint bounds in ``app.models.interview_evaluation``
# (asserted by the unit tests so the two can never drift).
EVALUATION_MIN_RATING = 1
EVALUATION_MAX_RATING = 5
EVALUATION_STRENGTHS_MAX_LENGTH = 1000
EVALUATION_WEAKNESSES_MAX_LENGTH = 1000
EVALUATION_NOTES_MAX_LENGTH = 2000
EVALUATION_RECOMMENDATION_VALUES = (
    "strong_hire",
    "hire",
    "no_hire",
    "strong_no_hire",
)

_RATING_FIELD = Field(ge=EVALUATION_MIN_RATING, le=EVALUATION_MAX_RATING)


def _validate_recommendation(value: str | None) -> str | None:
    if value is None:
        return None
    if value not in EVALUATION_RECOMMENDATION_VALUES:
        raise ValueError(
            "recommendation must be one of "
            f"{', '.join(EVALUATION_RECOMMENDATION_VALUES)}"
        )
    return value


class InterviewEvaluationCreate(BaseModel):
    rating: int = _RATING_FIELD
    strengths: str | None = Field(
        default=None, max_length=EVALUATION_STRENGTHS_MAX_LENGTH
    )
    weaknesses: str | None = Field(
        default=None, max_length=EVALUATION_WEAKNESSES_MAX_LENGTH
    )
    recommendation: str | None = None
    notes: str | None = Field(default=None, max_length=EVALUATION_NOTES_MAX_LENGTH)

    @field_validator("recommendation")
    @classmethod
    def _check_recommendation(cls, value: str | None) -> str | None:
        return _validate_recommendation(value)


class InterviewEvaluationUpdate(BaseModel):
    rating: int | None = Field(
        default=None, ge=EVALUATION_MIN_RATING, le=EVALUATION_MAX_RATING
    )
    strengths: str | None = Field(
        default=None, max_length=EVALUATION_STRENGTHS_MAX_LENGTH
    )
    weaknesses: str | None = Field(
        default=None, max_length=EVALUATION_WEAKNESSES_MAX_LENGTH
    )
    recommendation: str | None = None
    notes: str | None = Field(default=None, max_length=EVALUATION_NOTES_MAX_LENGTH)

    @field_validator("recommendation")
    @classmethod
    def _check_recommendation(cls, value: str | None) -> str | None:
        return _validate_recommendation(value)


class InterviewEvaluationRead(BaseModel):
    """Recruiter/admin view of a private interview scorecard.

    Candidates never receive this projection; evaluations stay internal to the
    hiring company (and admins).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    interview_id: uuid.UUID
    application_id: uuid.UUID
    evaluator_id: uuid.UUID
    rating: int
    strengths: str | None = None
    weaknesses: str | None = None
    recommendation: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
