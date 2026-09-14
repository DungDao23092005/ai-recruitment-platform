from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.enums import UserRole
from app.models import CandidateProfile, Company, Job, RecruiterProfile, Resume, User
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.context_resolver import ContextResolver
from sqlalchemy import select


class MockScalars:
    """Mock for result.scalars().all()"""
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


def make_mock_result(items):
    """Create a mock result for sync pattern: result.all() and result.scalars().all()"""
    class MockResult:
        def __init__(self, items):
            self._items = items

        def all(self):
            return self._items

        def scalars(self):
            class MockScalars:
                def __init__(self, items):
                    self._items = items
                def all(self):
                    return self._items
            return type('MockScalars', (), {'_items': self._items, 'all': lambda self: self._items})()

    return MockResult(items)


def make_user(role: UserRole, user_id: uuid.UUID | None = None):
    """Create a mock User object with the specified role."""
    user = MagicMock(spec=User)
    user.role = role
    user.id = user_id or uuid.uuid4()
    return user


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
    job.city = location
    job.job_type = job_type or JobType.FULL_TIME
    job.workplace_type = workplace_type or WorkplaceType.ON_SITE
    job.skills = skills or []
    job.required_skills = skills or []
    job.preferred_skills = []
    job.minimum_years_experience = None
    job.education_level = None
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


def make_mock_session():
    """Create a mock async session with a working execute method."""
    session = MagicMock()

    async def mock_execute(stmt):
        return make_mock_result([])

    session.execute = AsyncMock(side_effect=lambda *args, **kwargs: mock_execute_result([]))
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


async def mock_execute_result(items):
    """Async function that returns a mock result."""
    return make_mock_result(items)


def make_mock_result(items):
    """Create a mock result for sync pattern: result.all() and result.scalars().all()"""
    class MockResult:
        def __init__(self, items):
            self._items = items

        def all(self):
            return self._items

        def scalars(self):
            class MockScalars:
                def __init__(self, items):
                    self._items = items
                def all(self):
                    return self._items
            return type('MockScalars', (), {'_items': self._items, 'all': lambda self: self._items})()

    return MockResult(items)


def make_user(role: UserRole, user_id: uuid.UUID | None = None):
    """Create a mock User object with the specified role."""
    user = MagicMock(spec=User)
    user.role = role
    user.id = user_id or uuid.uuid4()
    return user


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
    job.city = location
    job.job_type = job_type or JobType.FULL_TIME
    job.workplace_type = workplace_type or WorkplaceType.ON_SITE
    job.skills = skills or []
    job.required_skills = skills or []
    job.preferred_skills = []
    job.minimum_years_experience = None
    job.education_level = None
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



