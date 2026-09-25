from __future__ import annotations

import uuid

import pytest
import httpx
from sqlalchemy import select

from app.ai.embeddings.embedding_service import EmbeddingService
from app.ai.interfaces.base_provider import BaseVectorRepository
from app.ai.matching.matching_engine import MatchingEngine
from app.ai.parsers.job_parser import JobParser
from app.ai.parsers.resume_parser import ResumeParser
from app.ai.vector_db.qdrant_client import QdrantVectorRepository
from app.api.v1.endpoints.ai import _get_ai_service
from app.core.config import settings
from app.database.session import async_session_factory
from app.domain.enums import CompanySize, JobStatus, JobType, UserRole, WorkplaceType
from app.main import app
from app.models import CandidateProfile, Company, Job, RecruiterProfile, Resume, User
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.ai_matching_service import AIMatchingService

from tests.integration.conftest import run as run_async
from .conftest import (
    FakeEmbeddingProvider,
    FakeLLMProvider,
    QDRANT_AVAILABLE,
    SKIP_REASON_QDRANT,
    VECTOR_DIM,
)

pytestmark = [
    pytest.mark.skipif(
        not QDRANT_AVAILABLE,
        reason=SKIP_REASON_QDRANT,
    ),
]

API_V1 = settings.API_V1_STR


def _get_test_ai_service(vector_repository: BaseVectorRepository) -> AIMatchingService:
    """Test version of AIMatchingService using FakeEmbeddingProvider."""
    return AIMatchingService(
        vector_repository=vector_repository,
        embedding_service=EmbeddingService(FakeEmbeddingProvider()),
    )


@pytest.fixture(autouse=True)
def override_ai_service_dependency(vector_repository):
    """Override the AI service dependency for tests to use FakeEmbeddingProvider."""
    app.dependency_overrides[_get_ai_service] = lambda: _get_test_ai_service(vector_repository)
    yield
    app.dependency_overrides.pop(_get_ai_service, None)


MINIMAL_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n"
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
    b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\n"
    b"endobj\n"
    b"4 0 obj\n<< /Length 100 >>\nstream\n"
    b"BT\n/F1 12 Tf\n72 720 Td\n"
    b"(John Doe - Senior Python Developer) Tj\n"
    b"0 -14 Td\n(Skills: Python, FastAPI) Tj\n"
    b"ET\nendstream\nendobj\n"
    b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    b"trailer\n<< /Size 6 /Root 1 0 R >>\n%%EOF\n"
)

EXPECTED_RESUME = ParsedResumeSchema(
    full_name="John Doe",
    title="Senior Python Developer",
    summary="Experienced Python developer with FastAPI and SQL Server.",
    total_years_experience=5.0,
    skills=["Python", "FastAPI", "SQL Server"],
)

EXPECTED_JOB = ParsedJobSchema(
    title="Senior Python Developer",
    summary="Backend role focused on Python and FastAPI.",
    required_skills=["Python", "FastAPI", "Docker"],
    preferred_skills=["GraphQL"],
    minimum_years_experience=3.0,
)


def _make_service(vector_repository) -> AIMatchingService:
    llm = FakeLLMProvider(
        resume=EXPECTED_RESUME,
        job=EXPECTED_JOB,
    )
    return AIMatchingService(
        resume_parser=ResumeParser(llm_provider=llm),
        job_parser=JobParser(llm_provider=llm),
        embedding_service=EmbeddingService(FakeEmbeddingProvider()),
        vector_repository=vector_repository,
        matching_engine=MatchingEngine(),
    )


async def _create_company(session, company_id: uuid.UUID):
    """Create a Company in SQL."""
    company = Company(
        id=company_id,
        name="Test Company",
        slug=f"test-company-{uuid.uuid4()}",
        tax_code=f"TAX{uuid.uuid4().hex[:10].upper()}",
        size=CompanySize.STARTUP,
    )
    session.add(company)
    await session.commit()
    return company


