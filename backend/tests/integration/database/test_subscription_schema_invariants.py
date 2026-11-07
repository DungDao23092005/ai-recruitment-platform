"""Subscription schema, constraint, index, and migration verification tests.

Runs strictly against the isolated test database (``ai_recruitment_platform_test``).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import app.models  # noqa: F401
from app.core.security import get_password_hash
from app.database.session import async_session_factory, engine
from app.domain.enums import (
    CompanySize,
    PaymentOrderStatus,
    PaymentProvider,
    PlanAudience,
    SubscriptionScope,
    SubscriptionStatus,
    SubscriptionUsageFeatureType,
    SubscriptionUsageStatus,
    UserRole,
)
from app.models import (
    Company,
    PaymentOrder,
    RecruitmentPlan,
    Subscription,
    SubscriptionUsage,
    User,
)
from tests.integration.conftest import _assert_not_development_database


def _load_subscription_migration_module():
    migration_path = (
        Path(__file__).resolve().parents[3]
        / "alembic"
        / "versions"
        / "wave1_4_subscriptions.py"
    )
    spec = importlib.util.spec_from_file_location("wave1_4_subscriptions", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _seed_user_company_and_plan(session) -> tuple[User, Company, RecruitmentPlan]:
    user = User(
        email=f"user-{uuid.uuid4()}@example.com",
        password_hash=get_password_hash("Password123!"),
        role=UserRole.RECRUITER,
        is_active=True,
    )
    company = Company(
        name=f"Company {uuid.uuid4()}",
        slug=f"company-{uuid.uuid4()}",
        tax_code=str(uuid.uuid4())[:18],
        size=CompanySize.SME,
    )
    plan = RecruitmentPlan(
        name=f"Plan {uuid.uuid4()}",
        price=500000,
        currency="VND",
        duration_days=30,
        max_job_posts=10,
        max_candidate_searches=50,
        max_ai_features=20,
        is_active=True,
        display_order=1,
    )
    session.add_all([user, company, plan])
    await session.flush()
    return user, company, plan


def test_orm_transitional_defaults_on_flush_and_commit(run_async):
    """Existing constructors that omit Wave 1.4 fields must persist transitional defaults."""

    async def _exercise():
        async with async_session_factory() as session:
            user, _, plan = await _seed_user_company_and_plan(session)

            # RecruitmentPlan constructed without plan_audience or is_free
            assert plan.plan_audience == PlanAudience.COMPANY
            assert plan.is_free is False

            # Subscription constructed without scope, company_id, is_free, current_period_key
            subscription = Subscription(
                user_id=user.id,
                plan_id=plan.id,
                status=SubscriptionStatus.PENDING,
            )
            session.add(subscription)
            await session.flush()

            assert subscription.scope == SubscriptionScope.LEGACY_RECRUITER_PERSONAL
            assert subscription.company_id is None
            assert subscription.is_free is False
            assert subscription.current_period_key is None

            # PaymentOrder constructed without scope or company_id
            order = PaymentOrder(
                user_id=user.id,
                plan_id=plan.id,
                subscription_id=subscription.id,
                amount=plan.price,
                currency="VND",
                provider=PaymentProvider.MOMO,
                internal_order_id=f"ORD-{uuid.uuid4()}",
                status=PaymentOrderStatus.PENDING,
            )
            session.add(order)
            await session.flush()

            assert order.scope == SubscriptionScope.LEGACY_RECRUITER_PERSONAL
            assert order.company_id is None

            # SubscriptionUsage constructed without scope, company_id, period_key
            usage = SubscriptionUsage(
                subscription_id=subscription.id,
                user_id=user.id,
                feature_type=SubscriptionUsageFeatureType.JOB_POST,
                status=SubscriptionUsageStatus.COMPLETED,
                amount=1,
            )
            session.add(usage)
            await session.commit()

            await session.refresh(plan)
            await session.refresh(subscription)
            await session.refresh(order)
            await session.refresh(usage)

            assert plan.plan_audience == PlanAudience.COMPANY
            assert plan.is_free is False
            assert subscription.scope == SubscriptionScope.LEGACY_RECRUITER_PERSONAL
            assert order.scope == SubscriptionScope.LEGACY_RECRUITER_PERSONAL
            assert usage.scope == SubscriptionScope.LEGACY_RECRUITER_PERSONAL

    run_async(_exercise())


def test_recruitment_plan_check_constraints_and_filtered_unique_index(run_async):
    """Verify recruitment_plans check constraints and single active candidate free plan index."""

    async def _exercise():
        # 1. Invalid plan_audience rejected by ck_recruitment_plans_audience
        async with async_session_factory() as session:
            with pytest.raises(IntegrityError):
                await session.execute(
                    text(
                        """
                        INSERT INTO recruitment_plans (
                            id, name, price, currency, duration_days, max_job_posts,
                            plan_audience, is_free, is_active, display_order,
                            created_at, updated_at, is_deleted
                        ) VALUES (
                            :id, 'Bad Plan', 0, 'VND', 30, 0,
                            'invalid_audience', 0, 1, 0,
                            SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET(), 0
                        )
                        """
                    ),
                    {"id": uuid.uuid4()},
                )
            await session.rollback()

        # 2. Free company plan rejected by ck_recruitment_plans_free_candidate
        async with async_session_factory() as session:
            bad_company_free = RecruitmentPlan(
                name="Invalid Free Company Plan",
                price=0,
                currency="VND",
                duration_days=30,
                max_job_posts=1,
                plan_audience=PlanAudience.COMPANY,
                is_free=True,
                is_active=True,
                display_order=0,
            )
            session.add(bad_company_free)
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

        # 3. Single active candidate free plan enforced by uq_recruitment_plans_active_candidate_free
        async with async_session_factory() as session:
            free_plan_1 = RecruitmentPlan(
                name="Candidate Free Tier",
                price=0,
                currency="VND",
                duration_days=30,
                max_job_posts=0,
                max_ai_features=3,
                plan_audience=PlanAudience.CANDIDATE,
                is_free=True,
                is_active=True,
                display_order=0,
            )
            inactive_free_plan = RecruitmentPlan(
                name="Archived Candidate Free Tier",
                price=0,
                currency="VND",
                duration_days=30,
                max_job_posts=0,
                plan_audience=PlanAudience.CANDIDATE,
                is_free=True,
                is_active=False,
                display_order=1,
            )
            paid_candidate_1 = RecruitmentPlan(
                name="Candidate Pro Monthly",
                price=99000,
                currency="VND",
                duration_days=30,
                max_job_posts=0,
                plan_audience=PlanAudience.CANDIDATE,
                is_free=False,
                is_active=True,
                display_order=2,
            )
            paid_candidate_2 = RecruitmentPlan(
                name="Candidate Pro Yearly",
                price=990000,
                currency="VND",
                duration_days=365,
                max_job_posts=0,
                plan_audience=PlanAudience.CANDIDATE,
                is_free=False,
                is_active=True,
                display_order=3,
            )
            session.add_all(
                [free_plan_1, inactive_free_plan, paid_candidate_1, paid_candidate_2]
            )
            await session.commit()

            duplicate_active_free = RecruitmentPlan(
                name="Duplicate Active Candidate Free Tier",
                price=0,
                currency="VND",
                duration_days=30,
                max_job_posts=0,
                plan_audience=PlanAudience.CANDIDATE,
                is_free=True,
                is_active=True,
                display_order=4,
            )
            session.add(duplicate_active_free)
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

    run_async(_exercise())


def test_subscription_payment_and_usage_check_constraints(run_async):
    """Verify scope validity, (scope, company_id) pairing, free-candidate constraint, and user_id NOT NULL."""

    async def _exercise():
        async with async_session_factory() as session:
            user, company, plan = await _seed_user_company_and_plan(session)
            valid_sub = Subscription(
                user_id=user.id,
                plan_id=plan.id,
                scope=SubscriptionScope.LEGACY_RECRUITER_PERSONAL,
                status=SubscriptionStatus.ACTIVE,
            )
            session.add(valid_sub)
            await session.commit()

            user_id = user.id
            company_id = company.id
            plan_id = plan.id
            sub_id = valid_sub.id

        # 1. company_recruiting without company_id -> fails ck_subscriptions_scope_company_pairing
        async with async_session_factory() as session:
            session.add(
                Subscription(
                    user_id=user_id,
                    company_id=None,
                    plan_id=plan_id,
                    scope=SubscriptionScope.COMPANY_RECRUITING,
                    status=SubscriptionStatus.PENDING,
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

        # 2. candidate_personal with company_id -> fails ck_subscriptions_scope_company_pairing
        async with async_session_factory() as session:
            session.add(
                Subscription(
                    user_id=user_id,
                    company_id=company_id,
                    plan_id=plan_id,
                    scope=SubscriptionScope.CANDIDATE_PERSONAL,
                    status=SubscriptionStatus.PENDING,
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

        # 3. legacy_recruiter_personal with company_id -> fails ck_subscriptions_scope_company_pairing
        async with async_session_factory() as session:
            session.add(
                Subscription(
                    user_id=user_id,
                    company_id=company_id,
                    plan_id=plan_id,
                    scope=SubscriptionScope.LEGACY_RECRUITER_PERSONAL,
                    status=SubscriptionStatus.PENDING,
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

        # 4. is_free=True on company_recruiting -> fails ck_subscriptions_free_candidate
        async with async_session_factory() as session:
            session.add(
                Subscription(
                    user_id=user_id,
                    company_id=company_id,
                    plan_id=plan_id,
                    scope=SubscriptionScope.COMPANY_RECRUITING,
                    is_free=True,
                    status=SubscriptionStatus.PENDING,
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

        # 5. payment_orders invalid (scope, company_id) pairing -> fails ck_payment_orders_scope_company_pairing
        async with async_session_factory() as session:
            session.add(
                PaymentOrder(
                    user_id=user_id,
                    company_id=None,
                    plan_id=plan_id,
                    subscription_id=sub_id,
                    scope=SubscriptionScope.COMPANY_RECRUITING,
                    amount=100000,
                    currency="VND",
                    provider=PaymentProvider.MOMO,
                    internal_order_id=f"ORD-{uuid.uuid4()}",
                    status=PaymentOrderStatus.PENDING,
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

        # 6. subscription_usages invalid (scope, company_id) pairing -> fails ck_subscription_usages_scope_company_pairing
        async with async_session_factory() as session:
            session.add(
                SubscriptionUsage(
                    subscription_id=sub_id,
                    user_id=user_id,
                    company_id=None,
                    scope=SubscriptionScope.COMPANY_RECRUITING,
                    feature_type=SubscriptionUsageFeatureType.RECRUITING_AI,
                    status=SubscriptionUsageStatus.RESERVED,
                    amount=1,
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

        # 7. user_id IS NULL rejected on subscriptions, payment_orders, subscription_usages
        for sql in (
            """
            INSERT INTO subscriptions (
                id, user_id, plan_id, scope, is_free, status,
                max_job_posts, max_candidate_searches, max_ai_features,
                job_posts_used, candidate_searches_used, ai_features_used,
                created_at, updated_at, is_deleted
            ) VALUES (
                NEWID(), NULL, :plan_id, 'legacy_recruiter_personal', 0, 'pending',
                0, 0, 0, 0, 0, 0, SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET(), 0
            )
            """,
            """
            INSERT INTO payment_orders (
                id, user_id, plan_id, scope, amount, currency, provider,
                internal_order_id, status, created_at, updated_at, is_deleted
            ) VALUES (
                NEWID(), NULL, :plan_id, 'legacy_recruiter_personal', 1000, 'VND', 'momo',
                :order_id, 'pending', SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET(), 0
            )
            """,
            """
            INSERT INTO subscription_usages (
                id, subscription_id, user_id, scope, feature_type, status, amount,
                created_at, updated_at
            ) VALUES (
                NEWID(), :sub_id, NULL, 'legacy_recruiter_personal', 'job_post', 'reserved', 1,
                SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET()
            )
            """,
        ):
            async with async_session_factory() as session:
                with pytest.raises(IntegrityError):
                    await session.execute(
                        text(sql),
                        {
                            "plan_id": plan_id,
                            "sub_id": sub_id,
                            "order_id": f"ORD-{uuid.uuid4()}",
                        },
                    )
                await session.rollback()

    run_async(_exercise())


def test_subscription_filtered_unique_indexes_and_candidate_free_plus_paid_coexistence(
    run_async,
):
    """Verify company active uniqueness, legacy active uniqueness, and candidate Free + Paid coexistence."""

    async def _exercise():
        async with async_session_factory() as session:
            user, company, plan = await _seed_user_company_and_plan(session)

            # 1. Company active subscription + expired historical company subscription allowed
            active_company_sub = Subscription(
                user_id=user.id,
                company_id=company.id,
                plan_id=plan.id,
                scope=SubscriptionScope.COMPANY_RECRUITING,
                is_free=False,
                status=SubscriptionStatus.ACTIVE,
            )
            expired_company_sub = Subscription(
                user_id=user.id,
                company_id=company.id,
                plan_id=plan.id,
                scope=SubscriptionScope.COMPANY_RECRUITING,
                is_free=False,
                status=SubscriptionStatus.EXPIRED,
            )
            # 2. Candidate active Free + active Paid coexistence for the same user
            active_candidate_free = Subscription(
                user_id=user.id,
                company_id=None,
                plan_id=plan.id,
                scope=SubscriptionScope.CANDIDATE_PERSONAL,
                is_free=True,
                current_period_key="2026-04",
                status=SubscriptionStatus.ACTIVE,
            )
            active_candidate_paid = Subscription(
                user_id=user.id,
                company_id=None,
                plan_id=plan.id,
                scope=SubscriptionScope.CANDIDATE_PERSONAL,
                is_free=False,
                status=SubscriptionStatus.ACTIVE,
            )
            # 3. Legacy active subscription for the user
            active_legacy = Subscription(
                user_id=user.id,
                company_id=None,
                plan_id=plan.id,
                scope=SubscriptionScope.LEGACY_RECRUITER_PERSONAL,
                is_free=False,
                status=SubscriptionStatus.ACTIVE,
            )
            session.add_all(
                [
                    active_company_sub,
                    expired_company_sub,
                    active_candidate_free,
                    active_candidate_paid,
                    active_legacy,
                ]
            )
            await session.commit()

            user_id = user.id
            company_id = company.id
            plan_id = plan.id

        # Duplicate active company subscription -> rejected by uq_subscriptions_active_company
        async with async_session_factory() as session:
            session.add(
                Subscription(
                    user_id=user_id,
                    company_id=company_id,
                    plan_id=plan_id,
                    scope=SubscriptionScope.COMPANY_RECRUITING,
                    is_free=False,
                    status=SubscriptionStatus.ACTIVE,
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

        # Duplicate active candidate free subscription -> rejected by uq_subscriptions_candidate_free
        async with async_session_factory() as session:
            session.add(
                Subscription(
                    user_id=user_id,
                    company_id=None,
                    plan_id=plan_id,
                    scope=SubscriptionScope.CANDIDATE_PERSONAL,
                    is_free=True,
                    current_period_key="2026-04",
                    status=SubscriptionStatus.ACTIVE,
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

        # Duplicate active candidate paid subscription -> rejected by uq_subscriptions_candidate_paid
        async with async_session_factory() as session:
            session.add(
                Subscription(
                    user_id=user_id,
                    company_id=None,
                    plan_id=plan_id,
                    scope=SubscriptionScope.CANDIDATE_PERSONAL,
                    is_free=False,
                    status=SubscriptionStatus.ACTIVE,
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

        # Duplicate active legacy subscription -> rejected by uq_subscriptions_legacy_user
        async with async_session_factory() as session:
            session.add(
                Subscription(
                    user_id=user_id,
                    company_id=None,
                    plan_id=plan_id,
                    scope=SubscriptionScope.LEGACY_RECRUITER_PERSONAL,
                    is_free=False,
                    status=SubscriptionStatus.ACTIVE,
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

    run_async(_exercise())


def test_migration_upgrade_downgrade_backfill_and_preflight_guards(run_async):
    """Verify wave1_4_subscriptions downgrade/upgrade, historical usage backfill, and preflight aborts."""
    _assert_not_development_database()
    migration = _load_subscription_migration_module()

    def _run_migration_step(sync_conn, fn):
        ctx = MigrationContext.configure(sync_conn)
        with Operations.context(ctx):
            fn()

    async def _exercise():
        user_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        sub_1_id = uuid.uuid4()
        sub_2_id = uuid.uuid4()
        order_id = uuid.uuid4()
        usage_id = uuid.uuid4()
        orphan_usage_id = uuid.uuid4()
        missing_sub_id = uuid.uuid4()

        # Step 1: Downgrade from wave1_4_subscriptions to add_interview_assignments schema state
        async with engine.begin() as conn:
            await conn.run_sync(lambda sc: _run_migration_step(sc, migration.downgrade))

            # Seed pre-Wave-1.4 historical data (no scope, company_id, plan_audience, is_free columns)
            await conn.execute(
                text(
                    """
                    INSERT INTO users (
                        id, email, password_hash, role, is_active,
                        created_at, updated_at, is_deleted
                    ) VALUES (
                        :user_id, :email, 'hash', 'recruiter', 1,
                        SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET(), 0
                    )
                    """
                ),
                {"user_id": user_id, "email": f"hist-{user_id}@example.com"},
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO recruitment_plans (
                        id, name, price, currency, duration_days, max_job_posts,
                        is_active, display_order, created_at, updated_at, is_deleted
                    ) VALUES (
                        :plan_id, 'Historical Plan', 500000, 'VND', 30, 5,
                        1, 0, SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET(), 0
                    )
                    """
                ),
                {"plan_id": plan_id},
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO subscriptions (
                        id, user_id, plan_id, status,
                        max_job_posts, max_candidate_searches, max_ai_features,
                        job_posts_used, candidate_searches_used, ai_features_used,
                        created_at, updated_at, is_deleted
                    ) VALUES (
                        :sub_id, :user_id, :plan_id, 'active',
                        5, 10, 10, 1, 0, 0,
                        SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET(), 0
                    )
                    """
                ),
                {"sub_id": sub_1_id, "user_id": user_id, "plan_id": plan_id},
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO payment_orders (
                        id, user_id, plan_id, subscription_id, amount, currency,
                        provider, internal_order_id, status,
                        created_at, updated_at, is_deleted
                    ) VALUES (
                        :order_id, :user_id, :plan_id, :sub_id, 500000, 'VND',
                        'momo', :internal_order_id, 'paid',
                        SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET(), 0
                    )
                    """
                ),
                {
                    "order_id": order_id,
                    "user_id": user_id,
                    "plan_id": plan_id,
                    "sub_id": sub_1_id,
                    "internal_order_id": f"HIST-{order_id}",
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO subscription_usages (
                        id, subscription_id, user_id, feature_type, status, amount,
                        created_at, updated_at
                    ) VALUES (
                        :usage_id, :sub_id, :user_id, 'job_post', 'completed', 1,
                        SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET()
                    )
                    """
                ),
                {"usage_id": usage_id, "sub_id": sub_1_id, "user_id": user_id},
            )

        # Step 2: Verify Preflight 1 fails fast if duplicate active subscriptions exist for a user
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO subscriptions (
                        id, user_id, plan_id, status,
                        max_job_posts, max_candidate_searches, max_ai_features,
                        job_posts_used, candidate_searches_used, ai_features_used,
                        created_at, updated_at, is_deleted
                    ) VALUES (
                        :sub_id, :user_id, :plan_id, 'active',
                        5, 10, 10, 0, 0, 0,
                        SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET(), 0
                    )
                    """
                ),
                {"sub_id": sub_2_id, "user_id": user_id, "plan_id": plan_id},
            )
            with pytest.raises(RuntimeError, match="duplicate active subscriptions"):
                await conn.run_sync(lambda sc: _run_migration_step(sc, migration.upgrade))
            await conn.rollback()

        # Step 3: Verify Preflight 3 fails fast if an orphaned subscription_usages row exists
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE subscription_usages NOCHECK CONSTRAINT ALL"))
            await conn.execute(
                text(
                    """
                    INSERT INTO subscription_usages (
                        id, subscription_id, user_id, feature_type, status, amount,
                        created_at, updated_at
                    ) VALUES (
                        :usage_id, :missing_sub_id, :user_id, 'job_post', 'completed', 1,
                        SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET()
                    )
                    """
                ),
                {
                    "usage_id": orphan_usage_id,
                    "missing_sub_id": missing_sub_id,
                    "user_id": user_id,
                },
            )
            await conn.execute(text("ALTER TABLE subscription_usages CHECK CONSTRAINT ALL"))
            with pytest.raises(
                RuntimeError, match="orphaned subscription_usages rows found"
            ):
                await conn.run_sync(lambda sc: _run_migration_step(sc, migration.upgrade))
            await conn.rollback()

        # Step 4: Run clean upgrade() and verify backfill + defaults
        async with engine.begin() as conn:
            await conn.run_sync(lambda sc: _run_migration_step(sc, migration.upgrade))

            plan_row = (
                await conn.execute(
                    text(
                        "SELECT plan_audience, is_free FROM recruitment_plans WHERE id = :id"
                    ),
                    {"id": plan_id},
                )
            ).one()
            assert plan_row.plan_audience == "company"
            assert bool(plan_row.is_free) is False

            sub_row = (
                await conn.execute(
                    text(
                        "SELECT scope, company_id, is_free, current_period_key "
                        "FROM subscriptions WHERE id = :id"
                    ),
                    {"id": sub_1_id},
                )
            ).one()
            assert sub_row.scope == "legacy_recruiter_personal"
            assert sub_row.company_id is None
            assert bool(sub_row.is_free) is False
            assert sub_row.current_period_key is None

            order_row = (
                await conn.execute(
                    text(
                        "SELECT scope, company_id FROM payment_orders WHERE id = :id"
                    ),
                    {"id": order_id},
                )
            ).one()
            assert order_row.scope == "legacy_recruiter_personal"
            assert order_row.company_id is None

            usage_row = (
                await conn.execute(
                    text(
                        "SELECT scope, company_id, period_key "
                        "FROM subscription_usages WHERE id = :id"
                    ),
                    {"id": usage_id},
                )
            ).one()
            assert usage_row.scope == "legacy_recruiter_personal"
            assert usage_row.company_id is None
            assert usage_row.period_key is None

            # Step 5: Verify downgrade() -> upgrade() round-trip idempotency
            await conn.run_sync(lambda sc: _run_migration_step(sc, migration.downgrade))
            await conn.run_sync(lambda sc: _run_migration_step(sc, migration.upgrade))

    run_async(_exercise())
