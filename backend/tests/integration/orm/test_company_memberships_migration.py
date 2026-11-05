"""Run the company-membership Alembic revision against the SQL Server test DB."""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.database.session import async_session_factory
from app.domain.enums import CompanySize, UserRole
from app.models import (
    Company,
    CompanyInvitation,
    CompanyMembership,
    RecruiterProfile,
    User,
)

pytestmark = pytest.mark.integration

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "add_company_memberships.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "add_company_memberships", _MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply_upgrade(connection, migration) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        migration.upgrade()


def _drop_workspace_objects(connection) -> None:
    CompanyInvitation.__table__.drop(connection, checkfirst=True)
    CompanyMembership.__table__.drop(connection, checkfirst=True)


def _column_info(connection, table_name):
    result = connection.execute(
        sa.text(
            """
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = :table_name
            """
        ),
        {"table_name": table_name},
    )
    return {row[0]: (row[1].lower(), row[2]) for row in result}


def _index_info(connection, table_name):
    result = connection.execute(
        sa.text(
            """
            SELECT i.name, i.is_unique, i.has_filter, i.filter_definition
            FROM sys.indexes i
            WHERE i.object_id = OBJECT_ID(:table_name)
              AND i.name IS NOT NULL
            """
        ),
        {"table_name": table_name},
    )
    return {row[0]: (row[1], row[2], row[3]) for row in result}


def _fk_actions(connection, table_name):
    result = connection.execute(
        sa.text(
            """
            SELECT fk.name, fk.delete_referential_action_desc
            FROM sys.foreign_keys fk
            WHERE fk.parent_object_id = OBJECT_ID(:table_name)
            """
        ),
        {"table_name": table_name},
    )
    return {row[0]: row[1] for row in result}


def _company() -> Company:
    return Company(
        name="Migration Workspace Co",
        slug=f"migration-workspace-{uuid.uuid4().hex[:8]}",
        tax_code=str(uuid.uuid4().int)[:12],
        size=CompanySize.STARTUP,
    )


def _recruiter() -> User:
    return User(
        email=f"migration-rec-{uuid.uuid4()}@example.com",
        password_hash="hash",
        role=UserRole.RECRUITER,
        is_active=True,
    )


class TestCompanyMembershipsUpgrade:
    def test_upgrade_creates_columns_indexes_and_fks(self, run_async):
        async def _test() -> None:
            migration = _load_migration()
            async with async_session_factory() as session:
                conn = await session.connection()
                await conn.run_sync(_drop_workspace_objects)
                await conn.run_sync(_apply_upgrade, migration)
                await session.commit()
                conn = await session.connection()

                membership_columns = await conn.run_sync(
                    _column_info, "company_memberships"
                )
                assert membership_columns["role"] == ("varchar", 50)
                assert membership_columns["status"] == ("varchar", 50)
                assert membership_columns["is_deleted"][0] == "bit"

                invitation_columns = await conn.run_sync(
                    _column_info, "company_invitations"
                )
                assert invitation_columns["email"] == ("nvarchar", 320)
                assert invitation_columns["token_hash"] == ("varchar", 64)
                assert invitation_columns["role"] == ("varchar", 50)
                assert invitation_columns["status"] == ("varchar", 50)

                membership_indexes = await conn.run_sync(
                    _index_info, "company_memberships"
                )
                active = membership_indexes[
                    "uq_company_memberships_active_company_user"
                ]
                assert active[0] is True
                assert active[1] is True
                assert "active" in active[2]
                assert "is_deleted" in active[2]

                invitation_indexes = await conn.run_sync(
                    _index_info, "company_invitations"
                )
                pending = invitation_indexes[
                    "uq_company_invitations_pending_company_email"
                ]
                assert pending[0] is True
                assert pending[1] is True
                assert "pending" in pending[2]
                assert "is_deleted" in pending[2]
                token = invitation_indexes[
                    "uq_company_invitations_token_hash"
                ]
                assert token[0] is True
                assert token[1] is False

                membership_fks = await conn.run_sync(
                    _fk_actions, "company_memberships"
                )
                invitation_fks = await conn.run_sync(
                    _fk_actions, "company_invitations"
                )
                assert set(membership_fks.values()) == {"NO_ACTION"}
                assert set(invitation_fks.values()) == {"NO_ACTION"}
                assert len(membership_fks) == 4
                assert len(invitation_fks) == 2

        run_async(_test())

    def test_backfill_creates_admin_membership_from_legacy_profile(
        self, run_async
    ):
        async def _test() -> None:
            migration = _load_migration()
            async with async_session_factory() as session:
                conn = await session.connection()
                await conn.run_sync(_drop_workspace_objects)

                company = _company()
                recruiter = _recruiter()
                session.add_all([company, recruiter])
                await session.flush()
                session.add(
                    RecruiterProfile(
                        user_id=recruiter.id,
                        company_id=company.id,
                        full_name="Legacy Recruiter",
                    )
                )
                await session.commit()

                conn = await session.connection()
                await conn.run_sync(_apply_upgrade, migration)
                await session.commit()
                conn = await session.connection()
                rows = (
                    await conn.execute(
                        sa.text(
                            """
                            SELECT company_id, user_id, role, status
                            FROM company_memberships
                            """
                        )
                    )
                ).all()
                assert len(rows) == 1
                assert uuid.UUID(str(rows[0][0])) == company.id
                assert uuid.UUID(str(rows[0][1])) == recruiter.id
                assert rows[0][2] == "admin"
                assert rows[0][3] == "active"

        run_async(_test())

    def test_ambiguous_legacy_company_fails_closed(self, run_async):
        async def _test() -> None:
            migration = _load_migration()
            async with async_session_factory() as session:
                conn = await session.connection()
                await conn.run_sync(_drop_workspace_objects)

                company = _company()
                first = _recruiter()
                second = _recruiter()
                session.add_all([company, first, second])
                await session.flush()
                session.add_all(
                    [
                        RecruiterProfile(
                            user_id=first.id,
                            company_id=company.id,
                            full_name="First",
                        ),
                        RecruiterProfile(
                            user_id=second.id,
                            company_id=company.id,
                            full_name="Second",
                        ),
                    ]
                )
                await session.commit()

                conn = await session.connection()
                with pytest.raises(
                    RuntimeError,
                    match="multiple active recruiter profiles",
                ):
                    await conn.run_sync(_apply_upgrade, migration)
                await session.rollback()

        run_async(_test())
