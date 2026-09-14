"""add_job_structured_criteria

Revision ID: 3c57e134e916
Revises: 911b0cc53b2a
Create Date: 2026-09-14 16:22:35.024519

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mssql import NVARCHAR


# revision identifiers, used by Alembic.
revision: str = '3c57e134e916'
down_revision: Union[str, None] = '911b0cc53b2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add minimum_years_experience column to jobs table
    op.add_column(
        'jobs',
        sa.Column('minimum_years_experience', sa.Float(), nullable=True)
    )
    # Add education_level column to jobs table
    op.add_column(
        'jobs',
        sa.Column(
            'education_level',
            sa.String(255).with_variant(NVARCHAR(255), 'mssql'),
            nullable=True
        )
    )


def downgrade() -> None:
    op.drop_column('jobs', 'education_level')
    op.drop_column('jobs', 'minimum_years_experience')
