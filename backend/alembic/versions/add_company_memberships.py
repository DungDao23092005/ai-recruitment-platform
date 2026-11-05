"""add company memberships and invitations

Adds the authoritative workspace membership and invitation tables. The legacy
``recruiter_profiles.company_id`` column is preserved for compatibility but is
backfilled into memberships exactly when the mapping is unambiguous: one active
recruiter profile for one active company. Companies with multiple recruiters
are intentionally rejected until an operator resolves the case, because
silently choosing a workspace admin would grant authority incorrectly.

Revision ID: add_company_memberships
Revises: add_admin_audit_logs
Create Date: 2026-11-04 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mssql import NVARCHAR


revision: str = "add_company_memberships"
down_revision: Union[str, None] = "add_admin_audit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("invited_by_id", sa.Uuid(), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="NO ACTION"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="NO ACTION"
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_id"], ["users.id"], ondelete="NO ACTION"
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_id"], ["users.id"], ondelete="NO ACTION"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_company_memberships_active_company_user",
        "company_memberships",
        ["company_id", "user_id"],
        unique=True,
        mssql_where=sa.text("status = 'active' AND is_deleted = 0"),
    )
    op.create_index(
        "ix_company_memberships_user_status",
        "company_memberships",
        ["user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_company_memberships_company_status",
        "company_memberships",
        ["company_id", "status"],
        unique=False,
    )

    op.create_table(
        "company_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("email", NVARCHAR(320), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("invited_by_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="NO ACTION"
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_id"], ["users.id"], ondelete="NO ACTION"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_company_invitations_pending_company_email",
        "company_invitations",
        ["company_id", "email"],
        unique=True,
        mssql_where=sa.text("status = 'pending' AND is_deleted = 0"),
    )
    op.create_index(
        "uq_company_invitations_token_hash",
        "company_invitations",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_company_invitations_company_status",
        "company_invitations",
        ["company_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_company_invitations_email_status",
        "company_invitations",
        ["email", "status"],
        unique=False,
    )

    connection = op.get_bind()

    ambiguous = connection.execute(
        sa.text(
            """
            SELECT rp.company_id, COUNT(*) AS recruiter_count
            FROM recruiter_profiles rp
            JOIN companies c ON c.id = rp.company_id
            WHERE rp.company_id IS NOT NULL
              AND rp.is_deleted = 0
              AND c.is_deleted = 0
            GROUP BY rp.company_id
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    if ambiguous:
        company_ids = ", ".join(str(row[0]) for row in ambiguous)
        raise RuntimeError(
            "Cannot safely backfill company memberships: multiple active "
            f"recruiter profiles exist for companies [{company_ids}]. "
            "Resolve these companies explicitly before retrying."
        )

    invalid = connection.execute(
        sa.text(
            """
            SELECT rp.id
            FROM recruiter_profiles rp
            LEFT JOIN companies c ON c.id = rp.company_id
            LEFT JOIN users u ON u.id = rp.user_id
            WHERE rp.company_id IS NOT NULL
              AND rp.is_deleted = 0
              AND (
                    c.id IS NULL
                 OR c.is_deleted = 1
                 OR u.id IS NULL
                 OR u.is_deleted = 1
              )
            """
        )
    ).fetchall()
    if invalid:
        profile_ids = ", ".join(str(row[0]) for row in invalid)
        raise RuntimeError(
            "Cannot safely backfill company memberships: recruiter profiles "
            f"reference missing or deleted companies/users [{profile_ids}]."
        )

    connection.execute(
        sa.text(
            """
            INSERT INTO company_memberships
                (id, company_id, user_id, role, status, invited_by_id,
                 joined_at, revoked_at, revoked_by_id, created_at, updated_at,
                 is_deleted)
            SELECT NEWID(), rp.company_id, rp.user_id, 'admin', 'active', NULL,
                   GETUTCDATE(), NULL, NULL, GETUTCDATE(), GETUTCDATE(), 0
            FROM recruiter_profiles rp
            JOIN companies c ON c.id = rp.company_id
            WHERE rp.company_id IS NOT NULL
              AND rp.is_deleted = 0
              AND c.is_deleted = 0
              AND NOT EXISTS (
                  SELECT 1
                  FROM company_memberships cm
                  WHERE cm.company_id = rp.company_id
                    AND cm.user_id = rp.user_id
                    AND cm.status = 'active'
                    AND cm.is_deleted = 0
              )
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_invitations_email_status",
        table_name="company_invitations",
    )
    op.drop_index(
        "ix_company_invitations_company_status",
        table_name="company_invitations",
    )
    op.drop_index(
        "uq_company_invitations_token_hash",
        table_name="company_invitations",
    )
    op.drop_index(
        "uq_company_invitations_pending_company_email",
        table_name="company_invitations",
    )
    op.drop_table("company_invitations")
    op.drop_index(
        "ix_company_memberships_company_status",
        table_name="company_memberships",
    )
    op.drop_index(
        "ix_company_memberships_user_status",
        table_name="company_memberships",
    )
    op.drop_index(
        "uq_company_memberships_active_company_user",
        table_name="company_memberships",
    )
    op.drop_table("company_memberships")