async def _create_recruiter_profile(session, user_id: uuid.UUID, company_id: uuid.UUID):
    """Create a RecruiterProfile in SQL for the given user."""
    profile = RecruiterProfile(
        user_id=user_id,
        company_id=company_id,
        full_name="Test Recruiter",
        position="Hiring Manager",
    )
    session.add(profile)
    await session.commit()
    return profile


async def _create_job(session, job_id: uuid.UUID, company_id: uuid.UUID, skills: list[str]):
    """Create a Job in SQL with the given skills."""
    job = Job(
        id=job_id,
        company_id=company_id,
        title="Test Job",
        description="Test job description",
        status=JobStatus.PUBLISHED,
        job_type=JobType.FULL_TIME,
        workplace_type=WorkplaceType.REMOTE,
        location="Ho Chi Minh",
        minimum_years_experience=3.0,
        education_level="Bachelor",
    )
    session.add(job)
    await session.flush()

    # Add skills to the job
    for skill_name in skills:
        from app.models import JobSkill, Skill
        from sqlalchemy import select

        stmt = select(Skill).where(Skill.name == skill_name)
        result = await session.execute(stmt)
        skill = result.scalars().first()
        if skill is None:
            skill = Skill(name=skill_name)
            session.add(skill)
            await session.flush()

        job_skill = JobSkill(job_id=job.id, skill_id=skill.id, is_mandatory=True)
        session.add(job_skill)

    await session.commit()
    return job


async def _create_candidate_profile(session, candidate_id: uuid.UUID, user_id: uuid.UUID, skills: list[str]):
    """Create a CandidateProfile and Resume in SQL for the given candidate."""
    profile = CandidateProfile(
        id=candidate_id,
        user_id=user_id,
        full_name="Test Candidate",
        title="Engineer",
    )
    session.add(profile)

    # Create a primary resume with parsed data
    resume = Resume(
        candidate_id=candidate_id,
        is_primary=True,
        title="Test Candidate Resume",
        parsed_data=ParsedResumeSchema(
            skills=skills,
            total_years_experience=3.0,
        ).model_dump(mode="json"),
    )
    session.add(resume)
    await session.commit()
    return profile


async def _seed_job_vectors(vector_repository, job_ids: list[uuid.UUID], skills_list: list[list[str]]) -> None:
    for job_id, skills in zip(job_ids, skills_list):
        vector = FakeEmbeddingProvider._hash_vector(" ".join(skills))
        await vector_repository.upsert_job_vector(
            job_id=job_id, vector=vector, skills=skills, status="published"
        )


async def _seed_candidate_vectors(
    vector_repository, candidate_ids: list[uuid.UUID], skills_list: list[list[str]]
) -> None:
    for candidate_id, skills in zip(candidate_ids, skills_list):
        vector = FakeEmbeddingProvider._hash_vector(" ".join(skills))
        await vector_repository.upsert_resume_vector(
            candidate_id=candidate_id, vector=vector, skills=skills
        )


async def _setup_recommendation_test_data(vector_repository, session, skills_list, actor_role="candidate"):
    """
    Set up complete test data for recommendation tests including SQL entities.
    Returns (job_ids, candidate_id, user_id, company_id).
    """
    job_ids = [uuid.uuid4() for _ in skills_list]
    candidate_id = uuid.uuid4()
    user_id = uuid.uuid4()
    company_id = uuid.uuid4()

    # Create company
    await _create_company(session, company_id)

    # Create user and candidate profile
    user = User(
        id=user_id,
        email=f"candidate-{uuid.uuid4()}@example.com",
        password_hash="hashed",
        role=UserRole.CANDIDATE,
    )
    session.add(user)
    await session.commit()

    await _create_candidate_profile(session, candidate_id, user_id, ["Python", "FastAPI"])

    # Create jobs
    for job_id, skills in zip(job_ids, skills_list):
        await _create_job(session, job_id, company_id, skills)

    # Seed Qdrant vectors with the same job_ids
    await _seed_job_vectors(vector_repository, job_ids, skills_list)
    await vector_repository.upsert_resume_vector(
        candidate_id=candidate_id,
        vector=FakeEmbeddingProvider._hash_vector("Python FastAPI"),
        skills=["Python", "FastAPI"],
    )

    return job_ids, candidate_id, user_id, company_id


