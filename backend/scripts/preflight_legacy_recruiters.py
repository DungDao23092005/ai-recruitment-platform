#!/usr/bin/env python
"""
Preflight report script for legacy recruiters.

This script identifies recruiters who will be affected by quota enforcement rollout.
It is READ-ONLY and does not modify any data.

Run with: python backend/scripts/preflight_legacy_recruiters.py
"""

import asyncio
import sys
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Allow running directly: python backend/scripts/preflight_legacy_recruiters.py
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import async_session_factory
from app.domain.enums import SubscriptionStatus, UserRole, JobStatus
from app.models import User, Subscription, RecruitmentPlan, Job, RecruiterProfile

# Columns that exist in the legacy subscription schema (before the quota
# enforcement migration adds max_job_posts / max_candidate_searches / etc.).
LEGACY_SUBSCRIPTION_COLUMNS = (
    Subscription.id,
    Subscription.user_id,
    Subscription.status,
    Subscription.expires_at,
)


async def run_preflight() -> dict:
    """
    Run preflight analysis and return summary statistics.

    Only legacy subscription columns are selected so the script works against
    a SQL Server database that has not yet received the quota enforcement
    migration.

    Returns dict with summary counts and minimal diagnostic information.
    """
    async with async_session_factory() as session:
        # Get all recruiters
        recruiters_stmt = select(User).where(User.role == UserRole.RECRUITER)
        recruiters_result = await session.execute(recruiters_stmt)
        all_recruiters = list(recruiters_result.scalars().all())

        total_recruiters = len(all_recruiters)

        # Get active subscriptions using only legacy columns
        now = datetime.utcnow()
        active_subs_stmt = select(*LEGACY_SUBSCRIPTION_COLUMNS).where(
            Subscription.is_deleted == False,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.expires_at > now,
        )
        active_subs_result = await session.execute(active_subs_stmt)
        active_subscriptions = active_subs_result.all()

        # Map user_id -> active subscription row
        active_sub_by_user = {row.user_id: row for row in active_subscriptions}

        # Get all subscriptions for recruiters (including expired/cancelled)
        recruiter_ids = [r.id for r in all_recruiters]
        all_subs_stmt = select(*LEGACY_SUBSCRIPTION_COLUMNS).where(
            Subscription.is_deleted == False,
            Subscription.user_id.in_(recruiter_ids),
        )
        all_subs_result = await session.execute(all_subs_stmt)
        all_subscriptions = all_subs_result.all()

        # Map user_id -> list of all subscription rows
        all_subs_by_user = defaultdict(list)
        for sub in all_subscriptions:
            all_subs_by_user[sub.user_id].append(sub)

        # Categorize recruiters
        recruiters_with_active = []
        recruiters_without_any = []
        recruiters_with_expired_only = []
        affected_recruiters = []

        for recruiter in all_recruiters:
            has_active = recruiter.id in active_sub_by_user
            has_any_sub = recruiter.id in all_subs_by_user and len(all_subs_by_user[recruiter.id]) > 0

            if has_active:
                recruiters_with_active.append(recruiter.id)
            elif has_any_sub:
                # Has subscription but none active
                recruiters_with_expired_only.append(recruiter.id)
                affected_recruiters.append({
                    "user_id": str(recruiter.id),
                    "reason": "Has expired/cancelled subscription only",
                    "subscription_count": len(all_subs_by_user[recruiter.id]),
                })
            else:
                recruiters_without_any.append(recruiter.id)
                affected_recruiters.append({
                    "user_id": str(recruiter.id),
                    "reason": "No subscription at all",
                    "subscription_count": 0,
                })

        # Get legacy PUBLISHED jobs from affected recruiters
        affected_user_ids = [r["user_id"] for r in affected_recruiters]
        legacy_jobs_count = 0
        legacy_jobs_by_recruiter = defaultdict(int)

        if affected_user_ids:
            # Get company IDs owned by affected recruiters
            company_stmt = select(RecruiterProfile.company_id).where(
                RecruiterProfile.user_id.in_([uuid.UUID(uid) for uid in affected_user_ids]),
                RecruiterProfile.is_deleted == False,
            )
            company_result = await session.execute(company_stmt)
            company_ids = list(company_result.scalars().all())

            if company_ids:
                # More precise: get jobs with recruiter info
                jobs_detail_stmt = select(
                    User.id.label("user_id"),
                    func.count(Job.id).label("job_count")
                ).select_from(User).join(
                    RecruiterProfile, RecruiterProfile.user_id == User.id
                ).join(
                    Job, Job.company_id == RecruiterProfile.company_id
                ).where(
                    User.id.in_([uuid.UUID(uid) for uid in affected_user_ids]),
                    Job.is_deleted == False,
                    Job.status == JobStatus.PUBLISHED,
                ).group_by(User.id)

                jobs_detail_result = await session.execute(jobs_detail_stmt)
                for row in jobs_detail_result.all():
                    legacy_jobs_by_recruiter[str(row.user_id)] = row.job_count
                    legacy_jobs_count += row.job_count

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_recruiters": total_recruiters,
            "recruiters_with_active_subscription": len(recruiters_with_active),
            "recruiters_without_subscription": len(recruiters_without_any),
            "recruiters_with_expired_subscription": len(recruiters_with_expired_only),
            "legacy_published_jobs": legacy_jobs_count,
            "legacy_jobs_by_recruiter": dict(legacy_jobs_by_recruiter),
            "affected_recruiters": affected_recruiters,
            "summary": {
                "ready_for_enforcement": len(recruiters_with_active),
                "need_subscription": len(affected_recruiters),
                "grandfathered_jobs_not_counted": legacy_jobs_count,
            },
        }


