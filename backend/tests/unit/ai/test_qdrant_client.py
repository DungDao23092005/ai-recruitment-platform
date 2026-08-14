from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.ai.vector_db.qdrant_client import (
    QdrantVectorRepository,
    SOFT_DELETE_FILTER,
)
from app.core.config import settings
from app.core.exceptions import AIError, InvalidDocumentError

VECTOR_DIM = settings.VECTOR_DIMENSION


def _vector(dim: int = VECTOR_DIM) -> list[float]:
    return [0.1] * dim


@pytest.fixture
def mock_client() -> AsyncMock:
    client = AsyncMock(spec=AsyncQdrantClient)
    client.collection_exists.return_value = False
    return client


@pytest.fixture
def repo(mock_client: AsyncMock) -> QdrantVectorRepository:
    return QdrantVectorRepository(client=mock_client)


@pytest.mark.asyncio
async def test_init_collections(repo: QdrantVectorRepository, mock_client: AsyncMock):
    await repo.init_collections()

    assert mock_client.collection_exists.call_count == 2
    assert (
        mock_client.collection_exists.await_args_list[0].kwargs[
            "collection_name"
        ]
        == QdrantVectorRepository.RESUME_COLLECTION
    )
    assert (
        mock_client.collection_exists.await_args_list[1].kwargs[
            "collection_name"
        ]
        == QdrantVectorRepository.JOB_COLLECTION
    )

    assert mock_client.create_collection.await_count == 2
    resume_call = mock_client.create_collection.await_args_list[0].kwargs
    job_call = mock_client.create_collection.await_args_list[1].kwargs

    assert resume_call["collection_name"] == "resumes"
    assert job_call["collection_name"] == "jobs"

    for call in (resume_call, job_call):
        vectors_config = call["vectors_config"]
        assert isinstance(vectors_config, VectorParams)
        assert vectors_config.size == VECTOR_DIM
        assert vectors_config.distance == Distance.COSINE


@pytest.mark.asyncio
async def test_upsert_vector_success(repo: QdrantVectorRepository, mock_client: AsyncMock):
    vector = _vector()
    payload = {"candidate_id": "c-1", "skills": ["Python"], "is_deleted": False}

    await repo.upsert_vector("resumes", "point-1", vector, payload)

    mock_client.upsert.assert_awaited_once()
    call_kwargs = mock_client.upsert.call_args.kwargs
    assert call_kwargs["collection_name"] == "resumes"
    assert len(call_kwargs["points"]) == 1

    point = call_kwargs["points"][0]
    assert isinstance(point, PointStruct)
    assert point.id == "point-1"
    assert point.vector == vector
    assert point.payload == payload


@pytest.mark.asyncio
async def test_upsert_resume_vector_payload(repo: QdrantVectorRepository, mock_client: AsyncMock):
    candidate_id = "candidate-42"
    skills = ["Python", "FastAPI"]
    created_at = datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc)

    await repo.upsert_resume_vector(
        candidate_id=candidate_id,
        vector=_vector(),
        skills=skills,
        created_at=created_at,
    )

    mock_client.upsert.assert_awaited_once()
    call_kwargs = mock_client.upsert.call_args.kwargs
    assert call_kwargs["collection_name"] == "resumes"
    point = call_kwargs["points"][0]

    payload = point.payload
    assert payload["candidate_id"] == "candidate-42"
    assert payload["skills"] == skills
    assert payload["created_at"] == "2026-01-15T10:30:00+00:00"
    assert payload["is_deleted"] is False
    assert not {"summary", "experiences", "education", "raw_text"}.intersection(
        payload
    )


@pytest.mark.asyncio
async def test_upsert_job_vector_payload(repo: QdrantVectorRepository, mock_client: AsyncMock):
    job_id = "job-7"
    skills = ["SQL Server", "Python"]

    await repo.upsert_job_vector(
        job_id=job_id,
        vector=_vector(),
        skills=skills,
    )

    mock_client.upsert.assert_awaited_once()
    call_kwargs = mock_client.upsert.call_args.kwargs
    assert call_kwargs["collection_name"] == "jobs"
    point = call_kwargs["points"][0]

    payload = point.payload
    assert payload["job_id"] == "job-7"
    assert payload["skills"] == skills
    assert isinstance(payload["created_at"], str)
    assert payload["is_deleted"] is False
    assert not {"title", "summary", "requirements", "description"}.intersection(
        payload
    )