async def _setup_candidate_recommendation_test_data(vector_repository, session, skills_list):
    """
    Set up complete test data for candidate recommendation tests.
    Returns (job_id, candidate_ids, user_id, company_id).
    """
    job_id = uuid.uuid4()
    candidate_ids = [uuid.uuid4() for _ in skills_list]
    user_id = uuid.uuid4()
    company_id = uuid.uuid4()

    # Create company
    await _create_company(session, company_id)

    # Create recruiter user and profile
    recruiter_user = User(
        id=uuid.uuid4(),
        email=f"recruiter-{uuid.uuid4()}@example.com",
        password_hash="hashed",
        role=UserRole.RECRUITER,
    )
    session.add(recruiter_user)
    await session.commit()

    await _create_recruiter_profile(session, recruiter_user.id, company_id)

    # Create job
    await _create_job(session, job_id, company_id, ["Python", "FastAPI"])

    # Create candidate users and profiles
    for candidate_id in candidate_ids:
        user = User(
            id=uuid.uuid4(),
            email=f"candidate-{uuid.uuid4()}@example.com",
            password_hash="hashed",
            role=UserRole.CANDIDATE,
        )
        session.add(user)
        await session.commit()
        await _create_candidate_profile(session, candidate_id, user.id, skills_list[candidate_ids.index(candidate_id)])

    # Seed Qdrant vectors with the same candidate_ids
    await vector_repository.upsert_job_vector(
        job_id=job_id,
        vector=FakeEmbeddingProvider._hash_vector("Python FastAPI"),
        skills=["Python", "FastAPI"],
    )
    await _seed_candidate_vectors(vector_repository, candidate_ids, skills_list)

    return job_id, candidate_ids, recruiter_user.id, company_id


class TestResumeIndexFlow:
    def test_full_resume_index_and_retrieve_flow(self, vector_repository, tracked):
        async def _run():
            await vector_repository.init_collections()
            candidate_id = uuid.uuid4()
            tracked("resumes", candidate_id)
            service = _make_service(vector_repository)

            result = await service.process_and_index_resume(
                candidate_id=candidate_id,
                pdf_source=MINIMAL_PDF_BYTES,
            )

            assert result == EXPECTED_RESUME

            retrieved = await vector_repository.retrieve_vector(
                "resumes", candidate_id
            )
            assert retrieved is not None
            assert len(retrieved["vector"]) == VECTOR_DIM
            assert retrieved["payload"]["candidate_id"] == str(candidate_id)
            assert retrieved["payload"]["skills"] == result.skills

        run_async(_run())


class TestJobIndexFlow:
    def test_full_job_index_and_retrieve_flow(self, vector_repository, tracked):
        async def _run():
            await vector_repository.init_collections()
            job_id = uuid.uuid4()
            tracked("jobs", job_id)
            service = _make_service(vector_repository)

            result = await service.process_and_index_job(
                job_id=job_id,
                job_title="Senior Python Developer",
                job_description=(
                    "We are hiring a Senior Python Developer with FastAPI and "
                    "SQL Server experience. 3+ years required."
                ),
            )

            assert result == EXPECTED_JOB

            retrieved = await vector_repository.retrieve_vector("jobs", job_id)
            assert retrieved is not None
            assert len(retrieved["vector"]) == VECTOR_DIM
            assert retrieved["payload"]["job_id"] == str(job_id)
            assert "Python" in retrieved["payload"]["skills"]

        run_async(_run())


