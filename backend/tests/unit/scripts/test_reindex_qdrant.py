from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.knowledge import KnowledgeCategory
from scripts import reindex_qdrant as rq


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def unique(self):
        return self

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


class _FakeSession:
    def __init__(self, pages):
        self._pages = [list(page) for page in pages]
        self.execute = AsyncMock(side_effect=self._execute)
        self.calls = 0

    async def _execute(self, _statement):
        self.calls += 1
        if self._pages:
            return _Result(self._pages.pop(0))
        return _Result([])


class _FakeVectorRepository:
    def __init__(self, dimension=384, points_count=0, error=None):
        self.client = SimpleNamespace()
        if error is not None:
            self.client.get_collection = AsyncMock(side_effect=error)
        else:
            self.client.get_collection = AsyncMock(
                return_value=SimpleNamespace(
                    config=SimpleNamespace(
                        params=SimpleNamespace(
                            vectors=SimpleNamespace(size=dimension)
                        )
                    ),
                    points_count=points_count,
                )
            )
        self.upsert_vector = AsyncMock()
        self.delete_vector = AsyncMock()
        self.delete_vectors_by_filter = AsyncMock()
        self.create_collection = AsyncMock()


def _embedding(vector):
    return SimpleNamespace(embed_text=AsyncMock(return_value=vector))


def _resume(parsed_data=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        candidate_id=uuid.uuid4(),
        parsed_data=parsed_data,
        confirmed_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )


def _job():
    return SimpleNamespace(id=uuid.uuid4())


def _knowledge_document(content="Knowledge content", title="Doc"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        content=content,
        title=title,
        category=KnowledgeCategory.CAREER,
    )


def _stats(collection, dimension=384):
    return rq.CollectionStats(
        collection=collection,
        collection_dimension=dimension,
    )


@pytest.mark.asyncio
async def test_preflight_rejects_dimension_mismatch():
    repository = _FakeVectorRepository(dimension=768)

    with pytest.raises(rq.ReindexError, match="dimension"):
        await rq.preflight_collections(
            repository, [rq.JOBS], expected_dimension=384
        )


@pytest.mark.asyncio
async def test_preflight_rejects_missing_collection_without_creating_it():
    repository = _FakeVectorRepository(error=RuntimeError("not found"))

    with pytest.raises(rq.ReindexError, match="Refusing to create"):
        await rq.preflight_collections(repository, [rq.JOBS])

    repository.create_collection.assert_not_called()


@pytest.mark.asyncio
async def test_preflight_records_existing_points():
    repository = _FakeVectorRepository(dimension=384, points_count=7)

    stats = await rq.preflight_collections(
        repository, [rq.JOBS], expected_dimension=384
    )

    assert stats[rq.JOBS].collection_dimension == 384
    assert stats[rq.JOBS].existing_points == 7


def test_knowledge_point_id_is_deterministic_and_namespaced():
    document_id = uuid.uuid4()

    first = rq.knowledge_point_id(document_id, 0)
    second = rq.knowledge_point_id(document_id, 0)
    other_chunk = rq.knowledge_point_id(document_id, 1)

    assert first == second
    assert first != other_chunk
    assert isinstance(first, uuid.UUID)


def test_knowledge_payload_matches_rag_reader_contract():
    document_id = uuid.uuid4()

    payload = rq.build_knowledge_payload(
        document_id=document_id,
        chunk_index=3,
        category="career",
        title="Career guide",
    )

    assert payload == {
        "document_id": str(document_id),
        "chunk_index": 3,
        "category": "career",
        "title": "Career guide",
    }


def test_validate_vector_dimension_rejects_mismatch():
    with pytest.raises(rq.ReindexError, match="does not match"):
        rq.validate_vector_dimension([0.0, 1.0], 384)

    rq.validate_vector_dimension([0.0] * 384, 384)