class TestContextResolverResolveResumes:
    @pytest.mark.asyncio
    async def test_resolves_valid_resume_ids_for_admin(self):
        session = make_mock_session()
        resolver = ContextResolver(session)

        candidate_id = uuid.uuid4()
        resume = make_resume(candidate_id)

        session.execute.return_value = make_mock_result_async([resume])

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
        session.execute.return_value = make_mock_result_async([resume])

        result = await resolver.resolve_resumes([candidate_id, other_candidate_id], candidate_user)

        assert candidate_id in result
        assert other_candidate_id not in result

    @pytest.mark.asyncio
    async def test_candidate_resume_query_uses_candidate_profile_id_not_user_id(self):
        """Regression test: verify CANDIDATE resume query uses candidate_profile.id (CandidateProfile.id)
        not actor_user.id (User.id). This prevents RAG-01/RAG-02 data isolation bug."""
        session = make_mock_session()
        resolver = ContextResolver(session)

        candidate_id = uuid.uuid4()
        user_id = uuid.uuid4()

        resume = make_resume(candidate_id)

        candidate_user = make_user(UserRole.CANDIDATE, user_id)
        candidate_profile = MagicMock(spec=CandidateProfile)
        candidate_profile.id = candidate_id
        candidate_profile.user_id = user_id
        candidate_profile.is_deleted = False

        resolver._get_candidate_profile = AsyncMock(return_value=candidate_profile)

        session.execute.return_value = make_mock_result_async([resume])

        await resolver.resolve_resumes([candidate_id], candidate_user)

        # Verify the query was executed with candidate_profile.id, NOT user_id
        assert session.execute.call_count == 1
        executed_stmt = session.execute.call_args[0][0]
        # Compile the statement to check the WHERE clause
        compiled = executed_stmt.compile(compile_kwargs={"literal_binds": True})
        sql_str = str(compiled)
        # The filter should use candidate_id (CandidateProfile.id), not user_id (User.id)
        # UUID in SQL is without hyphens
        assert str(candidate_id).replace("-", "") in sql_str
        assert str(user_id).replace("-", "") not in sql_str

    @pytest.mark.asyncio
    async def test_candidate_cannot_access_other_candidate_resume(self):
        session = make_mock_session()
        resolver = ContextResolver(session)

        candidate_id = uuid.uuid4()
        user_id = uuid.uuid4()

        resume = make_resume(candidate_id)

        session.execute.return_value = make_mock_result_async([resume])

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

        session.execute.return_value = make_mock_result_async([profile])

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
        session.execute.return_value = make_mock_result_async([profile])

        result = await resolver.resolve_candidate_profiles([candidate_id, other_candidate_id], candidate_user)

        assert candidate_id in result
        assert other_candidate_id not in result

    @pytest.mark.asyncio
    async def test_candidate_profile_query_uses_candidate_profile_id_not_user_id(self):
        """Regression test: verify CANDIDATE profile query uses candidate_profile.id (CandidateProfile.id)
        not actor_user.id (User.id). This prevents RAG-01/RAG-02 data isolation bug."""
        session = make_mock_session()
        resolver = ContextResolver(session)

        candidate_id = uuid.uuid4()
        user_id = uuid.uuid4()

        profile = make_candidate_profile(candidate_id, user_id)

        candidate_user = make_user(UserRole.CANDIDATE, user_id)
        candidate_profile = MagicMock(spec=CandidateProfile)
        candidate_profile.id = candidate_id
        candidate_profile.user_id = user_id
        candidate_profile.is_deleted = False

        resolver._get_candidate_profile = AsyncMock(return_value=candidate_profile)

        session.execute.return_value = make_mock_result_async([profile])

        await resolver.resolve_candidate_profiles([candidate_id], candidate_user)

        # Verify the query was executed with candidate_profile.id, NOT user_id
        assert session.execute.call_count == 1
        executed_stmt = session.execute.call_args[0][0]
        # Compile the statement to check the WHERE clause
        compiled = executed_stmt.compile(compile_kwargs={"literal_binds": True})
        sql_str = str(compiled)
        # The filter should use candidate_id (CandidateProfile.id), not user_id (User.id)
        # UUID in SQL is without hyphens
        assert str(candidate_id).replace("-", "") in sql_str
        assert str(user_id).replace("-", "") not in sql_str


class TestContextResolverBatching:
    @pytest.mark.asyncio
    async def test_batches_resume_queries(self):
        session = make_mock_session()
        resolver = ContextResolver(session)

        candidate_ids = [uuid.uuid4() for _ in range(5)]
        resumes = [make_resume(cid) for cid in candidate_ids]

        session.execute.return_value = make_mock_result_async(resumes)

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


