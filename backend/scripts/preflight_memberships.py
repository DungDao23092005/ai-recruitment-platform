#!/usr/bin/env python
"""Read-only preflight for the company membership backfill.

Detects legacy recruiter-to-company mappings that cannot be converted into a
single unambiguous workspace admin. Exits non-zero when a blocking case exists
so the migration is never run against an unsafe mapping.

Run:
    python backend/scripts/preflight_memberships.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database.session import async_session_factory
from app.domain.enums import MembershipStatus
from app.models import Company, CompanyMembership, RecruiterProfile, User


async def _table_exists(session: AsyncSession, table_name: str) -> bool:
    connection = await session.connection()
    return await connection.run_sync(
        lambda sync_connection: inspect(sync_connection).has_table(table_name)
    )


async def run_preflight() -> tuple[dict, list[str]]:
    blockers: list[str] = []
    report: dict = {
        "profiles_total": 0,
        "profiles_unassigned": 0,
        "companies_mapped": 0,
        "proposed_admins": 0,
        "ambiguous_companies": [],
        "invalid_profiles": [],
        "duplicate_profile_users": [],
        "memberships_table_exists": False,
        "active_memberships": 0,
        "companies_without_active_admin": [],
    }

    async with async_session_factory() as session:
        profiles = list(
            (
                await session.execute(
                    select(RecruiterProfile).where(
                        RecruiterProfile.is_deleted == False  # noqa: E712
                    )
                )
            )
            .scalars()
            .all()
        )
        report["profiles_total"] = len(profiles)

        user_ids = {profile.user_id for profile in profiles}
        company_ids = {
            profile.company_id
            for profile in profiles
            if profile.company_id is not None
        }

        users = {
            user.id: user
            for user in (
                (
                    await session.execute(
                        select(User).where(User.id.in_(user_ids))
                    )
                )
                .scalars()
                .all()
            )
        }
        companies = {
            company.id: company
            for company in (
                (
                    await session.execute(
                        select(Company).where(Company.id.in_(company_ids))
                    )
                )
                .scalars()
                .all()
            )
        }

        profiles_by_user: dict = defaultdict(list)
        profiles_by_company: dict = defaultdict(list)
        for profile in profiles:
            profiles_by_user[profile.user_id].append(profile)
            if profile.company_id is None:
                report["profiles_unassigned"] += 1
                continue
            profiles_by_company[profile.company_id].append(profile)

            user = users.get(profile.user_id)
            company = companies.get(profile.company_id)
            if (
                user is None
                or user.is_deleted
                or company is None
                or company.is_deleted
            ):
                report["invalid_profiles"].append(
                    {
                        "profile_id": str(profile.id),
                        "user_id": str(profile.user_id),
                        "company_id": str(profile.company_id),
                    }
                )

        for user_id, items in profiles_by_user.items():
            if len(items) > 1:
                report["duplicate_profile_users"].append(str(user_id))

        for company_id, items in profiles_by_company.items():
            company = companies.get(company_id)
            if company is not None and not company.is_deleted:
                report["companies_mapped"] += 1
            if len(items) > 1:
                report["ambiguous_companies"].append(
                    {
                        "company_id": str(company_id),
                        "recruiter_count": len(items),
                    }
                )
            else:
                report["proposed_admins"] += 1

        if report["ambiguous_companies"]:
            blockers.append(
                "Multiple active recruiter profiles map to the same company; "
                "an initial admin must be chosen explicitly."
            )
        if report["invalid_profiles"]:
            blockers.append(
                "Recruiter profiles reference a missing or soft-deleted "
                "user/company."
            )
        if report["duplicate_profile_users"]:
            blockers.append(
                "A user has multiple active recruiter profiles; the legacy "
                "company mapping is ambiguous."
            )

        report["memberships_table_exists"] = await _table_exists(
            session, "company_memberships"
        )
        if report["memberships_table_exists"]:
            memberships = list(
                (
                    await session.execute(
                        select(CompanyMembership).where(
                            CompanyMembership.is_deleted == False,  # noqa: E712
                            CompanyMembership.status == MembershipStatus.ACTIVE,
                        )
                    )
                )
                .scalars()
                .all()
            )
            report["active_memberships"] = len(memberships)
            admin_companies = {
                membership.company_id
                for membership in memberships
                if membership.role.value == "admin"
            }
            for company_id in sorted(company_ids, key=str):
                company = companies.get(company_id)
                if (
                    company is not None
                    and not company.is_deleted
                    and company_id not in admin_companies
                ):
                    report["companies_without_active_admin"].append(
                        str(company_id)
                    )

    return report, blockers


async def _main() -> int:
    report, blockers = await run_preflight()
    print(json.dumps(report, indent=2, default=str))
    if blockers:
        print("\nBLOCKERS:", file=sys.stderr)
        for blocker in blockers:
            print(f"- {blocker}", file=sys.stderr)
        print(
            "\nNo data was changed. Resolve the blockers before running the "
            "membership migration.",
            file=sys.stderr,
        )
        return 1
    print("\nNo blocking mapping issues found. No data was changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
