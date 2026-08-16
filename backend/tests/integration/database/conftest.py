import asyncio

import pytest

import app.models  # noqa: F401
from app.core.config import settings
from app.database.base_class import Base
from app.database.session import async_session_factory, engine
from app.repositories.base import BaseRepository

from tests.integration.conftest import run




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
