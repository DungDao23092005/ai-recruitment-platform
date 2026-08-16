from __future__ import annotations

import asyncio
import hashlib
import socket
import uuid

import httpx
import pytest
from qdrant_client import AsyncQdrantClient
from tests.integration.conftest import run

from app.ai.interfaces.base_provider import (
    BaseEmbeddingProvider,
    BaseLLMProvider,
)
from app.ai.vector_db.qdrant_client import QdrantVectorRepository
from app.core.config import settings
from app.core.exceptions import InvalidDocumentError
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


class FakeEmbeddingProvider(BaseEmbeddingProvider):
    """Deterministic 384-dimensional embedding provider (offline)."""

    def embed_text(self, text: str) -> list[float]:
        return self._hash_vector(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
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


def _make_authenticated_client(role: str) -> httpx.AsyncClient:
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
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )


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
    client = _make_authenticated_client("recruiter")
    yield client
    run(client.aclose())