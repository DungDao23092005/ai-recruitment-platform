from __future__ import annotations

import asyncio
import uuid

import pytest
from starlette.requests import Request

from app.repositories.analytics_repository import AnalyticsRepository
from app.services.job_view_telemetry_service import (
    UNIQUE_VIEW_KEY_PREFIX,
    JobViewTelemetryService,
)
from app.services.analytics_time import vietnam_today


class FakeRedis:
    def __init__(
        self, *, stored=True, error=None, eval_error=None
    ) -> None:
        self.stored = stored
        self.error = error
        self.eval_error = eval_error
        self.calls = []
        self.eval_calls = []
        self.values: dict[str, str] = {}

    async def set(self, key, value, ex=None, nx=False):
        self.calls.append({"key": key, "value": value, "ex": ex, "nx": nx})
        if self.error is not None:
            raise self.error
        if self.stored and (not nx or key not in self.values):
            self.values[key] = value
            return True
        return None

    async def eval(self, script, numkeys, *args):
        key, token = args
        self.eval_calls.append({"key": key, "token": token})
        if self.eval_error is not None:
            raise self.eval_error
        if self.values.get(key) == token:
            del self.values[key]
            return 1
        return 0


class FakeSession:
    def __init__(self, *, rollback_error=None, commit_error=None) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.rollback_error = rollback_error
        self.commit_error = commit_error

    async def commit(self):
        self.commits += 1
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self):
        self.rollbacks += 1
        if self.rollback_error is not None:
            raise self.rollback_error


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


def _request(user_agent="Mozilla/5.0", ip="203.0.113.9") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/v1/jobs/x",
            "raw_path": b"/api/v1/jobs/x",
            "query_string": b"",
            "headers": [(b"user-agent", user_agent.encode())],
            "client": (ip, 12345),
            "server": ("testserver", 80),
        }
    )


def _job():
    return type(
        "Job",
        (),
        {"id": uuid.uuid4(), "company_id": uuid.uuid4()},
    )()


@pytest.fixture
def captured(monkeypatch):
    calls = []

    async def record_view(self, **kwargs):
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(AnalyticsRepository, "record_view", record_view)
    return calls


@pytest.mark.asyncio
async def test_unique_view_is_persisted_and_ttl_scoped_to_vietnam_day(captured):
    redis = FakeRedis(stored=True)
    session = FakeSession()
    service = JobViewTelemetryService(
        redis_client=redis,
        session_factory=FakeFactory(session),
        ttl_seconds=900,
    )
    job = _job()

    assert await service.record_view(_request(), job) is True

    assert captured[0]["is_unique"] is True
    assert captured[0]["job_id"] == job.id
    assert captured[0]["company_id"] == job.company_id
    assert session.commits == 1
    key = redis.calls[0]["key"]
    assert key.startswith(f"{UNIQUE_VIEW_KEY_PREFIX}:{job.id}:")
    assert vietnam_today().isoformat() in key
    assert redis.calls[0]["nx"] is True
    assert redis.calls[0]["ex"] == 900
    assert redis.calls[0]["value"] == redis.values[key]
    assert len(redis.calls[0]["value"]) == 32
    assert redis.eval_calls == []
    assert "203.0.113.9" not in key
    assert "Mozilla" not in key


@pytest.mark.asyncio
async def test_repeat_view_is_recorded_as_not_unique(captured):
    service = JobViewTelemetryService(
        redis_client=FakeRedis(stored=False),
        session_factory=FakeFactory(FakeSession()),
    )
    assert await service.record_view(_request(), _job()) is True
    assert captured[0]["is_unique"] is False


@pytest.mark.asyncio
async def test_redis_outage_records_unverified_instead_of_guessing(captured):
    service = JobViewTelemetryService(
        redis_client=FakeRedis(error=ConnectionError("redis down")),
        session_factory=FakeFactory(FakeSession()),
    )
    assert await service.record_view(_request(), _job()) is True
    assert captured[0]["is_unique"] is None


@pytest.mark.asyncio
async def test_missing_redis_client_records_unverified(captured):
    service = JobViewTelemetryService(
        redis_client=None,
        session_factory=FakeFactory(FakeSession()),
    )
    assert await service.record_view(_request(), _job()) is True
    assert captured[0]["is_unique"] is None


@pytest.mark.asyncio
async def test_database_failure_is_swallowed(captured, monkeypatch):
    async def boom(self, **kwargs):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(AnalyticsRepository, "record_view", boom)
    service = JobViewTelemetryService(
        redis_client=FakeRedis(),
        session_factory=FakeFactory(FakeSession()),
    )
    assert await service.record_view(_request(), _job()) is False