@pytest.mark.asyncio
async def test_knowledge_dry_run_does_not_embed_or_write():
    document = _knowledge_document(content="x" * 1200)
    session = _FakeSession([[document]])
    embedding = _embedding([0.0] * 384)
    repository = _FakeVectorRepository()
    stats = _stats(rq.KNOWLEDGE)

    await rq.reindex_knowledge(
        session,
        stats,
        execute=False,
        batch_size=10,
        embedding_service=embedding,
        vector_repository=repository,
    )

    expected_chunks = len(rq.chunk_text(document.content))
    assert stats.source_records == 1
    assert stats.records_processed == 1
    assert stats.vectors_planned == expected_chunks
    assert stats.vectors_written == 0
    embedding.embed_text.assert_not_called()
    repository.upsert_vector.assert_not_called()
    repository.delete_vector.assert_not_called()
    repository.delete_vectors_by_filter.assert_not_called()


@pytest.mark.asyncio
async def test_knowledge_execute_upserts_stable_ids_and_payload():
    document = _knowledge_document(content="short knowledge")
    session = _FakeSession([[document]])
    embedding = _embedding([0.0] * 384)
    repository = _FakeVectorRepository()
    stats = _stats(rq.KNOWLEDGE)

    await rq.reindex_knowledge(
        session,
        stats,
        execute=True,
        batch_size=10,
        embedding_service=embedding,
        vector_repository=repository,
    )

    assert stats.records_processed == 1
    assert stats.vectors_written == 1
    assert repository.upsert_vector.await_count == 1
    call = repository.upsert_vector.await_args
    assert call.kwargs["collection_name"] == rq.KNOWLEDGE
    assert call.kwargs["point_id"] == rq.knowledge_point_id(document.id, 0)
    assert call.kwargs["payload"] == {
        "document_id": str(document.id),
        "chunk_index": 0,
        "category": "career",
        "title": document.title,
    }


@pytest.mark.asyncio
async def test_knowledge_rerun_reuses_same_point_ids():
    document = _knowledge_document(content="rerun-safe")
    repository = _FakeVectorRepository()
    embedding = _embedding([0.0] * 384)

    for _ in range(2):
        await rq.reindex_knowledge(
            _FakeSession([[document]]),
            _stats(rq.KNOWLEDGE),
            execute=True,
            batch_size=10,
            embedding_service=embedding,
            vector_repository=repository,
        )

    ids = [call.kwargs["point_id"] for call in repository.upsert_vector.await_args_list]
    assert len(ids) == 2
    assert ids[0] == ids[1]


@pytest.mark.asyncio
async def test_knowledge_dimension_mismatch_never_upserts():
    document = _knowledge_document(content="short knowledge")
    repository = _FakeVectorRepository()
    stats = _stats(rq.KNOWLEDGE, dimension=384)

    await rq.reindex_knowledge(
        _FakeSession([[document]]),
        stats,
        execute=True,
        batch_size=10,
        embedding_service=_embedding([0.0, 1.0]),
        vector_repository=repository,
    )

    assert stats.records_failed == 1
    assert stats.vectors_failed == 1
    repository.upsert_vector.assert_not_called()


@pytest.mark.asyncio
async def test_resume_dry_run_does_not_call_canonical_indexer():
    resume = _resume({"title": "Engineer", "skills": ["Python"]})
    matching_service = SimpleNamespace(_reindex_resume=AsyncMock())
    stats = _stats(rq.RESUMES)

    await rq.reindex_resumes(
        _FakeSession([[resume]]),
        stats,
        execute=False,
        batch_size=10,
        matching_service=matching_service,
    )

    assert stats.source_records == 1
    assert stats.records_processed == 1
    assert stats.vectors_planned == 1
    assert stats.vectors_written == 0
    matching_service._reindex_resume.assert_not_called()


