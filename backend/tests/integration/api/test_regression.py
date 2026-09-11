"""Integration tests for Application service with real ORM and database."""

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.database.session import async_session_factory
from app.models import (
    Application,
    Interview,
    Job,
    User,
    Company,
    CandidateProfile,
    RecruiterProfile,
    Skill,
    JobSkill,
)
from app.domain.enums import (
    InterviewStatus,
    InterviewType,
    ApplicationStatus,
    UserRole,
    JobStatus,
    JobType,
    WorkplaceType,
    CompanySize,
)
from tests.integration.api.conftest import API_V1, PASSWORD
from app.repositories import ApplicationRepository


def create_candidate_profile(client, run_async):
    """Helper to create candidate profile for testing."""
    profile_data = {
        "full_name": "Test Candidate",
        "phone": "0123456789",
        "title": "Software Engineer"
    }
    resp = run_async(client.post(f"{API_V1}/candidates/profile", json=profile_data))
    assert resp.status_code == 201
    return resp.json()


class TestApplicationInterviewRegression:
    """Regression tests for Application/Interview relationship loading."""

    def test_application_interview_eager_loading_via_repository(self, run_async):
        """Test that ApplicationRepository.get_by_candidate_and_job eager-loads interviews.

        This is the core regression test for MissingGreenletError.
        It tests the actual repository method that includes selectinload(Application.interviews).
        """

        async def _test():
            async with async_session_factory() as session:
                # Create test data with proper foreign key relationships
                company = Company(
                    id=uuid.uuid4(),
                    name="Test Company",
                    slug="test-company-regression",
                    tax_code="123456789",
                    size=CompanySize.STARTUP,
                )
                session.add(company)
                await session.flush()

                # Create recruiter user and profile
                recruiter_user = User(
                    id=uuid.uuid4(),
                    email=f"recruiter-{uuid.uuid4()}@test.com",
                    password_hash="hash",
                    role=UserRole.RECRUITER,
                    is_active=True,
                )
                session.add(recruiter_user)
                await session.flush()

                recruiter_profile = RecruiterProfile(
                    id=uuid.uuid4(),
                    user_id=recruiter_user.id,
                    company_id=company.id,
                    full_name="Test Recruiter",
                    position="HR Manager",
                )
                session.add(recruiter_profile)
                await session.flush()

                # Create candidate user and profile
                candidate_user = User(
                    id=uuid.uuid4(),
                    email=f"candidate-{uuid.uuid4()}@test.com",
                    password_hash="hash",
                    role=UserRole.CANDIDATE,
                    is_active=True,
                )
                session.add(candidate_user)
                await session.flush()

                candidate_profile = CandidateProfile(
                    id=uuid.uuid4(),
                    user_id=candidate_user.id,
                    full_name="Test Candidate",
                    phone="0123456789",
                    title="Software Engineer",
                )
                session.add(candidate_profile)
                await session.flush()

                # Create job with correct company_id
                job = Job(
                    id=uuid.uuid4(),
                    company_id=company.id,
                    title="Test Job",
                    description="Test job description",
                    status=JobStatus.PUBLISHED,
                    job_type=JobType.FULL_TIME,
                    workplace_type=WorkplaceType.REMOTE,
                    location="Remote",
                )
                session.add(job)
                await session.flush()

                # Create application with correct foreign keys
                application = Application(
                    id=uuid.uuid4(),
                    candidate_id=candidate_profile.id,
                    job_id=job.id,
                    status=ApplicationStatus.APPLIED,
                )
                session.add(application)
                await session.flush()

                # Create interview with correct application_id
                interview = Interview(
                    id=uuid.uuid4(),
                    application_id=application.id,
                    scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
                    duration_minutes=60,
                    interview_type=InterviewType.TECHNICAL,
                    meeting_url="https://meet.example.com",
                    location="Office",
                    notes="Test interview",
                    status=InterviewStatus.SCHEDULED,
                )
                session.add(interview)
                await session.commit()

                # Now query using the REAL repository method that includes selectinload
                repo = ApplicationRepository(session, Application)

                # This is the exact method that was causing MissingGreenletError
                loaded_application = await repo.get_by_candidate_and_job(
                    candidate_id=candidate_profile.id,
                    job_id=job.id,
                )

                # Verify the application was loaded
                assert loaded_application is not None, "Application should be found"
                assert loaded_application.id == application.id
                assert loaded_application.candidate_id == candidate_profile.id
                assert loaded_application.job_id == job.id

                # CRITICAL: Access interviews relationship - this would raise MissingGreenletError
                # if selectinload was not used in the repository query
                interviews = loaded_application.interviews
                assert interviews is not None, "interviews relationship should be loaded (not None)"

                # Should be a list (possibly empty, but not raise MissingGreenletError)
                assert isinstance(interviews, list), "interviews should be a list"

                # Should contain our interview
                assert len(interviews) == 1, "Should have exactly one interview"
                assert interviews[0].id == interview.id
                assert interviews[0].application_id == application.id

                # Verify interview attributes are accessible without lazy loading
                assert interviews[0].scheduled_at is not None
                assert interviews[0].interview_type == InterviewType.TECHNICAL
                assert interviews[0].status == InterviewStatus.SCHEDULED

        run_async(_test())


