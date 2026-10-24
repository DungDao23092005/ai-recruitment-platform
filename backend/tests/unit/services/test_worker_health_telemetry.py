from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import health
from app.services.analytics_rollup_worker import AnalyticsRollupWorker
from app.services.email_outbox_worker import EmailOutboxWorker

NOW = datetime.now(timezone.utc)


class AnalyticsSession:
    def __init__(self, *, lock_result: int = 0, error: Exception | None = None):
        self.lock_result = lock_result
        self.error = error
        self.commits = 0
        self.rollbacks = 0

    async def scalar(self, statement, params=None):
        if self.error is not None:
            raise self.error
        return self.lock_result

    async def execute(self, statement, params=None):
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class AnalyticsFactory:
    def __init__(self, session: AnalyticsSession) -> None:
        self.session = session

    def __call__(self):
        session = self.session

        class Context:
            async def __aenter__(self):
                return session

            async def __aexit__(self, *exc_info):
                return False

        return Context()


def _analytics(session: AnalyticsSession) -> AnalyticsRollupWorker:
    return AnalyticsRollupWorker(
        session_factory=AnalyticsFactory(session),
        interval_seconds=1,
        lookback_days=0,
        retention_days=0,
    )


@pytest.mark.asyncio
async def test_email_delivery_failure_is_not_a_worker_loop_failure():
    worker = EmailOutboxWorker(
        email_service=AsyncMock(),
        poll_interval=1,
    )
    worker.email_service.send_email.side_effect = RuntimeError(
        "smtp password=secret"
    )
    worker._recover_leases = AsyncMock()
    worker._claim_batch = AsyncMock(
        return_value=[
            {
                "id": "message-1",
                "to_email": "buyer@example.com",
                "subject": "Subject",
                "html_body": "<p>Body</p>",
                "text_body": "Body",
                "attempts": 1,
                "max_attempts": 3,
            }
        ]
    )
    worker._record_failure = AsyncMock()

    sent = await worker.process_due_messages()

    snapshot = worker.health_snapshot()
    assert sent == 1
    assert snapshot["last_outcome"] == "success"
    assert snapshot["consecutive_failures"] == 0
    assert snapshot["last_error_type"] is None
    assert snapshot["delivery_failures_total"] == 1
    assert snapshot["last_heartbeat_at"] is not None
    assert "secret" not in str(snapshot)


@pytest.mark.asyncio
async def test_worker_loop_failure_and_recovery_are_tracked():
    worker = EmailOutboxWorker(poll_interval=1)
    worker._recover_leases = AsyncMock(side_effect=RuntimeError("db secret"))
    worker._claim_batch = AsyncMock(return_value=[])

    with pytest.raises(RuntimeError):
        await worker.process_due_messages()

    snapshot = worker.health_snapshot()
    assert snapshot["last_outcome"] == "failure"
    assert snapshot["consecutive_failures"] == 1
    assert snapshot["last_error_type"] == "RuntimeError"
    assert "db secret" not in str(snapshot)

    worker._recover_leases = AsyncMock()
    await worker.process_due_messages()

    recovered = worker.health_snapshot()
    assert recovered["last_outcome"] == "success"
    assert recovered["consecutive_failures"] == 0
    assert recovered["last_error_type"] is None


@pytest.mark.asyncio
async def test_analytics_skip_and_failure_outcomes_are_distinct():
    skipped = _analytics(AnalyticsSession(lock_result=-1))
    skip_result = await skipped.run_once(now=NOW)
    assert skip_result["skipped"] is True
    assert skipped.health_snapshot()["last_outcome"] == "skipped"

    failed = _analytics(AnalyticsSession(error=RuntimeError("db secret")))
    with pytest.raises(RuntimeError):
        await failed.run_once(now=NOW)
    snapshot = failed.health_snapshot()
    assert snapshot["last_outcome"] == "failure"
    assert snapshot["consecutive_failures"] == 1
    assert snapshot["last_error_type"] == "RuntimeError"
    assert "db secret" not in str(snapshot)


