"""create candidate contact requests and audit logs

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-25 23:21:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidate_contact_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("requester_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requester_user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_candidate_contact_requests_company_id",
        "candidate_contact_requests",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_candidate_contact_requests_candidate_id",
        "candidate_contact_requests",
        ["candidate_id"],
        unique=False,
    )
    op.create_index(
        "ix_candidate_contact_requests_requester_user_id",
        "candidate_contact_requests",
        ["requester_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_candidate_contact_requests_status",
        "candidate_contact_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_candidate_contact_requests_expires_at",
        "candidate_contact_requests",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "uq_active_candidate_contact_request",
        "candidate_contact_requests",
        ["company_id", "candidate_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending', 'accepted') AND is_deleted = false"
        ),
        sqlite_where=sa.text(
            "status IN ('pending', 'accepted') AND is_deleted = 0"
        ),
        mssql_where=sa.text(
            "status IN ('pending', 'accepted') AND is_deleted = 0"
        ),
    )

    op.create_table(
        "contact_disclosure_audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contact_request_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("disclosed_to_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "disclosed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_profiles.id"],
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["contact_request_id"],
            ["candidate_contact_requests.id"],
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["disclosed_to_user_id"],
            ["users.id"],
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_contact_disclosure_audit_logs_request_id",
        "contact_disclosure_audit_logs",
        ["contact_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_contact_disclosure_audit_logs_company_id",
        "contact_disclosure_audit_logs",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_contact_disclosure_audit_logs_candidate_id",
        "contact_disclosure_audit_logs",
        ["candidate_id"],
        unique=False,
    )
    op.create_index(
        "ix_contact_disclosure_audit_logs_disclosed_to",
        "contact_disclosure_audit_logs",
        ["disclosed_to_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_contact_disclosure_audit_logs_disclosed_at",
        "contact_disclosure_audit_logs",
        ["disclosed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("contact_disclosure_audit_logs")
    op.drop_table("candidate_contact_requests")
