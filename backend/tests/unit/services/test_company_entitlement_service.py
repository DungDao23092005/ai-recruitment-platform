from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConfigurationError
from app.database.base_class import Base
from app.domain.enums import (
    MembershipRole,
    MembershipStatus,
    SubscriptionScope,
    SubscriptionStatus,
)
from app.models import CompanyMembership
from app.services.company_entitlement_service import CompanyEntitlementService
from sqlalchemy.dialects import mssql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def _service() -> tuple[CompanyEntitlementService, MagicMock]:
    session = MagicMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    savepoint = SimpleNamespace(
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    session.begin_nested = AsyncMock(return_value=savepoint)
    service = CompanyEntitlementService(session)
    service.subscriptions = MagicMock()
    service.subscriptions.get_active_by_company_id = AsyncMock(return_value=None)
    service.plans = MagicMock()
    service.plans.get_active_company_free_plan = AsyncMock(return_value=None)
    return service, session


def _plan():
    return SimpleNamespace(
        id=uuid4(),
        max_job_posts=1,
        max_candidate_searches=10,
        max_ai_features=5,
    )


def _membership(user_id):
    return SimpleNamespace(user_id=user_id)


def test_company_period_key_uses_vietnam_calendar_month():
    now = datetime(2026, 1, 31, 18, 30, tzinfo=timezone.utc)

    assert CompanyEntitlementService.company_period_key(now) == "2026-02"


@pytest.mark.asyncio
async def test_provision_returns_existing_active_subscription():
    service, session = _service()
    existing = SimpleNamespace(id=uuid4())
    service.subscriptions.get_active_by_company_id.return_value = existing

    result = await service.provision_company_free_subscription(uuid4())

    assert result is existing
    session.add.assert_not_called()
    service.plans.get_active_company_free_plan.assert_not_awaited()


@pytest.mark.asyncio
async def test_provision_fails_closed_without_canonical_plan():
    service, session = _service()

    with pytest.raises(ConfigurationError, match="Company Free Plan"):
        await service.provision_company_free_subscription(uuid4())

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_provision_snapshots_canonical_plan_and_resets_counters():
    service, session = _service()
    plan = _plan()
    owner_id = uuid4()
    company_id = uuid4()
    service.plans.get_active_company_free_plan.return_value = plan
    scalars = MagicMock()
    scalars.first.return_value = _membership(owner_id)
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars
    session.execute.return_value = execute_result

    now = datetime(2026, 11, 15, 3, 0, tzinfo=timezone.utc)
    result = await service.provision_company_free_subscription(company_id, now)

    assert result.company_id == company_id
    assert result.user_id == owner_id
    assert result.plan_id == plan.id
    assert result.scope == SubscriptionScope.COMPANY_RECRUITING
    assert result.is_free is True
    assert result.status == SubscriptionStatus.ACTIVE
    assert result.current_period_key == "2026-11"
    assert result.expires_at is None
    assert result.max_job_posts == 1
    assert result.max_candidate_searches == 10
    assert result.max_ai_features == 5
    assert result.job_posts_used == 0
    assert result.candidate_searches_used == 0
    assert result.ai_features_used == 0
    session.add.assert_called_once_with(result)
    session.flush.assert_awaited_once()
    session.begin_nested.return_value.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_provision_reuses_concurrent_winner_after_integrity_error():
    service, session = _service()
    service.plans.get_active_company_free_plan.return_value = _plan()
    scalars = MagicMock()
    scalars.first.return_value = _membership(uuid4())
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars
    session.execute.return_value = execute_result
    session.flush.side_effect = IntegrityError("stmt", {}, Exception("dup"))
    winner = SimpleNamespace(id=uuid4())
    service.subscriptions.get_active_by_company_id.side_effect = [
        None,
        winner,
    ]

    result = await service.provision_company_free_subscription(uuid4())

    assert result is winner
    session.begin_nested.return_value.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_provision_requires_an_active_member():
    service, _session = _service()
    service.plans.get_active_company_free_plan.return_value = _plan()
    scalars = MagicMock()
    scalars.first.return_value = None
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars
    service.session.execute.return_value = execute_result

    with pytest.raises(ConfigurationError, match="active member"):
        await service.provision_company_free_subscription(uuid4())


@pytest.mark.asyncio
async def test_resolve_owner_statement_compiles_for_mssql_with_case_expression():
    service, session = _service()
    company_id = uuid4()
    owner_id = uuid4()
    scalars = MagicMock()
    scalars.first.return_value = _membership(owner_id)
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars
    session.execute.return_value = execute_result

    resolved = await service._resolve_owner_user_id(company_id)
    assert resolved == owner_id

    session.execute.assert_awaited_once()
    statement = session.execute.await_args[0][0]

    compiled = statement.compile(
        dialect=mssql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    sql_str = str(compiled)

    # 1. Statement compiles successfully using MSSQL dialect without invalid boolean ordering
    assert "ORDER BY company_memberships.role = 'admin' DESC" not in sql_str
    assert "company_memberships.role = 'admin' DESC" not in sql_str

    # 2. Contains CASE WHEN expression for ADMIN prioritization
    assert "CASE WHEN (company_memberships.role = 'admin') THEN 1 ELSE 0 END DESC" in sql_str

    # 4. Secondary ordering by joined_at and created_at remains intact
    assert "company_memberships.joined_at ASC" in sql_str
    assert "company_memberships.created_at ASC" in sql_str


@pytest.mark.asyncio
async def test_resolve_owner_prioritizes_admin_membership():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        cid = uuid4()
        m_recruiter = CompanyMembership(
            company_id=cid,
            user_id=uuid4(),
            role=MembershipRole.RECRUITER,
            status=MembershipStatus.ACTIVE,
            joined_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        admin_id = uuid4()
        m_admin = CompanyMembership(
            company_id=cid,
            user_id=admin_id,
            role=MembershipRole.ADMIN,
            status=MembershipStatus.ACTIVE,
            joined_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
            created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        )
        session.add_all([m_recruiter, m_admin])
        await session.commit()

        service = CompanyEntitlementService(session)
        resolved_id = await service._resolve_owner_user_id(cid)
        assert resolved_id == admin_id

    await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_owner_secondary_ordering_by_joined_at():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        cid = uuid4()
        earlier_user_id = uuid4()
        m1 = CompanyMembership(
            company_id=cid,
            user_id=earlier_user_id,
            role=MembershipRole.RECRUITER,
            status=MembershipStatus.ACTIVE,
            joined_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            created_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
        )
        later_user_id = uuid4()
        m2 = CompanyMembership(
            company_id=cid,
            user_id=later_user_id,
            role=MembershipRole.RECRUITER,
            status=MembershipStatus.ACTIVE,
            joined_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        session.add_all([m1, m2])
        await session.commit()

        service = CompanyEntitlementService(session)
        resolved_id = await service._resolve_owner_user_id(cid)
        assert resolved_id == earlier_user_id

    await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_owner_secondary_ordering_by_created_at():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        cid = uuid4()
        earlier_created_id = uuid4()
        m1 = CompanyMembership(
            company_id=cid,
            user_id=earlier_created_id,
            role=MembershipRole.RECRUITER,
            status=MembershipStatus.ACTIVE,
            joined_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        later_created_id = uuid4()
        m2 = CompanyMembership(
            company_id=cid,
            user_id=later_created_id,
            role=MembershipRole.RECRUITER,
            status=MembershipStatus.ACTIVE,
            joined_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        session.add_all([m1, m2])
        await session.commit()

        service = CompanyEntitlementService(session)
        resolved_id = await service._resolve_owner_user_id(cid)
        assert resolved_id == earlier_created_id

    await engine.dispose()
