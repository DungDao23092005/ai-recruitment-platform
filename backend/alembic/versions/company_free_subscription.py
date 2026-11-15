"""Allow Company Free plans and company-scoped free subscriptions.

Revision ID: wave1_5_company_free
Revises: admin_audit_generic_target
Create Date: 2026-11-15 00:00:00.000000

The database previously allowed ``is_free`` only for the Candidate audience and
only for the ``candidate_personal`` subscription scope. Company Free V1
introduces a canonical Company Free plan and a Company-scoped free
subscription, so the two free-plan checks are widened while keeping the
existing Candidate Free and one-active-company-subscription guarantees.

Downgrading is only safe when no Company Free catalog or subscription row of
any lifecycle state exists. The preflight runs before any DDL and raises an
explicit error when rows are present.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "wave1_5_company_free"
down_revision: Union[str, None] = "admin_audit_generic_target"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_PLAN_FREE_CONSTRAINT = "ck_recruitment_plans_free_candidate"
NEW_PLAN_FREE_CONSTRAINT = "ck_recruitment_plans_free_audience"
OLD_SUBSCRIPTION_FREE_CONSTRAINT = "ck_subscriptions_free_candidate"
NEW_SUBSCRIPTION_FREE_CONSTRAINT = "ck_subscriptions_free_scope"
COMPANY_FREE_INDEX = "uq_recruitment_plans_active_company_free"


def _index_exists(
    bind: sa.engine.Connection, table_name: str, index_name: str
) -> bool:
    row = bind.execute(
        sa.text(
            "SELECT 1 FROM sys.indexes "
            "WHERE name = :index_name AND object_id = OBJECT_ID(:table_name)"
        ),
        {"index_name": index_name, "table_name": table_name},
    ).scalar()
    return row is not None


def _check_constraint_exists(
    bind: sa.engine.Connection, table_name: str, constraint_name: str
) -> bool:
    row = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM sys.check_constraints
            WHERE name = :constraint_name
              AND parent_object_id = OBJECT_ID(:table_name)
            """
        ),
        {"constraint_name": constraint_name, "table_name": table_name},
    ).scalar()
    return row is not None


def _count_company_free_plans(bind: sa.engine.Connection) -> int:
    return int(
        bind.execute(
            sa.text(
                """
                SELECT COUNT(*)
                FROM recruitment_plans
                WHERE plan_audience = 'company' AND is_free = 1
                """
            )
        ).scalar_one()
    )


def _count_company_free_subscriptions(bind: sa.engine.Connection) -> int:
    return int(
        bind.execute(
            sa.text(
                """
                SELECT COUNT(*)
                FROM subscriptions
                WHERE scope = 'company_recruiting' AND is_free = 1
                """
            )
        ).scalar_one()
    )


def upgrade() -> None:
    bind = op.get_bind()

    if _check_constraint_exists(
        bind, "recruitment_plans", OLD_PLAN_FREE_CONSTRAINT
    ):
        op.drop_constraint(
            OLD_PLAN_FREE_CONSTRAINT,
            "recruitment_plans",
            type_="check",
        )
    if not _check_constraint_exists(
        bind, "recruitment_plans", NEW_PLAN_FREE_CONSTRAINT
    ):
        op.create_check_constraint(
            NEW_PLAN_FREE_CONSTRAINT,
            "recruitment_plans",
            "is_free = 0 OR plan_audience IN ('candidate', 'company')",
        )

    if not _index_exists(
        bind, "recruitment_plans", COMPANY_FREE_INDEX
    ):
        op.create_index(
            COMPANY_FREE_INDEX,
            "recruitment_plans",
            ["plan_audience", "is_free"],
            unique=True,
            mssql_where=sa.text(
                "is_active = 1 AND is_deleted = 0 "
                "AND plan_audience = 'company' AND is_free = 1"
            ),
        )

    if _check_constraint_exists(
        bind, "subscriptions", OLD_SUBSCRIPTION_FREE_CONSTRAINT
    ):
        op.drop_constraint(
            OLD_SUBSCRIPTION_FREE_CONSTRAINT,
            "subscriptions",
            type_="check",
        )
    if not _check_constraint_exists(
        bind, "subscriptions", NEW_SUBSCRIPTION_FREE_CONSTRAINT
    ):
        op.create_check_constraint(
            NEW_SUBSCRIPTION_FREE_CONSTRAINT,
            "subscriptions",
            "is_free = 0 OR scope IN ('candidate_personal', 'company_recruiting')",
        )


def downgrade() -> None:
    bind = op.get_bind()

    company_free_plans = _count_company_free_plans(bind)
    if company_free_plans:
        raise RuntimeError(
            "Cannot downgrade wave1_5_company_free: "
            f"{company_free_plans} Company Free plan row(s) exist in "
            "recruitment_plans. Company Free is an active product entitlement; "
            "archive or delete every Company Free plan row before downgrading. "
            "No schema changes were applied."
        )

    company_free_subscriptions = _count_company_free_subscriptions(bind)
    if company_free_subscriptions:
        raise RuntimeError(
            "Cannot downgrade wave1_5_company_free: "
            f"{company_free_subscriptions} Company Free subscription row(s) "
            "exist in subscriptions. Company Free is an active product "
            "entitlement; archive or delete every company-scoped free "
            "subscription before downgrading. No schema changes were applied."
        )

    if _index_exists(bind, "recruitment_plans", COMPANY_FREE_INDEX):
        op.drop_index(
            COMPANY_FREE_INDEX,
            table_name="recruitment_plans",
        )

    if _check_constraint_exists(
        bind, "subscriptions", NEW_SUBSCRIPTION_FREE_CONSTRAINT
    ):
        op.drop_constraint(
            NEW_SUBSCRIPTION_FREE_CONSTRAINT,
            "subscriptions",
            type_="check",
        )
    if not _check_constraint_exists(
        bind, "subscriptions", OLD_SUBSCRIPTION_FREE_CONSTRAINT
    ):
        op.create_check_constraint(
            OLD_SUBSCRIPTION_FREE_CONSTRAINT,
            "subscriptions",
            "is_free = 0 OR scope = 'candidate_personal'",
        )

    if _check_constraint_exists(
        bind, "recruitment_plans", NEW_PLAN_FREE_CONSTRAINT
    ):
        op.drop_constraint(
            NEW_PLAN_FREE_CONSTRAINT,
            "recruitment_plans",
            type_="check",
        )
    if not _check_constraint_exists(
        bind, "recruitment_plans", OLD_PLAN_FREE_CONSTRAINT
    ):
        op.create_check_constraint(
            OLD_PLAN_FREE_CONSTRAINT,
            "recruitment_plans",
            "is_free = 0 OR plan_audience = 'candidate'",
        )
