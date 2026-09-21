from __future__ import annotations

import uuid
from typing import Any

from app.ai.embeddings.embedding_service import EmbeddingService
from app.ai.interfaces.base_provider import BaseVectorRepository
from app.core.exceptions import (
    AIError,
    EmptyDocumentError,
    InvalidDocumentError,
)
from app.domain.enums import JobStatus, UserRole
from app.models import CandidateProfile, Job
from app.repositories import BaseRepository
from app.schemas.ai_search import SemanticSearchResult


class SemanticSearchService:
    """Semantic search over indexed jobs and candidate resumes.

    Natural language query -> embedding -> vector search -> typed results.
    The semantic score is preserved exactly as returned by the vector store.
    """

    # Dynamic retrieval bounds (Architecture v3.2)
    PAGE_SIZE = 50
    MAX_PAGES = 3
    MAX_CANDIDATES = PAGE_SIZE * MAX_PAGES  # 150

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        vector_repository: BaseVectorRepository | None = None,
    ) -> None:
        from app.ai.vector_db.qdrant_client import QdrantVectorRepository
        from app.ai.embeddings.embedding_service import (
            SentenceTransformerEmbeddingProvider,
        )

        self.embedding_service = embedding_service or EmbeddingService(
            SentenceTransformerEmbeddingProvider()
        )
        self.vector_repository = vector_repository or QdrantVectorRepository()

    async def search_jobs(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float | None = None,
        job_repository: BaseRepository[Job] | None = None,
        actor_user: Any | None = None,
    ) -> list[SemanticSearchResult]:
        """Search jobs and enrich with job metadata.

        When ``job_repository`` is provided, results are enriched with
        ``title``, ``company_name``, and ``location`` from ``Job`` using a single
        batch query. Ghost/deleted jobs are filtered out. Qdrant ranking
        order is preserved.

        Role-based visibility is enforced at the SQL hydration layer:
        - CANDIDATE: only PUBLISHED, non-deleted jobs
        - RECRUITER: only jobs from their own company (non-deleted)
        - ADMIN: all non-deleted jobs

        Dynamic retrieval (Architecture v3.2):
        - Candidate/Public: Qdrant filter adds status=published to prevent starvation
        - Retrieval: up to 3 pages of 50 (150 max candidates)
        - Deduplication: seen Qdrant point IDs excluded across pages
        """
        effective_limit = max(1, min(100, limit))

        # Determine if we need candidate/public visibility filtering at Qdrant level
        is_candidate_public = (
            actor_user is not None
            and getattr(actor_user, "role", None) == UserRole.CANDIDATE
        ) or actor_user is None  # Public/unauthenticated also gets published-only

        # Dynamic retrieval with pagination and deduplication
        raw_results = await self._search_jobs_dynamic(
            query=query,
            score_threshold=score_threshold,
            is_candidate_public=is_candidate_public,
            max_results=effective_limit,
        )

        if job_repository is None or not raw_results:
            return raw_results[:effective_limit]

        # Extract job IDs from Qdrant results (preserving order)
        job_ids = [uuid.UUID(r.id) for r in raw_results]

        # Batch query for jobs with company, applying role-based visibility
        jobs = await self._fetch_jobs(job_repository, job_ids, actor_user)

        # Build lookup map
        job_map = {j.id: j for j in jobs}

        # Enrich results preserving Qdrant order, filter out missing/deleted
        enriched: list[SemanticSearchResult] = []
        for r in raw_results:
            job_id = uuid.UUID(r.id)
            job = job_map.get(job_id)
            if job is None:
                continue  # Ghost or deleted job - filter out
            enriched.append(
                SemanticSearchResult(
                    id=r.id,
                    score=r.score,
                    skills=r.skills,
                    created_at=r.created_at,
                    title=job.title,
                    company_name=job.company.name if job.company else None,
                    location=job.location,
                )
            )
        return enriched[:effective_limit]

    async def search_candidates(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float | None = None,
        candidate_repository: BaseRepository[CandidateProfile] | None = None,
    ) -> list[SemanticSearchResult]:
        """Search candidates and enrich with profile data.

        When ``candidate_repository`` is provided, results are enriched with
        ``full_name`` and ``title`` from ``CandidateProfile`` using a single
        batch query. Ghost/deleted candidates are filtered out. Qdrant ranking
        order is preserved.
        """
        effective_limit = max(1, min(100, limit))

        raw_results = await self._search(
            collection_name="resumes",
            id_field="candidate_id",
            query=query,
            limit=limit,
            score_threshold=score_threshold,
        )

        if candidate_repository is None or not raw_results:
            return raw_results[:effective_limit]

        # Extract candidate IDs from Qdrant results (preserving order)
        candidate_ids = [uuid.UUID(r.id) for r in raw_results]

        # Batch query for candidate profiles
        profiles = await self._fetch_candidate_profiles(
            candidate_repository, candidate_ids
        )

        # Build lookup map
        profile_map = {p.id: p for p in profiles}

        # Enrich results preserving Qdrant order, filter out missing/deleted
        enriched: list[SemanticSearchResult] = []
        for r in raw_results:
            cand_id = uuid.UUID(r.id)
            profile = profile_map.get(cand_id)
            if profile is None:
                continue  # Ghost or deleted candidate - filter out
            enriched.append(
                SemanticSearchResult(
                    id=r.id,
                    score=r.score,
                    skills=r.skills,
                    created_at=r.created_at,
                    full_name=profile.full_name,
                    title=profile.title,
                )
            )
        return enriched[:effective_limit]

    async def _fetch_candidate_profiles(
        self,
        repository: BaseRepository[CandidateProfile],
        candidate_ids: list[uuid.UUID],
    ) -> list[CandidateProfile]:
        """Batch fetch non-deleted candidate profiles by IDs."""
        if not candidate_ids:
            return []
        from sqlalchemy import select
        stmt = (
            select(CandidateProfile)
            .where(
                CandidateProfile.id.in_(candidate_ids),
                CandidateProfile.is_deleted == False,  # noqa: E712
            )
        )
        result = await repository.session.execute(stmt)
        return list(result.scalars().all())

    async def _fetch_jobs(
        self,
        repository: BaseRepository[Job],
        job_ids: list[uuid.UUID],
        actor_user: Any | None = None,
    ) -> list[Job]:
        """Batch fetch jobs with company by IDs, applying role-based visibility."""
        if not job_ids:
            return []
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload
        from app.domain.enums import JobStatus, UserRole
        from app.models import RecruiterProfile

        stmt = (
            select(Job)
            .options(joinedload(Job.company))
            .where(
                Job.id.in_(job_ids),
                Job.is_deleted == False,  # noqa: E712
            )
        )

        # Apply role-based visibility filters at SQL level
        if actor_user is not None:
            if actor_user.role == UserRole.CANDIDATE:
                # Candidate: only PUBLISHED jobs
                stmt = stmt.where(Job.status == JobStatus.PUBLISHED)
            elif actor_user.role == UserRole.RECRUITER:
                # Recruiter: only jobs from their company
                recruiter_company_id = await self._get_recruiter_company_id(repository, actor_user.id)
                if recruiter_company_id is None:
                    return []
                stmt = stmt.where(Job.company_id == recruiter_company_id)
            # ADMIN: no additional filters (can see all non-deleted jobs)

        result = await repository.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def _get_recruiter_company_id(self, repository: BaseRepository[Job], user_id: uuid.UUID) -> uuid.UUID | None:
        """Get the company ID for a recruiter user."""
        from sqlalchemy import select
        from app.models import RecruiterProfile
        stmt = select(RecruiterProfile.company_id).where(
            RecruiterProfile.user_id == user_id,
            RecruiterProfile.is_deleted == False,  # noqa: E712
        )
        result = await repository.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _search_jobs_dynamic(
        self,
        query: str,
        score_threshold: float | None,
        is_candidate_public: bool,
        max_results: int,
    ) -> list[SemanticSearchResult]:
        """
        Dynamic retrieval with pagination and deduplication (Architecture v3.2).

        - Page size: 50
        - Max pages: 3
        - Max candidates: 150
        - Excludes previously seen point IDs across pages
        - For candidate/public: adds status=published filter
        - Stops when max_results fulfilled, page < 50, or max pages reached
        """
        if not query or not query.strip():
            raise EmptyDocumentError("Search query cannot be empty")

        query_vector = await self.embedding_service.embed_text(query)

        # Build base filters
        base_filters: dict[str, Any] = {}
        if is_candidate_public:
            base_filters["status"] = JobStatus.PUBLISHED.value

        seen_ids: set[str] = set()
        all_results: list[SemanticSearchResult] = []
        pages_fetched = 0

        while pages_fetched < self.MAX_PAGES and len(all_results) < max_results:
            # Build filters for this page
            page_filters = dict(base_filters)

            try:
                raw_results = await self.vector_repository.search_similar(
                    collection_name="jobs",
                    query_vector=query_vector,
                    limit=self.PAGE_SIZE,
                    filters=page_filters if page_filters else None,
                    score_threshold=score_threshold,
                    exclude_ids=list(seen_ids) if seen_ids else None,
                )
            except AIError:
                raise
            except Exception as exc:
                raise AIError(
                    f"Failed to search similar vectors in collection 'jobs'"
                ) from exc

            if not raw_results:
                break

            # Process results, filter out seen IDs, and convert
            page_results: list[SemanticSearchResult] = []
            for res in raw_results:
                point_id = self._extract_point_id(res, "job_id")
                if point_id is None or point_id in seen_ids:
                    continue
                score = self._extract_score(res)
                if score is None:
                    continue
                if score_threshold is not None and score < score_threshold:
                    continue
                seen_ids.add(point_id)
                payload = res.get("payload") or {}
                page_results.append(
                    SemanticSearchResult(
                        id=point_id,
                        score=score,
                        skills=list(payload.get("skills") or []),
                        created_at=payload.get("created_at"),
                    )
                )

            all_results.extend(page_results)
            pages_fetched += 1

            # Stop if we got fewer than page_size (end of results)
            if len(raw_results) < self.PAGE_SIZE:
                break

        return all_results[:max_results]

    async def _search(
        self,
        collection_name: str,
        id_field: str,
        query: str,
        limit: int,
        score_threshold: float | None,
    ) -> list[SemanticSearchResult]:
        """Legacy search method for candidates and backward compatibility."""
        effective_limit = max(1, min(100, limit))
        search_limit = min(100, max(50, effective_limit * 3))

        if not query or not query.strip():
            raise EmptyDocumentError(
                "Search query cannot be empty"
            )

        query_vector = await self.embedding_service.embed_text(query)

        try:
            raw_results = await self.vector_repository.search_similar(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=search_limit,
            )
        except AIError:
            raise
        except Exception as exc:
            raise AIError(
                f"Failed to search similar vectors in collection "
                f"'{collection_name}'"
            ) from exc

        results: list[SemanticSearchResult] = []
        for res in raw_results:
            point_id = self._extract_point_id(res, id_field)
            if point_id is None:
                continue
            score = self._extract_score(res)
            if score is None:
                continue
            if score_threshold is not None and score < score_threshold:
                continue
            payload = res.get("payload") or {}
            results.append(
                SemanticSearchResult(
                    id=point_id,
                    score=score,
                    skills=list(payload.get("skills") or []),
                    created_at=payload.get("created_at"),
                )
            )
        return results

    @staticmethod
    def _extract_point_id(res: dict[str, Any], id_field: str) -> str | None:
        raw_id = res.get("id") or (res.get("payload") or {}).get(id_field)
        if raw_id is None:
            return None
        return str(raw_id)

    @staticmethod
    def _extract_score(res: dict[str, Any]) -> float | None:
        raw_score = res.get("score")
        if raw_score is None:
            return None
        try:
            return float(raw_score)
        except (TypeError, ValueError):
            return None