@pytest.mark.asyncio
async def test_analytics_success_resets_consecutive_failures():
    worker = _analytics(AnalyticsSession(lock_result=-1))
    await worker.run_once(now=NOW)
    assert worker.health_snapshot()["last_outcome"] == "skipped"

    worker._session_factory = AnalyticsFactory(AnalyticsSession(lock_result=0))
    await worker.run_once(now=NOW)

    snapshot = worker.health_snapshot()
    assert snapshot["last_outcome"] == "success"
    assert snapshot["consecutive_failures"] == 0


def _healthy_worker(**overrides):
    snapshot = {
        "enabled": True,
        "running": True,
        "started_at": NOW.isoformat(),
        "last_heartbeat_at": NOW.isoformat(),
        "last_run_at": NOW.isoformat(),
        "last_success_at": NOW.isoformat(),
        "last_outcome": "success",
        "consecutive_failures": 0,
        "last_error_type": None,
        "heartbeat_timeout_seconds": 300,
        "delivered_total": 0,
        "delivery_failures_total": 0,
        "cleanup": {
            "last_attempt_at": NOW.isoformat(),
            "last_success_at": NOW.isoformat(),
            "last_outcome": "success",
            "consecutive_failures": 0,
            "last_error_type": None,
            "deleted_total": 0,
            "release_failures": 0,
            "next_attempt_at": None,
        },
        "last_processed_days": 0,
        "last_pruned_events": 0,
    }
    snapshot.update(overrides)
    return snapshot


def test_worker_health_is_allowlisted_and_sanitized(monkeypatch):
    malicious = _healthy_worker(
        last_error_type="RuntimeError: password=secret",
        last_outcome="not-a-real-outcome",
    )
    malicious["raw_exception"] = "postgres://user:pass@host/db"

    monkeypatch.setattr(
        health, "email_outbox_worker_health", lambda: malicious
    )
    monkeypatch.setattr(
        health,
        "analytics_worker_health",
        lambda: _healthy_worker(last_error_type=None),
    )

    workers = health.build_workers_health()
    serialized = str(workers)

    assert workers["email_outbox"]["last_error_type"] is None
    assert workers["email_outbox"]["last_outcome"] == "unknown"
    assert "raw_exception" not in workers["email_outbox"]
    assert "secret" not in serialized
    assert "postgres" not in serialized


def test_stale_heartbeat_marks_worker_degraded(monkeypatch):
    stale = _healthy_worker(
        last_heartbeat_at=(NOW - timedelta(hours=2)).isoformat()
    )
    monkeypatch.setattr(
        health, "email_outbox_worker_health", lambda: stale
    )
    monkeypatch.setattr(
        health, "analytics_worker_health", lambda: _healthy_worker()
    )

    workers = health.build_workers_health()
    assert workers["email_outbox"]["status"] == "degraded"


@pytest.mark.asyncio
async def test_worker_degradation_does_not_make_health_503(monkeypatch):
    degraded = _healthy_worker(
        last_outcome="failure",
        consecutive_failures=2,
        last_error_type="RuntimeError",
    )
    monkeypatch.setattr(
        health,
        "build_workers_health",
        lambda: {
            "email_outbox": {
                **degraded,
                "status": "degraded",
            },
            "analytics_rollup": {
                **_healthy_worker(),
                "status": "healthy",
            },
        },
    )
    monkeypatch.setattr(
        health,
        "check_redis",
        AsyncMock(return_value={"status": "healthy"}),
    )
    monkeypatch.setattr(
        health,
        "check_qdrant",
        AsyncMock(return_value={"status": "healthy"}),
    )

    response = await health.health_check(db=AsyncMock())

    assert response["status"] == "degraded"
    assert response["workers"]["email_outbox"]["status"] == "degraded"


@pytest.mark.asyncio
async def test_infrastructure_failure_still_returns_503(monkeypatch):
    monkeypatch.setattr(
        health,
        "build_workers_health",
        lambda: {
            "email_outbox": {**_healthy_worker(), "status": "healthy"},
            "analytics_rollup": {**_healthy_worker(), "status": "healthy"},
        },
    )
    monkeypatch.setattr(
        health,
        "check_redis",
        AsyncMock(return_value={"status": "unhealthy"}),
    )
    monkeypatch.setattr(
        health,
        "check_qdrant",
        AsyncMock(return_value={"status": "healthy"}),
    )

    with pytest.raises(HTTPException) as exc_info:
        await health.health_check(db=AsyncMock())

    assert exc_info.value.status_code == 503
