"""Run the reset-token-used Alembic revision on SQL Server.

The test simulates the pre-migration schema by dropping ``reset_token_used``
from the freshly created test table, then exercises upgrade -> downgrade ->
re-upgrade against real rows. The database identity is asserted before any
DDL/DML because this test mutates schema.
"""

from __future__ import annotations

import importlib.util
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.database.session import async_session_factory

pytestmark = pytest.mark.integration

EXPECTED_DATABASE = "ai_recruitment_platform_test"

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "b7d2e8f190c4_add_reset_token_used.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "b7d2e8f190c4_add_reset_token_used", _MIGRATION_PATH
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


def _assert_test_database(connection) -> None:
    name = connection.execute(sa.text("SELECT DB_NAME()")).scalar_one()
    assert name == EXPECTED_DATABASE


def _column_info(connection):
    row = connection.execute(
        sa.text(
            """
            SELECT c.is_nullable,
                   (
                       SELECT COUNT(*)
                       FROM sys.default_constraints dc
                       WHERE dc.parent_object_id = c.object_id
                         AND dc.parent_column_id = c.column_id
                   ) AS has_default,
                   t.name AS type_name
            FROM sys.columns c
            JOIN sys.types t ON t.user_type_id = c.user_type_id
            WHERE c.object_id = OBJECT_ID('password_reset_otps')
              AND c.name = 'reset_token_used'
            """
        )
    ).first()
    if row is None:
        return None
    return (int(row[0]), int(row[1]), row[2].lower())


def _drop_legacy_column(connection) -> None:
    default_name = connection.execute(
        sa.text(
            """
            SELECT dc.name
            FROM sys.default_constraints dc
            JOIN sys.columns c
              ON c.object_id = dc.parent_object_id
             AND c.column_id = dc.parent_column_id
            WHERE dc.parent_object_id = OBJECT_ID('password_reset_otps')
              AND c.name = 'reset_token_used'
            """
        )
    ).scalar_one_or_none()
    if default_name:
        connection.execute(
            sa.text(
                "ALTER TABLE password_reset_otps "
                f"DROP CONSTRAINT [{default_name}]"
            )
        )
    connection.execute(
        sa.text(
            "ALTER TABLE password_reset_otps DROP COLUMN reset_token_used"
        )
    )


def _create_user(connection):
    user_id = uuid.uuid4()
    email = f"migration-{uuid.uuid4()}@example.com"
    connection.execute(
        sa.text(
            """
            INSERT INTO users
                (id, email, password_hash, role, is_active, is_deleted,
                 created_at, updated_at)
            VALUES
                (:id, :email, 'hash', 'candidate', 1, 0,
                 SYSUTCDATETIME(), SYSUTCDATETIME())
            """
        ),
        {"id": user_id, "email": email},
    )
    return user_id, email


def _insert_legacy_row(connection, user_id, email) -> uuid.UUID:
    row_id = uuid.uuid4()
    connection.execute(
        sa.text(
            """
            INSERT INTO password_reset_otps
                (id, user_id, email, otp_hash, reset_token_hash, expires_at,
                 attempts, max_attempts, is_used, created_at, updated_at)
            VALUES
                (:id, :user_id, :email, 'otp-hash', 'token-hash',
                 DATEADD(HOUR, 1, SYSUTCDATETIME()), 0, 5, 1,
                 SYSUTCDATETIME(), SYSUTCDATETIME())
            """
        ),
        {"id": row_id, "user_id": user_id, "email": email},
    )
    return row_id


def _expires_at(connection, row_id) -> datetime:
    return connection.execute(
        sa.text(
            "SELECT expires_at FROM password_reset_otps WHERE id = :id"
        ),
        {"id": row_id},
    ).scalar_one()


def _reset_token_used(connection, row_id) -> bool:
    return bool(
        connection.execute(
            sa.text(
                "SELECT reset_token_used FROM password_reset_otps "
                "WHERE id = :id"
            ),
            {"id": row_id},
        ).scalar_one()
    )


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _same_moment(left: datetime, right: datetime) -> bool:
    return abs((_as_utc(left) - _as_utc(right)).total_seconds()) < 1


class TestResetTokenUsedMigration:
    def test_upgrade_downgrade_reupgrade_on_sql_server(self, run_async):
        async def _test() -> None:
            migration = _load_migration()

            async with async_session_factory() as session:
                conn = await session.connection()
                # Guard runs before any DDL/DML in this test.
                await conn.run_sync(_assert_test_database)

                await conn.run_sync(_drop_legacy_column)
                user_id, email = await conn.run_sync(_create_user)
                valid_row = await conn.run_sync(
                    _insert_legacy_row, user_id, email
                )
                consumed_row = await conn.run_sync(
                    _insert_legacy_row, user_id, email
                )
                await session.commit()

                conn = await session.connection()
                valid_expires_before = await conn.run_sync(
                    _expires_at, valid_row
                )
                assert _as_utc(valid_expires_before) > datetime.now(timezone.utc)

                # Upgrade: column is added, backfilled to 0, not nullable and
                # carries a default constraint.
                conn = await session.connection()
                await conn.run_sync(_apply, migration)
                await session.commit()

                conn = await session.connection()
                info = await conn.run_sync(_column_info)
                assert info is not None
                is_nullable, has_default, type_name = info
                assert is_nullable == 0
                assert has_default == 1
                assert type_name == "bit"

                assert await conn.run_sync(
                    _reset_token_used, valid_row
                ) is False
                assert await conn.run_sync(
                    _reset_token_used, consumed_row
                ) is False
                # The backfill preserves a still-valid, unconsumed token.
                assert _same_moment(
                    await conn.run_sync(_expires_at, valid_row),
                    valid_expires_before,
                )

                # Consume one token, then downgrade.
                await conn.execute(
                    sa.text(
                        "UPDATE password_reset_otps "
                        "SET reset_token_used = 1 WHERE id = :id"
                    ),
                    {"id": consumed_row},
                )
                await session.commit()

                conn = await session.connection()
                await conn.run_sync(_apply, migration, downgrade=True)
                await session.commit()

                conn = await session.connection()
                assert await conn.run_sync(_column_info) is None

                now = datetime.now(timezone.utc)
                # A consumed token must never become usable again: its expiry
                # is moved into the past before the column is dropped.
                assert _as_utc(
                    await conn.run_sync(_expires_at, consumed_row)
                ) <= now
                # An unconsumed still-valid token keeps its original expiry.
                assert _same_moment(
                    await conn.run_sync(_expires_at, valid_row),
                    valid_expires_before,
                )

                # Re-upgrade restores the column and backfills both rows to 0.
                await conn.run_sync(_apply, migration)
                await session.commit()

                conn = await session.connection()
                info = await conn.run_sync(_column_info)
                assert info is not None
                assert info[0] == 0
                assert info[1] == 1
                assert await conn.run_sync(
                    _reset_token_used, valid_row
                ) is False
                assert await conn.run_sync(
                    _reset_token_used, consumed_row
                ) is False

        run_async(_test())

    def test_database_identity_is_the_isolated_test_database(self, run_async):
        async def _test() -> None:
            async with async_session_factory() as session:
                conn = await session.connection()
                await conn.run_sync(_assert_test_database)
                name = (
                    await conn.execute(sa.text("SELECT DB_NAME()"))
                ).scalar_one()
                assert name == EXPECTED_DATABASE
                assert name != "ai_recruitment_platform"

        run_async(_test())
