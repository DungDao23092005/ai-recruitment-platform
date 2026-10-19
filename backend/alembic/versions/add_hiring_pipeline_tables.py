"""add hiring pipeline tables

Introduces the persistence for the hiring pipeline Phase 1:

* ``application_notes``      - recruiter-authored internal notes (soft-deleted).
* ``interview_evaluations``  - structured interview scorecards, constrained so
  an evaluation can never point at a mismatched interview/application pair.
* ``application_activities`` - append-only audit trail of application events.

It also adds a composite unique constraint on ``interviews(id, application_id)``
which is the target of the evaluation composite foreign key. The change is
additive: no existing column type or value is modified.

Downgrade is guarded. Dropping the new tables would irreversibly lose any notes,
evaluations or audit history that has been written, so the downgrade refuses to
run while any of those tables contain rows. Empty tables (a fresh environment)
downgrade cleanly.

Revision ID: add_hiring_pipeline_tables
Revises: add_email_outbox
Create Date: 2026-10-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mssql import NVARCHAR


# revision identifiers, used by Alembic.
revision: str = 'add_hiring_pipeline_tables'
down_revision: Union[str, None] = 'add_email_outbox'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Returns one (table_name, row_count) row per new table that still holds rows.
REMAINING_ROWS_QUERY = sa.text(
    """
    SELECT 'application_notes' AS table_name, COUNT(*) AS row_count
    FROM application_notes
    HAVING COUNT(*) > 0
    UNION ALL
    SELECT 'interview_evaluations', COUNT(*)
    FROM interview_evaluations
    HAVING COUNT(*) > 0
    UNION ALL
    SELECT 'application_activities', COUNT(*)
    FROM application_activities
    HAVING COUNT(*) > 0
    """
)


def _remaining_row_counts(connection) -> list:
    """Return ``(table_name, count)`` pairs for the new tables that hold rows."""
    return list(connection.execute(REMAINING_ROWS_QUERY).fetchall())


def _assert_downgrade_safe(connection) -> None:
    """Refuse to drop the new tables while any of them contains rows.

    Back up the data (or explicitly export it) before downgrading, otherwise the
    notes, evaluations and audit history written since the upgrade are lost
    without a trace.
    """
    remaining = _remaining_row_counts(connection)
    if remaining:
        detail = ", ".join(f"{name}={count}" for name, count in remaining)
        raise RuntimeError(
            "Refusing to drop hiring pipeline tables: they still contain rows "
            f"({detail}). Export or delete that data first (a full database "
            "backup is recommended) before downgrading, otherwise it would be "
            "lost without a trace."
        )


def upgrade() -> None:
    # Composite unique target used by interview_evaluations' foreign key.
    # ``id`` is already the primary key, so this can never be violated.
    op.create_unique_constraint(
        'uq_interviews_id_application_id',
        'interviews',
        ['id', 'application_id'],
    )

    op.create_table(
        'application_notes',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('application_id', sa.Uuid(), nullable=False),
        sa.Column('author_id', sa.Uuid(), nullable=False),
        sa.Column('content', NVARCHAR(2000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ['application_id'], ['applications.id'],
        ),
        sa.ForeignKeyConstraint(
            ['author_id'], ['users.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_application_notes_application_id',
        'application_notes',
        ['application_id'],
        unique=False,
    )

    op.create_table(
        'interview_evaluations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('interview_id', sa.Uuid(), nullable=False),
        sa.Column('application_id', sa.Uuid(), nullable=False),
        sa.Column('evaluator_id', sa.Uuid(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('strengths', NVARCHAR(1000), nullable=True),
        sa.Column('weaknesses', NVARCHAR(1000), nullable=True),
        sa.Column('recommendation', NVARCHAR(20), nullable=True),
        sa.Column('notes', NVARCHAR(2000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ['application_id'], ['applications.id'],
        ),
        sa.ForeignKeyConstraint(
            ['evaluator_id'], ['users.id'],
        ),
        sa.ForeignKeyConstraint(
            ['interview_id', 'application_id'],
            ['interviews.id', 'interviews.application_id'],
            name='fk_interview_evaluations_interview_application',
        ),
        sa.CheckConstraint(
            'rating >= 1 AND rating <= 5',
            name='ck_interview_evaluations_rating_range',
        ),
        sa.CheckConstraint(
            "recommendation IS NULL OR recommendation IN "
            "('strong_hire', 'hire', 'no_hire', 'strong_no_hire')",
            name='ck_interview_evaluations_recommendation',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_interview_evaluations_interview_id',
        'interview_evaluations',
        ['interview_id'],
        unique=False,
    )
    op.create_index(
        'ix_interview_evaluations_application_id',
        'interview_evaluations',
        ['application_id'],
        unique=False,
    )

    op.create_table(
        'application_activities',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('application_id', sa.Uuid(), nullable=False),
        sa.Column('actor_id', sa.Uuid(), nullable=False),
        sa.Column('action_type', NVARCHAR(50), nullable=False),
        sa.Column('from_status', NVARCHAR(50), nullable=True),
        sa.Column('to_status', NVARCHAR(50), nullable=True),
        sa.Column('note', NVARCHAR(1000), nullable=True),
        sa.Column('metadata_json', NVARCHAR, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['application_id'], ['applications.id'],
        ),
        sa.ForeignKeyConstraint(
            ['actor_id'], ['users.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_application_activities_application_id',
        'application_activities',
        ['application_id'],
        unique=False,
    )


def downgrade() -> None:
    _assert_downgrade_safe(op.get_bind())

    op.drop_index(
        'ix_application_activities_application_id',
        table_name='application_activities',
    )
    op.drop_table('application_activities')

    op.drop_index(
        'ix_interview_evaluations_application_id',
        table_name='interview_evaluations',
    )
    op.drop_index(
        'ix_interview_evaluations_interview_id',
        table_name='interview_evaluations',
    )
    op.drop_table('interview_evaluations')

    op.drop_index(
        'ix_application_notes_application_id',
        table_name='application_notes',
    )
    op.drop_table('application_notes')

    op.drop_constraint(
        'uq_interviews_id_application_id',
        'interviews',
        type_='unique',
    )
