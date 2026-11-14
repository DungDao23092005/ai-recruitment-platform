import asyncio
import pytest
from sqlalchemy import text
from app.core.config import settings
from app.database.base_class import Base
from app.database.session import engine


# Ensure that tests never run against development database
DEVELOPMENT_DATABASE = "ai_recruitment_platform"

# Only the schema-teardown connection gets a bounded DDL lock wait. The value
# is restored to the SQL Server default before the connection returns to the
# pool so business/test queries never inherit it.
SCHEMA_DROP_LOCK_TIMEOUT_MS = 15_000
SCHEMA_LOCK_TIMEOUT_DEFAULT_MS = -1

# Post-commit dispatch is normally quick; keep teardown bounded but generous
# enough for a real database roundtrip under concurrent test load.
DISPATCH_DRAIN_TIMEOUT_SECONDS = 15.0
DISPATCH_CANCEL_GRACE_SECONDS = 5.0


# Use a single session-scoped event loop for all synchronous fixtures
_loop: asyncio.AbstractEventLoop | None = None


def _get_or_create_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def run(coro) -> object:
    """Run a coroutine using the shared session-scoped event loop."""
    loop = _get_or_create_loop()
    return loop.run_until_complete(coro)


def _assert_not_development_database() -> None:
    from app.core.config import settings
    if settings.DATABASE_NAME == "ai_recruitment_platform":
        raise RuntimeError(
            "REFUSED: integration tests must not run against the development "
            f"database '{DEVELOPMENT_DATABASE}'."
        )


async def _safe_rollback(conn) -> None:
    try:
        await conn.rollback()
    except Exception:
        pass


async def _drop_schema_with_connection(conn) -> None:
    """Drop all tables with a bounded DDL lock wait on ``conn`` only.

    A leaked post-commit dispatch can still hold a table lock when the fixture
    tears down. Without a lock timeout the drop waits forever and the CI job
    hangs; with one it fails with an actionable SQL Server error. The
    connection's LOCK_TIMEOUT is always restored to the default before the
    connection is returned to the pool.
    """
    try:
        await conn.execute(
            text(f"SET LOCK_TIMEOUT {SCHEMA_DROP_LOCK_TIMEOUT_MS}")
        )
        await conn.run_sync(Base.metadata.drop_all)
        await conn.commit()
    except BaseException:
        await _safe_rollback(conn)
        raise
    finally:
        try:
            await conn.execute(
                text(f"SET LOCK_TIMEOUT {SCHEMA_LOCK_TIMEOUT_DEFAULT_MS}")
            )
            await conn.commit()
        except BaseException:
            await _safe_rollback(conn)
            try:
                await conn.invalidate()
            except Exception:
                pass
            raise


async def _drop_schema() -> None:
    _assert_not_development_database()
    async with engine.connect() as conn:
        await _drop_schema_with_connection(conn)


async def _create_schema() -> None:
    _assert_not_development_database()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _drain_worker_dispatch() -> None:
    """Drain only post-commit dispatch tasks owned by EmailOutboxWorker."""
    from app.services.email_outbox_worker import (
        drain_default_worker_dispatch_tasks,
    )

    await drain_default_worker_dispatch_tasks(
        timeout=DISPATCH_DRAIN_TIMEOUT_SECONDS,
        cancel_grace=DISPATCH_CANCEL_GRACE_SECONDS,
    )


def _drain_worker_dispatch_sync() -> None:
    run(_drain_worker_dispatch())


def _reset_database_impl():
    _drain_worker_dispatch_sync()
    run(_drop_schema())
    run(_create_schema())
    yield
    _drain_worker_dispatch_sync()
    run(_drop_schema())


@pytest.fixture(scope="session", autouse=True)
def _manage_engine():
    yield
    # Don't dispose engine at teardown - let pytest-asyncio handle it


@pytest.fixture(autouse=True)
def _reset_database():
    yield from _reset_database_impl()


@pytest.fixture(scope="session")
def run_async():
    return run