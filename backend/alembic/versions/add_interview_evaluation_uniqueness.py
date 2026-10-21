"""add one-active-evaluation-per-interview-per-evaluator uniqueness

Phase 2 allows a recruiter to submit at most one scorecard per interview. To
enforce that rule in the database (and not just in the service layer), this
revision adds a *filtered* unique index on
``interview_evaluations(interview_id, evaluator_id)`` restricted to active
rows (``is_deleted = 0``).

Filtering on ``is_deleted = 0`` is deliberate: soft-deleting a scorecard must
not permanently block the evaluator from submitting a fresh one, while two
concurrent inserts of a duplicate active scorecard are still rejected by the
database. This is purely additive - no existing column, value or index is
modified - and the downgrade simply drops the index (it constrains future
duplicates, it does not hold data, so dropping it loses nothing).

Revision ID: add_interview_eval_uniqueness
Revises: add_hiring_pipeline_tables
Create Date: 2026-10-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_interview_eval_uniqueness'
down_revision: Union[str, None] = 'add_hiring_pipeline_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "uq_interview_evaluations_interview_evaluator_active"
_TABLE_NAME = "interview_evaluations"


def upgrade() -> None:
    op.create_index(
        _INDEX_NAME,
        _TABLE_NAME,
        ["interview_id", "evaluator_id"],
        unique=True,
        mssql_where=sa.text("is_deleted = 0"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME)
