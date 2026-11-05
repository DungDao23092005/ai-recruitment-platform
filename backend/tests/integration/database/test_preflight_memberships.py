"""Exercise the read-only membership backfill preflight against SQL Server."""

from __future__ import annotations

import uuid

import pytest

from app.domain.enums import CompanySize, UserRole
from app.models import Company, RecruiterProfile, User
from scripts.preflight_memberships import run_preflight

pytestmark = pytest.mark.integration


def _company() -> Company:
    return Company(
        name="Preflight Co",
        slug=f"preflight-{uuid.uuid4().hex[:8]}",
        tax_code=str(uuid.uuid4().int)[:12],
        size=CompanySize.STARTUP,
    )


def _recruiter() -> User:
    return User(
        email=f"preflight-{uuid.uuid4()}@example.com",
        password_hash="hash",
        role=UserRole.RECRUITER,
        is_active=True,
    )


def _profile(user: User, company: Company | None) -> RecruiterProfile:
    return RecruiterProfile(
        user_id=user.id,
        company_id=company.id if company is not None else None,
        full_name="Preflight Recruiter",
    )


def test_preflight_reports_no_blockers_for_unambiguous_mapping(
    session, run_async
):
    async def _test() -> None:
        company = _company()
        recruiter = _recruiter()
        session.add_all([company, recruiter])
        await session.flush()
        session.add(_profile(recruiter, company))
        await session.commit()

        report, blockers = await run_preflight()
        assert blockers == []
        assert report["profiles_total"] == 1
        assert report["profiles_unassigned"] == 0
        assert report["companies_mapped"] == 1
        assert report["proposed_admins"] == 1
        assert report["ambiguous_companies"] == []
        assert report["invalid_profiles"] == []
        assert report["duplicate_profile_users"] == []
        assert report["memberships_table_exists"] is True
        assert report["companies_without_active_admin"] == [str(company.id)]

    run_async(_test())


def test_preflight_blocks_ambiguous_company(session, run_async):
    async def _test() -> None:
        company = _company()
        first = _recruiter()
        second = _recruiter()
        session.add_all([company, first, second])
        await session.flush()
        session.add_all(
            [_profile(first, company), _profile(second, company)]
        )
        await session.commit()

        report, blockers = await run_preflight()
        assert len(blockers) == 1
        assert "Multiple active recruiter profiles" in blockers[0]
        assert report["ambiguous_companies"] == [
            {"company_id": str(company.id), "recruiter_count": 2}
        ]
        assert report["proposed_admins"] == 0

    run_async(_test())


def test_preflight_blocks_soft_deleted_company_mapping(
    session, run_async
):
    async def _test() -> None:
        company = _company()
        company.is_deleted = True
        recruiter = _recruiter()
        session.add_all([company, recruiter])
        await session.flush()
        session.add(_profile(recruiter, company))
        await session.commit()

        report, blockers = await run_preflight()
        assert any("missing or soft-deleted" in blocker for blocker in blockers)
        assert len(report["invalid_profiles"]) == 1
        invalid = report["invalid_profiles"][0]
        assert invalid["user_id"] == str(recruiter.id)
        assert invalid["company_id"] == str(company.id)

    run_async(_test())
