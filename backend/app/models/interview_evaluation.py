from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Uuid,
    text,
)
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin

STRENGTHS_MAX_LENGTH = 1000
WEAKNESSES_MAX_LENGTH = 1000
NOTES_MAX_LENGTH = 2000
RECOMMENDATION_MAX_LENGTH = 20

# Bounded, explicit set of hiring recommendations (see check constraint below).
RECOMMENDATION_VALUES = ("strong_hire", "hire", "no_hire", "strong_no_hire")

MIN_RATING = 1
MAX_RATING = 5


class InterviewEvaluation(Base, TimestampMixin, SoftDeleteMixin):
    """A recruiter's evaluation of a completed interview.

    ``application_id`` is denormalised onto the evaluation so evaluations can be
    queried per application. To make an inconsistent ``interview``/``application``
    pair impossible, the pair is constrained with a composite foreign key to the
    ``interviews(id, application_id)`` unique constraint (see the migration and
    :class:`app.models.interview.Interview`).
    """

    __tablename__ = "interview_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    interview_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id"),
        nullable=False,
    )
    evaluator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    strengths: Mapped[str | None] = mapped_column(
        String(STRENGTHS_MAX_LENGTH).with_variant(
            NVARCHAR(STRENGTHS_MAX_LENGTH), "mssql"
        ),
        nullable=True,
    )
    weaknesses: Mapped[str | None] = mapped_column(
        String(WEAKNESSES_MAX_LENGTH).with_variant(
            NVARCHAR(WEAKNESSES_MAX_LENGTH), "mssql"
        ),
        nullable=True,
    )
    recommendation: Mapped[str | None] = mapped_column(
        String(RECOMMENDATION_MAX_LENGTH).with_variant(
            NVARCHAR(RECOMMENDATION_MAX_LENGTH), "mssql"
        ),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(
        String(NOTES_MAX_LENGTH).with_variant(NVARCHAR(NOTES_MAX_LENGTH), "mssql"),
        nullable=True,
    )

    __table_args__ = (
        # Guarantees the evaluation's interview really belongs to the
        # evaluation's application (no inconsistent pairs).
        ForeignKeyConstraint(
            ["interview_id", "application_id"],
            ["interviews.id", "interviews.application_id"],
            name="fk_interview_evaluations_interview_application",
        ),
        CheckConstraint(
            f"rating >= {MIN_RATING} AND rating <= {MAX_RATING}",
            name="ck_interview_evaluations_rating_range",
        ),
        CheckConstraint(
            "recommendation IS NULL OR recommendation IN "
            "('strong_hire', 'hire', 'no_hire', 'strong_no_hire')",
            name="ck_interview_evaluations_recommendation",
        ),
        Index("ix_interview_evaluations_interview_id", "interview_id"),
        Index("ix_interview_evaluations_application_id", "application_id"),
        # At most one *active* evaluation per interviewer per interview. The
        # index is filtered on ``is_deleted = 0`` so a soft-deleted scorecard
        # does not block a fresh one, while concurrent inserts of a duplicate
        # scorecard are rejected by the database (defence in depth on top of
        # the service-level check).
        Index(
            "uq_interview_evaluations_interview_evaluator_active",
            "interview_id",
            "evaluator_id",
            unique=True,
            mssql_where=text("is_deleted = 0"),
        ),
    )
