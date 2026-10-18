"""alter users.lock_reason to NVARCHAR(500)

Administrators type the account lock reason in Vietnamese. The column was
originally created as ``VARCHAR(500)`` (see 7c3a8d3084d3), which silently
replaces any character outside the database codepage with ``?`` and destroys
the audit trail. This migration widens the column to ``NVARCHAR(500)`` so the
reason round-trips losslessly, mirroring the other Unicode columns converted
in 911b0cc53b2a.

The downgrade is intentionally guarded: reverting to ``VARCHAR`` is lossy for
one-way (non-codepage) characters, so it refuses to run while any stored
reason would be corrupted. Operators must clear or transliterate those values
first.

Revision ID: alter_lock_reason_nvarchar
Revises: add_sub_audit_logs
Create Date: 2026-10-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mssql import NVARCHAR


# revision identifiers, used by Alembic.
revision: str = 'alter_lock_reason_nvarchar'
down_revision: Union[str, None] = 'add_sub_audit_logs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# A row is "lossy" when casting the stored NVARCHAR value down to VARCHAR and
# back to NVARCHAR no longer equals the original. The BIN2 collation forces a
# code-point comparison so accent/case-insensitive database collations cannot
# hide corruption.
LOSSY_LOCK_REASON_QUERY = sa.text(
    """
    SELECT id, lock_reason
    FROM users
    WHERE lock_reason IS NOT NULL
      AND CAST(CAST(lock_reason AS VARCHAR(500)) AS NVARCHAR(500))
            COLLATE Latin1_General_BIN2
          <> lock_reason COLLATE Latin1_General_BIN2
    """
)


def _lossy_lock_reason_rows(connection) -> list:
    """Return ``(id, lock_reason)`` rows that would not survive a VARCHAR cast."""
    return list(connection.execute(LOSSY_LOCK_REASON_QUERY).fetchall())


def _assert_downgrade_safe(connection) -> None:
    """Refuse an NVARCHAR -> VARCHAR downgrade when it would corrupt data."""
    lossy = _lossy_lock_reason_rows(connection)
    if lossy:
        raise RuntimeError(
            "Refusing to downgrade users.lock_reason to VARCHAR(500): "
            f"{len(lossy)} row(s) contain characters that the database codepage "
            "cannot represent and would be replaced with '?'. Clear or "
            "transliterate those lock reasons before downgrading."
        )


def upgrade() -> None:
    op.alter_column(
        "users",
        "lock_reason",
        type_=NVARCHAR(500),
        existing_type=sa.String(500),
        existing_nullable=True,
    )


def downgrade() -> None:
    _assert_downgrade_safe(op.get_bind())
    op.alter_column(
        "users",
        "lock_reason",
        type_=sa.String(500),
        existing_type=NVARCHAR(500),
        existing_nullable=True,
    )