@pytest.mark.asyncio
async def test_delete_vector_success(repo: QdrantVectorRepository, mock_client: AsyncMock):
    await repo.delete_vector("resumes", "point-9")

    mock_client.delete.assert_awaited_once()
    call_kwargs = mock_client.delete.call_args.kwargs
    assert call_kwargs["collection_name"] == "resumes"
    assert call_kwargs["points_selector"] == ["point-9"]


@pytest.mark.asyncio
async def test_search_similar_success(repo: QdrantVectorRepository, mock_client: AsyncMock):
    response = SimpleNamespace(
        points=[
            SimpleNamespace(
                model_dump=lambda: {
                    "id": "point-1",
                    "score": 0.87,
                    "payload": {"candidate_id": "c-1"},
                }
            ),
            SimpleNamespace(
                model_dump=lambda: {
                    "id": "point-2",
                    "score": 0.61,
                    "payload": {"candidate_id": "c-2"},
                }
            ),
        ]
    )
    mock_client.query_points.return_value = response

    query = _vector()
    result = await repo.search_similar("resumes", query, limit=5)

    mock_client.query_points.assert_awaited_once()
    call_kwargs = mock_client.query_points.call_args.kwargs
    assert call_kwargs["collection_name"] == "resumes"
    assert call_kwargs["query"] == query
    assert call_kwargs["limit"] == 5

    query_filter = call_kwargs["query_filter"]
    assert query_filter.must_not == [
        FieldCondition(key="is_deleted", match=MatchValue(value=True))
    ]

    assert result == [
        {"id": "point-1", "score": 0.87, "payload": {"candidate_id": "c-1"}},
        {"id": "point-2", "score": 0.61, "payload": {"candidate_id": "c-2"}},
    ]


@pytest.mark.asyncio
async def test_search_similar_preserves_soft_delete_with_extra_filters(
    repo: QdrantVectorRepository, mock_client: AsyncMock
):
    response = SimpleNamespace(points=[])
    mock_client.query_points.return_value = response

    await repo.search_similar(
        "jobs", _vector(), limit=3, filters={"job_id": "job-7"}
    )

    call_kwargs = mock_client.query_points.call_args.kwargs
    query_filter = call_kwargs["query_filter"]
    assert query_filter.must_not == [
        FieldCondition(key="is_deleted", match=MatchValue(value=True))
    ]
    assert query_filter.must == [
        FieldCondition(key="job_id", match=MatchValue(value="job-7"))
    ]


@pytest.mark.asyncio
async def test_vector_dimension_mismatch_raises_error(
    repo: QdrantVectorRepository, mock_client: AsyncMock
):
    with pytest.raises(InvalidDocumentError):
        await repo.upsert_vector("resumes", "point-1", [0.1, 0.2], {})

    with pytest.raises(InvalidDocumentError):
        await repo.search_similar("resumes", [0.1, 0.2], limit=5)

    mock_client.upsert.assert_not_awaited()
    mock_client.query_points.assert_not_awaited()


@pytest.mark.asyncio
async def test_connection_error_maps_to_ai_error(
    repo: QdrantVectorRepository, mock_client: AsyncMock
):
    mock_client.upsert.side_effect = RuntimeError("connection refused")

    with pytest.raises(AIError):
        await repo.upsert_vector(
            "resumes", "point-1", _vector(), {"candidate_id": "c-1"}
        )

    error_message = None
    try:
        await repo.upsert_vector(
            "resumes", "point-1", _vector(), {"candidate_id": "c-1"}
        )
    except AIError as exc:
        error_message = str(exc)
    assert "connection refused" not in (error_message or "")
    assert "resumes" in (error_message or "")


@pytest.mark.asyncio
async def test_existing_collections_not_recreated(
    repo: QdrantVectorRepository, mock_client: AsyncMock
):
    mock_client.collection_exists.return_value = True

    await repo.init_collections()

    mock_client.collection_exists.assert_awaited()
    mock_client.create_collection.assert_not_awaited()


@pytest.mark.asyncio
async def test_uuid_vector_id_serialization(
    repo: QdrantVectorRepository, mock_client: AsyncMock
):
    point_id = uuid.uuid4()

    await repo.upsert_vector("resumes", point_id, _vector(), {"k": "v"})

    mock_client.upsert.assert_awaited_once()
    point = mock_client.upsert.call_args.kwargs["points"][0]
    assert point.id == str(point_id)


def test_soft_delete_filter_definition():
    assert SOFT_DELETE_FILTER.must_not == [
        FieldCondition(key="is_deleted", match=MatchValue(value=True))
    ]