@pytest.mark.asyncio
async def test_commit_failure_rolls_back_and_releases_claim(captured):
    redis = FakeRedis()
    session = FakeSession(commit_error=RuntimeError("commit failed"))
    service = JobViewTelemetryService(
        redis_client=redis,
        session_factory=FakeFactory(session),
    )

    assert await service.record_view(_request(), _job()) is False

    assert session.rollbacks == 1
    assert len(redis.eval_calls) == 1
    assert redis.eval_calls[0]["key"] == redis.calls[0]["key"]
    assert redis.eval_calls[0]["token"] == redis.calls[0]["value"]
    assert redis.values == {}


@pytest.mark.asyncio
async def test_repository_failure_rolls_back_and_releases_claim(
    captured, monkeypatch
):
    async def boom(self, **kwargs):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(AnalyticsRepository, "record_view", boom)
    redis = FakeRedis()
    session = FakeSession()
    service = JobViewTelemetryService(
        redis_client=redis,
        session_factory=FakeFactory(session),
    )

    assert await service.record_view(_request(), _job()) is False

    assert session.rollbacks == 1
    assert len(redis.eval_calls) == 1
    assert redis.values == {}


@pytest.mark.asyncio
async def test_failed_rollback_keeps_claim_for_uncertain_persistence(
    captured,
):
    redis = FakeRedis()
    session = FakeSession(
        commit_error=RuntimeError("commit failed"),
        rollback_error=RuntimeError("connection lost"),
    )
    service = JobViewTelemetryService(
        redis_client=redis,
        session_factory=FakeFactory(session),
    )

    assert await service.record_view(_request(), _job()) is False

    assert session.rollbacks == 1
    assert redis.eval_calls == []
    assert len(redis.values) == 1


@pytest.mark.asyncio
async def test_claim_release_survives_redis_outage(captured):
    redis = FakeRedis(eval_error=ConnectionError("redis down"))
    session = FakeSession(commit_error=RuntimeError("commit failed"))
    service = JobViewTelemetryService(
        redis_client=redis,
        session_factory=FakeFactory(session),
    )

    assert await service.record_view(_request(), _job()) is False
    assert session.rollbacks == 1
    assert len(redis.eval_calls) == 1


@pytest.mark.asyncio
async def test_concurrent_same_visitor_records_single_unique(captured):
    redis = FakeRedis()
    service = JobViewTelemetryService(
        redis_client=redis,
        session_factory=FakeFactory(FakeSession()),
    )
    job = _job()

    results = await asyncio.gather(
        service.record_view(_request(), job),
        service.record_view(_request(), job),
    )

    assert results == [True, True]
    assert [call["is_unique"] for call in captured] == [True, False]
    assert len(redis.values) == 1


@pytest.mark.asyncio
async def test_concurrent_distinct_visitors_are_both_unique(captured):
    redis = FakeRedis()
    service = JobViewTelemetryService(
        redis_client=redis,
        session_factory=FakeFactory(FakeSession()),
    )
    job = _job()

    await asyncio.gather(
        service.record_view(_request(ip="203.0.113.9"), job),
        service.record_view(_request(ip="198.51.100.7"), job),
    )

    assert [call["is_unique"] for call in captured] == [True, True]
    assert len(redis.values) == 2


@pytest.mark.asyncio
async def test_failed_claim_does_not_delete_another_owners_key(captured):
    redis = FakeRedis()
    session = FakeSession(commit_error=RuntimeError("commit failed"))
    service = JobViewTelemetryService(
        redis_client=redis,
        session_factory=FakeFactory(session),
    )

    assert await service.record_view(_request(), _job()) is False
    # A concurrent request re-claimed the same key before our rollback ran.
    key = redis.calls[0]["key"]
    redis.values[key] = "another-owner-token"
    assert await service._release_claim(key, redis.calls[0]["value"]) is False
    assert redis.values[key] == "another-owner-token"


def test_visitor_digest_is_stable_per_day_and_differs_by_visitor():
    service = JobViewTelemetryService(redis_client=None)
    job_id = uuid.uuid4()
    day = "2026-01-01"
    first = service._visitor_digest(job_id, _request(), day)
    second = service._visitor_digest(job_id, _request(), day)
    other_ip = service._visitor_digest(
        job_id, _request(ip="198.51.100.7"), day
    )
    other_day = service._visitor_digest(job_id, _request(), "2026-01-02")

    assert first == second
    assert first != other_ip
    assert first != other_day
    assert len(first) == 64
