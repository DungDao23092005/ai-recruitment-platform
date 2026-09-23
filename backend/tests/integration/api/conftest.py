import asyncio
import uuid

import httpx
import pytest
from asgi_lifespan import LifespanManager
from tests.integration.conftest import run

import app.models  # noqa: F401
from app.core.config import settings
from app.core.rate_limit import set_rate_limiter, get_rate_limiter
from app.core.rate_limit import RateLimiter
from app.core.security import get_password_hash
from app.database.session import async_session_factory
from app.domain.enums import UserRole
from app.main import app
from app.models import User
from redis.asyncio import Redis, ConnectionPool

API_V1 = "/api/v1"
PASSWORD = "password123"


@pytest.fixture(scope="session", autouse=True)
def configure_test_settings():
    """Configure test settings to avoid rate limit interference."""
    settings.RATE_LIMIT_LOGIN_IP_PER_MINUTE = 10000
    settings.RATE_LIMIT_LOGIN_EMAIL_PER_MINUTE = 10000
    settings.RATE_LIMIT_REGISTER_IP_PER_MINUTE = 10000
    settings.RATE_LIMIT_FORGOT_PASSWORD_IP_PER_MINUTE = 10000
    settings.RATE_LIMIT_FORGOT_PASSWORD_EMAIL_PER_MINUTE = 10000
    settings.RATE_LIMIT_VERIFY_OTP_IP_PER_MINUTE = 10000
    settings.RATE_LIMIT_AI_CHAT_PER_MINUTE = 10000
    settings.RATE_LIMIT_PARSE_RESUME_PER_MINUTE = 10000
    settings.RATE_LIMIT_PARSE_JD_PER_MINUTE = 10000
    settings.RATE_LIMIT_MATCH_PER_MINUTE = 10000
    settings.RATE_LIMIT_RECOMMENDATIONS_PER_MINUTE = 10000
    yield


@pytest.fixture(scope="session")
async def lifespan_manager():
    """Manage the FastAPI lifespan for integration tests."""
    async with LifespanManager(app) as manager:
        yield manager


@pytest.fixture(scope="session")
def client(lifespan_manager):
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


def _make_admin_client(client: httpx.AsyncClient) -> httpx.AsyncClient:
    """Create an admin user directly in the test DB and return an authenticated client."""
    email = f"admin-{uuid.uuid4()}@example.com"
    password_hash = get_password_hash(PASSWORD)

    # Create admin user directly in test DB
    async def create_admin():
        async with async_session_factory() as session:
            admin_user = User(
                email=email,
                password_hash=password_hash,
                role=UserRole.ADMIN,
                is_active=True,
            )
            session.add(admin_user)
            await session.commit()
            await session.refresh(admin_user)
            return admin_user

    run(create_admin())

    # Now login using the real login endpoint
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
    auth_client = _make_admin_client(client)
    yield auth_client
    run(auth_client.aclose())