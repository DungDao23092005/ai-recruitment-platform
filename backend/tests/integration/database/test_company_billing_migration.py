"""Wave 1.4 Phase 2 — Company Billing Migration & Filtered Index integration tests.

Scenarios:
- P57: Migration preflight duplicate check exists
- P58: SubscriptionUsage model table args index matches migration definition
- A01: Filtered index uniqueness enforcement on (subscription_id, idempotency_key) including soft-deleted rows
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.database.session import async_session_factory
from app.domain.enums import (
    SubscriptionScope,
    SubscriptionUsageFeatureType,
    SubscriptionUsageStatus,
)
from app.models import Subscription, SubscriptionUsage
from tests.integration.company_billing_helpers import (
    _create_company,
    _create_company_subscription,
    _create_plan,
    _create_user,
    _load_company_billing_migration_module,
)

pytestmark = pytest.mark.integration


def test_p57_company_billing_migration_preflight_detects_duplicate_usage_ids():
    """P57: company_billing migration preflight identifies duplicate usage IDs and aborts upgrade."""
    module = _load_company_billing_migration_module()
    assert hasattr(module, "_preflight_duplicate_idempotency_keys")

    # 1. Clean database state allows upgrade
    mock_bind_clean = MagicMock()
    mock_bind_clean.execute.return_value.fetchall.return_value = []
    assert module.check_duplicate_idempotency_keys(mock_bind_clean) == []

    # 2. Duplicate rows detected and upgrade() aborts with RuntimeError
    mock_bind_dup = MagicMock()
    id1, id2 = str(uuid.uuid4()), str(uuid.uuid4())
    mock_bind_dup.execute.return_value.fetchall.return_value = [(id1,), (id2,)]

    conflicts = module.check_duplicate_idempotency_keys(mock_bind_dup)
    assert conflicts == [id1, id2]

    with patch.object(module.op, "get_bind", return_value=mock_bind_dup):
        with pytest.raises(RuntimeError) as exc_info:
            module.upgrade()
        err_msg = str(exc_info.value)
        assert "Cannot create uq_subscription_usages_subscription_idempotency" in err_msg
        assert id1 in err_msg
        assert id2 in err_msg


def test_p58_subscription_usage_table_args_index_matches_migration_definition():
    indexes = {idx.name: idx for idx in SubscriptionUsage.__table__.indexes}
    assert "uq_subscription_usages_subscription_idempotency" in indexes
    idx = indexes["uq_subscription_usages_subscription_idempotency"]
    col_names = [col.name for col in idx.columns]
    assert col_names == ["subscription_id", "idempotency_key"]
    assert idx.unique is True
    assert str(idx.dialect_options["mssql"]["where"]).strip() == (
        "[idempotency_key] IS NOT NULL"
    )


def test_a01_sql_server_filtered_index_includes_soft_deleted_usage_rows(run_async):
    """A01: The filtered unique index enforces uniqueness on (subscription_id, idempotency_key) where not null, including soft-deleted rows."""
    async def _run():
        async with async_session_factory() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            plan = await _create_plan(session)
            sub = await _create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
            )
            sub_id = sub.id
            comp_id = company.id
            uid = user.id
            idem_key = f"idem-uniq-{uuid.uuid4().hex}"
            u1 = SubscriptionUsage(
                subscription_id=sub_id,
                user_id=uid,
                company_id=comp_id,
                scope=SubscriptionScope.COMPANY_RECRUITING,
                feature_type=SubscriptionUsageFeatureType.JOB_POST,
                status=SubscriptionUsageStatus.COMPLETED,
                amount=1,
                idempotency_key=idem_key,
            )
            session.add(u1)
            await session.commit()

            # Attempting to insert another row with the same subscription_id and idempotency_key
            # must fail with IntegrityError
            u2 = SubscriptionUsage(
                subscription_id=sub_id,
                user_id=uid,
                company_id=comp_id,
                scope=SubscriptionScope.COMPANY_RECRUITING,
                feature_type=SubscriptionUsageFeatureType.JOB_POST,
                status=SubscriptionUsageStatus.COMPLETED,
                amount=1,
                idempotency_key=idem_key,
            )
            session.add(u2)
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

            # Multiple rows with idempotency_key=None are allowed by the filtered index
            u_null1 = SubscriptionUsage(
                subscription_id=sub_id,
                user_id=uid,
                company_id=comp_id,
                scope=SubscriptionScope.COMPANY_RECRUITING,
                feature_type=SubscriptionUsageFeatureType.JOB_POST,
                status=SubscriptionUsageStatus.COMPLETED,
                amount=1,
                idempotency_key=None,
            )
            u_null2 = SubscriptionUsage(
                subscription_id=sub_id,
                user_id=uid,
                company_id=comp_id,
                scope=SubscriptionScope.COMPANY_RECRUITING,
                feature_type=SubscriptionUsageFeatureType.JOB_POST,
                status=SubscriptionUsageStatus.COMPLETED,
                amount=1,
                idempotency_key=None,
            )
            session.add_all([u_null1, u_null2])
            await session.commit()

    run_async(_run())
