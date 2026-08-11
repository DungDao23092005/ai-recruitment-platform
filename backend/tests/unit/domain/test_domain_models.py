import sys
import time
import uuid
from datetime import datetime, timezone

import pytest

from app.domain.enums import (
    ApplicationStatus,
    CompanySize,
    JobStatus,
    JobType,
    UserRole,
    WorkplaceType,
)
from app.domain.models import (
    Application,
    BaseDomainEntity,
    Company,
    Job,
    User,
)


def test_base_entity_defaults():
    entity = BaseDomainEntity()

    assert isinstance(entity.id, uuid.UUID)
    assert isinstance(entity.created_at, datetime)
    assert isinstance(entity.updated_at, datetime)
    assert entity.created_at.tzinfo is not None
    assert entity.updated_at.tzinfo is not None
    assert entity.is_deleted is False


def test_base_entity_generates_unique_ids():
    first = BaseDomainEntity()
    second = BaseDomainEntity()

    assert first.id != second.id


def test_mark_updated_refreshes_updated_at():
    entity = BaseDomainEntity()
    time.sleep(0.001)
    entity.mark_updated()

    assert entity.updated_at > entity.created_at


def test_soft_delete_marks_entity_deleted():
    entity = BaseDomainEntity()
    time.sleep(0.001)
    entity.soft_delete()

    assert entity.is_deleted is True
    assert entity.updated_at > entity.created_at


def test_user_fields():
    user = User(
        email="john@example.com",
        password_hash="hashed-password",
        role=UserRole.CANDIDATE,
    )

    assert user.email == "john@example.com"
    assert user.password_hash == "hashed-password"
    assert user.role is UserRole.CANDIDATE
    assert user.is_active is True


def test_user_is_active_can_be_disabled():
    user = User(
        email="john@example.com",
        password_hash="hashed-password",
        role=UserRole.ADMIN,
        is_active=False,
    )

    assert user.is_active is False


def test_company_fields():
    company = Company(
        name="Acme Corp",
        slug="acme-corp",
        tax_code="0123456789",
        size=CompanySize.STARTUP,
    )

    assert company.name == "Acme Corp"
    assert company.slug == "acme-corp"
    assert company.tax_code == "0123456789"
    assert company.size is CompanySize.STARTUP


def test_job_defaults():
    job = Job(
        company_id=uuid.uuid4(),
        title="Backend Engineer",
        description="Build the platform backend",
        job_type=JobType.FULL_TIME,
        workplace_type=WorkplaceType.REMOTE,
    )

    assert job.status is JobStatus.DRAFT
    assert job.location == ""


def test_job_fields():
    job = Job(
        company_id=uuid.uuid4(),
        title="Backend Engineer",
        description="Build the platform backend",
        job_type=JobType.FULL_TIME,
        workplace_type=WorkplaceType.HYBRID,
        status=JobStatus.PUBLISHED,
        location="Ho Chi Minh City",
    )

    assert job.company_id is not None
    assert job.title == "Backend Engineer"
    assert job.description == "Build the platform backend"
    assert job.status is JobStatus.PUBLISHED
    assert job.job_type is JobType.FULL_TIME
    assert job.workplace_type is WorkplaceType.HYBRID
    assert job.location == "Ho Chi Minh City"


def test_application_defaults():
    application = Application(
        candidate_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
    )

    assert application.status is ApplicationStatus.APPLIED
    assert application.candidate_id is not None
    assert application.job_id is not None


def test_domain_models_are_pure_python():
    forbidden_prefixes = (
        "sqlalchemy",
        "app.database",
        "app.repositories",
        "fastapi",
    )
    before = set(sys.modules)
    import app.domain.models  # noqa: F401

    newly_loaded = set(sys.modules) - before
    assert not any(
        name.startswith(forbidden_prefixes) for name in newly_loaded
    )
