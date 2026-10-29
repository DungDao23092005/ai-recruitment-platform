from __future__ import annotations

import pytest

from app.services.quota_enforcement_service import QuotaEnforcementService
from app.services.quota_reconciliation_worker import QuotaReconciliationWorker


class FakeSession:
    def __init__(self, *, lock_result: int = 0) -> None:
        self.lock_result = lock_result
        self.commits = 0
        self.rollbacks = 0
        self.scalar_calls: list[tuple[str, dict | None]] = []

    async def scalar(self, statement, params=None):
        self.scalar_calls.append((str(statement), params))
        return self.lock_result

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self):
        session = self.session

        class Context:
            async def __aenter__(self):
                return session

            async def __aexit__(self, *args):
                return False

        return Context()


def _worker(session: FakeSession) -> QuotaReconciliationWorker:
    return QuotaReconciliationWorker(
        session_factory=FakeFactory(session),
        interval_seconds=1,
        max_age_minutes=60,
        batch_size=10,
    )


@pytest.mark.asyncio
async def test_lock_denied_skips_without_reconciling(monkeypatch):
    called = False

    async def reconcile(self, **kwargs):
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(
        QuotaEnforcementService, "reconcile_stale_reservations", reconcile
    )
    session = FakeSession(lock_result=-1)

    result = await _worker(session).run_once()

    assert result == {"skipped": True, "reconciled": 0}
    assert called is False
    assert session.commits == 0


@pytest.mark.asyncio
async def test_successful_pass_reconciles_and_commits(monkeypatch):
    calls = {}

    async def reconcile(self, **kwargs):
        calls.update(kwargs)
        return 3

    monkeypatch.setattr(
        QuotaEnforcementService, "reconcile_stale_reservations", reconcile
    )
    session = FakeSession()
    worker = _worker(session)

    result = await worker.run_once()

    assert result == {"skipped": False, "reconciled": 3}
    assert calls == {"max_age_minutes": 60, "limit": 10}
    assert session.commits >= 2
    assert any(
        "sp_releaseapplock" in statement for statement, _ in session.scalar_calls
    )
    snapshot = worker.health_snapshot()
    assert snapshot["last_outcome"] == "success"
    assert snapshot["last_reconciled"] == 3


@pytest.mark.asyncio
async def test_failure_rolls_back_and_records_failure(monkeypatch):
    async def reconcile(self, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        QuotaEnforcementService, "reconcile_stale_reservations", reconcile
    )
    session = FakeSession()
    worker = _worker(session)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await worker.run_once()

    assert session.rollbacks >= 2
    snapshot = worker.health_snapshot()
    assert snapshot["last_outcome"] == "failure"
    assert snapshot["consecutive_failures"] == 1
    assert snapshot["last_error_type"] == "RuntimeError"
    assert "database unavailable" not in str(snapshot)
