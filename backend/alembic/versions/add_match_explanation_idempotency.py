"""add AI match explanation idempotency registry and application leases

Revision ID: add_match_explain_idempotency
Revises: add_interview_eval_uniqueness
Create Date: 2026-10-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mssql import NVARCHAR


revision: str = "add_match_explain_idempotency"
down_revision: Union[str, None] = "add_interview_eval_uniqueness"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_match_explanation_idempotency",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("owner_token", sa.String(length=36), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(length=20), nullable=False),
        sa.Column("response_payload", NVARCHAR, nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("SYSUTCDATETIME()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("SYSUTCDATETIME()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name="fk_match_idempotency_application",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_match_idempotency_user",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_match_idempotency_user_key",
        "ai_match_explanation_idempotency",
        ["user_id", "key_hash"],
        unique=True,
    )
    op.create_index(
        "ix_match_idempotency_app",
        "ai_match_explanation_idempotency",
        ["application_id"],
        unique=False,
    )

    op.create_table(
        "ai_match_explanation_application_leases",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("owner_token", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("SYSUTCDATETIME()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("SYSUTCDATETIME()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name="fk_match_lease_application",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("application_id"),
    )


def downgrade() -> None:
    op.drop_table("ai_match_explanation_application_leases")
    op.drop_index(
        "ix_match_idempotency_app",
        table_name="ai_match_explanation_idempotency",
    )
    op.drop_index(
        "uq_match_idempotency_user_key",
        table_name="ai_match_explanation_idempotency",
    )
    op.drop_table("ai_match_explanation_idempotency")
