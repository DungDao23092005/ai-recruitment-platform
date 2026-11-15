from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import SubscriptionScope, SubscriptionStatus
from app.services.quota_enforcement_service import QuotaEnforcementService


def _subscription(**overrides):
    values = dict(
        id=uuid4(),
        company_id=uuid4(),
        plan_id=uuid4(),
        scope=SubscriptionScope.COMPANY_RECRUITING,
        is_free=True,
        is_deleted=False,
        status=SubscriptionStatus.ACTIVE,
        current_period_key="2026-10",
        max_job_posts=1,
        max_candidate_searches=10,
        max_ai_features=5,
        job_posts_used=1,
        candidate_searches_used=7,
        ai_features_used=3,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _service():
    session = AsyncMock(spec=AsyncSession)
    service = QuotaEnforcementService(session)
    service.plans = MagicMock()
    service.plans.get_active_company_free_plan = AsyncMock()
    return service, session


@pytest.mark.asyncio
async def test_rollover_resets_counters_and_refreshes_snapshot():
    service, session = _service()
    subscription = _subscription()
    new_plan_id = uuid4()
    service.plans.get_active_company_free_plan.return_value = SimpleNamespace(
        id=new_plan_id,
        max_job_posts=2,
        max_candidate_searches=20,
        max_ai_features=8,
    )
    session.execute.return_value = SimpleNamespace(rowcount=1)
    session.refresh = AsyncMock()

    now = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
    await service._rollover_company_free_period(subscription, now)

    emitted = session.execute.await_args.args[0]
    values = emitted.compile().params
    assert values["job_posts_used"] == 0
    assert values["candidate_searches_used"] == 0
    assert values["ai_features_used"] == 0
    assert values["current_period_key"] == "2026-11"
    assert values["plan_id"] == new_plan_id
    assert values["max_job_posts"] == 2
    assert values["max_candidate_searches"] == 20
    assert values["max_ai_features"] == 8
    session.refresh.assert_awaited_once_with(subscription)


@pytest.mark.asyncio
async def test_rollover_keeps_snapshot_when_canonical_plan_missing():
    service, session = _service()
    subscription = _subscription()
    service.plans.get_active_company_free_plan.return_value = None
    session.execute.return_value = SimpleNamespace(rowcount=1)
    session.refresh = AsyncMock()

    now = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
    await service._rollover_company_free_period(subscription, now)

    values = session.execute.await_args.args[0].compile().params
    assert "plan_id" not in values
    assert "max_job_posts" not in values
    assert values["current_period_key"] == "2026-11"
    assert values["job_posts_used"] == 0


@pytest.mark.asyncio
async def test_rollover_is_skipped_within_the_same_month():
    service, session = _service()
    subscription = _subscription(current_period_key="2026-11")

    now = datetime(2026, 11, 15, 0, 0, tzinfo=timezone.utc)
    await service._rollover_company_free_period(subscription, now)

    session.execute.assert_not_awaited()
    service.plans.get_active_company_free_plan.assert_not_awaited()
