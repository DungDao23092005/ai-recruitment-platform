"""Company billing idempotency index and usage constraints.

Revision ID: company_billing
Revises: wave1_4_subscriptions
Create Date: 2026-04-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "company_billing"
down_revision: Union[str, None] = "wave1_4_subscriptions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(bind: sa.engine.Connection, table_name: str, index_name: str) -> bool:
    row = bind.execute(
        sa.text(
            "SELECT 1 FROM sys.indexes "
            "WHERE name = :index_name AND object_id = OBJECT_ID(:table_name)"
        ),
        {"index_name": index_name, "table_name": table_name},
    ).scalar()
    return row is not None


def check_duplicate_idempotency_keys(bind: sa.engine.Connection) -> list[str]:
    duplicate_rows = bind.execute(
        sa.text(
            """
            SELECT su.id, su.subscription_id, su.idempotency_key
            FROM subscription_usages su
            INNER JOIN (
                SELECT subscription_id, idempotency_key
                FROM subscription_usages
                WHERE idempotency_key IS NOT NULL
                GROUP BY subscription_id, idempotency_key
                HAVING COUNT(*) > 1
            ) dup
                ON su.subscription_id = dup.subscription_id
               AND su.idempotency_key = dup.idempotency_key
            ORDER BY su.subscription_id, su.idempotency_key, su.id
            """
        )
    ).fetchall()
    return [str(row[0]) for row in duplicate_rows]


_preflight_duplicate_idempotency_keys = check_duplicate_idempotency_keys


def upgrade() -> None:
    bind = op.get_bind()

    conflicting_ids = check_duplicate_idempotency_keys(bind)
    if conflicting_ids:
        raise RuntimeError(
            "Cannot create uq_subscription_usages_subscription_idempotency: "
            "duplicate (subscription_id, idempotency_key) rows found in "
            f"subscription_usages with IDs: {', '.join(conflicting_ids)}"
        )

    if _index_exists(bind, "subscription_usages", "uq_subscription_usage_idempotency"):
        op.drop_index(
            "uq_subscription_usage_idempotency",
            table_name="subscription_usages",
        )

    if _index_exists(
        bind,
        "subscription_usages",
        "uq_subscription_usages_subscription_idempotency",
    ):
        op.drop_index(
            "uq_subscription_usages_subscription_idempotency",
            table_name="subscription_usages",
        )

    op.create_index(
        "uq_subscription_usages_subscription_idempotency",
        "subscription_usages",
        ["subscription_id", "idempotency_key"],
        unique=True,
        mssql_where=sa.text("[idempotency_key] IS NOT NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()

    if _index_exists(
        bind,
        "subscription_usages",
        "uq_subscription_usages_subscription_idempotency",
    ):
        op.drop_index(
            "uq_subscription_usages_subscription_idempotency",
            table_name="subscription_usages",
        )

    if not _index_exists(bind, "subscription_usages", "uq_subscription_usage_idempotency"):
        op.create_index(
            "uq_subscription_usage_idempotency",
            "subscription_usages",
            ["subscription_id", "feature_type", "idempotency_key"],
            unique=True,
            mssql_where=sa.text("idempotency_key IS NOT NULL"),
        )
