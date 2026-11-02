from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from app.domain.models.base import utc_now
from app.repositories.subscription_repository import SubscriptionRepository


def test_expire_stale_active_for_user_updates_only_stale_active_rows():
    session = MagicMock()
    result = MagicMock()
    result.rowcount = 2
    session.execute = AsyncMock(return_value=result)
    repository = SubscriptionRepository(session)
    now = utc_now()

    count = asyncio.run(
        repository.expire_stale_active_for_user(uuid.uuid4(), now)
    )

    assert count == 2
    session.execute.assert_awaited_once()
    statement = str(session.execute.await_args.args[0])
    assert "UPDATE subscriptions" in statement
    assert "subscriptions.status" in statement
    assert "subscriptions.expires_at" in statement


def test_expire_stale_active_for_user_clamps_negative_rowcount():
    session = MagicMock()
    result = MagicMock()
    result.rowcount = -1
    session.execute = AsyncMock(return_value=result)
    repository = SubscriptionRepository(session)

    count = asyncio.run(
        repository.expire_stale_active_for_user(
            uuid.uuid4(), utc_now() - timedelta(seconds=1)
        )
    )

    assert count == 0


def test_expire_stale_active_uses_conditional_update_with_limit_and_order():
    session = MagicMock()
    result = MagicMock()
    result.rowcount = 3
    session.execute = AsyncMock(return_value=result)
    repository = SubscriptionRepository(session)
    now = utc_now()

    count = asyncio.run(repository.expire_stale_active(now, limit=7))

    assert count == 3
    session.execute.assert_awaited_once()
    statement_obj = session.execute.await_args.args[0]
    assert statement_obj.get_execution_options().get("synchronize_session") is False
    statement = str(statement_obj)
    assert "UPDATE subscriptions" in statement
    assert "subscriptions.is_deleted = false" in statement
    assert "subscriptions.status" in statement
    assert "subscriptions.expires_at IS NOT NULL" in statement
    assert "subscriptions.expires_at <=" in statement
    assert "ORDER BY subscriptions.expires_at ASC" in statement
    assert "subscriptions.id ASC" in statement
    assert "LIMIT" in statement


def test_expire_stale_active_clamps_negative_rowcount():
    session = MagicMock()
    result = MagicMock()
    result.rowcount = -1
    session.execute = AsyncMock(return_value=result)
    repository = SubscriptionRepository(session)

    count = asyncio.run(
        repository.expire_stale_active(
            utc_now() - timedelta(seconds=1), limit=7
        )
    )

    assert count == 0
