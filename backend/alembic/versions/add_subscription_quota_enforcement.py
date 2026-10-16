"""add_subscription_quota_enforcement

Revision ID: add_subscription_quota_enforcement
Revises: 47c75548f388
Create Date: 2026-10-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mssql import NVARCHAR


# revision identifiers, used by Alembic.
revision: str = 'sub_quota_enforcement'
down_revision: Union[str, None] = '47c75548f388'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create subscription_usages table
    op.create_table(
        'subscription_usages',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('subscription_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('feature_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='reserved'),
        sa.Column('reference_id', sa.Uuid(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=255), nullable=True),
        sa.Column('amount', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('finalized_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        'ix_subscription_usages_subscription_feature_status',
        'subscription_usages',
        ['subscription_id', 'feature_type', 'status'],
        unique=False
    )
    op.create_index(
        'ix_subscription_usages_user_feature_status',
        'subscription_usages',
        ['user_id', 'feature_type', 'status'],
        unique=False
    )
    op.create_index(
        'ix_subscription_usages_reference',
        'subscription_usages',
        ['reference_id'],
        unique=False
    )
    # Filtered unique index for idempotency_key (allows multiple NULLs)
    # Created via raw SQL for SQL Server compatibility
    op.execute("""
        CREATE UNIQUE INDEX uq_subscription_usage_idempotency
        ON subscription_usages (subscription_id, feature_type, idempotency_key)
        WHERE idempotency_key IS NOT NULL
    """)

    # Add quota snapshot and usage counter columns to subscriptions table
    op.add_column('subscriptions', sa.Column('max_job_posts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('subscriptions', sa.Column('max_candidate_searches', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('subscriptions', sa.Column('max_ai_features', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('subscriptions', sa.Column('job_posts_used', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('subscriptions', sa.Column('candidate_searches_used', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('subscriptions', sa.Column('ai_features_used', sa.Integer(), nullable=False, server_default='0'))

    # Backfill quota snapshot for existing active subscriptions from their plan
    # This is done in a separate data migration step
    # The policy: for active subscriptions, snapshot from plan; for expired/cancelled, snapshot from plan
    # job_posts_used = 0 at cutover (grandfathered existing published jobs)
    # candidate_searches_used = 0
    # ai_features_used = 0

    op.execute("""
        UPDATE subscriptions
        SET
            max_job_posts = rp.max_job_posts,
            max_candidate_searches = COALESCE(rp.max_candidate_searches, 0),
            max_ai_features = COALESCE(rp.max_ai_features, 0),
            job_posts_used = 0,
            candidate_searches_used = 0,
            ai_features_used = 0
        FROM recruitment_plans rp
        WHERE subscriptions.plan_id = rp.id
    """)


def downgrade() -> None:
    # Drop columns from subscriptions
    op.drop_column('subscriptions', 'ai_features_used')
    op.drop_column('subscriptions', 'candidate_searches_used')
    op.drop_column('subscriptions', 'job_posts_used')
    op.drop_column('subscriptions', 'max_ai_features')
    op.drop_column('subscriptions', 'max_candidate_searches')
    op.drop_column('subscriptions', 'max_job_posts')

    # Drop indexes and table
    op.execute("DROP INDEX uq_subscription_usage_idempotency ON subscription_usages")
    op.drop_index('ix_subscription_usages_reference', table_name='subscription_usages')
    op.drop_index('ix_subscription_usages_user_feature_status', table_name='subscription_usages')
    op.drop_index('ix_subscription_usages_subscription_feature_status', table_name='subscription_usages')
    op.drop_table('subscription_usages')