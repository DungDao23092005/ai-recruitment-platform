"""Add Wave 1.4 dual-track subscription schema, constraints, and filtered indexes.

Revision ID: wave1_4_subscriptions
Revises: add_interview_assignments
Create Date: 2026-04-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "wave1_4_subscriptions"
down_revision: Union[str, Sequence[str], None] = "add_interview_assignments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _run_preflight_checks(bind: sa.Connection) -> None:
    """Validate historical data invariants before schema migration and index creation.

    Fails fast with exact affected IDs rather than silently deleting, expiring,
    or reclassifying historical records.
    """
    # Preflight 1: Duplicate active subscriptions per user
    duplicate_active_rows = bind.execute(
        sa.text(
            """
            SELECT
                user_id,
                COUNT(*) AS active_count,
                STRING_AGG(CAST(id AS NVARCHAR(36)), ', ') AS subscription_ids,
                STRING_AGG(CAST(plan_id AS NVARCHAR(36)), ', ') AS plan_ids,
                MIN(started_at) AS earliest_started_at,
                MAX(expires_at) AS latest_expires_at
            FROM subscriptions
            WHERE status = 'active' AND is_deleted = 0
            GROUP BY user_id
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    if duplicate_active_rows:
        details = "; ".join(
            f"user_id={row.user_id} (active_count={row.active_count}, "
            f"subscription_ids=[{row.subscription_ids}], plan_ids=[{row.plan_ids}])"
            for row in duplicate_active_rows
        )
        raise RuntimeError(
            "Wave 1.4 preflight failed: duplicate active subscriptions found for user(s): "
            f"{details}"
        )

    # Preflight 2: Historical user_id IS NULL verification
    for table_name in ("subscriptions", "payment_orders", "subscription_usages"):
        null_user_rows = bind.execute(
            sa.text(f"SELECT id FROM {table_name} WHERE user_id IS NULL")
        ).fetchall()
        if null_user_rows:
            affected_ids = ", ".join(str(row.id) for row in null_user_rows)
            raise RuntimeError(
                f"Wave 1.4 preflight failed: {table_name} contains rows with NULL user_id: "
                f"[{affected_ids}]"
            )

    # Preflight 3: Orphaned subscription_usages verification
    orphaned_usage_rows = bind.execute(
        sa.text(
            """
            SELECT u.id, u.subscription_id
            FROM subscription_usages u
            LEFT JOIN subscriptions s ON u.subscription_id = s.id
            WHERE s.id IS NULL
            """
        )
    ).fetchall()
    if orphaned_usage_rows:
        details = ", ".join(
            f"(usage_id={row.id}, subscription_id={row.subscription_id})"
            for row in orphaned_usage_rows
        )
        raise RuntimeError(
            "Wave 1.4 preflight failed: orphaned subscription_usages rows found without parent "
            f"subscription: [{details}]"
        )


