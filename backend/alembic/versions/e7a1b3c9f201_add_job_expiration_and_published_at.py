"""add job expiration and published_at columns

Revision ID: e7a1b3c9f201
Revises: c5e8f19a0d12
Create Date: 2026-11-23 20:30:00.000000

"""

from datetime import datetime, timedelta, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e7a1b3c9f201"
down_revision: Union[str, None] = "c5e8f19a0d12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "expiration_duration_days",
            sa.Integer(),
            nullable=True,
            server_default=sa.text("30"),
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "is_qdrant_synced",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )

    # Backfill non-deleted PUBLISHED jobs with single UTC anchor
    migration_now = datetime.now(timezone.utc)
    jobs_table = sa.table(
        "jobs",
        sa.column("status", sa.String),
        sa.column("is_deleted", sa.Boolean),
        sa.column("published_at", sa.DateTime(timezone=True)),
        sa.column("expires_at", sa.DateTime(timezone=True)),
        sa.column("expiration_duration_days", sa.Integer),
        sa.column("is_qdrant_synced", sa.Boolean),
    )
    op.execute(
        jobs_table.update()
        .where(
            sa.and_(
                jobs_table.c.status == "published",
                jobs_table.c.is_deleted == sa.false(),
            )
        )
        .values(
            published_at=migration_now,
            expires_at=migration_now + timedelta(days=30),
            expiration_duration_days=30,
            is_qdrant_synced=True,
        )
    )

    op.create_index(
        "ix_jobs_status_expires_at",
        "jobs",
        ["status", "is_deleted", "expires_at"],
    )
    op.create_index(
        "ix_jobs_qdrant_unsynced",
        "jobs",
        ["status", "is_qdrant_synced", "updated_at"],
        mssql_where=sa.text(
            "status = 'expired' AND is_qdrant_synced = 0 AND is_deleted = 0"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_qdrant_unsynced", table_name="jobs")
    op.drop_index("ix_jobs_status_expires_at", table_name="jobs")
    op.drop_column("jobs", "is_qdrant_synced")
    op.drop_column("jobs", "expiration_duration_days")
    op.drop_column("jobs", "expires_at")
    op.drop_column("jobs", "published_at")
