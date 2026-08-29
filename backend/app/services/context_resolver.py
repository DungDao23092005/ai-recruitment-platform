from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import EntityNotFoundException
from app.domain.enums import JobStatus
from app.models import CandidateProfile, Company, Job, KnowledgeDocument, RecruiterProfile, Resume, User
from app.repositories import ResumeRepository
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_resume import ParsedResumeSchema
from app.schemas.ai_knowledge import KnowledgeDocumentRead


class ContextResolver:
    """
    Shared SQL hydration layer for RAG and Matching services.

    Handles authorized SQL resolution of Qdrant-retrieved IDs.
    All authorization logic is centralized here to ensure the LLM
    never makes authorization decisions.

    Phase B: Authorized SQL hydration layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.resume_repo = ResumeRepository(session, Resume)

    async def resolve_resumes(
        self,
        candidate_ids: list[uuid.UUID],
        actor_user: User,
        include_primary_only: bool = True,
    ) -> dict[uuid.UUID, ParsedResumeSchema]:
        """
        Resolve parsed resumes by candidate IDs with authorization.

        Authorization rules:
        - CANDIDATE: Can only access their own resume
        - RECRUITER: Can access candidates who applied to their company's jobs
        - ADMIN: Can access all resumes

        Args:
            candidate_ids: List of candidate IDs to resolve
            actor_user: The user making the request (for authorization)
            include_primary_only: Only return primary resumes (default True)

        Returns:
            Mapping of candidate_id -> ParsedResumeSchema for authorized records only
        """
        if not candidate_ids or self.session is None:
            return {}

        # Build authorization filters based on actor role
        if actor_user.role.name == "ADMIN":
            # Admin can access all
            filters = [Resume.candidate_id.in_(candidate_ids)]
        elif actor_user.role.name == "RECRUITER":
            # Recruiter can only access candidates who applied to their company's jobs
            recruiter_company_id = await self._get_recruiter_company_id(actor_user.id)
            if recruiter_company_id is None:
                return {}

            # Get candidate IDs who applied to this recruiter's company jobs
            from app.models import Application, Job
            stmt = select(Application.candidate_id).join(
                Job, Application.job_id == Job.id
            ).where(
                Job.company_id == recruiter_company_id,
                Application.candidate_id.in_(candidate_ids),
                Application.is_deleted == False,
            )
            result = await self.session.execute(stmt)
            authorized_candidate_ids = [row[0] for row in result.all()]

            if not authorized_candidate_ids:
                return {}

            filters = [Resume.candidate_id.in_(authorized_candidate_ids)]
        else:
            # CANDIDATE - can only access their own resume
            candidate_profile = await self._get_candidate_profile(actor_user.id)
            if candidate_profile is None or candidate_profile.id not in candidate_ids:
                return {}
            filters = [Resume.candidate_id == actor_user.id]

        if include_primary_only:
            filters.append(Resume.is_primary == True)  # noqa: E712

        filters.append(Resume.is_deleted == False)  # noqa: E712

        stmt = select(Resume).where(*filters)
        result = await self.session.execute(stmt)

        resumes: dict[uuid.UUID, ParsedResumeSchema] = {}
        for r in result.scalars().all():
            if r.parsed_data:
                try:
                    resumes[r.candidate_id] = ParsedResumeSchema(**r.parsed_data)
                except Exception:
                    pass

        return resumes

    async def resolve_jobs(
        self,
        job_ids: list[uuid.UUID],
        actor_user: User,
        include_unpublished_for_admin: bool = True,
    ) -> dict[uuid.UUID, ParsedJobSchema]:
        """
        Resolve parsed jobs by job IDs with authorization.

        Authorization rules:
        - CANDIDATE: Can only access PUBLISHED jobs
        - RECRUITER: Can only access jobs from their own company
        - ADMIN: Can access all jobs (published and unpublished if flag is True)

        Args:
            job_ids: List of job IDs to resolve
            actor_user: The user making the request (for authorization)
            include_unpublished_for_admin: Whether admin can see unpublished jobs

        Returns:
            Mapping of job_id -> ParsedJobSchema for authorized records only
        """
        if not job_ids or self.session is None:
            return {}

        from app.models import Job
        filters = [Job.id.in_(job_ids), Job.is_deleted == False]  # noqa: E712

        if actor_user.role.name == "ADMIN":
            if not include_unpublished_for_admin:
                filters.append(Job.status == JobStatus.PUBLISHED)
        elif actor_user.role.name == "RECRUITER":
            # Recruiter can only access jobs from their own company
            recruiter_company_id = await self._get_recruiter_company_id(actor_user.id)
            if recruiter_company_id is None:
                return {}
            filters.append(Job.company_id == recruiter_company_id)
        else:
            # CANDIDATE - only published jobs
            filters.append(Job.status == JobStatus.PUBLISHED)

        stmt = select(Job).options(selectinload(Job.skills)).where(*filters)
        result = await self.session.execute(stmt)

        jobs: dict[uuid.UUID, ParsedJobSchema] = {}
        for j in result.scalars().all():
            skills = [skill.name for skill in j.skills] if j.skills else []
            try:
                jobs[j.id] = ParsedJobSchema(
                    title=j.title,
                    summary=j.description,
                    required_skills=skills,
                    location=j.location,
                    city=j.location,  # Using location as city since Job model only has location
                    employment_type=j.job_type.value if j.job_type else None,
                    workplace_type=j.workplace_type.value if j.workplace_type else None,
                )
            except Exception:
                pass

        return jobs

    async def resolve_candidate_profiles(
        self,
        candidate_ids: list[uuid.UUID],
        actor_user: User,
    ) -> dict[uuid.UUID, CandidateProfile]:
        """
        Resolve candidate profiles by IDs with authorization.

        Authorization rules:
        - CANDIDATE: Can only access their own profile
        - RECRUITER: Can access profiles of candidates who applied to their company's jobs
        - ADMIN: Can access all profiles

        Args:
            candidate_ids: List of candidate IDs to resolve
            actor_user: The user making the request (for authorization)

        Returns:
            Mapping of candidate_id -> CandidateProfile for authorized records only
        """
        if not candidate_ids or self.session is None:
            return {}

        if actor_user.role.name == "ADMIN":
            filters = [CandidateProfile.id.in_(candidate_ids)]
        elif actor_user.role.name == "RECRUITER":
            recruiter_company_id = await self._get_recruiter_company_id(actor_user.id)
            if recruiter_company_id is None:
                return {}

            from app.models import Application, Job
            stmt = select(Application.candidate_id).join(
                Job, Application.job_id == Job.id
            ).where(
                Job.company_id == recruiter_company_id,
                Application.candidate_id.in_(candidate_ids),
                Application.is_deleted == False,
            )
            result = await self.session.execute(stmt)
            authorized_candidate_ids = [row[0] for row in result.all()]

            if not authorized_candidate_ids:
                return {}

            filters = [CandidateProfile.id.in_(authorized_candidate_ids)]
        else:
            # CANDIDATE - can only access their own profile
            candidate_profile = await self._get_candidate_profile(actor_user.id)
            if candidate_profile is None or candidate_profile.id not in candidate_ids:
                return {}
            filters = [CandidateProfile.id == actor_user.id]

        filters.append(CandidateProfile.is_deleted == False)  # noqa: E712

        stmt = select(CandidateProfile).where(*filters)
        result = await self.session.execute(stmt)

        return {profile.id: profile for profile in result.scalars().all()}

    async def resolve_knowledge(
        self,
        document_ids: list[uuid.UUID],
        actor_user: User,
    ) -> dict[uuid.UUID, KnowledgeDocumentRead]:
        """
        Resolve knowledge documents by IDs with authorization.

        Authorization rules:
        - CANDIDATE: Can only access PUBLIC + PUBLISHED documents
        - RECRUITER: Can access PUBLIC + PUBLISHED and RECRUITER_ONLY + PUBLISHED
        - ADMIN: Can access all published documents according to architecture

        Args:
            document_ids: List of knowledge document IDs to resolve
            actor_user: The user making the request (for authorization)

        Returns:
            Mapping of document_id -> KnowledgeDocumentRead for authorized records only
        """
        if not document_ids or self.session is None:
            return {}

        # Build authorization filters based on actor role
        filters = [
            KnowledgeDocument.id.in_(document_ids),
            KnowledgeDocument.is_deleted == False,  # noqa: E712
            KnowledgeDocument.status == "published",
        ]

        if actor_user.role.name == "CANDIDATE":
            # Candidate: only PUBLIC + PUBLISHED
            filters.append(KnowledgeDocument.visibility == "public")
        elif actor_user.role.name == "RECRUITER":
            # Recruiter: PUBLIC + PUBLISHED and RECRUITER_ONLY + PUBLISHED
            from sqlalchemy import or_
            filters.append(
                or_(
                    KnowledgeDocument.visibility == "public",
                    KnowledgeDocument.visibility == "recruiter_only",
                )
            )
        # ADMIN: no additional visibility filter (can see all published)

        stmt = select(KnowledgeDocument).where(*filters)
        result = await self.session.execute(stmt)

        documents: dict[uuid.UUID, KnowledgeDocumentRead] = {}
        for doc in result.scalars().all():
            try:
                documents[doc.id] = KnowledgeDocumentRead.model_validate(doc)
            except Exception:
                pass

        return documents

    async def _get_recruiter_company_id(self, user_id: uuid.UUID) -> uuid.UUID | None:
        """Get the company ID for a recruiter user."""
        stmt = select(RecruiterProfile.company_id).where(
            RecruiterProfile.user_id == user_id,
            RecruiterProfile.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_candidate_profile(self, user_id: uuid.UUID) -> CandidateProfile | None:
        """Get candidate profile for a user."""
        stmt = select(CandidateProfile).where(
            CandidateProfile.user_id == user_id,
            CandidateProfile.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ContextBuilder:
    """
    High-level context builder that orchestrates Qdrant retrieval
    and SQL hydration for RAG and Matching services.

    Phase B: Authorized SQL hydration layer.
    """

    def __init__(
        self,
        session: AsyncSession,
        embedding_service: Any,
        vector_repository: Any,
    ) -> None:
        self.session = session
        self.resolver = ContextResolver(session)
        self.embedding_service = embedding_service
        self.vector_repository = vector_repository

    async def build_rag_context(
        self,
        message: str,
        user_role: Any,
        actor_user: Any,
    ) -> tuple[list, list, list]:
        """
        Build RAG context from vector retrieval + SQL hydration.

        Returns:
            tuple of (jobs, candidates, sources) where sources are ChatSource objects
        """
        from app.ai.embeddings.embedding_service import EmbeddingService
        from app.schemas.ai_chat import ChatSource
        from app.schemas.ai_resume import ParsedResumeSchema
        from app.schemas.ai_job import ParsedJobSchema

        query_vector = await self.embedding_service.embed_text(message)

        # 1. Retrieve jobs from Qdrant (always available)
        retrieved_jobs_raw = await self._retrieve_sources(
            collection_name="jobs",
            id_field="job_id",
            query_vector=query_vector,
        )

        # 2. Retrieve resumes for recruiters/admins with relevant queries
        retrieved_resumes_raw: list = []
        # We'll import UserRole here to avoid circular imports
        from app.domain.enums import UserRole

        if user_role in ("RECRUITER", "ADMIN") and self._is_candidate_search_query(message):
            retrieved_resumes_raw = await self._retrieve_resume_sources(query_vector)

        # 3. Hydrate from SQL with authorization
        job_ids = [source.entity_id for source in retrieved_jobs_raw if source.entity_id]
        resume_candidate_ids = [source.entity_id for source in await self._retrieve_resume_sources_for_ids(message) if source.entity_id]

        jobs_dict = await self.resolve_jobs(job_ids, user_role) if job_ids else {}
        resumes_dict = await self.resolve_resumes(resume_candidate_ids, user_role) if resume_candidate_ids else {}

        # Convert to structured schemas
        jobs = [ParsedJobSchema(title=source.title, skills=source.skills) for source in retrieved_jobs_raw]
        candidates = list(resumes_dict.values())

        # Build sources for citations
        sources = []
        for source in retrieved_jobs_raw:
            sources.append(source)

        # Convert resumes to ChatSource for citations
        for candidate_id, resume in resumes_dict.items():
            source = ChatSource(
                source_type="resume",
                entity_id=candidate_id,
                title=resume.title or f"Candidate {str(candidate_id)[:8]}",
                relevance_score=0.0,  # Would need to be retrieved from vector store
                skills=resume.skills or [],
            )
            sources.append(source)

        return list(jobs_dict.values()), list(resumes_dict.values()), sources

    def _is_candidate_search_query(self, message: str) -> bool:
        """Check if message is a candidate search query."""
        keywords = ("candidate", "candidates", "ứng viên", "hồ sơ", "cv", "resume", "resumes")
        lowered = message.lower()
        return any(keyword in lowered for keyword in keywords)

    async def _retrieve_sources(
        self,
        collection_name: str,
        id_field: str,
        query_vector: list[float],
    ) -> list:
        """Retrieve sources from vector repository."""
        from app.core.exceptions import AIError

        try:
            raw_results = await self.vector_repository.search_similar(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=3,
            )
        except Exception as exc:
            raise Exception(
                f"Failed to search similar vectors in collection '{collection_name}'"
            ) from exc

        from app.schemas.ai_chat import ChatSource
        sources = []
        for res in raw_results:
            source = self._map_source(
                res=res,
                id_field=id_field,
                source_type="job" if collection_name == "jobs" else "resume",
            )
            if source is not None:
                sources.append(source)
        return sources

    async def _retrieve_resume_sources(
        self,
        query_vector: list[float],
    ) -> list:
        """Retrieve resume sources from vector repository."""
        from app.core.exceptions import AIError

        try:
            raw_results = await self.vector_repository.search_similar(
                collection_name="resumes",
                query_vector=query_vector,
                limit=3,
            )
        except Exception as exc:
            raise Exception(
                f"Failed to search similar vectors in collection 'resumes'"
            ) from exc

        from app.schemas.ai_resume import ParsedResumeSchema
        resumes = []
        for res in raw_results:
            payload = res.get("payload") or {}
            raw_id = res.get("id") or payload.get("candidate_id")
            if raw_id is None:
                continue
            try:
                entity_id = uuid.UUID(str(raw_id))
            except (ValueError, TypeError):
                continue

            raw_score = res.get("score")
            if raw_score is None:
                continue
            try:
                score = float(raw_score)
            except (TypeError, ValueError):
                continue

            skills = list(payload.get("skills") or [])
            title = payload.get("title") or f"Candidate {str(entity_id)[:8]}"

            resume = ParsedResumeSchema(
                title=title,
                skills=skills,
            )
            resumes.append(resume)
        return resumes

    async def _retrieve_resume_sources_for_ids(self, message: str) -> list:
        """Retrieve resume sources from vector repository for authorization."""
        from app.core.exceptions import AIError

        try:
            raw_results = await self.vector_repository.search_similar(
                collection_name="resumes",
                query_vector=await self.embedding_service.embed_text(message),
                limit=3,
            )
        except Exception as exc:
            raise Exception(
                f"Failed to search similar vectors in collection 'resumes'"
            ) from exc

        sources = []
        for res in raw_results:
            payload = res.get("payload") or {}
            raw_id = res.get("id") or payload.get("candidate_id")
            if raw_id is None:
                continue
            try:
                entity_id = uuid.UUID(str(raw_id))
            except (ValueError, TypeError):
                continue

            raw_score = res.get("score")
            if raw_score is None:
                continue
            try:
                score = float(raw_score)
            except (TypeError, ValueError):
                continue

            from app.schemas.ai_chat import ChatSource
            source = ChatSource(
                source_type="resume",
                entity_id=entity_id,
                title=f"Candidate {str(entity_id)[:8]}",
                relevance_score=score,
                skills=list(payload.get("skills") or []),
            )
            sources.append(source)
        return sources

    @staticmethod
    def _map_source(
        res: dict[str, Any],
        id_field: str,
        source_type: str,
    ):
        payload = res.get("payload") or {}
        raw_id = res.get("id") or payload.get(id_field)
        if raw_id is None:
            return None
        try:
            entity_id = uuid.UUID(str(raw_id))
        except (ValueError, TypeError):
            return None

        raw_score = res.get("score")
        if raw_score is None:
            return None
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            return None

        from app.schemas.ai_chat import ChatSource
        return ChatSource(
            source_type=source_type,
            entity_id=entity_id,
            title=f"{source_type.capitalize()} {str(entity_id)[:8]}",
            relevance_score=score,
            skills=list(payload.get("skills") or []),
        )