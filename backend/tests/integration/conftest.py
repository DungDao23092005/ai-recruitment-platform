import os

# Set test-specific environment BEFORE any imports that might load settings
# Use Docker Compose service names when running in container, localhost otherwise
# The container environment is set via docker-compose.yml
# RATE_LIMIT_ENABLED is intentionally NOT set here - tests will verify both configurations

import asyncio
import importlib

# Force reload settings after environment variables are set
import app.core.config as config_module
import importlib
importlib.reload(config_module)

import asyncio
import pytest
from app.core.config import settings
from app.database.base_class import Base
from app.database.session import engine

# Ensure that tests never run against development database
DEVELOPMENT_DATABASE = "ai_recruitment_platform"

_LOOP = asyncio.new_event_loop()


def run(coro) -> object:
    """Run a coroutine in the current event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()
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
    run(engine.dispose())
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