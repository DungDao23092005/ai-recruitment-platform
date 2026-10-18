"""Real SQL Server integration tests for the account-locked forced-logout event.

Proves that a minimal ``account.locked`` event is published to the locked user's
*private* channel AFTER the lock commits, exactly once per genuine transition,
and that neither a rolled-back lock nor a Redis publish failure can emit or
break anything.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import EntityNotFoundException  # noqa: E402
from app.database.session import async_session_factory  # noqa: E402
from app.domain.enums import UserRole  # noqa: E402
from app.models import User  # noqa: E402
from app.services.account_lock_realtime import ACCOUNT_LOCKED_EVENT  # noqa: E402
from app.services.admin_service import AdminService  # noqa: E402


pytestmark = pytest.mark.integration

_PUBSUB_TARGET = "app.services.account_lock_realtime.pubsub_manager"


def _fake_manager() -> MagicMock:
    manager = MagicMock()
    manager.publish = AsyncMock()
    manager.get_user_channel = lambda user_id: f"notifications:user:{user_id}"
    return manager


async def _seed_user(
    session, *, role: UserRole = UserRole.CANDIDATE, is_active: bool = True
) -> User:
    user = User(
        email=f"lock-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="hashed",
        role=role,
        is_active=is_active,
    )
    session.add(user)
    await session.flush()
    return user


def test_lock_publishes_account_locked_event_after_commit(run_async):
    async def _run():
        async with async_session_factory() as setup:
            user = await _seed_user(setup)
            admin = await _seed_user(setup, role=UserRole.ADMIN)
            await setup.commit()
            user_id, admin_id = user.id, admin.id

        manager = _fake_manager()
        with patch(_PUBSUB_TARGET, manager):
            async with async_session_factory() as session:
                result = await AdminService(session).deactivate_user(
                    user_id, "Vi phạm điều khoản", admin_id
                )
                await asyncio.sleep(0.05)
                assert result.is_active is False

        assert manager.publish.await_count == 1
        channel, message = manager.publish.await_args.args
        assert channel == f"notifications:user:{user_id}"
        assert channel != "admin:subscriptions"
        assert message["type"] == ACCOUNT_LOCKED_EVENT
        assert message["user_id"] == str(user_id)
        assert message["reason"] == "Vi phạm điều khoản"
        assert isinstance(message["locked_at"], str)

    run_async(_run())


def test_repeated_lock_publishes_no_event(run_async):
    async def _run():
        async with async_session_factory() as setup:
            user = await _seed_user(setup, is_active=False)
            admin = await _seed_user(setup, role=UserRole.ADMIN)
            await setup.commit()
            user_id, admin_id = user.id, admin.id

        manager = _fake_manager()
        with patch(_PUBSUB_TARGET, manager):
            async with async_session_factory() as session:
                await AdminService(session).deactivate_user(
                    user_id, "Second reason", admin_id
                )
                await asyncio.sleep(0.05)

        manager.publish.assert_not_awaited()

    run_async(_run())


def test_missing_user_lock_raises_and_publishes_nothing(run_async):
    async def _run():
        async with async_session_factory() as setup:
            admin = await _seed_user(setup, role=UserRole.ADMIN)
            await setup.commit()
            admin_id = admin.id

        manager = _fake_manager()
        with patch(_PUBSUB_TARGET, manager):
            async with async_session_factory() as session:
                with pytest.raises(EntityNotFoundException):
                    await AdminService(session).deactivate_user(
                        uuid.uuid4(), "Lý do", admin_id
                    )
                await asyncio.sleep(0.05)

        manager.publish.assert_not_awaited()

    run_async(_run())


def test_rolled_back_lock_publishes_no_event(run_async):
    async def _run():
        async with async_session_factory() as setup:
            user = await _seed_user(setup)
            admin = await _seed_user(setup, role=UserRole.ADMIN)
            await setup.commit()
            user_id, admin_id = user.id, admin.id

        manager = _fake_manager()
        with patch(_PUBSUB_TARGET, manager):
            async with async_session_factory() as session:
                with patch.object(
                    session, "commit", new=AsyncMock(side_effect=RuntimeError("db down"))
                ):
                    with pytest.raises(RuntimeError):
                        await AdminService(session).deactivate_user(
                            user_id, "Lý do", admin_id
                        )
                await asyncio.sleep(0.05)

        manager.publish.assert_not_awaited()

    run_async(_run())


def test_publish_failure_does_not_break_committed_lock(run_async):
    async def _run():
        async with async_session_factory() as setup:
            user = await _seed_user(setup)
            admin = await _seed_user(setup, role=UserRole.ADMIN)
            await setup.commit()
            user_id, admin_id = user.id, admin.id

        manager = _fake_manager()
        manager.publish = AsyncMock(side_effect=RuntimeError("redis down"))
        with patch(_PUBSUB_TARGET, manager):
            async with async_session_factory() as session:
                result = await AdminService(session).deactivate_user(
                    user_id, "Lý do", admin_id
                )
                await asyncio.sleep(0.05)
                assert result.is_active is False

        async with async_session_factory() as check:
            stored = await check.get(User, user_id)
            assert stored is not None
            assert stored.is_active is False

    run_async(_run())
