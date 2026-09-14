"""update_existing_job_skills_mandatory

Revision ID: 2ab6e1b9e538
Revises: 3c57e134e916
Create Date: 2026-09-15 00:09:59.660496

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2ab6e1b9e538'
down_revision: Union[str, None] = '3c57e134e916'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update existing job_skills to set is_mandatory=True for legacy skills
    # All existing jobs were created with the old 'skills' behavior which meant required skills
    # The default for is_mandatory was False, so we need to update existing records
    op.execute(
        sa.text("""
            UPDATE job_skills
            SET is_mandatory = 1
            WHERE is_mandatory = 0
        """)
    )


def downgrade() -> None:
    # Cannot fully revert because we don't know which were originally mandatory
    # This is a best-effort revert - set all back to False
    # Note: This may not be accurate for jobs that had explicit preferred skills
    op.execute(
        sa.text("""
            UPDATE job_skills
            SET is_mandatory = 0
            WHERE is_mandatory = 1
        """)
    )