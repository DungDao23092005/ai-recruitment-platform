"""add declined_at to company_invitations

Revision ID: c5e8f19a0d12
Revises: b7d2e8f190c4
Create Date: 2026-11-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c5e8f19a0d12"
down_revision: Union[str, None] = "b7d2e8f190c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "company_invitations",
        sa.Column(
            "declined_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("company_invitations", "declined_at")
