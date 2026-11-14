import pytest
from sqlalchemy import text

from app.database.session import async_session_factory, engine
from app.domain.enums import UserRole
from app.models import User


def test_database_connection_works(run_async):
    async def _check():
        async with engine.connect() as conn:
            return (await conn.execute(text("SELECT 1"))).scalar()

    assert run_async(_check()) == 1


def test_connection_uses_test_database(run_async):
    from app.core.config import settings

    assert settings.DATABASE_NAME != "ai_recruitment_platform", (
        "integration tests must never run against the development database"
    )

    async def _check():
        async with engine.connect() as conn:
            return (await conn.execute(text("SELECT DB_NAME()"))).scalar()

    assert run_async(_check()) == settings.DATABASE_NAME


def test_session_commit_persists_row(run_async):
    async def _run():
        async with async_session_factory() as session:
            user = User(
                email="commit@example.com",
                password_hash="hashed",
                role=UserRole.CANDIDATE,
            )
            session.add(user)
            await session.commit()
            user_id = user.id
        async with async_session_factory() as session:
            return await session.get(User, user_id)

    fetched = run_async(_run())
    assert fetched is not None
    assert fetched.email == "commit@example.com"


def test_session_rollback_discards_changes(run_async):
    async def _run():
        async with async_session_factory() as session:
            user = User(
                email="rollback@example.com",
                password_hash="hashed",
                role=UserRole.CANDIDATE,
            )
            session.add(user)
            await session.flush()
            user_id = user.id
            await session.rollback()
        async with async_session_factory() as session:
            return await session.get(User, user_id)

    assert run_async(_run()) is None


def test_drop_schema_restores_lock_timeout(run_async):
    """The DDL watchdog must not leak its LOCK_TIMEOUT into the pool."""
    from tests.integration.conftest import _drop_schema_with_connection

    async def _run():
        async with engine.connect() as conn:
            await conn.execute(text("SET LOCK_TIMEOUT 12345"))
            await conn.commit()

            await _drop_schema_with_connection(conn)

            restored = (
                await conn.execute(text("SELECT @@LOCK_TIMEOUT"))
            ).scalar()
            await conn.rollback()
            return restored

    assert run_async(_run()) == -1


def test_reset_database_drains_dispatch_before_schema_drop(monkeypatch):
    import tests.integration.conftest as integration_conftest

    calls: list[str] = []

    async def _drain():
        calls.append("drain")

    async def _drop():
        calls.append("drop")

    monkeypatch.setattr(
        integration_conftest, "_drain_worker_dispatch", _drain
    )
    monkeypatch.setattr(integration_conftest, "_drop_schema", _drop)

    reset = integration_conftest._reset_database_impl()
    next(reset)
    with pytest.raises(StopIteration):
        next(reset)

    assert calls == ["drain", "drop", "drain", "drop"]
