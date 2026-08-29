"""create knowledge_documents table

Revision ID: 0006_knowledge_documents
Revises: 7c3a8d3084d3
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# revision identifiers, used by Alembic.
revision: str = '0006_knowledge_documents'
down_revision: Union[str, None] = '7c3a8d3084d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create knowledge_documents table
    op.create_table(
        'knowledge_documents',
        sa.Column('id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('visibility', sa.String(50), nullable=False, server_default='public'),
        sa.Column('status', sa.String(50), nullable=False, server_default='draft'),
        sa.Column('language', sa.String(10), nullable=False, server_default='vi'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create index for filtering by category, status, visibility
    op.create_index(
        'ix_knowledge_documents_category_status_visibility',
        'knowledge_documents',
        ['category', 'status', 'visibility'],
        mssql_where=sa.text("is_deleted = 0"),
    )

    # Create index for is_deleted for soft delete queries
    op.create_index(
        'ix_knowledge_documents_is_deleted',
        'knowledge_documents',
        ['is_deleted'],
    )


def downgrade() -> None:
    op.drop_index('ix_knowledge_documents_is_deleted', table_name='knowledge_documents')
    op.drop_index('ix_knowledge_documents_category_status_visibility', table_name='knowledge_documents')
    op.drop_table('knowledge_documents')