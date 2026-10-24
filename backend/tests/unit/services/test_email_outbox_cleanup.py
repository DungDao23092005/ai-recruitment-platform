from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.services.email_outbox_service import EmailOutboxService
from app.services.email_outbox_worker import (
    CLEANUP_CONTENTION_COOLDOWN_SECONDS,
    CLEANUP_FAILURE_RETRY_SECONDS,
    CLEANUP_INTERVAL_SECONDS,
    EmailOutboxWorker,
)

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


class FakeResult:
    def __init__(self, rowcount: int = 0) -> None:
        self.rowcount = rowcount


class FakeConnection:
    def __init__(self) -> None:
        self.invalidated = False

    async def invalidate(self) -> None:
        self.invalidated = True


class FakeSession:
    def __init__(
        self,
        *,
        name: str,
        lock_result: int = 0,
        release_result: int = 0,
        deleted: int = 0,
        purge_error: BaseException | None = None,
        release_error: BaseException | None = None,
        release_started: asyncio.Event | None = None,
        release_delay: float = 0.0,
    ) -> None:
        self.name = name
        self.lock_result = lock_result
        self.release_result = release_result
        self.deleted = deleted
        self.purge_error = purge_error
        self.release_error = release_error
        self.release_started = release_started
        self.release_delay = release_delay
        self.scalar_calls: list[tuple[str, dict | None]] = []
        self.execute_calls: list[tuple[str, dict | None]] = []
        self.commits = 0
        self.rollbacks = 0
        self.connection_obj = FakeConnection()

    async def scalar(self, statement, params=None):
        sql = str(statement)
        self.scalar_calls.append((sql, params))
        if "sp_getapplock" in sql:
            return self.lock_result
        if "sp_releaseapplock" in sql:
            if self.release_started is not None:
                self.release_started.set()
            if self.release_delay:
                await asyncio.sleep(self.release_delay)
            if self.release_error is not None:
                raise self.release_error
            return self.release_result
        return None

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.execute_calls.append((sql, params))
        if self.purge_error is not None:
            raise self.purge_error
        return FakeResult(self.deleted)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def connection(self):
        return self.connection_obj


class FakeFactory:
    def __init__(self, *sessions: FakeSession) -> None:
        self._sessions = list(sessions)

    def __call__(self):
        session = self._sessions.pop(0)

        class Context:
            async def __aenter__(self):
                return session

            async def __aexit__(self, *exc_info):
                return False

        return Context()


def _worker(*sessions: FakeSession) -> EmailOutboxWorker:
    return EmailOutboxWorker(
        session_factory=FakeFactory(*sessions),
        cleanup_interval_seconds=CLEANUP_INTERVAL_SECONDS,
    )


@pytest.mark.asyncio
async def test_purge_sent_only_targets_old_sent_rows():
    session = FakeSession(name="work", deleted=4)

    deleted = await EmailOutboxService(session).purge_sent(
        older_than_days=30, now=NOW
    )

    assert deleted == 4
    sql, params = session.execute_calls[0]
    assert "DELETE FROM email_outbox" in sql
    assert "status = :sent" in sql
    assert "sent_at IS NOT NULL" in sql
    assert "sent_at < :cutoff" in sql
    assert params["sent"] == "sent"
    assert params["cutoff"] == NOW - timedelta(days=30)
    assert session.commits == 1


@pytest.mark.asyncio
async def test_cleanup_uses_same_lock_session_for_acquire_and_release():
    lock = FakeSession(name="lock", deleted=0)
    work = FakeSession(name="work", deleted=2)
    worker = _worker(lock, work)

    result = await worker.cleanup_now(NOW)

    assert result == {"outcome": "success", "deleted": 2}
    assert worker._next_cleanup_at == NOW + timedelta(
        seconds=CLEANUP_INTERVAL_SECONDS
    )
    assert any("sp_getapplock" in sql for sql, _ in lock.scalar_calls)
    assert any("sp_releaseapplock" in sql for sql, _ in lock.scalar_calls)
    assert not any("sp_getapplock" in sql for sql, _ in work.scalar_calls)
    assert not any("sp_releaseapplock" in sql for sql, _ in work.scalar_calls)
    assert lock.connection_obj.invalidated is False


