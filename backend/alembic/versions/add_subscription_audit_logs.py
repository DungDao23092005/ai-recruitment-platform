"""add_subscription_audit_logs

Append-only audit trail for administrator subscription mutations
(provision / change-plan / revoke). Additive only: introduces a single new
table and its indexes, and does not alter any existing table.

Revision ID: add_sub_audit_logs
Revises: add_po_user_status_ix
Create Date: 2026-10-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mssql import NVARCHAR


# revision identifiers, used by Alembic.
revision: str = 'add_sub_audit_logs'
down_revision: Union[str, None] = 'add_po_user_status_ix'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'subscription_audit_logs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('admin_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('subscription_id', sa.Uuid(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('old_plan_id', sa.Uuid(), nullable=True),
        sa.Column('new_plan_id', sa.Uuid(), nullable=True),
        sa.Column('reason', NVARCHAR(500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['admin_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ),
        sa.ForeignKeyConstraint(['old_plan_id'], ['recruitment_plans.id'], ),
        sa.ForeignKeyConstraint(['new_plan_id'], ['recruitment_plans.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_subscription_audit_logs_subscription',
        'subscription_audit_logs',
        ['subscription_id', 'created_at'],
        unique=False,
    )
    op.create_index(
        'ix_subscription_audit_logs_user',
        'subscription_audit_logs',
        ['user_id', 'created_at'],
        unique=False,
    )
    op.create_index(
        'ix_subscription_audit_logs_admin',
        'subscription_audit_logs',
        ['admin_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_subscription_audit_logs_admin',
        table_name='subscription_audit_logs',
    )
    op.drop_index(
        'ix_subscription_audit_logs_user',
        table_name='subscription_audit_logs',
    )
    op.drop_index(
        'ix_subscription_audit_logs_subscription',
        table_name='subscription_audit_logs',
    )
    op.drop_table('subscription_audit_logs')
