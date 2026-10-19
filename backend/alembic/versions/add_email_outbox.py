"""add durable email_outbox table

Introduces the transactional outbox backing durable business notification
emails (account lock/delete, subscription lifecycle, VNPAY receipt). The table
is additive only and does not alter any existing table.

The downgrade is guarded: dropping the table would irreversibly lose any queued
(PENDING/PROCESSING) or failed (FAILED) notification that has not been delivered
yet, so it refuses to run while such rows exist. Only already-delivered (SENT)
history is discarded silently, because that is an audit convenience and never a
pending side effect.

Revision ID: add_email_outbox
Revises: alter_lock_reason_nvarchar
Create Date: 2026-10-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mssql import NVARCHAR


# revision identifiers, used by Alembic.
revision: str = 'add_email_outbox'
down_revision: Union[str, None] = 'alter_lock_reason_nvarchar'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Rows that represent work that has not finished yet (or failed). Losing them
# would silently drop a user-visible notification, so the downgrade refuses.
UNFINISHED_STATUSES = ("pending", "processing", "failed")

REMAINING_UNFINISHED_QUERY = sa.text(
    """
    SELECT status, COUNT(*) AS row_count
    FROM email_outbox
    WHERE status IN ('pending', 'processing', 'failed')
    GROUP BY status
    """
)


def _remaining_unfinished_counts(connection) -> list:
    """Return ``(status, count)`` pairs for rows that are not SENT."""
    return list(connection.execute(REMAINING_UNFINISHED_QUERY).fetchall())


def _assert_downgrade_safe(connection) -> None:
    """Refuse to drop the outbox while any notification is still unfinished."""
    remaining = _remaining_unfinished_counts(connection)
    if remaining:
        detail = ", ".join(f"{status}={count}" for status, count in remaining)
        raise RuntimeError(
            "Refusing to drop email_outbox: there are still unfinished "
            f"notifications ({detail}). Deliver or explicitly discard them "
            "first (e.g. mark them SENT or delete the rows) before downgrading, "
            "otherwise those emails would be lost without a trace."
        )


def upgrade() -> None:
    op.create_table(
        'email_outbox',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('to_email', NVARCHAR(320), nullable=False),
        sa.Column('subject', NVARCHAR(500), nullable=False),
        sa.Column('html_body', NVARCHAR, nullable=False),
        sa.Column('text_body', NVARCHAR, nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('max_attempts', sa.Integer(), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('processing_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', NVARCHAR(1000), nullable=True),
        sa.Column('idempotency_key', NVARCHAR(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_email_outbox_status_next_attempt',
        'email_outbox',
        ['status', 'next_attempt_at'],
        unique=False,
    )
    op.create_index(
        'ix_email_outbox_status_processing_started',
        'email_outbox',
        ['status', 'processing_started_at'],
        unique=False,
    )
    op.create_index(
        'uq_email_outbox_idempotency_key',
        'email_outbox',
        ['idempotency_key'],
        unique=True,
        mssql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    _assert_downgrade_safe(op.get_bind())
    op.drop_index(
        'uq_email_outbox_idempotency_key',
        table_name='email_outbox',
    )
    op.drop_index(
        'ix_email_outbox_status_processing_started',
        table_name='email_outbox',
    )
    op.drop_index(
        'ix_email_outbox_status_next_attempt',
        table_name='email_outbox',
    )
    op.drop_table('email_outbox')