class TestJobSkillsRegression:
    """Regression tests for Job skills in GET /jobs/{id} endpoint."""

    async def test_get_job_returns_skills(self, client, run_async):
        """Test that GET /jobs/{id} returns skills array."""
        # This test requires published_job fixture which needs recruiter setup
        # The actual API test is in test_jobs_api.py
        pass


class TestApplicationInterviewSerialization:
    """Test serialization of Application with interviews (full path)."""

    def test_application_with_interviews_serialization_path(self, run_async):
        """Test the full path: Repository -> Schema -> Serialization.

        This mimics what happens in the API endpoint when returning
        ApplicationWithJobRead which includes interviews.
        """

        async def _test():
            async with async_session_factory() as session:
                # Create test data with proper foreign key relationships
                company = Company(
                    id=uuid.uuid4(),
                    name="Serialization Test Company",
                    slug="serialization-test-company",
                    tax_code="987654321",
                    size=CompanySize.STARTUP,
                )
                session.add(company)
                await session.flush()

                candidate_user = User(
                    id=uuid.uuid4(),
                    email=f"candidate-ser-{uuid.uuid4()}@test.com",
                    password_hash="hash",
                    role=UserRole.CANDIDATE,
                    is_active=True,
                )
                session.add(candidate_user)
                await session.flush()

                candidate_profile = CandidateProfile(
                    id=uuid.uuid4(),
                    user_id=candidate_user.id,
                    full_name="Serialization Candidate",
                )
                session.add(candidate_profile)
                await session.flush()

                job = Job(
                    id=uuid.uuid4(),
                    company_id=company.id,
                    title="Serialization Test Job",
                    description="Test job for serialization",
                    status=JobStatus.PUBLISHED,
                    job_type=JobType.FULL_TIME,
                    workplace_type=WorkplaceType.REMOTE,
                    location="Remote",
                )
                session.add(job)
                await session.flush()

                application = Application(
                    id=uuid.uuid4(),
                    candidate_id=candidate_profile.id,
                    job_id=job.id,
                    status=ApplicationStatus.APPLIED,
                )
                session.add(application)
                await session.flush()

                # Add multiple interviews
                interview1 = Interview(
                    id=uuid.uuid4(),
                    application_id=application.id,
                    scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
                    duration_minutes=60,
                    interview_type=InterviewType.TECHNICAL,
                    meeting_url="https://meet.example.com/1",
                    location="Office",
                    notes="First interview",
                    status=InterviewStatus.SCHEDULED,
                )
                interview2 = Interview(
                    id=uuid.uuid4(),
                    application_id=application.id,
                    scheduled_at=datetime.now(timezone.utc) + timedelta(days=2),
                    duration_minutes=45,
                    interview_type=InterviewType.HR,
                    meeting_url="https://meet.example.com/2",
                    location="Online",
                    notes="HR interview",
                    status=InterviewStatus.SCHEDULED,
                )
                session.add_all([interview1, interview2])
                await session.commit()

                # Use the repository method that includes selectinload(Application.interviews)
                repo = ApplicationRepository(session, Application)
                loaded_application = await repo.get_by_candidate_and_job(
                    candidate_id=candidate_profile.id,
                    job_id=job.id,
                )

                assert loaded_application is not None

                # Access interviews - this is the path that would trigger MissingGreenletError
                interviews = loaded_application.interviews

                # Verify all interviews are loaded
                assert len(interviews) == 2

                # Verify we can access all interview attributes (no lazy loading)
                for interview in interviews:
                    assert interview.id is not None
                    assert interview.application_id == application.id
                    assert interview.scheduled_at is not None
                    assert interview.duration_minutes > 0
                    assert interview.interview_type in [InterviewType.TECHNICAL, InterviewType.HR]
                    assert interview.status == InterviewStatus.SCHEDULED

                # Now test that Pydantic serialization works (this is what the API does)
                # Import the schema used by the API
                from app.schemas.interview import InterviewRead

                # This serialization would fail with MissingGreenletError if interviews
                # were not eager-loaded
                interview_schemas = [InterviewRead.model_validate(interview) for interview in interviews]

                assert len(interview_schemas) == 2

                for interview_schema in interview_schemas:
                    assert interview_schema.id is not None
                    assert interview_schema.application_id == application.id
                    assert interview_schema.scheduled_at is not None

        run_async(_test())
