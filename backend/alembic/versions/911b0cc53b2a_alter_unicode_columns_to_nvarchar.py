"""alter_unicode_columns_to_nvarchar

Revision ID: 911b0cc53b2a
Revises: c37cd920e3f8
Create Date: 2026-09-11 01:30:13.169723

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mssql import NVARCHAR


# revision identifiers, used by Alembic.
revision: str = '911b0cc53b2a'
down_revision: Union[str, None] = 'c37cd920e3f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # jobs.title -> NVARCHAR(255)
    op.alter_column(
        "jobs",
        "title",
        type_=NVARCHAR(255),
        existing_type=sa.String(255),
        existing_nullable=False,
    )
    # companies.name -> NVARCHAR(255)
    op.alter_column(
        "companies",
        "name",
        type_=NVARCHAR(255),
        existing_type=sa.String(255),
        existing_nullable=False,
    )
    # knowledge_documents.title -> NVARCHAR(255)
    op.alter_column(
        "knowledge_documents",
        "title",
        type_=NVARCHAR(255),
        existing_type=sa.String(255),
        existing_nullable=False,
    )
    # candidate_profiles.full_name -> NVARCHAR(255)
    op.alter_column(
        "candidate_profiles",
        "full_name",
        type_=NVARCHAR(255),
        existing_type=sa.String(255),
        existing_nullable=True,
    )
    # recruiter_profiles.full_name -> NVARCHAR(255)
    op.alter_column(
        "recruiter_profiles",
        "full_name",
        type_=NVARCHAR(255),
        existing_type=sa.String(255),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Revert jobs.title -> VARCHAR(255)
    op.alter_column(
        "jobs",
        "title",
        type_=sa.String(255),
        existing_type=NVARCHAR(255),
        existing_nullable=False,
    )
    # Revert companies.name -> VARCHAR(255)
    op.alter_column(
        "companies",
        "name",
        type_=sa.String(255),
        existing_type=NVARCHAR(255),
        existing_nullable=False,
    )
    # Revert knowledge_documents.title -> VARCHAR(255)
    op.alter_column(
        "knowledge_documents",
        "title",
        type_=sa.String(255),
        existing_type=NVARCHAR(255),
        existing_nullable=False,
    )
    # Revert candidate_profiles.full_name -> VARCHAR(255)
    op.alter_column(
        "candidate_profiles",
        "full_name",
        type_=sa.String(255),
        existing_type=NVARCHAR(255),
        existing_nullable=True,
    )
    # Revert recruiter_profiles.full_name -> VARCHAR(255)
    op.alter_column(
        "recruiter_profiles",
        "full_name",
        type_=sa.String(255),
        existing_type=NVARCHAR(255),
        existing_nullable=True,
    )
