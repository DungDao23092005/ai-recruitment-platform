import asyncio
import uuid

import httpx
import pytest
from tests.integration.conftest import run

import app.models  # noqa: F401
from app.api.deps import get_db
from app.core.config import settings
from app.database.base_class import Base
from app.database.session import async_session_factory, engine
from app.main import app

API_V1 = "/api/v1"
PASSWORD = "password123"




@pytest.fixture(scope="session")
def client():
    async_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )
    yield async_client
    run(async_client.aclose())


def _make_auth_client(client: httpx.AsyncClient, role: str) -> httpx.AsyncClient:
    email = f"{role}-{uuid.uuid4()}@example.com"
    register = run(
        client.post(
            f"{API_V1}/auth/register",
            json={"email": email, "password": PASSWORD, "role": role},
        )
    )
    assert register.status_code == 201, register.text
    login = run(
        client.post(
            f"{API_V1}/auth/login",
            data={"username": email, "password": PASSWORD},
        )
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )


@pytest.fixture
def candidate_client(client):
    auth_client = _make_auth_client(client, "candidate")
    yield auth_client
    run(auth_client.aclose())


@pytest.fixture
def candidate_b_client(client):
    auth_client = _make_auth_client(client, "candidate")
    yield auth_client
    run(auth_client.aclose())


@pytest.fixture
def recruiter_client(client):
    auth_client = _make_auth_client(client, "recruiter")
    yield auth_client
    run(auth_client.aclose())


@pytest.fixture
def recruiter_a_client(client):
    auth_client = _make_auth_client(client, "recruiter")
    yield auth_client
    run(auth_client.aclose())


@pytest.fixture
def recruiter_b_client(client):
    auth_client = _make_auth_client(client, "recruiter")
    yield auth_client
    run(auth_client.aclose())


@pytest.fixture
def admin_client(client):
    auth_client = _make_auth_client(client, "admin")
    yield auth_client
    run(auth_client.aclose())