class TestRecommendJobsRealQdrant:
    def test_recommend_jobs_for_candidate_with_real_qdrant(self, vector_repository, tracked, session):
        async def _run():
            await vector_repository.init_collections()
            # Clear collections to ensure clean state (previous test data may persist)
            from qdrant_client.models import Filter
            await vector_repository.client.delete(
                collection_name="jobs",
                points_selector=Filter(must=[]),
            )
            await vector_repository.client.delete(
                collection_name="resumes",
                points_selector=Filter(must=[]),
            )
            service = _make_service(vector_repository)

            # Get the actual session object
            db_session = session()
            job_ids, candidate_id, user_id, company_id = await _setup_recommendation_test_data(
                vector_repository, db_session,
                [
                    ["Python", "FastAPI"],
                    ["Java", "Spring"],
                    ["Python", "Docker"],
                ],
            )
            for job_id in job_ids:
                tracked("jobs", job_id)
            tracked("resumes", candidate_id)

            # Load the actual user from database for proper authorization context
            stmt = select(User).where(User.id == user_id)
            result = await db_session.execute(stmt)
            actor_user = result.scalar_one()

            # Real Qdrant retrieval path: let service retrieve candidate vector from Qdrant
            # No jobs_data provided - service will search Qdrant, then hydrate/authorize via SQL
            recommendations = await service.recommend_jobs_for_candidate(
                candidate_id=candidate_id,
                limit=10,
                session=db_session,
                actor_user=actor_user,
            )

            assert recommendations, "recommendations should be returned"
            scores = [rec.match_result.overall_score for rec in recommendations]
            assert scores == sorted(scores, reverse=True), (
                "ranking must be descending"
            )

            # Second call to verify deterministic ranking
            first = await service.recommend_jobs_for_candidate(
                candidate_id=candidate_id,
                limit=10,
                session=db_session,
                actor_user=actor_user,
            )
            assert [r.match_result.overall_score for r in first] == scores

        run_async(_run())


class TestRecommendCandidatesRealQdrant:
    def test_recommend_candidates_for_job_with_real_qdrant(self, vector_repository, tracked, session):
        async def _run():
            await vector_repository.init_collections()
            # Clear collections to ensure clean state (previous test data may persist)
            from qdrant_client.models import Filter
            await vector_repository.client.delete(
                collection_name="jobs",
                points_selector=Filter(must=[]),
            )
            await vector_repository.client.delete(
                collection_name="resumes",
                points_selector=Filter(must=[]),
            )
            service = _make_service(vector_repository)

            # Get the actual session object
            db_session = session()
            job_id, candidate_ids, recruiter_user_id, company_id = await _setup_candidate_recommendation_test_data(
                vector_repository, db_session,
                [
                    ["Python", "FastAPI"],
                    ["Java", "Spring"],
                    ["Python"],
                ],
            )
            tracked("jobs", job_id)
            for candidate_id in candidate_ids:
                tracked("resumes", candidate_id)

            # Load the actual recruiter user from database for proper authorization context
            stmt = select(User).where(User.id == recruiter_user_id)
            result = await db_session.execute(stmt)
            actor_user = result.scalar_one()

            # Real Qdrant retrieval path: let service retrieve job vector from Qdrant
            # No candidates_data provided - service will search Qdrant, then hydrate/authorize via SQL
            recommendations = await service.recommend_candidates_for_job(
                job_id=job_id,
                limit=10,
                session=db_session,
                actor_user=actor_user,
            )

            assert recommendations, "recommendations should be returned"
            scores = [rec.match_result.overall_score for rec in recommendations]
            assert scores == sorted(scores, reverse=True)

        run_async(_run())