def _drop_column_default_constraint(table_name: str, column_name: str) -> None:
    op.execute(
        f"""
        DECLARE @constraint_name NVARCHAR(256);
        SELECT @constraint_name = dc.name
        FROM sys.default_constraints dc
        INNER JOIN sys.columns c
            ON dc.parent_object_id = c.object_id
            AND dc.parent_column_id = c.column_id
        WHERE dc.parent_object_id = OBJECT_ID(N'{table_name}')
          AND c.name = N'{column_name}';
        IF @constraint_name IS NOT NULL
            EXEC(N'ALTER TABLE {table_name} DROP CONSTRAINT [' + @constraint_name + N']');
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    _run_preflight_checks(bind)

    # 1. recruitment_plans
    op.add_column(
        "recruitment_plans",
        sa.Column(
            "plan_audience",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'company'"),
        ),
    )
    op.add_column(
        "recruitment_plans",
        sa.Column(
            "is_free",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_check_constraint(
        "ck_recruitment_plans_audience",
        "recruitment_plans",
        "plan_audience IN ('company', 'candidate')",
    )
    op.create_check_constraint(
        "ck_recruitment_plans_free_candidate",
        "recruitment_plans",
        "is_free = 0 OR plan_audience = 'candidate'",
    )
    op.create_index(
        "ix_recruitment_plans_audience_active",
        "recruitment_plans",
        ["plan_audience", "is_active", "display_order"],
        unique=False,
        mssql_where=sa.text("is_deleted = 0"),
    )
    op.create_index(
        "uq_recruitment_plans_active_candidate_free",
        "recruitment_plans",
        ["plan_audience", "is_free"],
        unique=True,
        mssql_where=sa.text(
            "is_active = 1 AND is_deleted = 0 AND plan_audience = 'candidate' AND is_free = 1"
        ),
    )

    # 2. subscriptions
    op.add_column(
        "subscriptions",
        sa.Column("company_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column(
            "scope",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'legacy_recruiter_personal'"),
        ),
    )
    op.add_column(
        "subscriptions",
        sa.Column(
            "is_free",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "subscriptions",
        sa.Column("current_period_key", sa.String(length=7), nullable=True),
    )
    op.create_foreign_key(
        "fk_subscriptions_company_id_companies",
        "subscriptions",
        "companies",
        ["company_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_subscriptions_scope_valid",
        "subscriptions",
        "scope IN ('company_recruiting', 'candidate_personal', 'legacy_recruiter_personal')",
    )
    op.create_check_constraint(
        "ck_subscriptions_scope_company_pairing",
        "subscriptions",
        "(scope = 'company_recruiting' AND company_id IS NOT NULL) OR "
        "(scope IN ('candidate_personal', 'legacy_recruiter_personal') AND company_id IS NULL)",
    )
    op.create_check_constraint(
        "ck_subscriptions_free_candidate",
        "subscriptions",
        "is_free = 0 OR scope = 'candidate_personal'",
    )
    op.create_index(
        "uq_subscriptions_active_company",
        "subscriptions",
        ["company_id"],
        unique=True,
        mssql_where=sa.text(
            "status = 'active' AND is_deleted = 0 AND scope = 'company_recruiting'"
        ),
    )
    op.create_index(
        "uq_subscriptions_candidate_paid",
        "subscriptions",
        ["user_id"],
        unique=True,
        mssql_where=sa.text(
            "status = 'active' AND is_deleted = 0 AND scope = 'candidate_personal' AND is_free = 0"
        ),
    )
    op.create_index(
        "uq_subscriptions_candidate_free",
        "subscriptions",
        ["user_id"],
        unique=True,
        mssql_where=sa.text(
            "status = 'active' AND is_deleted = 0 AND scope = 'candidate_personal' AND is_free = 1"
        ),
    )
    op.create_index(
        "uq_subscriptions_legacy_user",
        "subscriptions",
        ["user_id"],
        unique=True,
        mssql_where=sa.text(
            "status = 'active' AND is_deleted = 0 AND scope = 'legacy_recruiter_personal'"
        ),
    )

    # 3. payment_orders
    op.add_column(
        "payment_orders",
        sa.Column("company_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "payment_orders",
        sa.Column(
            "scope",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'legacy_recruiter_personal'"),
        ),
    )
    op.create_foreign_key(
        "fk_payment_orders_company_id_companies",
        "payment_orders",
        "companies",
        ["company_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_payment_orders_scope_valid",
        "payment_orders",
        "scope IN ('company_recruiting', 'candidate_personal', 'legacy_recruiter_personal')",
    )
    op.create_check_constraint(
        "ck_payment_orders_scope_company_pairing",
        "payment_orders",
        "(scope = 'company_recruiting' AND company_id IS NOT NULL) OR "
        "(scope IN ('candidate_personal', 'legacy_recruiter_personal') AND company_id IS NULL)",
    )
    op.create_index(
        "ix_payment_orders_company_id_status",
        "payment_orders",
        ["company_id", "status"],
        unique=False,
        mssql_where=sa.text("company_id IS NOT NULL"),
    )
    op.create_index(
        "ix_payment_orders_user_id_scope",
        "payment_orders",
        ["user_id", "scope", "status"],
        unique=False,
    )

    # 4. subscription_usages (strict 6-step backfill & constraint order)
    op.add_column(
        "subscription_usages",
        sa.Column("company_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_subscription_usages_company_id_companies",
        "subscription_usages",
        "companies",
        ["company_id"],
        ["id"],
    )
    op.add_column(
        "subscription_usages",
        sa.Column("period_key", sa.String(length=7), nullable=True),
    )

    # Step 1: Add subscription_usages.scope as nullable without premature NOT NULL or default
    op.add_column(
        "subscription_usages",
        sa.Column("scope", sa.String(length=50), nullable=True),
    )

    # Step 2: Backfill from the referenced parent subscription
    op.execute(
        """
        UPDATE u
        SET u.scope = s.scope
        FROM subscription_usages u
        INNER JOIN subscriptions s ON u.subscription_id = s.id
        """
    )

    # Step 3 & 4: Validate that no rows remain NULL; abort if any orphaned records exist
    remaining_null_usages = bind.execute(
        sa.text(
            "SELECT id, subscription_id FROM subscription_usages WHERE scope IS NULL"
        )
    ).fetchall()
    if remaining_null_usages:
        details = ", ".join(
            f"(usage_id={row.id}, subscription_id={row.subscription_id})"
            for row in remaining_null_usages
        )
        raise RuntimeError(
            "Wave 1.4 backfill failed: subscription_usages rows remain with NULL scope "
            f"after parent subscription backfill: [{details}]"
        )

    # Step 5: Alter the column to NOT NULL and establish the transitional server default
    op.alter_column(
        "subscription_usages",
        "scope",
        existing_type=sa.String(length=50),
        nullable=False,
        server_default=sa.text("'legacy_recruiter_personal'"),
    )

    # Step 6: Apply the scope and company_id CHECK constraints and indexes
    op.create_check_constraint(
        "ck_subscription_usages_scope_valid",
        "subscription_usages",
        "scope IN ('company_recruiting', 'candidate_personal', 'legacy_recruiter_personal')",
    )
    op.create_check_constraint(
        "ck_subscription_usages_scope_company_pairing",
        "subscription_usages",
        "(scope = 'company_recruiting' AND company_id IS NOT NULL) OR "
        "(scope IN ('candidate_personal', 'legacy_recruiter_personal') AND company_id IS NULL)",
    )
    op.create_index(
        "ix_subscription_usages_company_period",
        "subscription_usages",
        ["company_id", "period_key", "feature_type", "status"],
        unique=False,
        mssql_where=sa.text("company_id IS NOT NULL"),
    )
    op.create_index(
        "ix_subscription_usages_user_period",
        "subscription_usages",
        ["user_id", "period_key", "feature_type", "status"],
        unique=False,
    )


def downgrade() -> None:
    # 4. subscription_usages
    op.drop_index("ix_subscription_usages_user_period", table_name="subscription_usages")
    op.drop_index("ix_subscription_usages_company_period", table_name="subscription_usages")
    op.drop_constraint(
        "ck_subscription_usages_scope_company_pairing",
        "subscription_usages",
        type_="check",
    )
    op.drop_constraint(
        "ck_subscription_usages_scope_valid",
        "subscription_usages",
        type_="check",
    )
    op.drop_constraint(
        "fk_subscription_usages_company_id_companies",
        "subscription_usages",
        type_="foreignkey",
    )
    _drop_column_default_constraint("subscription_usages", "scope")
    op.drop_column("subscription_usages", "scope")
    op.drop_column("subscription_usages", "period_key")
    op.drop_column("subscription_usages", "company_id")

    # 3. payment_orders
    op.drop_index("ix_payment_orders_user_id_scope", table_name="payment_orders")
    op.drop_index("ix_payment_orders_company_id_status", table_name="payment_orders")
    op.drop_constraint(
        "ck_payment_orders_scope_company_pairing",
        "payment_orders",
        type_="check",
    )
    op.drop_constraint(
        "ck_payment_orders_scope_valid",
        "payment_orders",
        type_="check",
    )
    op.drop_constraint(
        "fk_payment_orders_company_id_companies",
        "payment_orders",
        type_="foreignkey",
    )
    _drop_column_default_constraint("payment_orders", "scope")
    op.drop_column("payment_orders", "scope")
    op.drop_column("payment_orders", "company_id")

    # 2. subscriptions
    op.drop_index("uq_subscriptions_legacy_user", table_name="subscriptions")
    op.drop_index("uq_subscriptions_candidate_free", table_name="subscriptions")
    op.drop_index("uq_subscriptions_candidate_paid", table_name="subscriptions")
    op.drop_index("uq_subscriptions_active_company", table_name="subscriptions")
    op.drop_constraint(
        "ck_subscriptions_free_candidate",
        "subscriptions",
        type_="check",
    )
    op.drop_constraint(
        "ck_subscriptions_scope_company_pairing",
        "subscriptions",
        type_="check",
    )
    op.drop_constraint(
        "ck_subscriptions_scope_valid",
        "subscriptions",
        type_="check",
    )
    op.drop_constraint(
        "fk_subscriptions_company_id_companies",
        "subscriptions",
        type_="foreignkey",
    )
    op.drop_column("subscriptions", "current_period_key")
    _drop_column_default_constraint("subscriptions", "is_free")
    op.drop_column("subscriptions", "is_free")
    _drop_column_default_constraint("subscriptions", "scope")
    op.drop_column("subscriptions", "scope")
    op.drop_column("subscriptions", "company_id")

    # 1. recruitment_plans
    op.drop_index(
        "uq_recruitment_plans_active_candidate_free",
        table_name="recruitment_plans",
    )
    op.drop_index(
        "ix_recruitment_plans_audience_active",
        table_name="recruitment_plans",
    )
    op.drop_constraint(
        "ck_recruitment_plans_free_candidate",
        "recruitment_plans",
        type_="check",
    )
    op.drop_constraint(
        "ck_recruitment_plans_audience",
        "recruitment_plans",
        type_="check",
    )
    _drop_column_default_constraint("recruitment_plans", "is_free")
    op.drop_column("recruitment_plans", "is_free")
    _drop_column_default_constraint("recruitment_plans", "plan_audience")
    op.drop_column("recruitment_plans", "plan_audience")
