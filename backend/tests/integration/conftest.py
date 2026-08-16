import asyncio
import os

import pytest
from app.core.config import settings
from app.database.base_class import Base
from app.database.session import engine

# Ensure that tests never run against development database
DEVELOPMENT_DATABASE = "ai_recruitment_platform"

_LOOP = asyncio.new_event_loop()

def run(coro) -> object:
    return _LOOP.run_until_complete(coro)

def _assert_not_development_database() -> None:
    if settings.DATABASE_NAME == DEVELOPMENT_DATABASE:
        raise RuntimeError(
            "REFUSED: integration tests must not run against the development "
            f"database '{DEVELOPMENT_DATABASE}'."
        )

async def _drop_schema() -> None:
    _assert_not_development_database()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

async def _create_schema() -> None:
    _assert_not_development_database()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@pytest.fixture(scope="session", autouse=True)
def _manage_engine():
    run(engine.dispose())
    yield
    run(engine.dispose())
    _LOOP.close()

@pytest.fixture(autouse=True)
def _reset_database():
    run(_drop_schema())
    run(_create_schema())
    yield
    run(_drop_schema())
    run(engine.dispose())

@pytest.fixture(scope="session")
def run_async():
    return run
