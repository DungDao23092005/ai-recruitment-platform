from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.enums import UserRole
from app.models import CandidateProfile, Company, Job, RecruiterProfile, Resume, User
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.context_resolver import ContextResolver


def make_user(role: UserRole, user_id: uuid.UUID | None = None):
    """Create a mock User object with the specified role."""
    user = MagicMock(spec=User)
    user.role = role
    user.id = user_id or uuid.uuid4()
    return user


def make_mock_session():
    """Create a mock async session."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


def make_mock_result(items):
    """Create a mock result for sync pattern: result.scalars().all()"""

    class MockScalars:
        def __init__(self, items):
            self.items = items

        def all(self):
            return self.items

    scalars_mock = MockScalars(items)

    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars_mock)
    result.all = AsyncMock(return_value=[])

    return result


def make_mock_result_async(items):
    """Create a mock result for sync pattern: result.scalars().all()"""

    class MockScalars:
        def __init__(self, items):
            self.items = items

        def all(self):
            return self.items

    scalars_mock = MockScalars(items)

    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars_mock)
    result.all = AsyncMock(return_value=[])

    return result


def make_resume(candidate_id: uuid.UUID, parsed_data: dict | None = None, is_primary: bool = True, is_deleted: bool = False):
    """Create a mock Resume object."""
    resume = MagicMock(spec=Resume)
    resume.candidate_id = candidate_id
    resume.parsed_data = parsed_data or {"skills": ["Python"], "full_name": "Test User"}
    resume.is_primary = is_primary
    resume.is_deleted = is_deleted
    return resume


def make_job(job_id: uuid.UUID, company_id: uuid.UUID, skills: list | None = None, is_deleted: bool = False, status: str = "PUBLISHED", location: str = "Hanoi", job_type=None, workplace_type=None):
    """Create a mock Job object."""
    from app.domain.enums import JobType, WorkplaceType
    job = MagicMock(spec=Job)
    job.id = job_id
    job.company_id = company_id
    job.title = "Test Job"
    job.description = "Test job description"
    job.is_deleted = is_deleted
    job.status = status
    job.location = location
    job.city = location  # Using location as city as well
    job.job_type = job_type or JobType.FULL_TIME
    job.workplace_type = workplace_type or WorkplaceType.ON_SITE
    job.skills = skills or []
    return job


def make_candidate_profile(candidate_id: uuid.UUID, user_id: uuid.UUID, is_deleted: bool = False):
    """Create a mock CandidateProfile object."""
    profile = MagicMock(spec=CandidateProfile)
    profile.id = candidate_id
    profile.user_id = user_id
    profile.full_name = "Test Candidate"
    profile.title = "Software Engineer"
    profile.is_deleted = is_deleted
    return profile


class TestContextResolverResolveResumes:
    @pytest.mark.asyncio
    async def test_resolves_valid_resume_ids_for_admin(self):
        session = make_mock_session()
        resolver = ContextResolver(session)

        candidate_id = uuid.uuid4()
        resume = make_resume(candidate_id)

        session.execute.return_value = make_mock_result([resume])

        admin_user = make_user(UserRole.ADMIN)
        result = await resolver.resolve_resumes([candidate_id], admin_user)

        assert candidate_id in result
        assert isinstance(result[candidate_id], ParsedResumeSchema)

    @pytest.mark.asyncio
    async def test_candidate_can_only_access_own_resume(self):
        session = make_mock_session()
        resolver = ContextResolver(session)

        candidate_id = uuid.uuid4()
        other_candidate_id = uuid.uuid4()
        user_id = uuid.uuid4()

        resume = make_resume(candidate_id)
        other_resume = make_resume(other_candidate_id)

        # Mock the _get_candidate_profile to return the candidate's own profile
        candidate_user = make_user(UserRole.CANDIDATE, user_id)
        candidate_profile = MagicMock(spec=CandidateProfile)
        candidate_profile.id = candidate_id
        candidate_profile.user_id = user_id
        candidate_profile.is_deleted = False

        resolver._get_candidate_profile = AsyncMock(return_value=candidate_profile)

        # Mock session.execute to return only the authorized resume
        session.execute.return_value = make_mock_result([resume])

        result = await resolver.resolve_resumes([candidate_id, other_candidate_id], candidate_user)

        assert candidate_id in result
        assert other_candidate_id not in result

    @pytest.mark.asyncio
    async def test_candidate_cannot_access_other_candidate_resume(self):
        session = make_mock_session()
        resolver = ContextResolver(session)

        candidate_id = uuid.uuid4()
        user_id = uuid.uuid4()

        resume = make_resume(candidate_id)

        session.execute.return_value = make_mock_result([resume])

        candidate_user = make_user(UserRole.CANDIDATE, user_id)
        candidate_profile = MagicMock(spec=CandidateProfile)
        candidate_profile.id = uuid.uuid4()  # Different ID
        candidate_profile.user_id = user_id
        candidate_profile.is_deleted = False

        resolver._get_candidate_profile = AsyncMock(return_value=candidate_profile)

        result = await resolver.resolve_resumes([candidate_id], candidate_user)

        assert candidate_id not in result

    @pytest.mark.asyncio
    async def test_empty_candidate_ids_returns_empty(self):
        session = make_mock_session()
        resolver = ContextResolver(session)

        admin_user = make_user(UserRole.ADMIN)
        result = await resolver.resolve_resumes([], admin_user)

        assert result == {}

    @pytest.mark.asyncio
    async def test_none_session_returns_empty(self):
        resolver = ContextResolver(None)  # type: ignore

        admin_user = make_user(UserRole.ADMIN)
        candidate_id = uuid.uuid4()
        result = await resolver.resolve_resumes([candidate_id], admin_user)

        assert result == {}


class TestContextResolverResolveJobs:
    @pytest.mark.asyncio
    async def test_resolves_valid_job_ids_for_admin(self):
        session = make_mock_session()
        resolver = ContextResolver(session)

        job_id = uuid.uuid4()
        company_id = uuid.uuid4()
        job = make_job(job_id, company_id)

        session.execute.return_value = make_mock_result_async([job])

        admin_user = make_user(UserRole.ADMIN)
        result = await resolver.resolve_jobs([job_id], admin_user)

        assert job_id in result
        assert isinstance(result[job_id], ParsedJobSchema)

    @pytest.mark.asyncio
    async def test_candidate_can_only_access_published_jobs(self):
        session = make_mock_session()
        resolver = ContextResolver(session)

        job_id = uuid.uuid4()
        company_id = uuid.uuid4()
        job = make_job(job_id, company_id, status="DRAFT")

        # Mock session to return empty for draft jobs (SQL would filter them)
        session.execute.return_value = make_mock_result_async([])

        candidate_user = make_user(UserRole.CANDIDATE)
        result = await resolver.resolve_jobs([job_id], candidate_user)

        assert job_id not in result

    @pytest.mark.asyncio
    async def test_recruiter_can_only_access_own_company_jobs(self):
        session = make_mock_session()
        resolver = ContextResolver(session)

        job_id = uuid.uuid4()
        company_id = uuid.uuid4()
        other_company_id = uuid.uuid4()
        user_id = uuid.uuid4()

        job = make_job(job_id, company_id)
        other_job = make_job(uuid.uuid4(), other_company_id)

        # Mock session to return only the authorized job
        session.execute.return_value = make_mock_result_async([job])

        recruiter_user = make_user(UserRole.RECRUITER, user_id)
        resolver._get_recruiter_company_id = AsyncMock(return_value=company_id)

        result = await resolver.resolve_jobs([job_id, other_job.id], recruiter_user)

        assert job_id in result
        assert other_job.id not in result

    @pytest.mark.asyncio
    async def test_empty_job_ids_returns_empty(self):
        session = make_mock_session()
        resolver = ContextResolver(session)

        admin_user = make_user(UserRole.ADMIN)
        result = await resolver.resolve_jobs([], admin_user)

        assert result == {}


class TestContextResolverResolveCandidateProfiles:
    @pytest.mark.asyncio
    async def test_resolves_valid_candidate_profiles_for_admin(self):
        session = make_mock_session()
        resolver = ContextResolver(session)

        candidate_id = uuid.uuid4()
        user_id = uuid.uuid4()
        profile = make_candidate_profile(candidate_id, user_id)

        session.execute.return_value = make_mock_result([profile])

        admin_user = make_user(UserRole.ADMIN)
        result = await resolver.resolve_candidate_profiles([candidate_id], admin_user)

        assert candidate_id in result
        assert result[candidate_id].full_name == "Test Candidate"

    @pytest.mark.asyncio
    async def test_candidate_can_only_access_own_profile(self):
        session = make_mock_session()
        resolver = ContextResolver(session)

        candidate_id = uuid.uuid4()
        other_candidate_id = uuid.uuid4()
        user_id = uuid.uuid4()

        profile = make_candidate_profile(candidate_id, user_id)
        other_profile = make_candidate_profile(other_candidate_id, uuid.uuid4())

        # Mock _get_candidate_profile to return the candidate's own profile
        candidate_user = make_user(UserRole.CANDIDATE, user_id)
        candidate_profile = MagicMock(spec=CandidateProfile)
        candidate_profile.id = candidate_id
        candidate_profile.user_id = user_id
        candidate_profile.is_deleted = False

        resolver._get_candidate_profile = AsyncMock(return_value=candidate_profile)

        # Mock session to return only the authorized profile
        session.execute.return_value = make_mock_result([profile])

        result = await resolver.resolve_candidate_profiles([candidate_id, other_candidate_id], candidate_user)

        assert candidate_id in result
        assert other_candidate_id not in result


class TestContextResolverBatching:
    @pytest.mark.asyncio
    async def test_batches_resume_queries(self):
        session = make_mock_session()
        resolver = ContextResolver(session)

        candidate_ids = [uuid.uuid4() for _ in range(5)]
        resumes = [make_resume(cid) for cid in candidate_ids]

        session.execute.return_value = make_mock_result(resumes)

        admin_user = make_user(UserRole.ADMIN)
        result = await resolver.resolve_resumes(candidate_ids, admin_user)

        # Should execute only one query
        assert session.execute.call_count == 1
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_batches_job_queries(self):
        session = make_mock_session()
        resolver = ContextResolver(session)

        job_ids = [uuid.uuid4() for _ in range(5)]
        company_id = uuid.uuid4()
        jobs = [make_job(jid, company_id) for jid in job_ids]

        session.execute.return_value = make_mock_result_async(jobs)

        admin_user = make_user(UserRole.ADMIN)
        result = await resolver.resolve_jobs(job_ids, admin_user)

        # Should execute only one query
        assert session.execute.call_count == 1
        assert len(result) == 5


class TestContextResolverEmptyInputs:
    @pytest.mark.asyncio
    async def test_empty_candidate_ids_returns_empty(self):
        session = make_mock_session()
        resolver = ContextResolver(session)

        admin_user = make_user(UserRole.ADMIN)
        result = await resolver.resolve_resumes([], admin_user)

        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_job_ids_returns_empty(self):
        session = make_mock_session()
        resolver = ContextResolver(session)

        admin_user = make_user(UserRole.ADMIN)
        result = await resolver.resolve_jobs([], admin_user)

        assert result == {}

    @pytest.mark.asyncio
    async def test_none_session_returns_empty(self):
        resolver = ContextResolver(None)  # type: ignore

        admin_user = make_user(UserRole.ADMIN)
        candidate_id = uuid.uuid4()
        result = await resolver.resolve_resumes([candidate_id], admin_user)

        assert result == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])