"""Verify the email_outbox migration refuses a lossy downgrade.

The guard lives in the Alembic revision and is exercised directly against the
disposable test database, since the integration schema is created from ORM
metadata rather than by running migrations.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.database.base_class import utc_now
from app.database.session import async_session_factory
from app.domain.enums import OutboxStatus
from app.models import EmailOutbox

pytestmark = pytest.mark.integration

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "add_email_outbox.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("add_email_outbox", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(status: str, *, to_email: str) -> EmailOutbox:
    return EmailOutbox(
        event_type="t",
        to_email=to_email,
        subject="s",
        html_body="h",
        text_body="t",
        status=status,
        attempts=0,
        max_attempts=3,
        next_attempt_at=utc_now(),
    )


class TestEmailOutboxDowngradeGuard:
    def test_refuses_downgrade_with_pending_message(self, run_async):
        async def _test():
            migration = _load_migration()
            async with async_session_factory() as session:
                session.add(_row(OutboxStatus.PENDING.value, to_email="p@example.com"))
                await session.commit()

                conn = await session.connection()
                with pytest.raises(RuntimeError, match="Refusing to drop email_outbox"):
                    await conn.run_sync(migration._assert_downgrade_safe)

        run_async(_test())

    def test_refuses_downgrade_with_processing_or_failed(self, run_async):
        async def _test():
            migration = _load_migration()
            async with async_session_factory() as session:
                session.add(
                    _row(OutboxStatus.PROCESSING.value, to_email="pr@example.com")
                )
                session.add(_row(OutboxStatus.FAILED.value, to_email="f@example.com"))
                await session.commit()

                conn = await session.connection()
                counts = await conn.run_sync(migration._remaining_unfinished_counts)
                statuses = {row[0] for row in counts}
                assert statuses == {
                    OutboxStatus.PROCESSING.value,
                    OutboxStatus.FAILED.value,
                }
                with pytest.raises(RuntimeError, match="Refusing to drop email_outbox"):
                    await conn.run_sync(migration._assert_downgrade_safe)

        run_async(_test())

    def test_allows_downgrade_when_only_sent_history_remains(self, run_async):
        async def _test():
            migration = _load_migration()
            async with async_session_factory() as session:
                session.add(_row(OutboxStatus.SENT.value, to_email="s@example.com"))
                await session.commit()

                conn = await session.connection()
                # Must not raise: only delivered history would be discarded.
                await conn.run_sync(migration._assert_downgrade_safe)

        run_async(_test())
