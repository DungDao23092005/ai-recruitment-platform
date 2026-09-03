"""alter_notifications_to_nvarchar

Revision ID: c37cd920e3f8
Revises: 0006_knowledge_documents
Create Date: 2026-09-03 10:34:55.896181

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mssql import NVARCHAR


# revision identifiers, used by Alembic.
revision: str = 'c37cd920e3f8'
down_revision: Union[str, None] = '0006_knowledge_documents'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER title -> NVARCHAR(255)
    op.alter_column(
        "notifications",
        "title",
        type_=NVARCHAR(255),
        existing_type=sa.String(255),
        existing_nullable=False,
    )
    # ALTER content -> NVARCHAR(MAX)
    op.alter_column(
        "notifications",
        "content",
        type_=NVARCHAR(),
        existing_type=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Revert title -> VARCHAR(255)
    op.alter_column(
        "notifications",
        "title",
        type_=sa.String(255),
        existing_type=NVARCHAR(255),
        existing_nullable=False,
    )
    # Revert content -> TEXT
    op.alter_column(
        "notifications",
        "content",
        type_=sa.Text(),
        existing_type=NVARCHAR(),
        existing_nullable=False,
    )
