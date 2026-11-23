import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.domain.enums import JobStatus
from app.models import Job
from app.services.job_expiration_worker import JobExpirationWorker


def make_mock_session_factory():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.scalar = AsyncMock(return_value=0)
    session.bind = MagicMock()
    session.bind.dialect.name = "mssql"

    class AsyncContextManager:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    factory = MagicMock(return_value=AsyncContextManager())
    return factory, session


@pytest.mark.asyncio
async def test_job_expiration_worker_run_once_materializes_and_syncs():
    factory, session = make_mock_session_factory()
    vector_repo = MagicMock()
    vector_repo.set_payload = AsyncMock()

    job_id = uuid.uuid4()
    # Mock Step 1: select returns [job_id]
    mock_select_result = MagicMock()
    mock_select_result.scalars.return_value.all.return_value = [job_id]

    # Mock Step 2: select returns [job_id] for sync
    mock_sync_result = MagicMock()
    mock_sync_result.scalars.return_value.all.return_value = [job_id]

    session.execute.side_effect = [mock_select_result, None, mock_sync_result, None]

    worker = JobExpirationWorker(
        session_factory=factory,
        vector_repository=vector_repo,
        batch_size=50,
        sync_batch_size=50,
    )

    now = datetime.now(timezone.utc)
    result = await worker.run_once(now=now)

    assert result["skipped"] is False
    assert result["expired"] == 1
    assert result["synced"] == 1

    vector_repo.set_payload.assert_awaited_once_with(
        collection_name="jobs",
        payload={"status": "expired"},
        points=[str(job_id)],
    )


@pytest.mark.asyncio
async def test_job_expiration_worker_skips_when_lock_not_acquired():
    factory, session = make_mock_session_factory()
    session.scalar.return_value = -1  # Lock busy / failed

    worker = JobExpirationWorker(
        session_factory=factory,
    )

    result = await worker.run_once()
    assert result["skipped"] is True
    assert result["expired"] == 0
    assert result["synced"] == 0


@pytest.mark.asyncio
async def test_job_expiration_worker_qdrant_failure_isolation():
    factory, session = make_mock_session_factory()
    vector_repo = MagicMock()
    vector_repo.set_payload = AsyncMock(side_effect=RuntimeError("Qdrant unavailable"))

    job_id = uuid.uuid4()
    mock_select_result = MagicMock()
    mock_select_result.scalars.return_value.all.return_value = [job_id]
    mock_sync_result = MagicMock()
    mock_sync_result.scalars.return_value.all.return_value = [job_id]

    session.execute.side_effect = [mock_select_result, None, mock_sync_result]

    worker = JobExpirationWorker(
        session_factory=factory,
        vector_repository=vector_repo,
    )

    result = await worker.run_once()
    assert result["skipped"] is False
    assert result["expired"] == 1
    assert result["synced"] == 0  # 0 synced due to graceful isolation


@pytest.mark.asyncio
async def test_job_expiration_worker_health_snapshot():
    factory, _ = make_mock_session_factory()
    worker = JobExpirationWorker(session_factory=factory)
    snapshot = worker.health_snapshot()

    assert "enabled" in snapshot
    assert "running" in snapshot
    assert snapshot["last_outcome"] == "not_started"


# ---------------------------------------------------------------------------
# Stateful In-Memory Test Infrastructure for Concurrency & Resilience Tests
# ---------------------------------------------------------------------------

