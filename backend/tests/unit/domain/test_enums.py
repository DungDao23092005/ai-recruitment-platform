import json
import sys
from enum import Enum

import pytest

from app.domain.enums import (
    ApplicationStatus,
    CompanySize,
    JobStatus,
    JobType,
    ProficiencyLevel,
    UserRole,
    WorkplaceType,
)

ALL_ENUM_CLASSES = [
    UserRole,
    JobStatus,
    JobType,
    WorkplaceType,
    ApplicationStatus,
    ProficiencyLevel,
    CompanySize,
]


@pytest.mark.parametrize(
    "enum_class,expected_members",
    [
        (UserRole, {"ADMIN", "CANDIDATE", "RECRUITER"}),
        (JobStatus, {"DRAFT", "PUBLISHED", "CLOSED", "EXPIRED"}),
        (JobType, {"FULL_TIME", "PART_TIME", "CONTRACT", "INTERNSHIP"}),
        (WorkplaceType, {"ON_SITE", "HYBRID", "REMOTE"}),
        (
            ApplicationStatus,
            {
                "APPLIED",
                "UNDER_REVIEW",
                "SHORTLISTED",
                "INTERVIEWING",
                "ACCEPTED",
                "REJECTED",
                "WITHDRAWN",
            },
        ),
        (ProficiencyLevel, {"BEGINNER", "INTERMEDIATE", "ADVANCED", "EXPERT"}),
        (CompanySize, {"SEED", "STARTUP", "SME", "ENTERPRISE"}),
    ],
)
def test_enum_members_exist(enum_class, expected_members):
    assert set(enum_class.__members__) == expected_members


@pytest.mark.parametrize(
    "member,expected_value",
    [
        (UserRole.ADMIN, "admin"),
        (UserRole.CANDIDATE, "candidate"),
        (UserRole.RECRUITER, "recruiter"),
        (JobStatus.DRAFT, "draft"),
        (JobStatus.PUBLISHED, "published"),
        (JobStatus.CLOSED, "closed"),
        (JobStatus.EXPIRED, "expired"),
        (JobType.FULL_TIME, "full_time"),
        (JobType.PART_TIME, "part_time"),
        (JobType.CONTRACT, "contract"),
        (JobType.INTERNSHIP, "internship"),
        (WorkplaceType.ON_SITE, "on_site"),
        (WorkplaceType.HYBRID, "hybrid"),
        (WorkplaceType.REMOTE, "remote"),
        (ApplicationStatus.APPLIED, "applied"),
        (ApplicationStatus.UNDER_REVIEW, "under_review"),
        (ApplicationStatus.SHORTLISTED, "shortlisted"),
        (ApplicationStatus.INTERVIEWING, "interviewing"),
        (ApplicationStatus.ACCEPTED, "accepted"),
        (ApplicationStatus.REJECTED, "rejected"),
        (ApplicationStatus.WITHDRAWN, "withdrawn"),
        (ProficiencyLevel.BEGINNER, "beginner"),
        (ProficiencyLevel.INTERMEDIATE, "intermediate"),
        (ProficiencyLevel.ADVANCED, "advanced"),
        (ProficiencyLevel.EXPERT, "expert"),
        (CompanySize.SEED, "seed"),
        (CompanySize.STARTUP, "startup"),
        (CompanySize.SME, "sme"),
        (CompanySize.ENTERPRISE, "enterprise"),
    ],
)
def test_enum_values(member, expected_value):
    assert member.value == expected_value


@pytest.mark.parametrize("enum_class", ALL_ENUM_CLASSES)
def test_enums_inherit_str_and_enum(enum_class):
    for member in enum_class:
        assert isinstance(member, str)
        assert isinstance(member, Enum)


@pytest.mark.parametrize(
    "member,expected_str",
    [
        (UserRole.ADMIN, "UserRole.ADMIN"),
        (JobStatus.PUBLISHED, "JobStatus.PUBLISHED"),
        (WorkplaceType.REMOTE, "WorkplaceType.REMOTE"),
        (ApplicationStatus.ACCEPTED, "ApplicationStatus.ACCEPTED"),
    ],
)
def test_string_serialization(member, expected_str):
    assert str(member) == expected_str


@pytest.mark.parametrize(
    "member,expected_value",
    [
        (UserRole.ADMIN, "admin"),
        (JobStatus.CLOSED, "closed"),
        (ProficiencyLevel.EXPERT, "expert"),
        (CompanySize.ENTERPRISE, "enterprise"),
    ],
)
def test_json_serialization(member, expected_value):
    payload = {"value": member}
    assert json.loads(json.dumps(payload)) == {"value": expected_value}


def test_enum_values_are_unique():
    for enum_class in ALL_ENUM_CLASSES:
        values = [member.value for member in enum_class]
        assert len(values) == len(set(values))


def test_domain_enums_module_has_no_orm_or_framework_dependency():
    forbidden_prefixes = (
        "sqlalchemy",
        "app.database",
        "app.repositories",
        "fastapi",
    )
    before = set(sys.modules)
    import app.domain.enums  # noqa: F401

    newly_loaded = set(sys.modules) - before
    assert not any(
        name.startswith(forbidden_prefixes) for name in newly_loaded
    )