def _make_record(point_id: str, vector: list[float], payload: dict):
    return SimpleNamespace(id=point_id, vector=vector, payload=payload)


@pytest.mark.asyncio
async def test_retrieve_existing_vector(
    repo: QdrantVectorRepository, mock_client: AsyncMock
):
    vector = _vector()
    payload = {"candidate_id": "c-1", "skills": ["Python"]}
    mock_client.retrieve.return_value = [
        _make_record("point-1", vector, payload)
    ]

    result = await repo.retrieve_vector("resumes", "point-1")

    assert result == {"id": "point-1", "vector": vector, "payload": payload}


@pytest.mark.asyncio
async def test_retrieve_uuid_point_id(
    repo: QdrantVectorRepository, mock_client: AsyncMock
):
    point_id = uuid.uuid4()
    mock_client.retrieve.return_value = [
        _make_record(str(point_id), _vector(), {})
    ]

    result = await repo.retrieve_vector("resumes", point_id)

    assert result["id"] == str(point_id)


@pytest.mark.asyncio
async def test_retrieve_string_point_id(
    repo: QdrantVectorRepository, mock_client: AsyncMock
):
    mock_client.retrieve.return_value = [
        _make_record("job-9", _vector(), {})
    ]

    result = await repo.retrieve_vector("jobs", "job-9")

    assert result["id"] == "job-9"


@pytest.mark.asyncio
async def test_retrieve_missing_point_returns_none(
    repo: QdrantVectorRepository, mock_client: AsyncMock
):
    mock_client.retrieve.return_value = []

    result = await repo.retrieve_vector("resumes", "missing-1")

    assert result is None


@pytest.mark.asyncio
async def test_retrieve_uses_correct_collection(
    repo: QdrantVectorRepository, mock_client: AsyncMock
):
    mock_client.retrieve.return_value = [_make_record("point-1", _vector(), {})]

    await repo.retrieve_vector("jobs", "point-1")

    mock_client.retrieve.assert_awaited_once()
    assert mock_client.retrieve.call_args.kwargs["collection_name"] == "jobs"


@pytest.mark.asyncio
async def test_retrieve_uses_ids_list(
    repo: QdrantVectorRepository, mock_client: AsyncMock
):
    mock_client.retrieve.return_value = [_make_record("point-1", _vector(), {})]

    await repo.retrieve_vector("resumes", "point-1")

    assert mock_client.retrieve.call_args.kwargs["ids"] == ["point-1"]


@pytest.mark.asyncio
async def test_retrieve_with_vectors_true(
    repo: QdrantVectorRepository, mock_client: AsyncMock
):
    mock_client.retrieve.return_value = [_make_record("p", _vector(), {})]

    await repo.retrieve_vector("resumes", "p")

    assert mock_client.retrieve.call_args.kwargs["with_vectors"] is True


@pytest.mark.asyncio
async def test_retrieve_with_payload_true(
    repo: QdrantVectorRepository, mock_client: AsyncMock
):
    mock_client.retrieve.return_value = [_make_record("p", _vector(), {})]

    await repo.retrieve_vector("resumes", "p")

    assert mock_client.retrieve.call_args.kwargs["with_payload"] is True


@pytest.mark.asyncio
async def test_retrieve_failure_maps_to_ai_error(
    repo: QdrantVectorRepository, mock_client: AsyncMock
):
    mock_client.retrieve.side_effect = RuntimeError("connection refused")

    with pytest.raises(AIError):
        await repo.retrieve_vector("resumes", "point-1")

    error_message = None
    try:
        await repo.retrieve_vector("resumes", "point-1")
    except AIError as exc:
        error_message = str(exc)
    assert "connection refused" not in (error_message or "")
    assert "resumes" in (error_message or "")


@pytest.mark.asyncio
async def test_retrieve_payload_preserved(
    repo: QdrantVectorRepository, mock_client: AsyncMock
):
    payload = {"skills": ["Python", "SQL"], "is_deleted": False}
    mock_client.retrieve.return_value = [
        _make_record("point-1", _vector(), payload)
    ]

    result = await repo.retrieve_vector("resumes", "point-1")

    assert result["payload"] == payload


@pytest.mark.asyncio
async def test_retrieve_vector_preserved(
    repo: QdrantVectorRepository, mock_client: AsyncMock
):
    vector = [0.5, 0.25, 0.125]
    mock_client.retrieve.return_value = [
        _make_record("point-1", vector, {"k": "v"})
    ]

    result = await repo.retrieve_vector("resumes", "point-1")

    assert result["vector"] == vector
