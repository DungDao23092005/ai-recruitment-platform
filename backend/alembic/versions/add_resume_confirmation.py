"""add resume confirmation lifecycle fields

Revision ID: add_resume_confirmation
Revises: add_match_explain_idempotency
Create Date: 2026-10-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_resume_confirmation"
down_revision: Union[str, None] = "add_match_explain_idempotency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "resumes",
        sa.Column(
            "is_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "resumes",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_resumes_candidate_confirmation",
        "resumes",
        ["candidate_id", "is_confirmed", "is_primary"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_resumes_candidate_confirmation", table_name="resumes")
    op.drop_column("resumes", "confirmed_at")
    op.drop_column("resumes", "is_confirmed")