def print_report(report: dict) -> None:
    """Print human-readable preflight report."""
    print("=" * 60)
    print("PREFLIGHT REPORT - LEGACY RECRUITERS QUOTA ENFORCEMENT")
    print("=" * 60)
    print(f"Timestamp: {report['timestamp']}")
    print()
    print("SUMMARY:")
    print(f"  Total recruiters: {report['total_recruiters']}")
    print(f"  With active subscription: {report['recruiters_with_active_subscription']}")
    print(f"  Without any subscription: {report['recruiters_without_subscription']}")
    print(f"  With expired/cancelled only: {report['recruiters_with_expired_subscription']}")
    print(f"  Legacy PUBLISHED jobs (grandfathered): {report['legacy_published_jobs']}")
    print()
    print("ENFORCEMENT READINESS:")
    print(f"  Ready for enforcement: {report['summary']['ready_for_enforcement']}")
    print(f"  Need subscription before enforcement: {report['summary']['need_subscription']}")
    print(f"  Grandfathered jobs (not counted in quota): {report['summary']['grandfathered_jobs_not_counted']}")
    print()

    if report['affected_recruiters']:
        print("AFFECTED RECRUITERS (require action):")
        print("-" * 60)
        for rec in report['affected_recruiters']:
            print(f"  User ID: {rec['user_id']}")
            print(f"  Reason: {rec['reason']}")
            print(f"  Subscription count: {rec['subscription_count']}")
            if rec['user_id'] in report['legacy_jobs_by_recruiter']:
                print(f"  Legacy PUBLISHED jobs: {report['legacy_jobs_by_recruiter'][rec['user_id']]}")
            print()
    else:
        print("No affected recruiters found. All recruiters have active subscriptions.")

    print("=" * 60)
    print("NOTE: This report is READ-ONLY. No data was modified.")
    print("=" * 60)


async def main():
    print("Running preflight analysis...")
    report = await run_preflight()
    print_report(report)

    # Return non-zero exit code if there are affected recruiters
    if report['affected_recruiters']:
        print("\nWARNING: Some recruiters will be blocked by quota enforcement.")
        print("They need active subscriptions before enforcement is enabled.")
        return 1
    else:
        print("\nAll recruiters have active subscriptions. Safe to enable enforcement.")
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
