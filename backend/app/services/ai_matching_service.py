from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.embedding_service import (
    EmbeddingService,
    SentenceTransformerEmbeddingProvider,
)
from app.ai.extractors.isolated_pdf import extract_pdf_text_isolated
from app.ai.interfaces.base_provider import BaseVectorRepository
from app.ai.matching.matching_engine import MatchingEngine
from app.ai.parsers.job_parser import JobParser
from app.ai.parsers.resume_parser import ResumeParser
from app.ai.vector_db.qdrant_client import QdrantVectorRepository
from app.core.exceptions import EmptyDocumentError, EntityNotFoundException
from app.domain.enums import JobStatus
from app.models import CandidateProfile, Job, Resume, User
from app.repositories import ResumeRepository
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_matching import (
    CandidateMatchRecommendation,
    JobMatchRecommendation,
)
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.context_resolver import ContextResolver


class AIMatchingService:
    """Unified AI Matching Application Service coordinating extractors, parsers, embeddings, vector storage, and matching engine."""

    def __init__(
        self,
        resume_parser: ResumeParser | None = None,
        job_parser: JobParser | None = None,
        embedding_service: EmbeddingService | None = None,
        vector_repository: BaseVectorRepository | None = None,
        matching_engine: MatchingEngine | None = None,
        context_resolver: ContextResolver | None = None,
    ) -> None:
        self.resume_parser = resume_parser or ResumeParser()
        self.job_parser = job_parser or JobParser()
        self.embedding_service = embedding_service or EmbeddingService(SentenceTransformerEmbeddingProvider())
        self.vector_repository = vector_repository or QdrantVectorRepository()
        self.matching_engine = matching_engine or MatchingEngine()
        self._context_resolver = context_resolver

    def _get_resolver(self, session: AsyncSession) -> ContextResolver:
        """Get ContextResolver instance (use injected one for testing)."""
        if self._context_resolver is not None:
            return self._context_resolver
        return ContextResolver(session)

    async def parse_and_save_resume_draft(
        self,
        candidate_id: uuid.UUID,
        pdf_source: bytes | str | os.PathLike[str] | BinaryIO,
        session: AsyncSession,
        source_name: str | None = None,
    ) -> Resume:
        """Parse a PDF into an unconfirmed draft without touching Qdrant.

        The candidate's previously confirmed resume remains active until the
        draft is explicitly confirmed through the resume lifecycle service.
        """
        extracted_text = await extract_pdf_text_isolated(pdf_source)
        parsed_resume = await self.resume_parser.parse(extracted_text)

        repository = ResumeRepository(session, Resume)
        try:
            draft = await repository.upsert_draft(
                candidate_id=candidate_id,
                title=source_name,
                parsed_data=parsed_resume.model_dump(mode="json"),
            )
            await session.commit()
            await session.refresh(draft)
        except Exception:
            await session.rollback()
            raise

        return draft

    async def index_confirmed_resume(
        self,
        candidate_id: uuid.UUID,
        resume_id: uuid.UUID,
        parsed_resume: ParsedResumeSchema,
        confirmed_at: datetime | None = None,
    ) -> None:
        """Index only an explicitly confirmed resume in Qdrant."""
        vector = await self.embedding_service.embed_resume(parsed_resume)
        await self.vector_repository.upsert_vector(
            collection_name="resumes",
            point_id=candidate_id,
            vector=vector,
            payload=self._resume_payload(
                candidate_id=candidate_id,
                resume_id=resume_id,
                skills=parsed_resume.skills,
                is_deleted=False,
                confirmed_at=confirmed_at,
            ),
        )

    @staticmethod
    def _serialize_confirmed_at(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    @classmethod
    def _resume_payload(
        cls,
        candidate_id: uuid.UUID,
        resume_id: uuid.UUID | None,
        skills: list[str],
        is_deleted: bool,
        confirmed_at: datetime | None = None,
    ) -> dict:
        return {
            "candidate_id": str(candidate_id),
            "resume_id": str(resume_id) if resume_id else None,
            "skills": skills,
            "is_deleted": is_deleted,
            "is_confirmed": True,
            "confirmed_at": cls._serialize_confirmed_at(confirmed_at),
        }

    async def _reindex_resume(
        self,
        candidate_id: uuid.UUID,
        parsed_resume: ParsedResumeSchema,
        is_deleted: bool = False,
        vector: list[float] | None = None,
        resume_id: uuid.UUID | None = None,
        confirmed_at: datetime | None = None,
    ) -> None:
        """Canonical reindex method for an already-confirmed resume."""
        if vector is None:
            vector = await self.embedding_service.embed_resume(parsed_resume)
        await self.vector_repository.upsert_vector(
            collection_name="resumes",
            point_id=candidate_id,
            vector=vector,
            payload=self._resume_payload(
                candidate_id=candidate_id,
                resume_id=resume_id,
                skills=parsed_resume.skills,
                is_deleted=is_deleted,
                confirmed_at=confirmed_at,
            ),
        )

    async def delete_resume_vector(self, candidate_id: uuid.UUID) -> None:
        """Delete a resume vector from Qdrant.

        Used when a candidate's resume is soft-deleted or the candidate is removed.
        """
        await self.vector_repository.delete_vector(
            collection_name="resumes",
            point_id=candidate_id,
        )

    async def process_and_index_job(
        self,
        job_id: uuid.UUID,
        job_title: str,
        job_description: str,
    ) -> ParsedJobSchema:
        """Parse structured Job Description, generate embedding vector, and index to Qdrant."""
        if not job_description or not job_description.strip():
            raise EmptyDocumentError("Job description text for parsing cannot be empty")

        full_jd_text = f"Title: {job_title}\nDescription: {job_description.strip()}"
        parsed_job = await self.job_parser.parse(full_jd_text)

        if not parsed_job.title:
            parsed_job.title = job_title

        vector = await self.embedding_service.embed_job(parsed_job)
        all_skills = list(
            set(parsed_job.required_skills + parsed_job.preferred_skills)
        )
        payload = {
            "job_id": str(job_id),
            "skills": all_skills,
            "is_deleted": False,
        }
        await self.vector_repository.upsert_vector(
            collection_name="jobs",
            point_id=job_id,
            vector=vector,
            payload=payload,
        )

        return parsed_job

    async def match_candidate_with_job(
        self,
        parsed_resume: ParsedResumeSchema,
        parsed_job: ParsedJobSchema,
        resume_vector: list[float] | None = None,
        job_vector: list[float] | None = None,
    ) -> MatchResultSchema:
        """Compute comprehensive match score and explanation between a Candidate Resume and Job Description."""
        if resume_vector is None:
            resume_vector = await self.embedding_service.embed_resume(parsed_resume)
        if job_vector is None:
            job_vector = await self.embedding_service.embed_job(parsed_job)

        return self.matching_engine.match_resume_to_job(
            resume=parsed_resume,
            job=parsed_job,
            resume_vector=resume_vector,
            job_vector=job_vector,
        )

    async def recommend_jobs_for_candidate(
        self,
        candidate_id: uuid.UUID,
        parsed_resume: ParsedResumeSchema | None = None,
        candidate_vector: list[float] | None = None,
        jobs_data: list[tuple[uuid.UUID, ParsedJobSchema, list[float] | None]]
        | None = None,
        limit: int = 10,
        session: AsyncSession | None = None,
        actor_user: User | None = None,
    ) -> list[JobMatchRecommendation]:
        """Recommend Top-K jobs for a Candidate ranked by Match Score."""
        effective_limit = max(1, min(100, limit))

        if candidate_vector is None:
            if parsed_resume is not None:
                candidate_vector = await self.embedding_service.embed_resume(
                    parsed_resume
                )
            else:
                retrieved = await self.vector_repository.retrieve_vector(
                    collection_name="resumes",
                    point_id=candidate_id,
                )
                if retrieved is None:
                    # Lazy self-healing: attempt to rebuild the resume vector from SQL
                    if session is not None:
                        resume_repo = ResumeRepository(session, Resume)
                        primary_resume = await resume_repo.get_primary_by_candidate(candidate_id)
                        if primary_resume is not None and primary_resume.parsed_data:
                            try:
                                parsed_resume = ParsedResumeSchema(**primary_resume.parsed_data)
                                candidate_vector = await self.embedding_service.embed_resume(
                                    parsed_resume
                                )
                                # Self-heal: upsert the vector to Qdrant (pass vector to avoid double embedding)
                                await self._reindex_resume(
                                    candidate_id,
                                    parsed_resume,
                                    vector=candidate_vector,
                                    resume_id=primary_resume.id,
                                    confirmed_at=primary_resume.confirmed_at,
                                )
                            except Exception:
                                # If parsing fails, fall through to error
                                pass

                    if candidate_vector is None:
                        raise EntityNotFoundException(
                            "CV của bạn chưa được số hoá thành công. Vui lòng tải lại CV."
                        )
                else:
                    candidate_vector = retrieved["vector"]
                # Hydrate full resume from SQL (includes education, projects, experiences)
                # instead of building minimal schema from Qdrant payload
                if session is not None and actor_user is not None:
                    resolver = self._get_resolver(session)
                    resumes_dict = await resolver.resolve_resumes(
                        [candidate_id], actor_user
                    )
                    if candidate_id in resumes_dict:
                        parsed_resume = resumes_dict[candidate_id]
                    else:
                        # Fallback to minimal schema if hydration fails
                        skills = retrieved.get("payload", {}).get("skills", [])
                        parsed_resume = ParsedResumeSchema(skills=skills)
                else:
                    skills = retrieved.get("payload", {}).get("skills", [])
                    parsed_resume = parsed_resume or ParsedResumeSchema(
                        skills=skills
                    )

        recommendations: list[JobMatchRecommendation] = []

        if jobs_data is not None:
            for job_id, parsed_job, j_vec in jobs_data:
                if j_vec is None:
                    j_vec = await self.embedding_service.embed_job(parsed_job)
                match_result = self.matching_engine.match_resume_to_job(
                    resume=parsed_resume,
                    job=parsed_job,
                    resume_vector=candidate_vector,
                    job_vector=j_vec,
                )
                recommendations.append(
                    JobMatchRecommendation(
                        job_id=job_id,
                        parsed_job=parsed_job,
                        match_result=match_result,
                    )
                )
            recommendations.sort(
                key=lambda rec: rec.match_result.overall_score, reverse=True
            )
            return recommendations[:effective_limit]

        # Qdrant Vector Repository Search with enlarged retrieval pool for reranking
        search_limit = max(50, effective_limit * 2)
        # Candidate recommendations: only published jobs
        filters = {"status": JobStatus.PUBLISHED.value}
        qdrant_results = await self.vector_repository.search_similar(
            collection_name="jobs",
            query_vector=candidate_vector,
            limit=search_limit,
            filters=filters,
        )

        job_ids = [
            uuid.UUID(str(res.get("id") or res.get("payload", {}).get("job_id")))
            for res in qdrant_results
            if res.get("id") or res.get("payload", {}).get("job_id")
        ]

        # Hydrate jobs from SQL with authorization (Phase B)
        full_jobs: dict[uuid.UUID, ParsedJobSchema] = {}
        if session is not None and actor_user is not None and job_ids:
            resolver = self._get_resolver(session)
            full_jobs = await resolver.resolve_jobs(job_ids, actor_user)
        elif session is not None and job_ids:
            # Backward compatibility: use legacy resolution without authorization
            full_jobs = await self._resolve_jobs_legacy(session, job_ids)

        for res in qdrant_results:
            j_id_raw = res.get("id") or res.get("payload", {}).get("job_id")
            if not j_id_raw:
                continue
            j_id = uuid.UUID(str(j_id_raw))
            if j_id not in full_jobs:
                continue
            fallback_parsed_job = full_jobs[j_id]
            match_result = self.matching_engine.match_resume_to_job(
                resume=parsed_resume,
                job=fallback_parsed_job,
                resume_vector=candidate_vector,
                job_vector=res.get("vector"),
            )
            recommendations.append(
                JobMatchRecommendation(
                    job_id=j_id,
                    parsed_job=fallback_parsed_job,
                    match_result=match_result,
                )
            )

        recommendations.sort(
            key=lambda rec: rec.match_result.overall_score, reverse=True
        )
        return recommendations[:effective_limit]


    async def _resolve_primary_resumes_legacy(
        self,
        session: AsyncSession | None,
        candidate_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, ParsedResumeSchema]:
        if session is None or not candidate_ids:
            return {}
        from app.models import Resume
        stmt = select(Resume).where(
            Resume.candidate_id.in_(candidate_ids),
            Resume.is_primary == True,  # noqa: E712
            Resume.is_confirmed == True,  # noqa: E712
            Resume.is_deleted == False,  # noqa: E712
        )
        result = await session.execute(stmt)
        resumes = {}
        for r in result.scalars().all():
            if r.parsed_data:
                try:
                    resumes[r.candidate_id] = ParsedResumeSchema(**r.parsed_data)
                except Exception:
                    pass
        return resumes

    async def _resolve_jobs_legacy(
        self,
        session: AsyncSession | None,
        job_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, ParsedJobSchema]:
        if session is None or not job_ids:
            return {}
        from app.models import Job
        stmt = select(Job).options(selectinload(Job.skills)).where(
            Job.id.in_(job_ids),
            Job.is_deleted == False
        )
        result = await session.execute(stmt)
        jobs = {}
        for j in result.scalars().all():
            skills = [skill.name for skill in j.skills] if j.skills else []
            try:
                jobs[j.id] = ParsedJobSchema(
                    title=j.title,
                    summary=j.description,
                    required_skills=skills,
                    location=j.location,
                    city=j.location,
                    employment_type=j.job_type.value if j.job_type else None,
                    workplace_type=j.workplace_type.value if j.workplace_type else None,
                )
            except Exception:
                pass
        return jobs

    async def _resolve_candidate_profiles_legacy(
        self,
        session: AsyncSession | None,
        candidate_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, CandidateProfile]:
        """Resolve candidate profiles with ONE batched SQL query.

        Returns a mapping candidate_id -> CandidateProfile for the given ids.
        Soft-deleted candidates are excluded. Returns an empty mapping when
        no session or ids are provided.
        """
        if session is None or not candidate_ids:
            return {}

        stmt = select(CandidateProfile).where(
            CandidateProfile.id.in_(candidate_ids),
            CandidateProfile.is_deleted == False,  # noqa: E712
        )
        result = await session.execute(stmt)
        return {profile.id: profile for profile in result.scalars().all()}

    async def recommend_candidates_for_job(
        self,
        job_id: uuid.UUID,
        parsed_job: ParsedJobSchema | None = None,
        job_vector: list[float] | None = None,
        candidates_data: list[
            tuple[uuid.UUID, ParsedResumeSchema, list[float] | None]
        ]
        | None = None,
        limit: int = 10,
        session: AsyncSession | None = None,
        actor_user: User | None = None,
    ) -> list[CandidateMatchRecommendation]:
        """Recommend Top-K candidates for a Recruiter Job ranked by Match Score."""
        effective_limit = max(1, min(100, limit))

        if job_vector is None:
            if parsed_job is not None:
                job_vector = await self.embedding_service.embed_job(parsed_job)
            else:
                retrieved = await self.vector_repository.retrieve_vector(
                    collection_name="jobs",
                    point_id=job_id,
                )
                if retrieved is None:
                    raise EntityNotFoundException(
                        f"Job vector for Job {job_id} "
                        "not found in vector repository"
                    )
                job_vector = retrieved["vector"]
                payload = retrieved.get("payload", {}) or {}
                parsed_job = parsed_job or ParsedJobSchema(
                    required_skills=payload.get("skills", [])
                )

        recommendations: list[CandidateMatchRecommendation] = []

        if candidates_data is not None:
            for cand_id, parsed_resume, c_vec in candidates_data:
                if c_vec is None:
                    c_vec = await self.embedding_service.embed_resume(parsed_resume)
                match_result = self.matching_engine.match_resume_to_job(
                    resume=parsed_resume,
                    job=parsed_job,
                    resume_vector=c_vec,
                    job_vector=job_vector,
                )
                recommendations.append(
                    CandidateMatchRecommendation(
                        candidate_id=cand_id,
                        parsed_resume=parsed_resume,
                        match_result=match_result,
                    )
                )
            recommendations.sort(
                key=lambda rec: rec.match_result.overall_score, reverse=True
            )
            return recommendations[:effective_limit]

        # Qdrant Vector Repository Search with enlarged retrieval pool for reranking
        search_limit = max(50, effective_limit * 2)
        qdrant_results = await self.vector_repository.search_similar(
            collection_name="resumes",
            query_vector=job_vector,
            limit=search_limit,
        )

        candidate_ids = [
            uuid.UUID(
                str(
                    res.get("id")
                    or res.get("payload", {}).get("candidate_id")
                )
            )
            for res in qdrant_results
            if res.get("id") or res.get("payload", {}).get("candidate_id")
        ]

        # Hydrate candidate profiles and resumes from SQL with authorization (Phase B)
        full_resumes: dict[uuid.UUID, ParsedResumeSchema] = {}
        profiles: dict[uuid.UUID, CandidateProfile] = {}
        if session is not None and actor_user is not None and candidate_ids:
            resolver = self._get_resolver(session)
            profiles = await resolver.resolve_candidate_profiles(candidate_ids, actor_user, require_application=False)
            full_resumes = await resolver.resolve_resumes(candidate_ids, actor_user, require_application=False)
        elif session is not None and candidate_ids:
            # Backward compatibility: use legacy resolution without authorization
            profiles = await self._resolve_candidate_profiles_legacy(session, candidate_ids)
            full_resumes = await self._resolve_primary_resumes_legacy(session, candidate_ids)

        for res in qdrant_results:
            c_id_raw = res.get("id") or res.get("payload", {}).get(
                "candidate_id"
            )
            if not c_id_raw:
                continue
            c_id = uuid.UUID(str(c_id_raw))
            if c_id not in full_resumes:
                continue
            fallback_parsed_resume = full_resumes[c_id]
            match_result = self.matching_engine.match_resume_to_job(
                resume=fallback_parsed_resume,
                job=parsed_job,
                resume_vector=res.get("vector"),
                job_vector=job_vector,
            )
            recommendations.append(
                CandidateMatchRecommendation(
                    candidate_id=c_id,
                    parsed_resume=fallback_parsed_resume,
                    match_result=match_result,
                )
            )

        recommendations.sort(
            key=lambda rec: rec.match_result.overall_score, reverse=True
        )
        return recommendations[:effective_limit]
