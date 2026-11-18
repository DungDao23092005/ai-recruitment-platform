"""add reset_token_used to password_reset_otps

Tracks whether a password-reset token minted from an OTP row has already been
consumed. Existing rows are backfilled to ``0`` so currently valid, unexpired
reset tokens keep working.

Downgrade safety: before the column is dropped, rows whose token was consumed
under the new implementation are expired with ``GETUTCDATE()``. This prevents a
consumed token from becoming usable again under the old implementation. Rows
that were never consumed are left untouched.

Revision ID: b7d2e8f190c4
Revises: wave1_5_company_free
Create Date: 2026-11-18 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b7d2e8f190c4"
down_revision: Union[str, None] = "wave1_5_company_free"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "password_reset_otps",
        sa.Column(
            "reset_token_used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    # Defensive backfill for any pre-existing row not covered by the column
    # default (for example a provider that adds the column without filling it).
    op.execute(
        "UPDATE password_reset_otps "
        "SET reset_token_used = 0 "
        "WHERE reset_token_used IS NULL"
    )


def downgrade() -> None:
    # A token consumed by the new implementation must never become usable again
    # under the old implementation, which only checks ``expires_at``.
    op.execute(
        "UPDATE password_reset_otps "
        "SET expires_at = GETUTCDATE() "
        "WHERE reset_token_used = 1"
    )
    op.drop_column(
        "password_reset_otps",
        "reset_token_used",
        mssql_drop_default=True,
    )
