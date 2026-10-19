from __future__ import annotations

import asyncio
import hashlib
import socket
import uuid

import httpx
import pytest
from qdrant_client import AsyncQdrantClient
from sqlalchemy import select
from tests.integration.conftest import run

from app.ai.interfaces.base_provider import (
    BaseEmbeddingProvider,
    BaseLLMProvider,
)
from app.ai.vector_db.qdrant_client import QdrantVectorRepository
from app.core.config import settings
from app.core.exceptions import InvalidDocumentError
from app.database.session import async_session_factory
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_resume import ParsedResumeSchema

QDRANT_HOST = settings.QDRANT_HOST
QDRANT_PORT = settings.QDRANT_PORT
VECTOR_DIM = settings.VECTOR_DIMENSION

def is_qdrant_reachable(
    host: str | None = None, port: int | None = None
) -> bool:
    try:
        with socket.create_connection(
            (host or QDRANT_HOST, port or QDRANT_PORT), timeout=2
        ):
            return True
    except OSError:
        return False


def is_sql_reachable() -> bool:
    try:
        with socket.create_connection(
            (settings.DATABASE_HOST, settings.DATABASE_PORT), timeout=2
        ):
            return True
    except OSError:
        return False


QDRANT_AVAILABLE = is_qdrant_reachable()
SQL_AVAILABLE = is_sql_reachable()

SKIP_REASON_QDRANT = "BLOCKED BY ENVIRONMENT — Qdrant is not reachable"
SKIP_REASON_SQL = "BLOCKED BY ENVIRONMENT — SQL Server is not reachable"


@pytest.fixture(autouse=True)
def _disable_rate_limiting():
    """Disable rate limiting for AI pipeline integration tests.

    These tests authenticate via the real auth endpoints but do not start the
    application lifespan, so no Redis-backed rate limiter is initialized. Since
    authentication rate limits are fail-closed when Redis is absent, they are
    disabled here (rate limiting is covered by its own integration suite).

    Function scoped so the setting is restored before tests in other
    integration directories (e.g. the rate-limit suite) run.
    """
    original = settings.RATE_LIMIT_ENABLED
    settings.RATE_LIMIT_ENABLED = False
    yield
    settings.RATE_LIMIT_ENABLED = original


@pytest.fixture
def session():
    """Provide a database session for the test. Created lazily in the test's event loop."""
    session_holder = {"session": None}

    def _get_session():
        if session_holder["session"] is None:
            session_holder["session"] = async_session_factory()
        return session_holder["session"]

    try:
        yield _get_session
    finally:
        # Don't close the session here - let the database reset fixture handle cleanup
        # Closing causes event loop mismatch issues
        pass


class FakeEmbeddingProvider(BaseEmbeddingProvider):
    """Deterministic 384-dimensional embedding provider (offline)."""

    async def embed_text(self, text: str) -> list[float]:
        return self._hash_vector(text)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_vector(text) for text in texts]

    @staticmethod
    def _hash_vector(text: str, dim: int = VECTOR_DIM) -> list[float]:
        vector = [0.0] * dim
        for token in text.lower().replace(",", " ").replace(":", " ").split():
            index = (
                int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % dim
            )
            vector[index] += 1.0
        return vector


class FakeLLMProvider(BaseLLMProvider):
    """Deterministic LLM stub returning fixed schemas (offline)."""

    def __init__(self, resume: ParsedResumeSchema, job: ParsedJobSchema) -> None:
        self.resume = resume
        self.job = job

    async def generate_structured_output(
        self,
        prompt: str,
        response_schema,
        system_instruction: str | None = None,
    ):
        if response_schema is ParsedResumeSchema:
            return self.resume
        if response_schema is ParsedJobSchema:
            return self.job
        raise InvalidDocumentError("Unsupported response schema")


@pytest.fixture
def qdrant_client():
    client = AsyncQdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    yield client
    run(client.close())


@pytest.fixture
def vector_repository(qdrant_client) -> QdrantVectorRepository:
    return QdrantVectorRepository(client=qdrant_client)


@pytest.fixture
def tracked():
    """Tracks created points and cleans them up in teardown."""
    created: list[tuple[str, str]] = []

    def _track(collection_name: str, point_id) -> None:
        created.append((collection_name, str(point_id)))

    yield _track
    if not created:
        return
    client = AsyncQdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    try:
        for collection_name, point_id in created:
            try:
                run(
                    client.delete(
                        collection_name=collection_name,
                        points_selector=[point_id],
                    )
                )
            except Exception:
                pass
    finally:
        run(client.close())


def _make_authenticated_client(role: str, setup_subscription: bool = False) -> httpx.AsyncClient:
    from app.main import app

    email = f"ai-{role}-{uuid.uuid4()}@example.com"
    register = run(
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ).post(
            f"{settings.API_V1_STR}/auth/register",
            json={"email": email, "password": "password123", "role": role},
        )
    )
    assert register.status_code == 201, register.text
    login = run(
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ).post(
            f"{settings.API_V1_STR}/auth/login",
            data={"username": email, "password": "password123"},
        )
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )

    if setup_subscription and role == "recruiter":

        async def setup_subscription_db():
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
                    name=f"AI Integration Plan {uuid.uuid4()}",
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

        run(setup_subscription_db())

    return client


@pytest.fixture
def candidate_client():
    if not SQL_AVAILABLE:
        pytest.skip(SKIP_REASON_SQL)
    client = _make_authenticated_client("candidate")
    yield client
    run(client.aclose())


@pytest.fixture
def recruiter_client():
    if not SQL_AVAILABLE:
        pytest.skip(SKIP_REASON_SQL)
    client = _make_authenticated_client("recruiter", setup_subscription=True)
    yield client
    run(client.aclose())