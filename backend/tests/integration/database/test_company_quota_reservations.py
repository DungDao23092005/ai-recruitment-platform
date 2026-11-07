"""Wave 1.4 Phase 2 — Company Quota Reservations, Idempotency & Release integration tests.

Scenarios:
- P41: Session begin nested rolls back CAS on collision preserving outer tx
- P42: Same idempotency key reloads winning usage without double deduction
- P43: Same idempotency key with different reference_id raises 409
- P44: Same idempotency key with different acting user_id raises 409
- P45: Same idempotency key with different feature_type or amount raises 409
- P46: Reusing idempotency key whose usage row is FAILED raises 409
- P47: Revocation commits first, subsequent reservation select receives 403
- P48: Reservation locks first, concurrent revocation serializes
- P49: No unauthorized new reservations succeed after revocation commits
- P50: Actual SQL Server OUTPUT INSERTED executes and retrieves updated row
- P51: Release transitions usage RESERVED to FAILED, never consumed
- P52: Successful finalization transitions RESERVED to COMPLETED
- P53: Subscription counter decrements by exact released amount
- P54: Counter decrement failure rolls back complete transaction
- P55: Quota reconciliation worker reconciles stale reservations
- P78: Repeated release calls do not restore quota twice (idempotent release)
- A03: Repeated job publication via consume_job_post_quota_idempotent is idempotent
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import uuid

import pytest
from sqlalchemy import func, select, text, update

from app.core.exceptions import ConflictException, ForbiddenException
from app.database.session import async_session_factory
from app.domain.enums import (
    MembershipRole,
    MembershipStatus,
    SubscriptionScope,
    SubscriptionUsageFeatureType,
    SubscriptionUsageStatus,
)
from app.domain.models.base import utc_now
from app.models import (
    CompanyMembership,
    RecruiterProfile,
    Subscription,
    SubscriptionUsage,
)
from app.services.quota_enforcement_service import QuotaEnforcementService
from app.services.quota_reconciliation_worker import QuotaReconciliationWorker
from tests.integration.company_billing_helpers import (
    _create_company,
    _create_company_subscription,
    _create_membership,
    _create_plan,
    _create_user,
)

pytestmark = pytest.mark.integration


def test_p41_session_begin_nested_rolls_back_cas_on_collision_preserving_outer(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session, max_candidate_searches=10)
            sub = await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
                max_candidate_searches=10,
            )
            await session.commit()
            user_id, company_id, sub_id = user.id, company.id, sub.id

        key = f"idem-{uuid.uuid4().hex}"

        # First reservation succeeds
        async with async_session_factory() as s1:
            q1 = QuotaEnforcementService(s1)
            r1 = await q1.reserve_search_quota(
                user_id=user_id,
                company_id=company_id,
                idempotency_key=key,
            )
            await s1.commit()
            assert r1.usage_id is not None

        # Second reservation in an outer transaction encounters the existing row,
        # rolls back nested CAS attempt, preserves outer transaction, and returns the winner row
        async with async_session_factory() as s2:
            q2 = QuotaEnforcementService(s2)
            r2 = await q2.reserve_search_quota(
                user_id=user_id,
                company_id=company_id,
                idempotency_key=key,
            )
            # Outer session can perform further writes without rollback failure
            s2.add(
                RecruiterProfile(
                    user_id=user_id,
                    company_id=company_id,
                    full_name="Outer Tx User",
                )
            )
            await s2.commit()
            assert r2.usage_id == r1.usage_id

        async with async_session_factory() as check:
            sub_check = await check.get(Subscription, sub_id)
            assert sub_check.candidate_searches_used == 1

    run_async(_run())


def test_p42_same_idempotency_key_reloads_winning_usage_without_double_deduction(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session, max_candidate_searches=10)
            sub = await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
                max_candidate_searches=10,
            )
            await session.commit()
            user_id, company_id, sub_id = user.id, company.id, sub.id

        key = f"idem-search-{uuid.uuid4().hex}"
        async with async_session_factory() as s1:
            q1 = QuotaEnforcementService(s1)
            r1 = await q1.reserve_search_quota(
                user_id=user_id,
                company_id=company_id,
                idempotency_key=key,
            )
            await s1.commit()

        async with async_session_factory() as s2:
            q2 = QuotaEnforcementService(s2)
            r2 = await q2.reserve_search_quota(
                user_id=user_id,
                company_id=company_id,
                idempotency_key=key,
            )
            await s2.commit()

        assert r1.usage_id == r2.usage_id

        async with async_session_factory() as check:
            sub_check = await check.get(Subscription, sub_id)
            assert sub_check.candidate_searches_used == 1
            count = await check.scalar(
                select(func.count())
                .select_from(SubscriptionUsage)
                .where(SubscriptionUsage.idempotency_key == key)
            )
            assert count == 1

    run_async(_run())


def test_p43_same_idempotency_key_with_different_reference_id_raises_409(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session, max_candidate_searches=10)
            await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
            )
            await session.commit()
            user_id, company_id = user.id, company.id

        key = f"idem-ref-{uuid.uuid4().hex}"
        ref_a = uuid.uuid4()
        ref_b = uuid.uuid4()

        async with async_session_factory() as s1:
            q1 = QuotaEnforcementService(s1)
            await q1.reserve_search_quota(
                user_id=user_id,
                company_id=company_id,
                idempotency_key=key,
                reference_id=ref_a,
            )
            await s1.commit()

        async with async_session_factory() as s2:
            q2 = QuotaEnforcementService(s2)
            with pytest.raises(ConflictException):
                await q2.reserve_search_quota(
                    user_id=user_id,
                    company_id=company_id,
                    idempotency_key=key,
                    reference_id=ref_b,
                )

    run_async(_run())


def test_p44_same_idempotency_key_with_different_acting_user_id_raises_409(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user_a = await _create_user(session)
            user_b = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user_a.id,
                role=MembershipRole.ADMIN,
            )
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user_b.id,
                role=MembershipRole.RECRUITER,
            )
            plan = await _create_plan(session, max_candidate_searches=10)
            await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user_a.id,
                plan_id=plan.id,
            )
            await session.commit()
            user_a_id, user_b_id, company_id = user_a.id, user_b.id, company.id

        key = f"idem-user-{uuid.uuid4().hex}"
        async with async_session_factory() as s1:
            q1 = QuotaEnforcementService(s1)
            await q1.reserve_search_quota(
                user_id=user_a_id,
                company_id=company_id,
                idempotency_key=key,
            )
            await s1.commit()

        async with async_session_factory() as s2:
            q2 = QuotaEnforcementService(s2)
            with pytest.raises(ConflictException):
                await q2.reserve_search_quota(
                    user_id=user_b_id,
                    company_id=company_id,
                    idempotency_key=key,
                )

    run_async(_run())


def test_p45_same_idempotency_key_with_different_feature_type_or_amount_raises_409(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(
                session, max_candidate_searches=10, max_ai_features=10
            )
            await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
            )
            await session.commit()
            user_id, company_id = user.id, company.id

        key = f"idem-feature-{uuid.uuid4().hex}"
        async with async_session_factory() as s1:
            q1 = QuotaEnforcementService(s1)
            await q1.reserve_search_quota(
                user_id=user_id,
                company_id=company_id,
                idempotency_key=key,
            )
            await s1.commit()

        async with async_session_factory() as s2:
            q2 = QuotaEnforcementService(s2)
            with pytest.raises(ConflictException):
                await q2.reserve_ai_quota(
                    user_id=user_id,
                    company_id=company_id,
                    idempotency_key=key,
                )

    run_async(_run())


def test_p46_reusing_idempotency_key_whose_usage_row_is_failed_raises_409(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session, max_candidate_searches=10)
            await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
            )
            await session.commit()
            user_id, company_id = user.id, company.id

        key = f"idem-failed-{uuid.uuid4().hex}"
        async with async_session_factory() as s1:
            q1 = QuotaEnforcementService(s1)
            r1 = await q1.reserve_search_quota(
                user_id=user_id,
                company_id=company_id,
                idempotency_key=key,
            )
            await s1.commit()
            usage_id = r1.usage_id

        # Release reservation transitions it to FAILED
        async with async_session_factory() as s_rel:
            q_rel = QuotaEnforcementService(s_rel)
            released = await q_rel.release_reservation(usage_id)
            await s_rel.commit()
            assert released is True

        # Reusing the idempotency key whose usage row is FAILED must raise 409 Conflict
        async with async_session_factory() as s2:
            q2 = QuotaEnforcementService(s2)
            with pytest.raises(ConflictException):
                await q2.reserve_search_quota(
                    user_id=user_id,
                    company_id=company_id,
                    idempotency_key=key,
                )

    run_async(_run())


def test_p47_revocation_commits_first_subsequent_reservation_select_receives_403(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            membership = await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.RECRUITER,
                status=MembershipStatus.ACTIVE,
            )
            plan = await _create_plan(session, max_candidate_searches=10)
            await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
            )
            await session.commit()
            user_id, company_id, membership_id = (
                user.id,
                company.id,
                membership.id,
            )

        # Revoke membership and commit
        async with async_session_factory() as s_rev:
            m = await s_rev.get(CompanyMembership, membership_id)
            m.status = MembershipStatus.REVOKED
            await s_rev.commit()

        # Subsequent reservation attempt receives 403
        async with async_session_factory() as s_res:
            q = QuotaEnforcementService(s_res)
            with pytest.raises(ForbiddenException):
                await q.reserve_search_quota(
                    user_id=user_id,
                    company_id=company_id,
                    idempotency_key=f"rev-{uuid.uuid4()}",
                )

    run_async(_run())


def test_p48_reservation_locks_first_concurrent_revocation_serializes(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            membership = await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.RECRUITER,
                status=MembershipStatus.ACTIVE,
            )
            plan = await _create_plan(session, max_candidate_searches=10)
            await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
            )
            await session.commit()
            user_id, company_id, membership_id = (
                user.id,
                company.id,
                membership.id,
            )

        # In Session 1: acquire membership lock
        async with async_session_factory() as s1:
            q1 = QuotaEnforcementService(s1)
            await q1._verify_and_lock_company_membership(user_id, company_id)

            # In Session 2: attempt to revoke membership with a short timeout -> blocks or detects lock
            async with async_session_factory() as s2:
                # Setting lock timeout ensures fast verification that row is locked
                await s2.execute(text("SET LOCK_TIMEOUT 100"))
                with pytest.raises(Exception):
                    await s2.execute(
                        text(
                            "UPDATE company_memberships SET status = 'revoked' WHERE id = :id"
                        ),
                        {"id": membership_id},
                    )

            # Commit s1
            await s1.commit()

    run_async(_run())


def test_p49_no_unauthorized_new_reservations_succeed_after_revocation_commits(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            membership = await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.RECRUITER,
                status=MembershipStatus.ACTIVE,
            )
            plan = await _create_plan(
                session, max_candidate_searches=10, max_ai_features=10
            )
            await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
            )
            await session.commit()
            user_id, company_id, membership_id = (
                user.id,
                company.id,
                membership.id,
            )

        # Revocation commits
        async with async_session_factory() as s_rev:
            m = await s_rev.get(CompanyMembership, membership_id)
            m.status = MembershipStatus.REVOKED
            await s_rev.commit()

        # Both search and AI reservations must be forbidden
        async with async_session_factory() as s_chk:
            q = QuotaEnforcementService(s_chk)
            with pytest.raises(ForbiddenException):
                await q.reserve_search_quota(
                    user_id=user_id,
                    company_id=company_id,
                    idempotency_key=f"rev-s-{uuid.uuid4()}",
                )
            with pytest.raises(ForbiddenException):
                await q.reserve_ai_quota(
                    user_id=user_id,
                    company_id=company_id,
                    idempotency_key=f"rev-ai-{uuid.uuid4()}",
                )

    run_async(_run())


def test_p50_actual_sql_server_output_inserted_executes_and_retrieves_updated_row(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session, max_candidate_searches=10)
            sub = await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
            )
            await session.commit()
            user_id, company_id, sub_id = user.id, company.id, sub.id

        async with async_session_factory() as s_res:
            q = QuotaEnforcementService(s_res)
            res = await q.reserve_search_quota(
                user_id=user_id,
                company_id=company_id,
                idempotency_key=f"out-{uuid.uuid4()}",
            )
            await s_res.commit()
            usage_id = res.usage_id

        async with async_session_factory() as s_rel:
            q = QuotaEnforcementService(s_rel)
            released = await q.release_reservation(usage_id)
            await s_rel.commit()
            assert released is True

        async with async_session_factory() as check:
            usage = await check.get(SubscriptionUsage, usage_id)
            assert usage.status == SubscriptionUsageStatus.FAILED
            assert usage.finalized_at is not None

    run_async(_run())


def test_p51_release_transitions_usage_reserved_to_failed_never_consumed(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session, max_candidate_searches=10)
            await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
            )
            await session.commit()
            user_id, company_id = user.id, company.id

        async with async_session_factory() as s:
            q = QuotaEnforcementService(s)
            res = await q.reserve_search_quota(
                user_id=user_id,
                company_id=company_id,
                idempotency_key=f"fail-{uuid.uuid4()}",
            )
            await s.commit()
            usage_id = res.usage_id

        async with async_session_factory() as s:
            q = QuotaEnforcementService(s)
            await q.release_reservation(usage_id)
            await s.commit()

        async with async_session_factory() as check:
            row = (
                await check.execute(
                    text("SELECT status FROM subscription_usages WHERE id = :id"),
                    {"id": usage_id},
                )
            ).first()
            raw_status = str(row[0]).lower()
            assert raw_status == "failed"
            assert "consumed" not in raw_status

    run_async(_run())


def test_p52_successful_finalization_transitions_reserved_to_completed(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session, max_candidate_searches=10)
            await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
            )
            await session.commit()
            user_id, company_id = user.id, company.id

        async with async_session_factory() as s:
            q = QuotaEnforcementService(s)
            res = await q.reserve_search_quota(
                user_id=user_id,
                company_id=company_id,
                idempotency_key=f"fin-{uuid.uuid4()}",
            )
            await s.commit()
            usage_id = res.usage_id

        async with async_session_factory() as s:
            q = QuotaEnforcementService(s)
            await q.finalize_reservation(usage_id, success=True)
            await s.commit()

        async with async_session_factory() as check:
            usage = await check.get(SubscriptionUsage, usage_id)
            assert usage.status == SubscriptionUsageStatus.COMPLETED
            assert usage.finalized_at is not None

    run_async(_run())


def test_p53_subscription_counter_decrements_by_exact_released_amount(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session, max_candidate_searches=10)
            sub = await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
            )
            await session.commit()
            user_id, company_id, sub_id = user.id, company.id, sub.id

        async with async_session_factory() as s:
            q = QuotaEnforcementService(s)
            res = await q.reserve_search_quota(
                user_id=user_id,
                company_id=company_id,
                idempotency_key=f"dec-{uuid.uuid4()}",
            )
            await s.commit()
            usage_id = res.usage_id

        async with async_session_factory() as check1:
            s_row = await check1.get(Subscription, sub_id)
            assert s_row.candidate_searches_used == 1

        async with async_session_factory() as s:
            q = QuotaEnforcementService(s)
            await q.release_reservation(usage_id)
            await s.commit()

        async with async_session_factory() as check2:
            s_row = await check2.get(Subscription, sub_id)
            assert s_row.candidate_searches_used == 0

    run_async(_run())


def test_p54_counter_decrement_failure_rolls_back_complete_transaction(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session, max_candidate_searches=10)
            sub = await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
            )
            await session.commit()
            user_id, company_id, sub_id = user.id, company.id, sub.id

        async with async_session_factory() as s:
            q = QuotaEnforcementService(s)
            res = await q.reserve_search_quota(
                user_id=user_id,
                company_id=company_id,
                idempotency_key=f"roll-{uuid.uuid4()}",
            )
            await s.commit()
            usage_id = res.usage_id

        # Artificially set subscription counter to 0 so the decrement query finds rowcount == 0
        async with async_session_factory() as s:
            await s.execute(
                update(Subscription)
                .where(Subscription.id == sub_id)
                .values(candidate_searches_used=0)
            )
            await s.commit()

        async with async_session_factory() as s:
            q = QuotaEnforcementService(s)
            with pytest.raises(RuntimeError, match="Cannot safely decrement"):
                await q.release_reservation(usage_id)

        # After rollback, the usage status should still be RESERVED
        async with async_session_factory() as check:
            usage = await check.get(SubscriptionUsage, usage_id)
            assert usage.status == SubscriptionUsageStatus.RESERVED

    run_async(_run())


def test_p55_quota_reconciliation_worker_reconciles_stale_reservations(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            plan = await _create_plan(session, max_candidate_searches=10)
            sub = await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
                candidate_searches_used=1,
            )
            now = utc_now()
            stale_usage = SubscriptionUsage(
                subscription_id=sub.id,
                user_id=user.id,
                company_id=company.id,
                scope=SubscriptionScope.COMPANY_RECRUITING,
                feature_type=SubscriptionUsageFeatureType.CANDIDATE_SEARCH,
                status=SubscriptionUsageStatus.RESERVED,
                amount=1,
                idempotency_key=f"stale-{uuid.uuid4()}",
                created_at=now - timedelta(minutes=60),
                updated_at=now - timedelta(minutes=60),
            )
            session.add(stale_usage)
            await session.commit()
            sub_id, usage_id = sub.id, stale_usage.id

        worker = QuotaReconciliationWorker(
            max_age_minutes=15,
            batch_size=10,
        )
        result = await worker.run_once()
        assert result["reconciled"] >= 1

        async with async_session_factory() as check:
            u = await check.get(SubscriptionUsage, usage_id)
            s = await check.get(Subscription, sub_id)
            assert u.status == SubscriptionUsageStatus.FAILED
            assert s.candidate_searches_used == 0

    run_async(_run())


def test_p78_repeated_release_calls_do_not_restore_quota_twice(run_async):
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
            user_id, comp_id, sub_id = user.id, comp.id, sub.id

        async with async_session_factory() as s:
            q = QuotaEnforcementService(s)
            res = await q.reserve_search_quota(
                user_id=user_id,
                company_id=comp_id,
                idempotency_key=f"rep-{uuid.uuid4()}",
            )
            await s.commit()
            usage_id = res.usage_id

        # First release returns True
        async with async_session_factory() as s1:
            q1 = QuotaEnforcementService(s1)
            rel1 = await q1.release_reservation(usage_id)
            await s1.commit()
            assert rel1 is True

        # Second release returns False (no-op)
        async with async_session_factory() as s2:
            q2 = QuotaEnforcementService(s2)
            rel2 = await q2.release_reservation(usage_id)
            await s2.commit()
            assert rel2 is False

        async with async_session_factory() as check:
            sub_chk = await check.get(Subscription, sub_id)
            assert sub_chk.candidate_searches_used == 0

    run_async(_run())


def test_a03_repeated_job_publication_does_not_double_debit_quota(run_async):
    """A03: Publishing the same job twice via consume_job_post_quota_idempotent is idempotent."""
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            await _create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await _create_plan(session, max_job_posts=5)
            sub = await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
            )
            await session.commit()
            user_id, company_id, sub_id = user.id, company.id, sub.id

        job_id = uuid.uuid4()
        async with async_session_factory() as s1:
            q1 = QuotaEnforcementService(s1)
            res1 = await q1.consume_job_post_quota_idempotent(
                user_id=user_id,
                company_id=company_id,
                job_id=job_id,
            )
            await s1.commit()
            assert res1.used == 1

        async with async_session_factory() as s2:
            q2 = QuotaEnforcementService(s2)
            res2 = await q2.consume_job_post_quota_idempotent(
                user_id=user_id,
                company_id=company_id,
                job_id=job_id,
            )
            await s2.commit()
            assert res2.used == 1

        async with async_session_factory() as check:
            s = await check.get(Subscription, sub_id)
            assert s.job_posts_used == 1

    run_async(_run())
