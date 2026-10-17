"""add_payment_orders_user_status_index

Adds a composite index to speed up the user-scoped payment-order lookups that
the checkout guards and reconciliation paths rely on:
 * active pending checkout lookup: user_id + status (+ provider, expired_at,
   is_deleted)
 * paid-order-with-pending-subscription incident lookup: user_id + status

Revision ID: add_po_user_status_ix
Revises: sub_quota_enforcement
Create Date: 2026-10-17 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'add_po_user_status_ix'
down_revision: Union[str, None] = 'sub_quota_enforcement'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_payment_orders_user_id_status',
        'payment_orders',
        ['user_id', 'status'],
        unique=False,
        mssql_include=['expired_at', 'provider', 'is_deleted'],
    )


def downgrade() -> None:
    op.drop_index('ix_payment_orders_user_id_status', table_name='payment_orders')
