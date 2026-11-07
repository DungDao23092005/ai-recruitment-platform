import asyncio
import uuid
from sqlalchemy import select

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
from app.domain.enums import UserRole, SubscriptionStatus
from app.domain.models.base import utc_now
from app.main import app
from app.models import User, RecruitmentPlan, Subscription, Resume
from redis.asyncio import Redis, ConnectionPool

API_V1 = "/api/v1"
PASSWORD = "password123"


async def seed_confirmed_resume(
    candidate_profile_id,
    parsed_data: dict | None = None,
    *,
    is_primary: bool = True,
    is_confirmed: bool = True,
) -> Resume:
    """Create a CV; defaults to the confirmed primary required by policy."""
    async with async_session_factory() as session:
        if is_primary and is_confirmed:
            existing = await session.scalar(
                select(Resume).where(
                    Resume.candidate_id == candidate_profile_id,
                    Resume.is_primary == True,  # noqa: E712
                    Resume.is_confirmed == True,  # noqa: E712
                    Resume.is_deleted == False,  # noqa: E712
                )
            )
            if existing is not None:
                return existing
        resume = Resume(
            candidate_id=candidate_profile_id,
            title="cv.pdf",
            is_primary=is_primary,
            is_confirmed=is_confirmed,
            confirmed_at=utc_now() if is_confirmed else None,
            parsed_data=parsed_data if parsed_data is not None else {},
        )
        session.add(resume)
        await session.commit()
        await session.refresh(resume)
        return resume


def apply_job_with_resume(candidate_client, run_async, job_id):
    """Apply after ensuring the candidate has the policy-required CV."""
    profile = run_async(
        candidate_client.get(f"{API_V1}/users/me/candidate-profile")
    )
    assert profile.status_code == 200, profile.text
    run_async(seed_confirmed_resume(profile.json()["id"]))
    return run_async(
        candidate_client.post(
            f"{API_V1}/applications",
            json={"job_id": job_id},
        )
    )


@pytest.fixture(scope="session", autouse=True)
def configure_test_settings():
    """Configure test settings to avoid rate limit interference."""
    settings.RATE_LIMIT_LOGIN_IP_PER_MINUTE = 10000
    settings.RATE_LIMIT_LOGIN_EMAIL_PER_MINUTE = 10000
    settings.RATE_LIMIT_REGISTER_IP_PER_MINUTE = 10000
    settings.RATE_LIMIT_FORGOT_PASSWORD_IP_PER_MINUTE = 10000
    settings.RATE_LIMIT_FORGOT_PASSWORD_EMAIL_PER_MINUTE = 10000
    settings.RATE_LIMIT_VERIFY_OTP_IP_PER_MINUTE = 10000
    settings.RATE_LIMIT_VERIFY_OTP_EMAIL_PER_MINUTE = 10000
    settings.RATE_LIMIT_AI_CHAT_PER_MINUTE = 10000
    settings.RATE_LIMIT_PARSE_RESUME_PER_MINUTE = 10000
    settings.RATE_LIMIT_PARSE_JD_PER_MINUTE = 10000
    settings.RATE_LIMIT_MATCH_PER_MINUTE = 10000
    settings.RATE_LIMIT_RECOMMENDATIONS_PER_MINUTE = 10000
    yield


@pytest.fixture(scope="session")
def lifespan_manager():
    """Manage the FastAPI lifespan for integration tests using the shared event loop."""
    async def _start():
        manager = LifespanManager(app)
        await manager.__aenter__()
        return manager

    async def _stop(manager):
        await manager.__aexit__(None, None, None)

    manager = run(_start())
    try:
        yield manager
    finally:
        run(_stop(manager))


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
    auth_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )

    # For recruiters, create a subscription with quota
    if role == "recruiter":
        seeded_ids: dict[str, uuid.UUID] = {}

        async def setup_subscription():
            async with async_session_factory() as session:
                from app.models import RecruitmentPlan, Subscription, User
                from app.domain.enums import SubscriptionStatus
                from app.domain.models.base import utc_now
                from datetime import timedelta

                # Get the user
                user_result = await session.execute(
                    select(User).where(User.email == email)
                )
                user = user_result.scalar_one_or_none()
                if not user:
                    return

                # Create a plan with quota
                plan = RecruitmentPlan(
                    name=f"Test Plan {uuid.uuid4()}",
                    price=1000,
                    currency="VND",
                    duration_days=30,
                    max_job_posts=10,
                    max_candidate_searches=10,
                    max_ai_features=10,
                    is_active=True,
                    display_order=0,
                )
                session.add(plan)
                await session.flush()

                # Create active subscription
                now = utc_now()
                subscription = Subscription(
                    user_id=user.id,
                    plan_id=plan.id,
                    status=SubscriptionStatus.ACTIVE,
                    started_at=now,
                    expires_at=now + timedelta(days=30),
                    max_job_posts=plan.max_job_posts,
                    max_candidate_searches=plan.max_candidate_searches or 0,
                    max_ai_features=plan.max_ai_features or 0,
                    job_posts_used=0,
                    candidate_searches_used=0,
                    ai_features_used=0,
                )
                session.add(subscription)
                await session.commit()
                seeded_ids["user_id"] = user.id
                seeded_ids["plan_id"] = plan.id

        run(setup_subscription())

        async def _seed_company_subscription_on_create(
            response: httpx.Response,
        ) -> None:
            if (
                response.request.method == "POST"
                and response.request.url.path.rstrip("/") == f"{API_V1}/companies"
                and response.status_code == 201
                and "user_id" in seeded_ids
                and "plan_id" in seeded_ids
            ):
                await response.aread()
                try:
                    payload = response.json()
                    company_id = uuid.UUID(str(payload["id"]))
                except Exception:
                    return

                from datetime import timedelta
                from app.domain.enums import (
                    SubscriptionScope,
                    SubscriptionStatus,
                )
                from app.domain.models.base import utc_now
                from app.models import Subscription

                async with async_session_factory() as session:
                    existing = await session.scalar(
                        select(Subscription).where(
                            Subscription.company_id == company_id,
                            Subscription.scope
                            == SubscriptionScope.COMPANY_RECRUITING,
                            Subscription.is_deleted == False,  # noqa: E712
                        )
                    )
                    if existing is None:
                        now = utc_now()
                        session.add(
                            Subscription(
                                user_id=seeded_ids["user_id"],
                                company_id=company_id,
                                plan_id=seeded_ids["plan_id"],
                                scope=SubscriptionScope.COMPANY_RECRUITING,
                                is_free=False,
                                status=SubscriptionStatus.ACTIVE,
                                started_at=now,
                                expires_at=now + timedelta(days=30),
                                max_job_posts=10,
                                max_candidate_searches=10,
                                max_ai_features=10,
                                job_posts_used=0,
                                candidate_searches_used=0,
                                ai_features_used=0,
                            )
                        )
                        await session.commit()

        auth_client.event_hooks["response"].append(
            _seed_company_subscription_on_create
        )

    return auth_client


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