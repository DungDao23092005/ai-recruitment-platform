"""Run the admin-audit generic-target Alembic revision on SQL Server."""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.database.session import async_session_factory
from app.domain.enums import UserRole
from app.models import User

pytestmark = pytest.mark.integration

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "admin_audit_generic_target.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "admin_audit_generic_target", _MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply(connection, migration, *, downgrade: bool = False) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        if downgrade:
            migration.downgrade()
        else:
            migration.upgrade()


def _legacy_table() -> sa.Table:
    return sa.Table(
        "admin_audit_logs",
        sa.MetaData(),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("admin_id", sa.Uuid(), nullable=False),
        sa.Column("target_user_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.NVARCHAR(500), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def _create_legacy_table(connection) -> None:
    table = _legacy_table()
    table.drop(connection, checkfirst=True)
    table.create(connection)
    connection.execute(
        sa.text(
            "CREATE INDEX ix_admin_audit_logs_target_created "
            "ON admin_audit_logs (target_user_id, created_at)"
        )
    )


def _column_info(connection) -> dict[str, tuple[str, int | None, str]]:
    result = connection.execute(
        sa.text(
            """
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                   IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'admin_audit_logs'
            """
        )
    )
    return {
        row[0]: (row[1].lower(), row[2], row[3]) for row in result
    }


def _index_names(connection) -> set[str]:
    result = connection.execute(
        sa.text(
            """
            SELECT i.name
            FROM sys.indexes i
            WHERE i.object_id = OBJECT_ID('admin_audit_logs')
              AND i.name IS NOT NULL
            """
        )
    )
    return {row[0] for row in result}


def _users() -> tuple[User, User]:
    admin = User(
        email=f"audit-admin-{uuid.uuid4()}@example.com",
        password_hash="hash",
        role=UserRole.ADMIN,
        is_active=True,
    )
    target = User(
        email=f"audit-target-{uuid.uuid4()}@example.com",
        password_hash="hash",
        role=UserRole.CANDIDATE,
        is_active=True,
    )
    return admin, target


def _insert_legacy_row(connection, admin: User, target: User) -> uuid.UUID:
    row_id = uuid.uuid4()
    connection.execute(
        sa.text(
            """
            INSERT INTO admin_audit_logs
                (id, admin_id, target_user_id, action, reason, details,
                 created_at)
            VALUES
                (:id, :admin_id, :target_user_id, 'user_lock', 'Legacy',
                 NULL, SYSUTCDATETIME())
            """
        ),
        {
            "id": row_id,
            "admin_id": admin.id,
            "target_user_id": target.id,
        },
    )
    return row_id


class TestAdminAuditGenericTargetMigration:
    def test_upgrade_backfills_and_downgrade_restores_user_only_schema(
        self, run_async
    ):
        async def _test() -> None:
            migration = _load_migration()
            async with async_session_factory() as session:
                admin, target = _users()
                session.add_all([admin, target])
                await session.commit()

                conn = await session.connection()
                await conn.run_sync(_create_legacy_table)
                row_id = await conn.run_sync(
                    _insert_legacy_row, admin, target
                )
                await session.commit()

                conn = await session.connection()
                await conn.run_sync(_apply, migration)
                await session.commit()
                conn = await session.connection()

                columns = await conn.run_sync(_column_info)
                assert columns["target_user_id"][2] == "YES"
                assert columns["target_id"][0] == "uniqueidentifier"
                assert columns["target_type"] == ("varchar", 50, "NO")
                assert columns["target_name"] == ("nvarchar", 255, "YES")

                row = (
                    await conn.execute(
                        sa.text(
                            """
                            SELECT target_user_id, target_id, target_type,
                                   target_name
                            FROM admin_audit_logs
                            WHERE id = :id
                            """
                        ),
                        {"id": row_id},
                    )
                ).one()
                assert str(row[1]) == str(row[0])
                assert row[2] == "user"
                assert row[3] is None

                indexes = await conn.run_sync(_index_names)
                assert "ix_admin_audit_logs_generic_target_created" in indexes

                await conn.run_sync(_apply, migration, downgrade=True)
                await session.commit()
                conn = await session.connection()

                columns = await conn.run_sync(_column_info)
                assert "target_id" not in columns
                assert "target_type" not in columns
                assert "target_name" not in columns
                assert columns["target_user_id"][2] == "NO"
                indexes = await conn.run_sync(_index_names)
                assert "ix_admin_audit_logs_target_created" in indexes
                assert (
                    "ix_admin_audit_logs_generic_target_created"
                    not in indexes
                )

        run_async(_test())

    def test_downgrade_refuses_to_drop_non_user_targets(self, run_async):
        async def _test() -> None:
            migration = _load_migration()
            async with async_session_factory() as session:
                admin, target = _users()
                session.add_all([admin, target])
                await session.commit()

                conn = await session.connection()
                await conn.run_sync(_create_legacy_table)
                await conn.run_sync(_insert_legacy_row, admin, target)
                await session.commit()

                conn = await session.connection()
                await conn.run_sync(_apply, migration)
                await session.commit()

                conn = await session.connection()
                await conn.execute(
                    sa.text(
                        """
                        INSERT INTO admin_audit_logs
                            (id, admin_id, target_user_id, target_id,
                             target_type, target_name, action, reason,
                             details, created_at)
                        VALUES
                            (:id, :admin_id, NULL, :target_id, 'plan',
                             'Pro Plan', 'plan_lock', NULL, NULL,
                             SYSUTCDATETIME())
                        """
                    ),
                    {
                        "id": uuid.uuid4(),
                        "admin_id": admin.id,
                        "target_id": uuid.uuid4(),
                    },
                )
                await session.commit()

                conn = await session.connection()
                with pytest.raises(
                    RuntimeError,
                    match="Cannot downgrade admin_audit_generic_target",
                ):
                    await conn.run_sync(_apply, migration, downgrade=True)
                await session.rollback()

        run_async(_test())
