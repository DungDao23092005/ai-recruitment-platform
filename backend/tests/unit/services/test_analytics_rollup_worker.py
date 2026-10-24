from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.repositories.analytics_repository import AnalyticsRepository
from app.services.analytics_rollup_worker import AnalyticsRollupWorker
from app.services.analytics_time import day_start_utc, vietnam_today


class FakeSession:
    def __init__(self, *, lock_result=1) -> None:
        self.lock_result = lock_result
        self.scalar_calls = []
        self.execute_calls = []
        self.commits = 0
        self.rollbacks = 0
        self.scalar_error = None

    async def scalar(self, statement, params=None):
        self.scalar_calls.append((str(statement), params))
        if self.scalar_error is not None:
            raise self.scalar_error
        return self.lock_result

    async def execute(self, statement, params=None):
        self.execute_calls.append((str(statement), params))
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
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


def _row(job_id, company_id, total=3, unique=2, unverified=1):
    return {
        "job_id": job_id,
        "company_id": company_id,
        "total_views": total,
        "unique_views": unique,
        "unverified_views": unverified,
    }


@pytest.fixture
def repository_stub(monkeypatch):
    state = {
        "raw_by_day": {},
        "flags": {},
        "raw_calls": [],
        "upserts": [],
        "flag_calls": [],
        "marked": [],
        "deleted": [],
    }

    async def raw_for_day(self, start, end):
        state["raw_calls"].append(start)
        from app.services.analytics_time import VIETNAM_TZ

        return state["raw_by_day"].get(start.astimezone(VIETNAM_TZ).date(), [])

    async def flags(self, view_date):
        state["flag_calls"].append(view_date)
        return state["flags"].get(view_date, {})

    async def upsert(self, **kwargs):
        state["upserts"].append(kwargs)

    async def mark(self, cutoff_date, now):
        state["marked"].append((cutoff_date, now))
        return 2

    async def delete(self, cutoff_utc):
        state["deleted"].append(cutoff_utc)
        return 5

    monkeypatch.setattr(
        AnalyticsRepository, "raw_view_counts_for_day", raw_for_day
    )
    monkeypatch.setattr(
        AnalyticsRepository, "aggregate_flags_for_date", flags
    )
    monkeypatch.setattr(
        AnalyticsRepository, "upsert_daily_aggregate", upsert
    )
    monkeypatch.setattr(AnalyticsRepository, "mark_raw_pruned", mark)
    monkeypatch.setattr(AnalyticsRepository, "delete_pruned_events", delete)
    return state


def _worker(session, *, lookback=2, retention=0):
    return AnalyticsRollupWorker(
        session_factory=FakeFactory(session),
        interval_seconds=1,
        lookback_days=lookback,
        retention_days=retention,
    )


@pytest.mark.asyncio
async def test_lock_denied_skips_the_entire_pass(repository_stub):
    session = FakeSession(lock_result=-1)
    worker = _worker(session)
    result = await worker.run_once()
    assert result["skipped"] is True
    assert result["days"] == 0
    assert repository_stub["raw_calls"] == []
    assert session.commits <= 1
    assert worker.health_snapshot()["last_outcome"] == "skipped"


@pytest.mark.asyncio
async def test_lock_query_failure_is_a_failed_run(repository_stub):
    session = FakeSession()
    session.scalar_error = RuntimeError("db down")
    worker = _worker(session)

    with pytest.raises(RuntimeError):
        await worker.run_once()

    assert repository_stub["raw_calls"] == []
    assert session.rollbacks >= 1
    snapshot = worker.health_snapshot()
    assert snapshot["last_outcome"] == "failure"
    assert snapshot["consecutive_failures"] == 1
    assert snapshot["last_error_type"] == "RuntimeError"