@pytest.mark.asyncio
async def test_lock_contention_cools_down_for_ten_minutes():
    lock = FakeSession(name="lock", lock_result=-1)
    worker = _worker(lock)

    result = await worker.cleanup_now(NOW)

    assert result == {"outcome": "skipped", "deleted": 0}
    assert worker._next_cleanup_at == NOW + timedelta(
        seconds=CLEANUP_CONTENTION_COOLDOWN_SECONDS
    )
    snapshot = worker.health_snapshot()
    assert snapshot["cleanup"]["last_outcome"] == "skipped"
    assert snapshot["cleanup"]["consecutive_failures"] == 0


@pytest.mark.asyncio
async def test_cleanup_failure_retries_in_one_hour():
    lock = FakeSession(name="lock")
    work = FakeSession(name="work", purge_error=RuntimeError("secret db error"))
    worker = _worker(lock, work)

    result = await worker.cleanup_now(NOW)

    assert result == {"outcome": "failure", "deleted": 0}
    assert worker._next_cleanup_at == NOW + timedelta(
        seconds=CLEANUP_FAILURE_RETRY_SECONDS
    )
    snapshot = worker.health_snapshot()
    assert snapshot["cleanup"]["last_outcome"] == "failure"
    assert snapshot["cleanup"]["last_error_type"] == "RuntimeError"
    assert "secret" not in str(snapshot)


@pytest.mark.asyncio
async def test_release_failure_invalidates_connection_and_retries_later():
    lock = FakeSession(name="lock", release_result=-1)
    work = FakeSession(name="work", deleted=3)
    worker = _worker(lock, work)

    result = await worker.cleanup_now(NOW)

    assert result == {"outcome": "failure", "deleted": 0}
    assert lock.connection_obj.invalidated is True
    assert worker._next_cleanup_at == NOW + timedelta(
        seconds=CLEANUP_FAILURE_RETRY_SECONDS
    )
    snapshot = worker.health_snapshot()
    assert snapshot["cleanup"]["last_error_type"] == "LockReleaseError"
    assert snapshot["cleanup"]["release_failures"] == 1


@pytest.mark.asyncio
async def test_release_exception_invalidates_connection():
    lock = FakeSession(
        name="lock", release_error=RuntimeError("release failed")
    )
    work = FakeSession(name="work", deleted=1)
    worker = _worker(lock, work)

    result = await worker.cleanup_now(NOW)

    assert result["outcome"] == "failure"
    assert lock.connection_obj.invalidated is True
    assert worker.health_snapshot()["cleanup"]["release_failures"] == 1


@pytest.mark.asyncio
async def test_cancellation_still_attempts_release():
    lock = FakeSession(name="lock")
    work = FakeSession(name="work", purge_error=asyncio.CancelledError())
    worker = _worker(lock, work)

    with pytest.raises(asyncio.CancelledError):
        await worker.cleanup_now(NOW)

    assert any("sp_releaseapplock" in sql for sql, _ in lock.scalar_calls)
    assert worker._next_cleanup_at == NOW + timedelta(
        seconds=CLEANUP_FAILURE_RETRY_SECONDS
    )


@pytest.mark.asyncio
async def test_cancellation_during_release_is_not_swallowed():
    release_started = asyncio.Event()
    lock = FakeSession(
        name="lock",
        release_started=release_started,
        release_delay=0.05,
    )
    work = FakeSession(name="work", deleted=1)
    worker = _worker(lock, work)

    task = asyncio.create_task(worker.cleanup_now(NOW))
    await release_started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert lock.commits == 1
    assert lock.connection_obj.invalidated is True
    assert worker.health_snapshot()["cleanup"]["last_outcome"] == "cancelled"


@pytest.mark.asyncio
async def test_cleanup_is_not_run_before_next_due_time():
    lock = FakeSession(name="lock")
    worker = _worker(lock)
    worker._next_cleanup_at = datetime(2099, 1, 1, tzinfo=timezone.utc)

    await worker._maybe_run_cleanup()

    assert lock.scalar_calls == []
