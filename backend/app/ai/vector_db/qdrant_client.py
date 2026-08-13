from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.ai.interfaces.base_provider import BaseVectorRepository
from app.core.config import settings
from app.core.exceptions import AIError, InvalidDocumentError

SOFT_DELETE_FILTER = Filter(
    must_not=[
        FieldCondition(
            key="is_deleted",
            match=MatchValue(value=True),
        )
    ]
)


class QdrantVectorRepository(BaseVectorRepository):
    """Qdrant-backed vector repository for resume and job vectors."""

    RESUME_COLLECTION = "resumes"
    JOB_COLLECTION = "jobs"

    def __init__(self, client: AsyncQdrantClient | None = None) -> None:
        self.client = client or AsyncQdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
        )

    @staticmethod
    def _serialize_point_id(point_id: str | uuid.UUID) -> str:
        return str(point_id)

    @staticmethod
    def _serialize_timestamp(value: datetime | None) -> str:
        if value is None:
            value = datetime.now(timezone.utc)
        elif value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()

    async def init_collections(self) -> None:
        """Ensure the resumes and jobs collections exist.

        Existing collections are never recreated.
        """
        for collection_name in (
            self.RESUME_COLLECTION,
            self.JOB_COLLECTION,
        ):
            if await self.client.collection_exists(
                collection_name=collection_name
            ):
                continue
            await self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=settings.VECTOR_DIMENSION,
                    distance=Distance.COSINE,
                ),
            )

    def _validate_vector(self, vector: list[float]) -> None:
        if len(vector) != settings.VECTOR_DIMENSION:
            raise InvalidDocumentError(
                f"Vector dimension {len(vector)} does not match expected "
                f"dimension {settings.VECTOR_DIMENSION}"
            )

    async def upsert_vector(
        self,
        collection_name: str,
        point_id: str | uuid.UUID,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        self._validate_vector(vector)
        point = PointStruct(
            id=self._serialize_point_id(point_id),
            vector=vector,
            payload=payload,
        )
        try:
            await self.client.upsert(
                collection_name=collection_name,
                points=[point],
            )
        except AIError:
            raise
        except Exception as exc:
            raise AIError(
                f"Failed to upsert vector into collection "
                f"'{collection_name}'"
            ) from exc

    async def upsert_resume_vector(
        self,
        candidate_id: str | uuid.UUID,
        vector: list[float],
        skills: list[str] | None = None,
        created_at: datetime | None = None,
    ) -> None:
        await self.upsert_vector(
            collection_name=self.RESUME_COLLECTION,
            point_id=candidate_id,
            vector=vector,
            payload={
                "candidate_id": self._serialize_point_id(candidate_id),
                "skills": skills or [],
                "created_at": self._serialize_timestamp(created_at),
                "is_deleted": False,
            },
        )

    async def upsert_job_vector(
        self,
        job_id: str | uuid.UUID,
        vector: list[float],
        skills: list[str] | None = None,
        created_at: datetime | None = None,
    ) -> None:
        await self.upsert_vector(
            collection_name=self.JOB_COLLECTION,
            point_id=job_id,
            vector=vector,
            payload={
                "job_id": self._serialize_point_id(job_id),
                "skills": skills or [],
                "created_at": self._serialize_timestamp(created_at),
                "is_deleted": False,
            },
        )

    async def delete_vector(
        self,
        collection_name: str,
        point_id: str | uuid.UUID,
    ) -> None:
        try:
            await self.client.delete(
                collection_name=collection_name,
                points_selector=[self._serialize_point_id(point_id)],
            )
        except AIError:
            raise
        except Exception as exc:
            raise AIError(
                f"Failed to delete vector from collection "
                f"'{collection_name}'"
            ) from exc

    async def search_similar(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self._validate_vector(query_vector)
        query_filter = self._build_query_filter(filters)
        try:
            response = await self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )
        except AIError:
            raise
        except Exception as exc:
            raise AIError(
                f"Failed to search similar vectors in collection "
                f"'{collection_name}'"
            ) from exc
        return [point.model_dump() for point in response.points]

    @staticmethod
    def _build_query_filter(
        filters: dict[str, Any] | None = None,
    ) -> Filter:
        if not filters:
            return SOFT_DELETE_FILTER
        return Filter(
            must=[
                FieldCondition(
                    key=str(key),
                    match=MatchValue(value=value),
                )
                for key, value in filters.items()
            ],
            must_not=SOFT_DELETE_FILTER.must_not,
        )
