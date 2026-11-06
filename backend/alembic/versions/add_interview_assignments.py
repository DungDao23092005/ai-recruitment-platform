"""add interview assignments and scorecard workflow state

Revision ID: add_interview_assignments
Revises: add_company_memberships
Create Date: 2026-11-05 00:00:00.000000

Scope amendment
---------------
This approved revision also adds the persistent scorecard workflow state to
``interview_evaluations`` (``status`` and nullable ``submitted_at``). It must
remain a single Alembic revision: no separate migration is allowed for the
draft/submit workflow.

Historical evaluations predate the workflow and are backfilled as
``submitted``. Their original submission timestamp is unknown, so
``submitted_at`` intentionally remains NULL for those rows. New evaluations
default to ``draft`` via the column server default.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_interview_assignments"
down_revision: Union[str, None] = "add_company_memberships"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "interview_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("interview_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"], ["interviews.id"], ondelete="NO ACTION"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="NO ACTION"
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_id"], ["users.id"], ondelete="NO ACTION"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_interview_assignments_active_interview_user",
        "interview_assignments",
        ["interview_id", "user_id"],
        unique=True,
        mssql_where=sa.text("is_deleted = 0"),
    )
    op.create_index(
        "ix_interview_assignments_user_active",
        "interview_assignments",
        ["user_id"],
        unique=False,
        mssql_where=sa.text("is_deleted = 0"),
    )
    op.create_index(
        "ix_interview_assignments_interview_active",
        "interview_assignments",
        ["interview_id"],
        unique=False,
        mssql_where=sa.text("is_deleted = 0"),
    )

    op.add_column(
        "interview_evaluations",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
    )
    op.add_column(
        "interview_evaluations",
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # Historical rows predate the workflow and are considered submitted.
    op.execute("UPDATE interview_evaluations SET status = 'submitted'")
    op.create_check_constraint(
        "ck_interview_evaluations_status",
        "interview_evaluations",
        "status IN ('draft', 'submitted')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_interview_evaluations_status",
        "interview_evaluations",
        type_="check",
    )
    op.drop_column("interview_evaluations", "submitted_at")
    # SQL Server refuses to drop a column while its server-default constraint
    # still exists, and the auto-generated constraint name is not stable.
    op.execute(
        """
        DECLARE @constraint sysname;
        SELECT @constraint = dc.name
        FROM sys.default_constraints AS dc
        JOIN sys.columns AS c
          ON c.object_id = dc.parent_object_id
         AND c.column_id = dc.parent_column_id
        WHERE dc.parent_object_id = OBJECT_ID('interview_evaluations')
          AND c.name = 'status';
        IF @constraint IS NOT NULL
        BEGIN
            DECLARE @sql nvarchar(max);
            SET @sql = N'ALTER TABLE interview_evaluations DROP CONSTRAINT '
                + QUOTENAME(@constraint);
            EXEC sp_executesql @sql;
        END
        """
    )
    op.drop_column("interview_evaluations", "status")
    op.drop_index(
        "ix_interview_assignments_interview_active",
        table_name="interview_assignments",
    )
    op.drop_index(
        "ix_interview_assignments_user_active",
        table_name="interview_assignments",
    )
    op.drop_index(
        "uq_interview_assignments_active_interview_user",
        table_name="interview_assignments",
    )
    op.drop_table("interview_assignments")