class TestRecommendationsApi:
    def test_recommend_jobs_endpoint_with_real_qdrant(self, candidate_client, vector_repository, tracked, session):
        async def _run():
            await vector_repository.init_collections()

            # Get the actual session object
            db_session = session()

            # Create candidate profile via API
            profile = await candidate_client.post(
                f"{API_V1}/users/me/candidate-profile",
                json={"full_name": "Jane Doe", "title": "Engineer"},
            )
            assert profile.status_code == 201, profile.text
            candidate_id = uuid.UUID(profile.json()["id"])
            tracked("resumes", candidate_id)

            # Upsert resume vector for the candidate
            await vector_repository.upsert_resume_vector(
                candidate_id=candidate_id,
                vector=FakeEmbeddingProvider._hash_vector("Python FastAPI"),
                skills=["Python", "FastAPI"],
            )

            # Create jobs directly in SQL with known IDs (published, so candidates can see them)
            job_ids = [uuid.uuid4() for _ in range(2)]
            company_id = uuid.uuid4()
            await _create_company(db_session, company_id)
            for job_id, skills in zip(job_ids, [["Python", "FastAPI"], ["Java", "Spring"]]):
                await _create_job(db_session, job_id, company_id, skills)
                await vector_repository.upsert_job_vector(
                    job_id=job_id, vector=FakeEmbeddingProvider._hash_vector(" ".join(skills)), skills=skills, status="published"
                )
                tracked("jobs", job_id)

            resp = await candidate_client.get(f"{API_V1}/ai/recommendations/jobs")

            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert isinstance(body, list)
            assert len(body) >= 1
            scores = [item["match_result"]["overall_score"] for item in body]
            assert scores == sorted(scores, reverse=True)

        run_async(_run())

    def test_recommend_candidates_endpoint_with_real_qdrant(self, recruiter_client, vector_repository, tracked, session):
        async def _run():
            await vector_repository.init_collections()

            # Get the actual session object
            db_session = session()

            # Create company via API
            company = await recruiter_client.post(
                f"{API_V1}/companies",
                json={
                    "name": "Acme Corp",
                    "slug": f"acme-corp-{uuid.uuid4()}",
                    "tax_code": str(uuid.uuid4())[:15],
                    "size": "startup",
                },
            )
            assert company.status_code == 201, company.text
            company_data = company.json()
            company_id = company_data["id"]

            # Create job via API
            job = await recruiter_client.post(
                f"{API_V1}/jobs",
                json={
                    "title": "Backend Engineer",
                    "description": "Build robust APIs",
                    "job_type": "full_time",
                    "workplace_type": "remote",
                    "location": "Ho Chi Minh",
                    "status": "published",
                    "company_id": company_id,
                },
            )
            assert job.status_code == 201, job.text
            job_data = job.json()
            job_id = uuid.UUID(job_data["id"])
            tracked("jobs", job_id)

            # Upsert job vector with matching ID
            await vector_repository.upsert_job_vector(
                job_id=job_id,
                vector=FakeEmbeddingProvider._hash_vector("Python FastAPI"),
                skills=["Python", "FastAPI"],
                status="published",
            )

            # Create candidates directly in SQL with known IDs and upsert vectors
            candidate_ids = [uuid.uuid4() for _ in range(2)]
            skills_list = [["Python", "FastAPI"], ["Java", "Spring"]]
            for candidate_id, skills in zip(candidate_ids, skills_list):
                # Create candidate user and profile in SQL
                user = User(
                    id=uuid.uuid4(),
                    email=f"candidate-{uuid.uuid4()}@example.com",
                    password_hash="hashed",
                    role=UserRole.CANDIDATE,
                )
                db_session.add(user)
                await db_session.commit()
                await _create_candidate_profile(db_session, candidate_id, user.id, skills)

                await vector_repository.upsert_resume_vector(
                    candidate_id=candidate_id, vector=FakeEmbeddingProvider._hash_vector(" ".join(skills)), skills=skills
                )
                tracked("resumes", candidate_id)

            resp = await recruiter_client.get(
                f"{API_V1}/ai/recommendations/candidates",
                params={"job_id": str(job_id)},
            )

            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert isinstance(body, list)
            assert len(body) >= 1
            scores = [item["match_result"]["overall_score"] for item in body]
            assert scores == sorted(scores, reverse=True)

        run_async(_run())