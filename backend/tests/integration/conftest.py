import asyncio
import pytest
from app.core.config import settings
from app.database.base_class import Base
from app.database.session import engine


# Ensure that tests never run against development database
DEVELOPMENT_DATABASE = "ai_recruitment_platform"


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


async def _drop_schema() -> None:
    from app.core.config import settings
    _assert_not_development_database()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _create_schema() -> None:
    from app.core.config import settings
    _assert_not_development_database()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(scope="session", autouse=True)
def _manage_engine():
    yield
    # Don't dispose engine at teardown - let pytest-asyncio handle it


@pytest.fixture(autouse=True)
def _reset_database():
    run(_drop_schema())
    run(_create_schema())
    yield
    run(_drop_schema())


@pytest.fixture(scope="session")
def run_async():
    return run