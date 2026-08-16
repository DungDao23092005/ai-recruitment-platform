from __future__ import annotations

import uuid

import pytest
from qdrant_client.models import Distance

from app.core.exceptions import InvalidDocumentError
from app.core.config import settings

from .conftest import (
    QDRANT_AVAILABLE,
    SKIP_REASON_QDRANT,
    VECTOR_DIM,
    run,
)

pytestmark = [
    pytest.mark.skipif(
        not QDRANT_AVAILABLE,
        reason=SKIP_REASON_QDRANT,
    ),
    pytest.mark.asyncio,
]


def _vector(dim: int = VECTOR_DIM) -> list[float]:
    return [0.1] * dim


class TestInitCollections:
    async def test_init_collections_creates_resumes_and_jobs(
        self, vector_repository, qdrant_client
    ):
        await vector_repository.init_collections()

        for collection in ("resumes", "jobs"):
            exists = await qdrant_client.collection_exists(collection)
            assert exists, f"{collection} collection should exist"
            info = await qdrant_client.get_collection(collection)
            assert info.config.params.vectors.size == settings.VECTOR_DIMENSION
            assert info.config.params.vectors.distance == Distance.COSINE


class TestUpsertAndRetrieve:
    async def test_upsert_and_retrieve_resume_vector(
        self, vector_repository, tracked
    ):
        candidate_id = uuid.uuid4()
        skills = ["Python", "FastAPI"]
        tracked("resumes", candidate_id)

        await vector_repository.upsert_resume_vector(
            candidate_id=candidate_id,
            vector=_vector(),
            skills=skills,
        )

        retrieved = await vector_repository.retrieve_vector(
            "resumes", candidate_id
        )
        assert retrieved is not None
        assert retrieved["id"] == str(candidate_id)
        assert len(retrieved["vector"]) == VECTOR_DIM
        assert retrieved["payload"]["candidate_id"] == str(candidate_id)
        assert retrieved["payload"]["skills"] == skills

    async def test_upsert_and_retrieve_job_vector(
        self, vector_repository, tracked
    ):
        job_id = uuid.uuid4()
        skills = ["Python", "Docker"]
        tracked("jobs", job_id)

        await vector_repository.upsert_job_vector(
            job_id=job_id,
            vector=_vector(),
            skills=skills,
        )

        retrieved = await vector_repository.retrieve_vector("jobs", job_id)
        assert retrieved is not None
        assert retrieved["id"] == str(job_id)
        assert len(retrieved["vector"]) == VECTOR_DIM
        assert retrieved["payload"]["job_id"] == str(job_id)
        assert retrieved["payload"]["skills"] == skills


class TestSearch:
    async def test_search_similar_returns_relevant_points(
        self, vector_repository, tracked
    ):
        await vector_repository.init_collections()
        target_id = uuid.uuid4()
        far_id = uuid.uuid4()
        tracked("resumes", target_id)
        tracked("resumes", far_id)

        target_vector = [1.0] + [0.0] * (VECTOR_DIM - 1)
        far_vector = [0.0] + [1.0] + [0.0] * (VECTOR_DIM - 2)
        await vector_repository.upsert_resume_vector(
            candidate_id=target_id, vector=target_vector, skills=["Python"]
        )
        await vector_repository.upsert_resume_vector(
            candidate_id=far_id, vector=far_vector, skills=["Java"]
        )

        results = await vector_repository.search_similar(
            "resumes", target_vector, limit=5
        )

        assert results, "search should return points"
        assert results[0]["payload"]["candidate_id"] == str(target_id)
        ids = [r["payload"]["candidate_id"] for r in results]
        assert str(far_id) in ids

    async def test_soft_delete_filter_excludes_deleted_vectors(
        self, vector_repository, tracked
    ):
        await vector_repository.init_collections()
        active_id = uuid.uuid4()
        deleted_id = uuid.uuid4()
        tracked("jobs", active_id)
        tracked("jobs", deleted_id)

        vector = _vector()
        await vector_repository.upsert_job_vector(
            job_id=active_id, vector=vector, skills=["Python"]
        )
        await vector_repository.upsert_vector(
            collection_name="jobs",
            point_id=deleted_id,
            vector=vector,
            payload={
                "job_id": str(deleted_id),
                "skills": ["Python"],
                "is_deleted": True,
            },
        )

        results = await vector_repository.search_similar(
            "jobs", vector, limit=10
        )

        returned_ids = [r["payload"].get("job_id") for r in results]
        assert str(active_id) in returned_ids
        assert str(deleted_id) not in returned_ids


class TestDelete:
    async def test_delete_vector_removes_point(
        self, vector_repository, tracked
    ):
        point_id = uuid.uuid4()
        tracked("resumes", point_id)
        await vector_repository.upsert_resume_vector(
            candidate_id=point_id, vector=_vector(), skills=["Python"]
        )

        assert await vector_repository.retrieve_vector(
            "resumes", point_id
        ) is not None

        await vector_repository.delete_vector("resumes", point_id)

        assert await vector_repository.retrieve_vector(
            "resumes", point_id
        ) is None


class TestDimensionValidation:
    async def test_vector_dimension_mismatch_raises_error(
        self, vector_repository, tracked
    ):
        point_id = uuid.uuid4()
        tracked("resumes", point_id)

        with pytest.raises(InvalidDocumentError, match="dimension"):
            await vector_repository.upsert_resume_vector(
                candidate_id=point_id,
                vector=[0.1] * (VECTOR_DIM - 1),
                skills=["Python"],
            )

        assert await vector_repository.retrieve_vector(
            "resumes", point_id
        ) is None