class TestContextResolverRequireApplication:
    """Regression tests for require_application parameter (AI-REC-01)."""

    @pytest.mark.asyncio
    async def test_recruiter_require_application_false_returns_candidates_without_applications(self):
        """A. Candidate has Resume + Qdrant candidate ID + ZERO Applications.
        Recommendation hydration MUST return candidate data when require_application=False."""
        session = make_mock_session()
        resolver = ContextResolver(session)

        candidate_id = uuid.uuid4()
        recruiter_user_id = uuid.uuid4()
        company_id = uuid.uuid4()

        # Mock recruiter company
        resolver._get_recruiter_company_id = AsyncMock(return_value=company_id)

        # Mock candidate profile (exists but has NO applications)
        profile = make_candidate_profile(candidate_id, uuid.uuid4())

        # Create mock result for profile query
        profile_result = MagicMock()
        profile_scalars = MagicMock()
        profile_scalars.all = MagicMock(return_value=[profile])
        profile_result.scalars = MagicMock(return_value=profile_scalars)

        session.execute.return_value = profile_result

        recruiter_user = make_user(UserRole.RECRUITER, recruiter_user_id)

        # With require_application=False, candidate should be returned even without applications
        result = await resolver.resolve_candidate_profiles(
            [candidate_id], recruiter_user, require_application=False
        )

        assert candidate_id in result
        assert result[candidate_id].full_name == "Test Candidate"

    @pytest.mark.asyncio
    async def test_recruiter_require_application_false_returns_resumes_without_applications(self):
        """A. Candidate has Resume + Qdrant candidate ID + ZERO Applications.
        Recommendation hydration MUST return resume data when require_application=False."""
        session = make_mock_session()
        resolver = ContextResolver(session)

        candidate_id = uuid.uuid4()
        recruiter_user_id = uuid.uuid4()
        company_id = uuid.uuid4()

        resolver._get_recruiter_company_id = AsyncMock(return_value=company_id)

        resume = make_resume(candidate_id)

        resume_result = MagicMock()
        resume_scalars = MagicMock()
        resume_scalars.all = MagicMock(return_value=[resume])
        resume_result.scalars = MagicMock(return_value=resume_scalars)

        session.execute.return_value = resume_result

        recruiter_user = make_user(UserRole.RECRUITER, recruiter_user_id)

        # With require_application=False, resume should be returned even without applications
        result = await resolver.resolve_resumes(
            [candidate_id], recruiter_user, require_application=False
        )

        assert candidate_id in result
        assert isinstance(result[candidate_id], ParsedResumeSchema)

    @pytest.mark.asyncio
    async def test_recruiter_require_application_true_excludes_candidates_without_applications(self):
        """C. Existing security filter: require_application=True (default) excludes candidates without applications."""
        session = make_mock_session()
        resolver = ContextResolver(session)

        candidate_id = uuid.uuid4()
        recruiter_user_id = uuid.uuid4()
        company_id = uuid.uuid4()

        resolver._get_recruiter_company_id = AsyncMock(return_value=company_id)

        # Mock Application query to return empty (no applications)
        application_result = MagicMock()
        application_scalars = MagicMock()
        application_scalars.all = MagicMock(return_value=[])
        application_result.scalars = MagicMock(return_value=application_scalars)

        session.execute.return_value = application_result

        recruiter_user = make_user(UserRole.RECRUITER, recruiter_user_id)

        # With require_application=True (default), candidate should be EXCLUDED
        result = await resolver.resolve_candidate_profiles([candidate_id], recruiter_user)

        assert candidate_id not in result
        assert result == {}

    @pytest.mark.asyncio
    async def test_recruiter_require_application_true_includes_candidates_with_applications(self):
        """B. Candidate with Application still works with require_application=True."""
        session = make_mock_session()
        resolver = ContextResolver(session)

        candidate_id = uuid.uuid4()
        recruiter_user_id = uuid.uuid4()
        company_id = uuid.uuid4()

        resolver._get_recruiter_company_id = AsyncMock(return_value=company_id)

        # Mock Application query to return the candidate (has application)
        application_result = MagicMock()
        application_scalars = MagicMock()
        application_scalars.all = MagicMock(return_value=[(candidate_id,)])
        application_result.scalars = MagicMock(return_value=application_scalars)

        # Mock profile query
        profile = make_candidate_profile(candidate_id, uuid.uuid4())
        profile_result = MagicMock()
        profile_scalars = MagicMock()
        profile_scalars.all = MagicMock(return_value=[profile])
        profile_result.scalars = MagicMock(return_value=profile_scalars)

        # Execute will be called twice: once for Application check, once for profile query
        # Use a simple side_effect with a list that yields the two results
        call_count = [0]
        async def mock_execute_side_effect(*args, **kwargs):
            if call_count[0] == 0:
                call_count[0] += 1
                return application_result
            return profile_result

        session.execute.side_effect = mock_execute_side_effect

        recruiter_user = make_user(UserRole.RECRUITER, recruiter_user_id)

        # With require_application=True, candidate with application should be included
        result = await resolver.resolve_candidate_profiles([candidate_id], recruiter_user)

        assert candidate_id in result
        assert result[candidate_id].full_name == "Test Candidate"

    @pytest.mark.asyncio
    async def test_recruiter_require_application_false_resume_query_uses_candidate_ids_directly(self):
        """Verify SQL query uses candidate_ids directly when require_application=False (no Application join)."""
        session = make_mock_session()
        resolver = ContextResolver(session)

        candidate_id = uuid.uuid4()
        recruiter_user_id = uuid.uuid4()
        company_id = uuid.uuid4()

        resolver._get_recruiter_company_id = AsyncMock(return_value=company_id)

        resume = make_resume(candidate_id)

        resume_result = MagicMock()
        resume_scalars = MagicMock()
        resume_scalars.all = MagicMock(return_value=[resume])
        resume_result.scalars = MagicMock(return_value=resume_scalars)

        session.execute.return_value = resume_result

        recruiter_user = make_user(UserRole.RECRUITER, recruiter_user_id)

        await resolver.resolve_resumes([candidate_id], recruiter_user, require_application=False)

        # Verify the query was executed ONCE (no Application join)
        assert session.execute.call_count == 1
        executed_stmt = session.execute.call_args[0][0]
        compiled = executed_stmt.compile(compile_kwargs={"literal_binds": True})
        sql_str = str(compiled)
        # Should filter by candidate_id directly, NOT join Application table
        assert "Application" not in sql_str
        assert str(candidate_id).replace("-", "") in sql_str

    @pytest.mark.asyncio
    async def test_recruiter_require_application_true_resume_query_joins_application(self):
        """Verify SQL query joins Application table when require_application=True."""
        session = make_mock_session()
        resolver = ContextResolver(session)

        candidate_id = uuid.uuid4()
        recruiter_user_id = uuid.uuid4()
        company_id = uuid.uuid4()

        resolver._get_recruiter_company_id = AsyncMock(return_value=company_id)

        # Mock Application query returning the candidate (has application)
        application_result = MagicMock()
        application_scalars = MagicMock()
        application_scalars.all = MagicMock(return_value=[(candidate_id,)])
        application_result.scalars = MagicMock(return_value=application_scalars)

        # Mock resume query
        resume = make_resume(candidate_id)
        resume_result = MagicMock()
        resume_scalars = MagicMock()
        resume_scalars.all = MagicMock(return_value=[resume])
        resume_result.scalars = MagicMock(return_value=resume_scalars)

        call_count = [0]
        async def mock_execute_side_effect(*args, **kwargs):
            if call_count[0] == 0:
                call_count[0] += 1
                return application_result
            return resume_result

        session.execute.side_effect = mock_execute_side_effect

        recruiter_user = make_user(UserRole.RECRUITER, recruiter_user_id)

        await resolver.resolve_resumes([candidate_id], recruiter_user, require_application=True)

        # Verify TWO queries executed: Application check + Resume query
        assert session.execute.call_count == 2
        # First call should be Application join
        first_call_stmt = session.execute.call_args_list[0][0][0]
        first_compiled = first_call_stmt.compile(compile_kwargs={"literal_binds": True})
        first_sql = str(first_compiled)
        assert "applications" in first_sql.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
