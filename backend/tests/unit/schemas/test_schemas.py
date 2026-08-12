import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.domain.enums import (
    ApplicationStatus,
    CompanySize,
    JobStatus,
    JobType,
    UserRole,
    WorkplaceType,
)
from app.schemas import (
    ApplicationCreate,
    ApplicationRead,
    ApplicationStatusUpdate,
    CandidateProfileCreate,
    CompanyCreate,
    CompanyRead,
    CompanyUpdate,
    JobCreate,
    JobRead,
    JobUpdate,
    RecruiterProfileCreate,
    SkillCreate,
    SkillRead,
    Token,
    TokenPayload,
    UserCreate,
    UserRead,
)


def make_user_read_source():
    class FakeUser:
        def __init__(self):
            self.id = uuid.uuid4()
            self.email = "john@example.com"
            self.role = UserRole.CANDIDATE
            self.is_active = True
            self.created_at = datetime.now(timezone.utc)
            self.updated_at = datetime.now(timezone.utc)

    return FakeUser()


class TestUserSchemas:
    def test_user_create_valid_email_and_password(self):
        user = UserCreate(email="john@example.com", password="password123")

        assert user.email == "john@example.com"
        assert user.role is UserRole.CANDIDATE

    def test_user_create_invalid_email(self):
        with pytest.raises(ValidationError):
            UserCreate(email="not-an-email", password="password123")

    def test_user_create_password_too_short(self):
        with pytest.raises(ValidationError):
            UserCreate(email="john@example.com", password="short")

    def test_user_create_invalid_role(self):
        with pytest.raises(ValidationError):
            UserCreate(
                email="john@example.com",
                password="password123",
                role="superuser",
            )

    def test_user_read_from_attributes(self):
        source = make_user_read_source()

        user = UserRead.model_validate(source)

        assert user.id == source.id
        assert user.email == "john@example.com"
        assert user.role is UserRole.CANDIDATE
        assert user.is_active is True

    def test_candidate_profile_create_all_optional(self):
        profile = CandidateProfileCreate()

        assert profile.full_name is None
        assert profile.phone is None
        assert profile.title is None

    def test_recruiter_profile_create_all_optional(self):
        profile = RecruiterProfileCreate()

        assert profile.full_name is None
        assert profile.position is None
        assert profile.company_id is None


class TestTokenSchemas:
    def test_token_defaults(self):
        token = Token(access_token="abc.def.ghi")

        assert token.token_type == "bearer"

    def test_token_payload(self):
        payload = TokenPayload(sub="user-1", exp=1700000000)

        assert payload.sub == "user-1"
        assert payload.exp == 1700000000


class TestCompanySchemas:
    def test_company_create_valid(self):
        company = CompanyCreate(
            name="Acme",
            slug="acme",
            tax_code="123",
            size=CompanySize.STARTUP,
        )

        assert company.size is CompanySize.STARTUP

    def test_company_create_invalid_size(self):
        with pytest.raises(ValidationError):
            CompanyCreate(name="Acme", slug="acme", tax_code="123", size="huge")

    def test_company_read_from_attributes(self):
        class FakeCompany:
            def __init__(self):
                self.id = uuid.uuid4()
                self.name = "Acme"
                self.slug = "acme"
                self.tax_code = "123"
                self.size = CompanySize.STARTUP
                self.created_at = datetime.now(timezone.utc)
                self.updated_at = datetime.now(timezone.utc)

        company = CompanyRead.model_validate(FakeCompany())

        assert company.slug == "acme"
        assert company.size is CompanySize.STARTUP

    def test_company_update_all_optional(self):
        company = CompanyUpdate()

        assert company.model_dump() == {
            "name": None,
            "slug": None,
            "tax_code": None,
            "size": None,
        }


class TestJobSchemas:
    def test_job_create_defaults(self):
        job = JobCreate(
            company_id=uuid.uuid4(),
            title="Engineer",
            description="desc",
            job_type=JobType.FULL_TIME,
            workplace_type=WorkplaceType.REMOTE,
        )

        assert job.status is JobStatus.DRAFT
        assert job.location is None

    def test_job_create_invalid_job_type(self):
        with pytest.raises(ValidationError):
            JobCreate(
                company_id=uuid.uuid4(),
                title="Engineer",
                description="desc",
                job_type="fulltime",
                workplace_type=WorkplaceType.REMOTE,
            )

    def test_job_read_from_attributes(self):
        class FakeJob:
            def __init__(self):
                self.id = uuid.uuid4()
                self.company_id = uuid.uuid4()
                self.title = "Engineer"
                self.description = "desc"
                self.status = JobStatus.PUBLISHED
                self.job_type = JobType.FULL_TIME
                self.workplace_type = WorkplaceType.REMOTE
                self.location = ""
                self.created_at = datetime.now(timezone.utc)
                self.updated_at = datetime.now(timezone.utc)

        job = JobRead.model_validate(FakeJob())

        assert job.title == "Engineer"
        assert job.status is JobStatus.PUBLISHED
        assert job.location == ""

    def test_job_update_all_optional(self):
        job = JobUpdate()

        assert job.title is None
        assert job.status is None


class TestApplicationSchemas:
    def test_application_create_requires_valid_uuid(self):
        with pytest.raises(ValidationError):
            ApplicationCreate(job_id="not-a-uuid")

    def test_application_status_update_valid(self):
        update = ApplicationStatusUpdate(status=ApplicationStatus.INTERVIEWING)

        assert update.status is ApplicationStatus.INTERVIEWING

    def test_application_status_update_invalid(self):
        with pytest.raises(ValidationError):
            ApplicationStatusUpdate(status="not-a-status")

    def test_application_read_from_attributes_and_serialize(self):
        class FakeApplication:
            def __init__(self):
                self.id = uuid.uuid4()
                self.candidate_id = uuid.uuid4()
                self.job_id = uuid.uuid4()
                self.status = ApplicationStatus.APPLIED
                self.created_at = datetime.now(timezone.utc)
                self.updated_at = datetime.now(timezone.utc)

        application = ApplicationRead.model_validate(FakeApplication())
        dumped = application.model_dump()

        assert application.status is ApplicationStatus.APPLIED
        assert dumped["candidate_id"] == application.candidate_id
        assert dumped["status"] == "applied"


class TestSkillSchemas:
    def test_skill_create(self):
        skill = SkillCreate(name="Python")

        assert skill.name == "Python"

    def test_skill_read_from_attributes(self):
        class FakeSkill:
            def __init__(self):
                self.id = uuid.uuid4()
                self.name = "Python"
                self.created_at = datetime.now(timezone.utc)
                self.updated_at = datetime.now(timezone.utc)

        skill = SkillRead.model_validate(FakeSkill())

        assert skill.name == "Python"
