"""Company usage-history API integration tests."""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.database.session import async_session_factory
from app.domain.enums import (
    MembershipRole,
    SubscriptionScope,
    SubscriptionUsageFeatureType,
    SubscriptionUsageStatus,
    UserRole,
)
from app.domain.models.base import utc_now
from app.models import RecruiterProfile, SubscriptionUsage
from tests.integration import company_billing_helpers as cbh
from tests.integration.api.conftest import API_V1

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


async def _create_usage(
    session,
    *,
    subscription_id: uuid.UUID,
    company_id: uuid.UUID | None,
    user_id: uuid.UUID,
    created_at: datetime,
    feature_type: SubscriptionUsageFeatureType = (
        SubscriptionUsageFeatureType.JOB_POST
    ),
    status: SubscriptionUsageStatus = SubscriptionUsageStatus.COMPLETED,
    scope: SubscriptionScope = SubscriptionScope.COMPANY_RECRUITING,
    amount: int = 1,
    reference_id: uuid.UUID | None = None,
) -> SubscriptionUsage:
    usage = SubscriptionUsage(
        subscription_id=subscription_id,
        company_id=company_id,
        user_id=user_id,
        scope=scope,
        feature_type=feature_type,
        status=status,
        amount=amount,
        reference_id=reference_id,
        created_at=created_at,
        updated_at=created_at,
        finalized_at=(
            created_at if status == SubscriptionUsageStatus.COMPLETED else None
        ),
    )
    session.add(usage)
    await session.flush()
    return usage


async def _workspace_setup(
    session,
    *,
    role: MembershipRole = MembershipRole.ADMIN,
):
    admin_user = await cbh._create_user(session)
    member = admin_user
    if role != MembershipRole.ADMIN:
        member = await cbh._create_user(session)
    company = await cbh._create_company(session)
    await cbh._create_membership(
        session,
        company_id=company.id,
        user_id=admin_user.id,
        role=MembershipRole.ADMIN,
    )
    if member is not admin_user:
        await cbh._create_membership(
            session,
            company_id=company.id,
            user_id=member.id,
            role=role,
        )
    plan = await cbh._create_plan(session)
    subscription = await cbh._create_company_subscription(
        session,
        company_id=company.id,
        user_id=admin_user.id,
        plan_id=plan.id,
    )
    return admin_user, member, company, subscription