@pytest.mark.asyncio
async def test_aggregates_completed_days_only_and_backfills(repository_stub):
    today = vietnam_today()
    yesterday = today - timedelta(days=1)
    older = today - timedelta(days=2)
    job_id = uuid.uuid4()
    company_id = uuid.uuid4()
    repository_stub["raw_by_day"] = {
        yesterday: [_row(job_id, company_id, total=5, unique=3, unverified=1)],
        # older day is missing entirely: this exercises backfill (no crash).
    }

    session = FakeSession()
    result = await _worker(session, lookback=3).run_once()

    assert result["days"] == 1
    assert len(repository_stub["upserts"]) == 1
    upsert = repository_stub["upserts"][0]
    assert upsert["job_id"] == job_id
    assert upsert["view_date"] == yesterday
    assert upsert["total_views"] == 5
    assert upsert["unique_views"] == 3
    assert upsert["unverified_views"] == 1
    assert day_start_utc(today) not in repository_stub["raw_calls"]


@pytest.mark.asyncio
async def test_raw_pruned_aggregates_are_never_recomputed(repository_stub):
    today = vietnam_today()
    day = today - timedelta(days=1)
    job_id = uuid.uuid4()
    repository_stub["raw_by_day"] = {day: [_row(job_id, uuid.uuid4())]}
    repository_stub["flags"] = {day: {job_id: True}}

    result = await _worker(FakeSession(), lookback=1).run_once()

    assert result["days"] == 0
    assert repository_stub["upserts"] == []


@pytest.mark.asyncio
async def test_unpruned_aggregates_are_recomputed_idempotently(repository_stub):
    today = vietnam_today()
    day = today - timedelta(days=1)
    job_id = uuid.uuid4()
    row = _row(job_id, uuid.uuid4())
    repository_stub["raw_by_day"] = {day: [row]}
    repository_stub["flags"] = {day: {job_id: False}}

    worker = _worker(FakeSession(), lookback=1)
    first = await worker.run_once()
    second = await worker.run_once()

    assert first["days"] == 1
    assert second["days"] == 1
    assert len(repository_stub["upserts"]) == 2
    assert repository_stub["upserts"][0]["total_views"] == row["total_views"]
    assert repository_stub["upserts"][1]["total_views"] == row["total_views"]


@pytest.mark.asyncio
async def test_retention_marks_then_deletes_old_pruned_events(repository_stub):
    session = FakeSession()
    today = vietnam_today()
    result = await _worker(session, lookback=0, retention=7).run_once()

    cutoff = today - timedelta(days=7)
    assert repository_stub["marked"][0][0] == cutoff
    assert repository_stub["deleted"]
    assert result["pruned_events"] == 5
    # Mark and delete are committed separately so a crash cannot delete raw
    # events whose aggregate was never durably flagged.
    assert session.commits >= 3


@pytest.mark.asyncio
async def test_retention_disabled_does_not_touch_raw_events(repository_stub):
    result = await _worker(FakeSession(), lookback=0, retention=0).run_once()
    assert result["pruned_events"] == 0
    assert repository_stub["marked"] == []
    assert repository_stub["deleted"] == []


@pytest.mark.asyncio
async def test_zero_lookback_still_runs_retention(repository_stub):
    result = await _worker(
        FakeSession(), lookback=0, retention=30
    ).run_once()
    assert repository_stub["raw_calls"] == []
    assert repository_stub["marked"]


@pytest.mark.asyncio
async def test_worker_releases_the_app_lock_on_success(repository_stub):
    session = FakeSession()
    await _worker(session, lookback=0).run_once()
    assert any("sp_releaseapplock" in call[0] for call in session.scalar_calls)
    assert session.rollbacks >= 1


@pytest.mark.asyncio
async def test_failed_lock_release_discards_the_connection(repository_stub):
    class ReleaseFailSession(FakeSession):
        async def connection(self):
            class Connection:
                async def invalidate(self):
                    self.invalidated = True

            self.connection_obj = Connection()
            self.connection_obj.invalidated = False
            return self.connection_obj

        async def scalar(self, statement, params=None):
            self.scalar_calls.append((str(statement), params))
            if "sp_releaseapplock" in str(statement):
                return -1
            return self.lock_result

    session = ReleaseFailSession()
    await _worker(session, lookback=0).run_once()

    assert session.connection_obj.invalidated is True
    assert session.commits == 1
