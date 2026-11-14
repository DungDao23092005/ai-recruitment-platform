"""generalize admin audit targets

Allow the append-only admin audit ledger to record mutations whose target is
not a user (for example a recruitment plan). ``target_user_id`` becomes
nullable and is backfilled into the new generic ``target_id`` column so that
existing user-management rows keep their current semantics.

Revision ID: admin_audit_generic_target
Revises: company_billing
Create Date: 2026-11-14 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mssql import NVARCHAR


revision: str = "admin_audit_generic_target"
down_revision: Union[str, None] = "company_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _count_rows_lost_on_downgrade(bind: sa.engine.Connection) -> int:
    """Count rows that cannot be represented by the legacy user-only schema."""
    return int(
        bind.execute(
            sa.text(
                """
                SELECT COUNT(*)
                FROM admin_audit_logs
                WHERE target_type <> 'user' OR target_user_id IS NULL
                """
            )
        ).scalar_one()
    )


def upgrade() -> None:
    op.drop_index(
        "ix_admin_audit_logs_target_created",
        table_name="admin_audit_logs",
    )
    op.alter_column(
        "admin_audit_logs",
        "target_user_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.add_column(
        "admin_audit_logs",
        sa.Column("target_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "admin_audit_logs",
        sa.Column(
            "target_type",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
    )
    op.add_column(
        "admin_audit_logs",
        sa.Column("target_name", NVARCHAR(255), nullable=True),
    )

    op.execute(
        "UPDATE admin_audit_logs "
        "SET target_id = target_user_id "
        "WHERE target_id IS NULL"
    )

    op.create_index(
        "ix_admin_audit_logs_target_created",
        "admin_audit_logs",
        ["target_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_audit_logs_generic_target_created",
        "admin_audit_logs",
        ["target_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    lost_rows = _count_rows_lost_on_downgrade(bind)
    if lost_rows:
        raise RuntimeError(
            "Cannot downgrade admin_audit_generic_target: "
            f"{lost_rows} audit row(s) target a non-user entity or have no "
            "target_user_id. Archive those rows before downgrading."
        )

    op.drop_index(
        "ix_admin_audit_logs_generic_target_created",
        table_name="admin_audit_logs",
    )
    op.drop_index(
        "ix_admin_audit_logs_target_created",
        table_name="admin_audit_logs",
    )
    op.drop_column("admin_audit_logs", "target_name")
    op.drop_column(
        "admin_audit_logs",
        "target_type",
        mssql_drop_default=True,
    )
    op.drop_column("admin_audit_logs", "target_id")
    op.alter_column(
        "admin_audit_logs",
        "target_user_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.create_index(
        "ix_admin_audit_logs_target_created",
        "admin_audit_logs",
        ["target_user_id", "created_at"],
        unique=False,
    )
