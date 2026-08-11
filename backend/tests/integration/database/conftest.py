import asyncio

import pytest

import app.models  # noqa: F401
from app.database.base_class import Base
from app.database.session import async_session_factory, engine
from app.repositories.base import BaseRepository

_LOOP = asyncio.new_event_loop()


def run(coro) -> object:
    return _LOOP.run_until_complete(coro)


async def _drop_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _create_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(scope="session", autouse=True)
def _cleanup_engine():
    yield
    run(engine.dispose())
    _LOOP.close()


@pytest.fixture(autouse=True)
def _reset_database():
    run(_drop_schema())
    run(_create_schema())
    yield
    run(_drop_schema())


@pytest.fixture
def run_async():
    return run


@pytest.fixture
def session():
    session = async_session_factory()
    yield session
    run(session.close())


@pytest.fixture
def make_repo(session):
    def _factory(model):
        return BaseRepository(session, model)

    return _factory
