"""add recruitment analytics telemetry and daily aggregates

Adds two additive tables:

* ``job_view_events`` - append-only raw job-view telemetry. ``is_unique`` is
  nullable because uniqueness depends on a best-effort Redis dedup check; a
  failed check is recorded as unverified instead of being guessed.
* ``job_view_daily_aggregates`` - durable per-job per-Vietnam-local-day rollup.
  ``raw_pruned`` marks rows whose raw events were deleted by retention so a
  later backfill can never overwrite real history with zeros.

No existing table is altered. Downgrading drops analytics history and is
intended only for development rollbacks.

Revision ID: add_recruitment_analytics
Revises: add_resume_confirmation
Create Date: 2026-10-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_recruitment_analytics"
down_revision: Union[str, None] = "add_resume_confirmation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_view_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_unique", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_job_view_events_company_viewed_at",
        "job_view_events",
        ["company_id", "viewed_at"],
        unique=False,
    )
    op.create_index(
        "ix_job_view_events_job_viewed_at",
        "job_view_events",
        ["job_id", "viewed_at"],
        unique=False,
    )
    op.create_index(
        "ix_job_view_events_viewed_at",
        "job_view_events",
        ["viewed_at"],
        unique=False,
    )

    op.create_table(
        "job_view_daily_aggregates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("view_date", sa.Date(), nullable=False),
        sa.Column("total_views", sa.Integer(), nullable=False),
        sa.Column("unique_views", sa.Integer(), nullable=False),
        sa.Column("unverified_views", sa.Integer(), nullable=False),
        sa.Column("raw_pruned", sa.Boolean(), nullable=False),
        sa.Column("aggregated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id",
            "view_date",
            name="uq_job_view_daily_aggregates_job_date",
        ),
    )
    op.create_index(
        "ix_job_view_daily_aggregates_company_view_date",
        "job_view_daily_aggregates",
        ["company_id", "view_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_job_view_daily_aggregates_company_view_date",
        table_name="job_view_daily_aggregates",
    )
    op.drop_table("job_view_daily_aggregates")
    op.drop_index("ix_job_view_events_viewed_at", table_name="job_view_events")
    op.drop_index(
        "ix_job_view_events_job_viewed_at", table_name="job_view_events"
    )
    op.drop_index(
        "ix_job_view_events_company_viewed_at", table_name="job_view_events"
    )
    op.drop_table("job_view_events")