@pytest.mark.asyncio
async def test_resume_execute_uses_canonical_reindex_and_payload_inputs():
    resume = _resume({"title": "Engineer", "skills": ["Python"]})
    matching_service = SimpleNamespace(_reindex_resume=AsyncMock())
    stats = _stats(rq.RESUMES)

    await rq.reindex_resumes(
        _FakeSession([[resume]]),
        stats,
        execute=True,
        batch_size=10,
        matching_service=matching_service,
    )

    matching_service._reindex_resume.assert_awaited_once()
    call = matching_service._reindex_resume.await_args
    assert call.kwargs["candidate_id"] == resume.candidate_id
    assert call.kwargs["resume_id"] == resume.id
    assert call.kwargs["confirmed_at"] == resume.confirmed_at
    assert call.kwargs["is_deleted"] is False
    assert call.kwargs["parsed_resume"].title == "Engineer"
    assert stats.records_processed == 1
    assert stats.vectors_written == 1


@pytest.mark.asyncio
async def test_resume_with_missing_parsed_data_is_skipped():
    resume = _resume(None)
    matching_service = SimpleNamespace(_reindex_resume=AsyncMock())
    stats = _stats(rq.RESUMES)

    await rq.reindex_resumes(
        _FakeSession([[resume]]),
        stats,
        execute=True,
        batch_size=10,
        matching_service=matching_service,
    )

    assert stats.records_skipped == 1
    assert stats.records_processed == 0
    matching_service._reindex_resume.assert_not_called()


@pytest.mark.asyncio
async def test_resume_failure_continues_to_next_record():
    resumes = [
        _resume({"skills": ["Python"]}),
        _resume({"skills": ["SQL"]}),
    ]
    matching_service = SimpleNamespace(
        _reindex_resume=AsyncMock(side_effect=[RuntimeError("embedding down"), None])
    )
    stats = _stats(rq.RESUMES)

    await rq.reindex_resumes(
        _FakeSession([resumes]),
        stats,
        execute=True,
        batch_size=10,
        matching_service=matching_service,
    )

    assert stats.source_records == 2
    assert stats.records_failed == 1
    assert stats.records_processed == 1
    assert matching_service._reindex_resume.await_count == 2


@pytest.mark.asyncio
async def test_jobs_batch_processing_and_continue_on_error():
    jobs = [_job() for _ in range(3)]
    job_service = SimpleNamespace(
        _reindex_job=AsyncMock(side_effect=[None, RuntimeError("boom"), None])
    )
    session = _FakeSession([jobs[0:2], jobs[2:3]])
    stats = _stats(rq.JOBS)

    await rq.reindex_jobs(
        session,
        stats,
        execute=True,
        batch_size=2,
        job_service=job_service,
    )

    assert session.execute.await_count == 2
    assert job_service._reindex_job.await_count == 3
    assert stats.source_records == 3
    assert stats.records_processed == 2
    assert stats.records_failed == 1
    assert stats.vectors_written == 2
    assert stats.vectors_failed == 1


@pytest.mark.asyncio
async def test_jobs_dry_run_does_not_call_canonical_indexer():
    job_service = SimpleNamespace(_reindex_job=AsyncMock())
    stats = _stats(rq.JOBS)

    await rq.reindex_jobs(
        _FakeSession([[_job()]]),
        stats,
        execute=False,
        batch_size=10,
        job_service=job_service,
    )

    assert stats.records_processed == 1
    assert stats.vectors_written == 0
    job_service._reindex_job.assert_not_called()


def test_cli_defaults_to_dry_run_and_requires_explicit_execute():
    parser = rq.build_parser()

    assert parser.parse_args([]).execute is False
    assert parser.parse_args(["--dry-run"]).execute is False
    assert parser.parse_args(["--execute"]).execute is True

    with pytest.raises(SystemExit):
        parser.parse_args(["--execute", "--dry-run"])


def test_cli_rejects_unknown_collection():
    parser = rq.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--collection", "unknown"])
