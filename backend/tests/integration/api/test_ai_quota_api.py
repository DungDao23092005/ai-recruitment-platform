"""Wave 1.4 Phase 2 — Recruiter AI Quota Metering, Scope & Reservation API integration tests.

Scenarios:
- P16: consume_job_post_quota_idempotent debits only selected company
- P17: reserve_search_quota debits only selected company
- P18: reserve_ai_quota debits only selected company
- P19: Candidate-facing AI endpoints do not create company usage rows
- P20: Public AI search jobs remains unmetered
- P21: Legacy calls without company workspace preserve personal quota
- P72: Legacy recruiter can use recruiter AI with personal quota
- P73: Recruiter without active membership cannot use recruiter AI through personal quota
- P74: Revoked workspace member cannot bypass revocation omitting header
- P75: Legacy recruiter cannot access workspace company job for AI recommend
- P76: Successful recruiter AI transitions usage RESERVED to COMPLETED once
- P77: Failed recruiter AI releases reservation and restores counter
- P79: Recruiter AI task cancellation triggers canonical quota release
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch
import uuid

import pytest
from sqlalchemy import func, select

from app.database.session import async_session_factory
from app.domain.enums import (
    JobStatus,
    JobType,
    MembershipRole,
    MembershipStatus,
    SubscriptionScope,
    SubscriptionUsageStatus,
    UserRole,
    WorkplaceType,
)
from app.models import (
    Job,
    RecruiterProfile,
    Subscription,
    SubscriptionUsage,
)
from app.services.quota_enforcement_service import QuotaEnforcementService
from tests.integration.api.conftest import API_V1
from tests.integration.company_billing_helpers import (
    _create_company,
    _create_company_subscription,
    _create_membership,
    _create_personal_subscription,
    _create_plan,
    _create_user,
    _make_jwt_client_for_user,
)

pytestmark = pytest.mark.integration


def test_p16_consume_job_post_quota_idempotent_debits_only_selected_company(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            comp_a = await _create_company(session)
            comp_b = await _create_company(session)
            await _create_membership(
                session,
                company_id=comp_a.id,
                user_id=user.id,
                role=MembershipRole.RECRUITER,
            )
            await _create_membership(
                session,
                company_id=comp_b.id,
                user_id=user.id,
                role=MembershipRole.RECRUITER,
            )
            plan = await _create_plan(session)
            sub_a = await _create_company_subscription(
                session, company_id=comp_a.id, user_id=user.id, plan_id=plan.id
            )
            sub_b = await _create_company_subscription(
                session, company_id=comp_b.id, user_id=user.id, plan_id=plan.id
            )
            sub_personal = await _create_personal_subscription(
                session, user_id=user.id, plan_id=plan.id
            )
            await session.commit()

            q = QuotaEnforcementService(session)
            job_id = uuid.uuid4()
            res = await q.consume_job_post_quota_idempotent(
                user_id=user.id,
                company_id=comp_a.id,
                job_id=job_id,
            )
            await session.commit()
            assert res.used == 1

            await session.refresh(sub_a)
            await session.refresh(sub_b)
            await session.refresh(sub_personal)
            assert sub_a.job_posts_used == 1
            assert sub_b.job_posts_used == 0
            assert sub_personal.job_posts_used == 0

            usage = await session.scalar(
                select(SubscriptionUsage).where(
                    SubscriptionUsage.subscription_id == sub_a.id
                )
            )
            assert usage is not None
            assert usage.company_id == comp_a.id
            assert usage.scope == SubscriptionScope.COMPANY_RECRUITING
            assert usage.user_id == user.id
            assert usage.status == SubscriptionUsageStatus.COMPLETED

    run_async(_run())


def test_p17_reserve_search_quota_debits_only_selected_company(run_async):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            comp_a = await _create_company(session)
            comp_b = await _create_company(session)
            await _create_membership(
                session,
                company_id=comp_a.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session)
            sub_a = await _create_company_subscription(
                session, company_id=comp_a.id, user_id=user.id, plan_id=plan.id
            )
            sub_b = await _create_company_subscription(
                session, company_id=comp_b.id, user_id=user.id, plan_id=plan.id
            )
            sub_personal = await _create_personal_subscription(
                session, user_id=user.id, plan_id=plan.id
            )
            await session.commit()

            q = QuotaEnforcementService(session)
            r = await q.reserve_search_quota(
                user_id=user.id,
                company_id=comp_a.id,
                idempotency_key=f"s-{uuid.uuid4()}",
            )
            await session.commit()

            await session.refresh(sub_a)
            await session.refresh(sub_b)
            await session.refresh(sub_personal)
            assert sub_a.candidate_searches_used == 1
            assert sub_b.candidate_searches_used == 0
            assert sub_personal.candidate_searches_used == 0
            assert r.subscription_id == sub_a.id

    run_async(_run())


def test_p18_reserve_ai_quota_debits_only_selected_company(run_async):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            comp_a = await _create_company(session)
            comp_b = await _create_company(session)
            await _create_membership(
                session,
                company_id=comp_a.id,
                user_id=user.id,
                role=MembershipRole.RECRUITER,
            )
            plan = await _create_plan(session)
            sub_a = await _create_company_subscription(
                session, company_id=comp_a.id, user_id=user.id, plan_id=plan.id
            )
            sub_b = await _create_company_subscription(
                session, company_id=comp_b.id, user_id=user.id, plan_id=plan.id
            )
            await session.commit()

            q = QuotaEnforcementService(session)
            r = await q.reserve_ai_quota(
                user_id=user.id,
                company_id=comp_a.id,
                idempotency_key=f"ai-{uuid.uuid4()}",
            )
            await session.commit()

            await session.refresh(sub_a)
            await session.refresh(sub_b)
            assert sub_a.ai_features_used == 1
            assert sub_b.ai_features_used == 0
            assert r.subscription_id == sub_a.id

    run_async(_run())


def test_p19_candidate_facing_ai_endpoints_do_not_create_company_usage_rows(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            cand = await _create_user(session, role=UserRole.CANDIDATE)
            await session.commit()

        client = await _make_jwt_client_for_user(cand)
        try:
            resp = await client.post(
                f"{API_V1}/ai/match",
                json={
                    "parsed_resume": {"full_name": "Test", "skills": ["Python"]},
                    "parsed_job": {"title": "Dev", "required_skills": ["Python"]},
                    "resume_vector": [0.1] * 384,
                    "job_vector": [0.1] * 384,
                },
            )
            assert resp.status_code == 200
        finally:
            await client.aclose()

        async with async_session_factory() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(SubscriptionUsage)
                .where(
                    SubscriptionUsage.scope
                    == SubscriptionScope.COMPANY_RECRUITING
                )
            )
            assert count == 0

    run_async(_run())


def test_p20_public_ai_search_jobs_remains_unmetered(run_async):
    async def _run():
        async with async_session_factory() as session:
            candidate = await _create_user(session, role=UserRole.CANDIDATE)
            await session.commit()

        client = await _make_jwt_client_for_user(candidate)
        try:
            with patch(
                "app.services.semantic_search_service.SemanticSearchService.search_jobs",
                new_callable=AsyncMock,
            ) as mock_search:
                mock_search.return_value = []
                resp = await client.get(
                    f"{API_V1}/ai/search/jobs",
                    params={"q": "Python developer", "limit": 5},
                )
                assert resp.status_code == 200
        finally:
            await client.aclose()

        async with async_session_factory() as session:
            count = await session.scalar(
                select(func.count()).select_from(SubscriptionUsage)
            )
            assert count == 0

    run_async(_run())


def test_p21_legacy_calls_without_company_workspace_preserve_personal_quota(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            plan = await _create_plan(session)
            sub_personal = await _create_personal_subscription(
                session, user_id=user.id, plan_id=plan.id
            )
            await session.commit()

            q = QuotaEnforcementService(session)
            res = await q.consume_job_post_quota_idempotent(
                user_id=user.id,
                job_id=uuid.uuid4(),
            )
            await session.commit()
            assert res.used == 1
            await session.refresh(sub_personal)
            assert sub_personal.job_posts_used == 1

            usage = await session.scalar(
                select(SubscriptionUsage).where(
                    SubscriptionUsage.subscription_id == sub_personal.id
                )
            )
            assert usage is not None
            assert usage.company_id is None
            assert usage.scope == SubscriptionScope.LEGACY_RECRUITER_PERSONAL

    run_async(_run())


def test_p72_legacy_recruiter_can_use_recruiter_ai_with_personal_quota(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            comp = await _create_company(session)
            rec_profile = RecruiterProfile(
                user_id=user.id,
                company_id=comp.id,
                full_name="Legacy Recruiter",
            )
            plan = await _create_plan(session, max_candidate_searches=10)
            sub = await _create_personal_subscription(
                session, user_id=user.id, plan_id=plan.id
            )
            session.add(rec_profile)
            await session.commit()
            sub_id = sub.id

        client = await _make_jwt_client_for_user(user)
        try:
            with patch(
                "app.services.semantic_search_service.SemanticSearchService.search_candidates",
                new_callable=AsyncMock,
            ) as mock_search:
                mock_search.return_value = []
                resp = await client.get(
                    f"{API_V1}/ai/search/candidates",
                    params={"q": "Python", "limit": 5},
                )
                assert resp.status_code == 200, resp.text
        finally:
            await client.aclose()

        async with async_session_factory() as check:
            s = await check.get(Subscription, sub_id)
            assert s.candidate_searches_used == 1

    run_async(_run())


def test_p73_recruiter_without_active_membership_cannot_use_ai_endpoints_403(
    run_async,
):
    """P73: Recruiter without active membership cannot use Recruiter AI endpoints through personal quota when company is Workspace-managed."""
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            comp = await _create_company(session)
            admin = await _create_user(session)
            await _create_membership(
                session,
                company_id=comp.id,
                user_id=admin.id,
                role=MembershipRole.ADMIN,
            )
            rec_profile = RecruiterProfile(
                user_id=user.id,
                company_id=comp.id,
                full_name="Recruiter Without Active Membership",
            )
            plan = await _create_plan(session, max_candidate_searches=10)
            sub = await _create_personal_subscription(
                session, user_id=user.id, plan_id=plan.id
            )
            session.add(rec_profile)
            await session.commit()
            comp_id = comp.id
            sub_id = sub.id

        client = await _make_jwt_client_for_user(user)
        try:
            # 1. Calling with X-Company-ID for workspace company caller doesn't belong to -> 403
            resp_header = await client.get(
                f"{API_V1}/ai/search/candidates",
                headers={"X-Company-ID": str(comp_id)},
                params={"q": "Python", "limit": 5},
            )
            assert resp_header.status_code == 403

            # 2. Calling without header cannot bypass: profile points to workspace company without active membership -> 403
            resp_no_header = await client.get(
                f"{API_V1}/ai/search/candidates",
                params={"q": "Python", "limit": 5},
            )
            assert resp_no_header.status_code == 403
        finally:
            await client.aclose()

        async with async_session_factory() as check:
            s = await check.get(Subscription, sub_id)
            assert s.candidate_searches_used == 0

    run_async(_run())


def test_p74_revoked_workspace_member_cannot_bypass_revocation_omitting_header_403(
    run_async,
):
    """P74: Revoked Workspace member cannot bypass revocation through Recruiter AI endpoints by omitting X-Company-ID."""
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            comp = await _create_company(session)
            await _create_membership(
                session,
                company_id=comp.id,
                user_id=user.id,
                role=MembershipRole.RECRUITER,
                status=MembershipStatus.REVOKED,
            )
            rec_profile = RecruiterProfile(
                user_id=user.id,
                company_id=comp.id,
                full_name="Revoked Recruiter",
            )
            plan = await _create_plan(session, max_candidate_searches=10)
            sub = await _create_personal_subscription(
                session, user_id=user.id, plan_id=plan.id
            )
            session.add(rec_profile)
            await session.commit()
            sub_id = sub.id

        client = await _make_jwt_client_for_user(user)
        try:
            resp = await client.get(
                f"{API_V1}/ai/search/candidates",
                params={"q": "Python", "limit": 5},
            )
            assert resp.status_code == 403
        finally:
            await client.aclose()

        async with async_session_factory() as check:
            s = await check.get(Subscription, sub_id)
            assert s.candidate_searches_used == 0

    run_async(_run())


def test_p75_legacy_recruiter_cannot_access_workspace_company_job_for_ai_recommend(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            admin_user = await _create_user(session)
            legacy_user = await _create_user(session)
            comp = await _create_company(session)
            await _create_membership(
                session,
                company_id=comp.id,
                user_id=admin_user.id,
                role=MembershipRole.ADMIN,
            )
            job = Job(
                company_id=comp.id,
                title="Workspace Job",
                description="Desc",
                job_type=JobType.FULL_TIME,
                workplace_type=WorkplaceType.REMOTE,
                status=JobStatus.PUBLISHED,
            )
            session.add(job)
            await session.commit()
            job_id = job.id

        client = await _make_jwt_client_for_user(legacy_user)
        try:
            resp = await client.get(
                f"{API_V1}/ai/recommendations/candidates",
                params={"job_id": str(job_id), "limit": 5},
            )
            assert resp.status_code == 403
        finally:
            await client.aclose()

    run_async(_run())


def test_p76_successful_recruiter_ai_transitions_usage_reserved_to_completed_once(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            comp = await _create_company(session)
            await _create_membership(
                session,
                company_id=comp.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session, max_candidate_searches=10)
            sub = await _create_company_subscription(
                session,
                company_id=comp.id,
                user_id=user.id,
                plan_id=plan.id,
            )
            await session.commit()
            comp_id = comp.id
            sub_id = sub.id

        client = await _make_jwt_client_for_user(user)
        try:
            with patch(
                "app.services.semantic_search_service.SemanticSearchService.search_candidates",
                new_callable=AsyncMock,
            ) as mock_search:
                mock_search.return_value = []
                resp = await client.get(
                    f"{API_V1}/ai/search/candidates",
                    headers={"X-Company-ID": str(comp_id)},
                    params={"q": "Python", "limit": 5},
                )
                assert resp.status_code == 200
        finally:
            await client.aclose()

        async with async_session_factory() as check:
            sub_chk = await check.get(Subscription, sub_id)
            assert sub_chk.candidate_searches_used == 1
            usage = await check.scalar(
                select(SubscriptionUsage).where(
                    SubscriptionUsage.subscription_id == sub_id
                )
            )
            assert usage.status == SubscriptionUsageStatus.COMPLETED
            assert usage.finalized_at is not None
            count = await check.scalar(
                select(func.count())
                .select_from(SubscriptionUsage)
                .where(SubscriptionUsage.subscription_id == sub_id)
            )
            assert count == 1

    run_async(_run())


def test_p77_failed_recruiter_ai_releases_reservation_and_restores_counter(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            comp = await _create_company(session)
            await _create_membership(
                session,
                company_id=comp.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session, max_candidate_searches=10)
            sub = await _create_company_subscription(
                session,
                company_id=comp.id,
                user_id=user.id,
                plan_id=plan.id,
            )
            await session.commit()
            comp_id = comp.id
            sub_id = sub.id

        client = await _make_jwt_client_for_user(user)
        try:
            with patch(
                "app.services.semantic_search_service.SemanticSearchService.search_candidates",
                side_effect=RuntimeError("AI search service exploded"),
            ):
                resp = await client.get(
                    f"{API_V1}/ai/search/candidates",
                    headers={"X-Company-ID": str(comp_id)},
                    params={"q": "Python", "limit": 5},
                )
                assert resp.status_code == 500
        finally:
            await client.aclose()

        async with async_session_factory() as check:
            sub_chk = await check.get(Subscription, sub_id)
            assert sub_chk.candidate_searches_used == 0
            usage = await check.scalar(
                select(SubscriptionUsage).where(
                    SubscriptionUsage.subscription_id == sub_id
                )
            )
            assert usage.status == SubscriptionUsageStatus.FAILED
            assert usage.finalized_at is not None
            count = await check.scalar(
                select(func.count())
                .select_from(SubscriptionUsage)
                .where(SubscriptionUsage.subscription_id == sub_id)
            )
            assert count == 1

    run_async(_run())


def test_p79_recruiter_ai_task_cancellation_triggers_canonical_quota_release(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            comp = await _create_company(session)
            await _create_membership(
                session,
                company_id=comp.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session, max_candidate_searches=10)
            sub = await _create_company_subscription(
                session,
                company_id=comp.id,
                user_id=user.id,
                plan_id=plan.id,
            )
            await session.commit()
            comp_id = comp.id
            sub_id = sub.id

        client = await _make_jwt_client_for_user(user)
        try:
            with patch(
                "app.services.semantic_search_service.SemanticSearchService.search_candidates",
                side_effect=asyncio.CancelledError(),
            ):
                with pytest.raises((asyncio.CancelledError, RuntimeError)):
                    await client.get(
                        f"{API_V1}/ai/search/candidates",
                        headers={"X-Company-ID": str(comp_id)},
                        params={"q": "Python", "limit": 5},
                    )
        finally:
            await client.aclose()

        async with async_session_factory() as check:
            sub_chk = await check.get(Subscription, sub_id)
            assert sub_chk.candidate_searches_used == 0
            usage = await check.scalar(
                select(SubscriptionUsage).where(
                    SubscriptionUsage.subscription_id == sub_id
                )
            )
            assert usage.status == SubscriptionUsageStatus.FAILED
            assert usage.finalized_at is not None
            count = await check.scalar(
                select(func.count())
                .select_from(SubscriptionUsage)
                .where(SubscriptionUsage.subscription_id == sub_id)
            )
            assert count == 1

    run_async(_run())