def test_company_usages_defaults_to_current_month_and_isolates_tenant(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            admin, _, company, subscription = await _workspace_setup(session)
            other_company = await cbh._create_company(session)
            profile = RecruiterProfile(
                user_id=admin.id,
                full_name="Nguyễn Quản Trị",
            )
            session.add(profile)

            now_local = utc_now().astimezone(VN_TZ)
            current = await _create_usage(
                session,
                subscription_id=subscription.id,
                company_id=company.id,
                user_id=admin.id,
                created_at=now_local - timedelta(minutes=5),
            )
            await _create_usage(
                session,
                subscription_id=subscription.id,
                company_id=company.id,
                user_id=admin.id,
                created_at=now_local.replace(day=1)
                - timedelta(days=1),
            )
            await _create_usage(
                session,
                subscription_id=subscription.id,
                company_id=other_company.id,
                user_id=admin.id,
                created_at=now_local - timedelta(minutes=4),
            )
            await _create_usage(
                session,
                subscription_id=subscription.id,
                company_id=None,
                user_id=admin.id,
                created_at=now_local - timedelta(minutes=3),
                scope=SubscriptionScope.CANDIDATE_PERSONAL,
                feature_type=SubscriptionUsageFeatureType.CANDIDATE_CHAT,
            )
            company_id, admin_id, current_id = (
                company.id,
                admin.id,
                current.id,
            )
            await session.commit()

        client = await cbh._make_jwt_client_for_user(admin)
        try:
            resp = await client.get(
                f"{API_V1}/subscriptions/company/usages",
                headers={"X-Company-ID": str(company_id)},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["total"] == 1
            assert body["page"] == 1
            assert body["page_size"] == 10
            assert body["total_pages"] == 1
            item = body["items"][0]
            assert item["id"] == str(current_id)
            assert item["user_id"] == str(admin_id)
            assert item["user_full_name"] == "Nguyễn Quản Trị"
            assert item["feature_type"] == "job_post"
            assert item["feature_label"] == "Tin tuyển dụng"
            assert item["status"] == "completed"
            assert item["status_label"] == "Hoàn tất"
        finally:
            await client.aclose()

    run_async(_run())


def test_company_usages_allow_workspace_recruiter_read_only(run_async):
    async def _run():
        async with async_session_factory() as session:
            _, recruiter, company, subscription = await _workspace_setup(
                session, role=MembershipRole.RECRUITER
            )
            await _create_usage(
                session,
                subscription_id=subscription.id,
                company_id=company.id,
                user_id=recruiter.id,
                created_at=utc_now(),
            )
            company_id = company.id
            await session.commit()

        client = await cbh._make_jwt_client_for_user(recruiter)
        try:
            resp = await client.get(
                f"{API_V1}/subscriptions/company/usages",
                headers={"X-Company-ID": str(company_id)},
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["total"] == 1
        finally:
            await client.aclose()

    run_async(_run())


def test_company_usages_require_explicit_header_and_deny_wrong_roles(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            admin, _, company, _ = await _workspace_setup(session)
            candidate = await cbh._create_user(
                session, role=UserRole.CANDIDATE
            )
            platform_admin = await cbh._create_user(
                session, role=UserRole.ADMIN
            )
            interviewer = await cbh._create_user(session)
            await cbh._create_membership(
                session,
                company_id=company.id,
                user_id=interviewer.id,
                role=MembershipRole.INTERVIEWER,
            )
            company_id = company.id
            await session.commit()

        admin_client = await cbh._make_jwt_client_for_user(admin)
        try:
            missing = await admin_client.get(
                f"{API_V1}/subscriptions/company/usages"
            )
            assert missing.status_code == 400
        finally:
            await admin_client.aclose()

        for user in (candidate, platform_admin, interviewer):
            client = await cbh._make_jwt_client_for_user(user)
            try:
                resp = await client.get(
                    f"{API_V1}/subscriptions/company/usages",
                    headers={"X-Company-ID": str(company_id)},
                )
                assert resp.status_code == 403
            finally:
                await client.aclose()

    run_async(_run())


def test_company_usages_filter_paginate_and_order(run_async):
    async def _run():
        async with async_session_factory() as session:
            admin, other_member, company, subscription = (
                await _workspace_setup(session, role=MembershipRole.RECRUITER)
            )
            now = utc_now()
            job = await _create_usage(
                session,
                subscription_id=subscription.id,
                company_id=company.id,
                user_id=admin.id,
                created_at=now - timedelta(minutes=3),
            )
            await _create_usage(
                session,
                subscription_id=subscription.id,
                company_id=company.id,
                user_id=admin.id,
                created_at=now - timedelta(minutes=2),
                feature_type=SubscriptionUsageFeatureType.CANDIDATE_SEARCH,
            )
            other = await _create_usage(
                session,
                subscription_id=subscription.id,
                company_id=company.id,
                user_id=other_member.id,
                created_at=now - timedelta(minutes=1),
                feature_type=SubscriptionUsageFeatureType.AI_FEATURE,
                status=SubscriptionUsageStatus.FAILED,
            )
            company_id, admin_id, other_member_id = (
                company.id,
                admin.id,
                other_member.id,
            )
            other_id = other.id
            job_id = job.id
            await session.commit()

        client = await cbh._make_jwt_client_for_user(admin)
        try:
            headers = {"X-Company-ID": str(company_id)}
            page_two = await client.get(
                f"{API_V1}/subscriptions/company/usages",
                headers=headers,
                params={"page": 2, "page_size": 2},
            )
            assert page_two.status_code == 200, page_two.text
            body = page_two.json()
            assert body["total"] == 3
            assert body["total_pages"] == 2
            assert [i["id"] for i in body["items"]] == [str(job_id)]

            by_feature = await client.get(
                f"{API_V1}/subscriptions/company/usages",
                headers=headers,
                params={"feature_type": "ai_feature"},
            )
            assert by_feature.status_code == 200, by_feature.text
            assert [i["id"] for i in by_feature.json()["items"]] == [
                str(other_id)
            ]
            assert by_feature.json()["items"][0]["status_label"] == "Thất bại"

            by_member = await client.get(
                f"{API_V1}/subscriptions/company/usages",
                headers=headers,
                params={"user_id": str(other_member_id)},
            )
            assert by_member.status_code == 200, by_member.text
            assert by_member.json()["total"] == 1

            by_admin = await client.get(
                f"{API_V1}/subscriptions/company/usages",
                headers=headers,
                params={"user_id": str(admin_id)},
            )
            assert by_admin.status_code == 200, by_admin.text
            assert by_admin.json()["total"] == 2
        finally:
            await client.aclose()

    run_async(_run())


def test_company_usages_date_range_includes_full_end_day(run_async):
    async def _run():
        async with async_session_factory() as session:
            admin, _, company, subscription = await _workspace_setup(session)
            day = utc_now().astimezone(VN_TZ).date() - timedelta(days=3)
            inside = await _create_usage(
                session,
                subscription_id=subscription.id,
                company_id=company.id,
                user_id=admin.id,
                created_at=datetime.combine(
                    day, time(12, 0), tzinfo=VN_TZ
                ),
            )
            await _create_usage(
                session,
                subscription_id=subscription.id,
                company_id=company.id,
                user_id=admin.id,
                created_at=datetime.combine(
                    day + timedelta(days=1), time(0, 0), tzinfo=VN_TZ
                ),
            )
            await _create_usage(
                session,
                subscription_id=subscription.id,
                company_id=company.id,
                user_id=admin.id,
                created_at=datetime.combine(
                    day - timedelta(days=1), time(23, 59), tzinfo=VN_TZ
                ),
            )
            company_id, inside_id = company.id, inside.id
            await session.commit()

        client = await cbh._make_jwt_client_for_user(admin)
        try:
            resp = await client.get(
                f"{API_V1}/subscriptions/company/usages",
                headers={"X-Company-ID": str(company_id)},
                params={
                    "start_date": day.isoformat(),
                    "end_date": day.isoformat(),
                },
            )
            assert resp.status_code == 200, resp.text
            assert [i["id"] for i in resp.json()["items"]] == [
                str(inside_id)
            ]

            inverted = await client.get(
                f"{API_V1}/subscriptions/company/usages",
                headers={"X-Company-ID": str(company_id)},
                params={
                    "start_date": day.isoformat(),
                    "end_date": (day - timedelta(days=1)).isoformat(),
                },
            )
            assert inverted.status_code == 422

            too_wide = await client.get(
                f"{API_V1}/subscriptions/company/usages",
                headers={"X-Company-ID": str(company_id)},
                params={
                    "start_date": day.isoformat(),
                    "end_date": (day + timedelta(days=366)).isoformat(),
                },
            )
            assert too_wide.status_code == 422

            exactly_366 = await client.get(
                f"{API_V1}/subscriptions/company/usages",
                headers={"X-Company-ID": str(company_id)},
                params={
                    "start_date": day.isoformat(),
                    "end_date": (day + timedelta(days=365)).isoformat(),
                },
            )
            assert exactly_366.status_code == 200, exactly_366.text
        finally:
            await client.aclose()

    run_async(_run())


def test_company_usages_forged_header_cannot_read_other_company(run_async):
    async def _run():
        async with async_session_factory() as session:
            user_a = await cbh._create_user(session)
            user_b = await cbh._create_user(session)
            company_a = await cbh._create_company(session)
            company_b = await cbh._create_company(session)
            await cbh._create_membership(
                session,
                company_id=company_a.id,
                user_id=user_a.id,
                role=MembershipRole.ADMIN,
            )
            await cbh._create_membership(
                session,
                company_id=company_b.id,
                user_id=user_b.id,
                role=MembershipRole.ADMIN,
            )
            company_b_id = company_b.id
            await session.commit()

        client = await cbh._make_jwt_client_for_user(user_a)
        try:
            resp = await client.get(
                f"{API_V1}/subscriptions/company/usages",
                headers={"X-Company-ID": str(company_b_id)},
            )
            assert resp.status_code == 403
        finally:
            await client.aclose()

    run_async(_run())