class InMemoryJob:
    def __init__(
        self,
        job_id: uuid.UUID | None = None,
        status: JobStatus = JobStatus.PUBLISHED,
        is_qdrant_synced: bool = False,
        is_deleted: bool = False,
        expires_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        self.id = job_id or uuid.uuid4()
        self.status = status
        self.is_qdrant_synced = is_qdrant_synced
        self.is_deleted = is_deleted
        self.expires_at = expires_at
        self.updated_at = updated_at or datetime.now(timezone.utc)


class StatefulJobDB:
    def __init__(self, jobs: list[InMemoryJob] | None = None):
        self.jobs: dict[uuid.UUID, InMemoryJob] = {
            j.id: j for j in (jobs or [])
        }
        self.events: list[tuple[str, Any]] = []
        self.lock_owner: int | None = None
        self.session_counter = 0

    def make_session_factory(self):
        db = self

        class StatefulSession:
            def __init__(self, session_id: int):
                self.session_id = session_id
                self.bind = MagicMock()
                self.bind.dialect.name = "mssql"
                self.staged_updates: list[tuple[dict[str, Any], list[uuid.UUID]]] = []

            async def __aenter__(self):
                db.events.append(("session_enter", self.session_id))
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                db.events.append(("session_exit", self.session_id))

            async def scalar(self, stmt, params=None):
                sql = str(stmt)
                if "sp_getapplock" in sql:
                    if db.lock_owner is None:
                        db.lock_owner = self.session_id
                        db.events.append(("lock_acquired", self.session_id))
                        return 0
                    elif db.lock_owner == self.session_id:
                        return 0
                    else:
                        db.events.append(("lock_rejected", self.session_id))
                        return -1
                elif "sp_releaseapplock" in sql:
                    if db.lock_owner == self.session_id:
                        db.lock_owner = None
                        db.events.append(("lock_released", self.session_id))
                        return 0
                    return 0
                return 0

            async def execute(self, stmt):
                from sqlalchemy.sql import Select, Update

                if isinstance(stmt, Select):
                    db.events.append(("execute_select", self.session_id))
                    params = stmt.compile().params
                    status_param = None
                    for k, v in params.items():
                        if "status" in k:
                            status_param = v
                            break

                    limit = stmt._limit or 50

                    if status_param == JobStatus.PUBLISHED:
                        matched = [
                            j for j in db.jobs.values()
                            if j.status == JobStatus.PUBLISHED
                            and not j.is_deleted
                            and j.expires_at is not None
                        ]
                        matched.sort(
                            key=lambda x: (
                                x.expires_at or datetime.min.replace(tzinfo=timezone.utc),
                                x.id,
                            )
                        )
                        selected = matched[:limit]
                    else:
                        excluded = set()
                        for k, v in params.items():
                            if "id" in k and isinstance(v, (list, tuple, set)):
                                excluded.update(v)

                        matched = [
                            j for j in db.jobs.values()
                            if j.status == JobStatus.EXPIRED
                            and not j.is_qdrant_synced
                            and not j.is_deleted
                            and j.id not in excluded
                        ]
                        matched.sort(key=lambda x: (x.updated_at, x.id))
                        selected = matched[:limit]

                    mock_res = MagicMock()
                    mock_res.scalars.return_value.all.return_value = [
                        j.id for j in selected
                    ]
                    return mock_res

                elif isinstance(stmt, Update):
                    db.events.append(("execute_update", self.session_id))
                    params = stmt.compile().params
                    target_ids = []
                    for k, v in params.items():
                        if "id" in k and isinstance(v, (list, tuple, set)):
                            target_ids = list(v)
                            break
                    self.staged_updates.append((params, target_ids))
                    return None

            async def commit(self):
                db.events.append(("commit", self.session_id))
                for params, target_ids in self.staged_updates:
                    if params.get("is_qdrant_synced") is True:
                        for tid in target_ids:
                            if tid in db.jobs:
                                db.jobs[tid].is_qdrant_synced = True
                    elif params.get("status") == JobStatus.EXPIRED:
                        for tid in target_ids:
                            if tid in db.jobs:
                                db.jobs[tid].status = JobStatus.EXPIRED
                                db.jobs[tid].is_qdrant_synced = False
                                if "updated_at" in params and params["updated_at"] is not None:
                                    db.jobs[tid].updated_at = params["updated_at"]
                self.staged_updates.clear()

            async def rollback(self):
                db.events.append(("rollback", self.session_id))
                self.staged_updates.clear()

        def factory():
            db.session_counter += 1
            return StatefulSession(db.session_counter)

        return factory


# ---------------------------------------------------------------------------
# Section 3 & 4 Verification Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_session_closed_before_qdrant_and_checkpoint_separate_session():
    """Verify that read session is closed before Qdrant network call, and checkpoint uses a separate session."""
    now = datetime.now(timezone.utc)
    job = InMemoryJob(
        status=JobStatus.EXPIRED,
        is_qdrant_synced=False,
        updated_at=now - timedelta(hours=1),
    )
    db = StatefulJobDB([job])
    factory = db.make_session_factory()

    vector_repo = MagicMock()

    async def mock_set_payload(**kwargs):
        db.events.append(("qdrant_network_call", kwargs.get("points")))

    vector_repo.set_payload = AsyncMock(side_effect=mock_set_payload)

    worker = JobExpirationWorker(
        session_factory=factory,
        vector_repository=vector_repo,
    )

    result = await worker.run_once()
    assert result["synced"] == 1

    event_names = [e[0] for e in db.events]
    assert "qdrant_network_call" in event_names
    qdrant_index = event_names.index("qdrant_network_call")

    # Lock session is session 1
    # Materialize read session is session 2 (exits because no published expired jobs)
    # Reconcile read session is session 3
    # Qdrant network call occurs AFTER session 3 exits
    # Checkpoint session is session 4 (occurs AFTER Qdrant network call)

    session_3_exit_index = len(event_names) - 1 - event_names[::-1].index("session_exit")
    # Find the session_exit event for the read session right before qdrant_network_call
    pre_qdrant_events = db.events[:qdrant_index]
    post_qdrant_events = db.events[qdrant_index + 1:]

    # Assert that read session exited before Qdrant call
    read_exits = [e for e in pre_qdrant_events if e[0] == "session_exit"]
    assert len(read_exits) >= 1

    # Assert that checkpoint session entered AFTER Qdrant call
    post_enters = [e for e in post_qdrant_events if e[0] == "session_enter"]
    assert len(post_enters) >= 1
    checkpoint_session_id = post_enters[0][1]

    # Checkpoint session id must be distinct from read session id
    read_session_id = [e for e in pre_qdrant_events if e[0] == "execute_select"][-1][1]
    assert checkpoint_session_id != read_session_id

    # Lock session is session 1 and must be released only at the end
    lock_release = [e for e in db.events if e[0] == "lock_released"]
    assert len(lock_release) == 1
    assert db.events.index(lock_release[0]) > qdrant_index


@pytest.mark.asyncio
async def test_pending_jobs_discoverable_after_24h_qdrant_outage():
    """1. Pending jobs remain discoverable after a Qdrant outage lasting more than 24 hours."""
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(hours=25)

    job1 = InMemoryJob(
        status=JobStatus.EXPIRED,
        is_qdrant_synced=False,
        updated_at=old_time,
    )
    job2 = InMemoryJob(
        status=JobStatus.EXPIRED,
        is_qdrant_synced=False,
        updated_at=old_time + timedelta(minutes=5),
    )

    db = StatefulJobDB([job1, job2])
    factory = db.make_session_factory()

    vector_repo = MagicMock()
    vector_repo.set_payload = AsyncMock()

    worker = JobExpirationWorker(
        session_factory=factory,
        vector_repository=vector_repo,
    )

    result = await worker.run_once(now=now)
    assert result["synced"] == 2
    assert db.jobs[job1.id].is_qdrant_synced is True
    assert db.jobs[job2.id].is_qdrant_synced is True

    vector_repo.set_payload.assert_awaited_once_with(
        collection_name="jobs",
        payload={"status": "expired"},
        points=[str(job1.id), str(job2.id)],
    )


@pytest.mark.asyncio
async def test_worker_restart_recovery():
    """2. A newly instantiated worker can recover pending jobs after a worker restart."""
    now = datetime.now(timezone.utc)
    job = InMemoryJob(
        status=JobStatus.EXPIRED,
        is_qdrant_synced=False,
        updated_at=now - timedelta(minutes=10),
    )
    db = StatefulJobDB([job])
    factory = db.make_session_factory()

    # Worker 1 terminates without syncing
    worker_1 = JobExpirationWorker(session_factory=factory)
    del worker_1

    # Worker 2 is freshly instantiated (worker restart simulation)
    vector_repo = MagicMock()
    vector_repo.set_payload = AsyncMock()

    worker_2 = JobExpirationWorker(
        session_factory=factory,
        vector_repository=vector_repo,
    )

    result = await worker_2.run_once(now=now)
    assert result["synced"] == 1
    assert db.jobs[job.id].is_qdrant_synced is True


@pytest.mark.asyncio
async def test_draining_more_than_100_pending_jobs_across_multiple_batches():
    """3. More than 100 pending jobs are drained across multiple batches."""
    now = datetime.now(timezone.utc)
    # Create 120 pending expired jobs
    jobs = [
        InMemoryJob(
            status=JobStatus.EXPIRED,
            is_qdrant_synced=False,
            updated_at=now - timedelta(minutes=i),
        )
        for i in range(120, 0, -1)
    ]

    db = StatefulJobDB(jobs)
    factory = db.make_session_factory()

    vector_repo = MagicMock()
    vector_repo.set_payload = AsyncMock()

    worker = JobExpirationWorker(
        session_factory=factory,
        vector_repository=vector_repo,
        sync_batch_size=50,
    )

    result = await worker.run_once(now=now)
    assert result["synced"] == 120
    assert all(j.is_qdrant_synced for j in db.jobs.values())

    # 120 jobs with batch_size=50 should result in 3 Qdrant batch calls: 50, 50, 20
    assert vector_repo.set_payload.await_count == 3
    call_batch_sizes = [
        len(call.kwargs["points"]) for call in vector_repo.set_payload.await_args_list
    ]
    assert call_batch_sizes == [50, 50, 20]


@pytest.mark.asyncio
async def test_deterministic_ordering_updated_at_asc_id_asc():
    """4. Pending jobs use deterministic updated_at ASC, id ASC ordering."""
    base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    id_low = uuid.UUID("11111111-1111-1111-1111-111111111111")
    id_high = uuid.UUID("99999999-9999-9999-9999-999999999999")

    # Tie on updated_at: id_low should come before id_high
    job_tie_high = InMemoryJob(
        job_id=id_high,
        status=JobStatus.EXPIRED,
        is_qdrant_synced=False,
        updated_at=base_time,
    )
    job_tie_low = InMemoryJob(
        job_id=id_low,
        status=JobStatus.EXPIRED,
        is_qdrant_synced=False,
        updated_at=base_time,
    )
    job_old = InMemoryJob(
        job_id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
        status=JobStatus.EXPIRED,
        is_qdrant_synced=False,
        updated_at=base_time - timedelta(hours=1),
    )
    job_new = InMemoryJob(
        job_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        status=JobStatus.EXPIRED,
        is_qdrant_synced=False,
        updated_at=base_time + timedelta(hours=1),
    )

    db = StatefulJobDB([job_tie_high, job_tie_low, job_old, job_new])
    factory = db.make_session_factory()

    vector_repo = MagicMock()
    vector_repo.set_payload = AsyncMock()

    worker = JobExpirationWorker(
        session_factory=factory,
        vector_repository=vector_repo,
        sync_batch_size=50,
    )

    result = await worker.run_once()
    assert result["synced"] == 4

    dispatched_points = vector_repo.set_payload.await_args.kwargs["points"]
    expected_order = [
        str(job_old.id),
        str(id_low),
        str(id_high),
        str(job_new.id),
    ]
    assert dispatched_points == expected_order


@pytest.mark.asyncio
async def test_partial_qdrant_failure_checkpoints_only_acknowledged_ids():
    """5. Partial Qdrant failures checkpoint only acknowledged IDs."""
    now = datetime.now(timezone.utc)
    job1 = InMemoryJob(status=JobStatus.EXPIRED, is_qdrant_synced=False, updated_at=now)
    job2 = InMemoryJob(status=JobStatus.EXPIRED, is_qdrant_synced=False, updated_at=now)
    job3 = InMemoryJob(status=JobStatus.EXPIRED, is_qdrant_synced=False, updated_at=now)

    db = StatefulJobDB([job1, job2, job3])
    factory = db.make_session_factory()

    vector_repo = MagicMock()

    async def mock_set_payload(**kwargs):
        points = kwargs.get("points", [])
        if len(points) > 1:
            # Batch fails with a non-transient point error
            raise ValueError(f"Batch rejected due to invalid point {job2.id}")
        if str(job2.id) in points:
            # Point 2 fails
            raise ValueError(f"Malformed point {job2.id}")
        # Points 1 & 3 succeed
        return None

    vector_repo.set_payload = AsyncMock(side_effect=mock_set_payload)

    worker = JobExpirationWorker(
        session_factory=factory,
        vector_repository=vector_repo,
    )

    result = await worker.run_once()
    assert result["synced"] == 2

    # Acknowledged points must be marked True
    assert db.jobs[job1.id].is_qdrant_synced is True
    assert db.jobs[job3.id].is_qdrant_synced is True

    # Failed point must remain False
    assert db.jobs[job2.id].is_qdrant_synced is False


@pytest.mark.asyncio
async def test_persistent_poison_point_does_not_starve_healthy_pending_jobs():
    """6. A persistent poison point does not starve healthy pending jobs across batches."""
    now = datetime.now(timezone.utc)
    poison_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    poison_job = InMemoryJob(
        job_id=poison_id,
        status=JobStatus.EXPIRED,
        is_qdrant_synced=False,
        updated_at=now - timedelta(days=1),  # Oldest job
    )
    # 104 healthy jobs
    healthy_jobs = [
        InMemoryJob(
            status=JobStatus.EXPIRED,
            is_qdrant_synced=False,
            updated_at=now - timedelta(minutes=i),
        )
        for i in range(104, 0, -1)
    ]

    db = StatefulJobDB([poison_job] + healthy_jobs)
    factory = db.make_session_factory()

    vector_repo = MagicMock()

    async def mock_set_payload(**kwargs):
        points = kwargs.get("points", [])
        if str(poison_id) in points:
            # Fails both batch and point sync
            raise ValueError(f"Poison point {poison_id} corrupted")
        return None

    vector_repo.set_payload = AsyncMock(side_effect=mock_set_payload)

    worker = JobExpirationWorker(
        session_factory=factory,
        vector_repository=vector_repo,
        sync_batch_size=50,
    )

    result = await worker.run_once()

    # All 104 healthy jobs must be synced without being starved by the poison point
    assert result["synced"] == 104
    assert db.jobs[poison_id].is_qdrant_synced is False
    assert all(
        j.is_qdrant_synced for j in db.jobs.values() if j.id != poison_id
    )


@pytest.mark.asyncio
async def test_is_qdrant_synced_transitions_only_after_acknowledgement():
    """7. is_qdrant_synced transitions from False to True only after successful acknowledgement."""
    now = datetime.now(timezone.utc)
    job = InMemoryJob(status=JobStatus.EXPIRED, is_qdrant_synced=False, updated_at=now)
    db = StatefulJobDB([job])
    factory = db.make_session_factory()

    vector_repo = MagicMock()
    # First attempt: fails
    vector_repo.set_payload = AsyncMock(side_effect=ConnectionError("Temporarily unavailable"))

    worker = JobExpirationWorker(
        session_factory=factory,
        vector_repository=vector_repo,
    )

    # Pass 1: fails
    res1 = await worker.run_once()
    assert res1["synced"] == 0
    assert db.jobs[job.id].is_qdrant_synced is False

    # Pass 2: succeeds
    vector_repo.set_payload = AsyncMock(return_value=None)
    res2 = await worker.run_once()
    assert res2["synced"] == 1
    assert db.jobs[job.id].is_qdrant_synced is True


@pytest.mark.asyncio
async def test_multiple_workers_respect_distributed_application_lock():
    """8. Multiple workers correctly respect the distributed application lock."""
    now = datetime.now(timezone.utc)
    job = InMemoryJob(status=JobStatus.EXPIRED, is_qdrant_synced=False, updated_at=now)
    db = StatefulJobDB([job])
    factory = db.make_session_factory()

    vector_repo = MagicMock()
    vector_repo.set_payload = AsyncMock()

    worker_a = JobExpirationWorker(session_factory=factory, vector_repository=vector_repo)
    worker_b = JobExpirationWorker(session_factory=factory, vector_repository=vector_repo)

    # Acquire lock manually under session 999
    db.lock_owner = 999

    # Worker B tries to run, but cannot acquire lock
    res_b = await worker_b.run_once()
    assert res_b["skipped"] is True
    assert res_b["synced"] == 0

    # Release lock
    db.lock_owner = None

    # Now Worker A can run and acquire lock
    res_a = await worker_a.run_once()
    assert res_a["skipped"] is False
    assert res_a["synced"] == 1


@pytest.mark.asyncio
async def test_crash_after_qdrant_acknowledgement_safely_retried():
    """Crash after Qdrant acknowledgement but before SQL checkpoint is safely retried and idempotent."""
    now = datetime.now(timezone.utc)
    job = InMemoryJob(status=JobStatus.EXPIRED, is_qdrant_synced=False, updated_at=now)
    db = StatefulJobDB([job])
    factory = db.make_session_factory()

    vector_repo = MagicMock()
    vector_repo.set_payload = AsyncMock()

    worker = JobExpirationWorker(session_factory=factory, vector_repository=vector_repo)

    # Patch session factory to raise during checkpoint commit on pass 1
    original_session = factory

    attempt = 0

    def faulty_factory():
        nonlocal attempt
        s = original_session()
        original_commit = s.commit

        async def faulty_commit():
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise RuntimeError("Simulated DB crash during checkpoint commit")
            return await original_commit()

        s.commit = faulty_commit
        return s

    worker._session_factory = faulty_factory

    with pytest.raises(RuntimeError, match="Simulated DB crash"):
        await worker.run_once()

    # Job is still unsynced in SQL
    assert db.jobs[job.id].is_qdrant_synced is False

    # Pass 2: worker retries, calls Qdrant idempotently and successfully checkpoints
    worker._session_factory = factory
    res = await worker.run_once()
    assert res["synced"] == 1
    assert db.jobs[job.id].is_qdrant_synced is True


@pytest.mark.asyncio
async def test_repeated_processing_is_idempotent():
    """Repeated processing is idempotent: subsequent runs find 0 pending jobs."""
    now = datetime.now(timezone.utc)
    job = InMemoryJob(status=JobStatus.EXPIRED, is_qdrant_synced=False, updated_at=now)
    db = StatefulJobDB([job])
    factory = db.make_session_factory()

    vector_repo = MagicMock()
    vector_repo.set_payload = AsyncMock()

    worker = JobExpirationWorker(session_factory=factory, vector_repository=vector_repo)

    res1 = await worker.run_once()
    assert res1["synced"] == 1
    assert vector_repo.set_payload.await_count == 1

    # Second pass immediately after
    res2 = await worker.run_once()
    assert res2["synced"] == 0
    assert res2["expired"] == 0
    # Qdrant must not be called again
    assert vector_repo.set_payload.await_count == 1


@pytest.mark.asyncio
async def test_worker_cancellation_releases_lock():
    """Worker cancellation during execution safely releases the application lock."""
    db = StatefulJobDB([])
    factory = db.make_session_factory()

    worker = JobExpirationWorker(session_factory=factory)

    # Simulate CancelledError inside _materialize_expired_jobs
    with patch.object(
        worker, "_materialize_expired_jobs", side_effect=asyncio.CancelledError()
    ):
        with pytest.raises(asyncio.CancelledError):
            await worker.run_once()

    # Lock must be released
    assert db.lock_owner is None
    lock_releases = [e for e in db.events if e[0] == "lock_released"]
    assert len(lock_releases) == 1


@pytest.mark.asyncio
async def test_transient_service_error_aborts_without_point_fallback():
    """Transient service-wide errors abort the pass without point-by-point fallback."""
    now = datetime.now(timezone.utc)
    job1 = InMemoryJob(status=JobStatus.EXPIRED, is_qdrant_synced=False, updated_at=now)
    job2 = InMemoryJob(status=JobStatus.EXPIRED, is_qdrant_synced=False, updated_at=now)

    db = StatefulJobDB([job1, job2])
    factory = db.make_session_factory()

    vector_repo = MagicMock()
    vector_repo.set_payload = AsyncMock(
        side_effect=ConnectionError("Failed to connect to Qdrant on port 6333")
    )

    worker = JobExpirationWorker(
        session_factory=factory,
        vector_repository=vector_repo,
    )

    res = await worker.run_once()
    assert res["synced"] == 0

    # set_payload was called once for the batch and aborted immediately without fallback
    assert vector_repo.set_payload.await_count == 1
    # Both jobs remain unsynced
    assert db.jobs[job1.id].is_qdrant_synced is False
    assert db.jobs[job2.id].is_qdrant_synced is False


@pytest.mark.asyncio
async def test_job_expiration_schedules_coalesced_realtime_event():
    """Worker schedules a coalesced realtime event with affected_count after materializing expired jobs."""
    factory, session = make_mock_session_factory()
    vector_repo = MagicMock()
    vector_repo.set_payload = AsyncMock()

    job_ids = [uuid.uuid4(), uuid.uuid4()]
    mock_select_result = MagicMock()
    mock_select_result.scalars.return_value.all.return_value = job_ids
    mock_sync_result = MagicMock()
    mock_sync_result.scalars.return_value.all.return_value = []

    session.execute.side_effect = [mock_select_result, None, mock_sync_result]

    worker = JobExpirationWorker(
        session_factory=factory,
        vector_repository=vector_repo,
        batch_size=50,
    )

    with patch(
        "app.services.job_expiration_worker.schedule_job_listing_event"
    ) as mock_schedule:
        result = await worker.run_once()

        assert result["expired"] == 2
        mock_schedule.assert_called_once_with(
            session,
            action="expired",
            affected_count=2,
        )


@pytest.mark.asyncio
async def test_job_expiration_skips_realtime_event_when_zero_expired():
    """Worker does not schedule a realtime event if no jobs were materialized as expired."""
    factory, session = make_mock_session_factory()
    vector_repo = MagicMock()
    vector_repo.set_payload = AsyncMock()

    mock_select_result = MagicMock()
    mock_select_result.scalars.return_value.all.return_value = []
    mock_sync_result = MagicMock()
    mock_sync_result.scalars.return_value.all.return_value = []

    session.execute.side_effect = [mock_select_result, mock_sync_result]

    worker = JobExpirationWorker(
        session_factory=factory,
        vector_repository=vector_repo,
    )

    with patch(
        "app.services.job_expiration_worker.schedule_job_listing_event"
    ) as mock_schedule:
        result = await worker.run_once()

        assert result["expired"] == 0
        mock_schedule.assert_not_called()