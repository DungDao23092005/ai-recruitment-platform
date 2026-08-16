"""add_resume_parsed_data

Revision ID: 0002_resume_parsed_data
Revises: 0001_initial_schema
Create Date: 2026-08-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002_resume_parsed_data'
down_revision: Union[str, None] = '0001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'resumes',
        sa.Column('parsed_data', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('resumes', 'parsed_data')