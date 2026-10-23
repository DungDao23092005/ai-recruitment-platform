"""add admin audit logs

Append-only audit trail for administrator user-management mutations
(lock / unlock / delete). Additive only: introduces a single new table and
its indexes, and does not alter any existing table.

Revision ID: add_admin_audit_logs
Revises: add_recruitment_analytics
Create Date: 2026-10-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mssql import NVARCHAR


revision: str = "add_admin_audit_logs"
down_revision: Union[str, None] = "add_recruitment_analytics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("admin_id", sa.Uuid(), nullable=False),
        sa.Column("target_user_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("reason", NVARCHAR(500), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["admin_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_audit_logs_created_at",
        "admin_audit_logs",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_audit_logs_admin_created",
        "admin_audit_logs",
        ["admin_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_audit_logs_target_created",
        "admin_audit_logs",
        ["target_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_audit_logs_action_created",
        "admin_audit_logs",
        ["action", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_admin_audit_logs_action_created",
        table_name="admin_audit_logs",
    )
    op.drop_index(
        "ix_admin_audit_logs_target_created",
        table_name="admin_audit_logs",
    )
    op.drop_index(
        "ix_admin_audit_logs_admin_created",
        table_name="admin_audit_logs",
    )
    op.drop_index(
        "ix_admin_audit_logs_created_at",
        table_name="admin_audit_logs",
    )
    op.drop_table("admin_audit_logs")
