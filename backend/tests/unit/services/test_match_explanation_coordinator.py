from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import suppress
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import (
    MatchExplanationIdempotencyConflictError,
    MatchExplanationRefreshError,
)
from app.domain.models.base import utc_now
from app.models.ai_match_explanation import (
    AIMatchExplanationApplicationLease,
    AIMatchExplanationIdempotency,
)
from app.services.match_explanation_coordinator import (
    LUA_FENCED_CACHE_PUBLISH,
    MatchExplanationCoordinator,
    _renew_sql_leases,
    build_idempotency_key,
    build_lock_key,
    hash_idempotency_key,
)


def _response(application_id: uuid.UUID):
    from app.schemas.ai_explanation import ApplicationMatchExplanationResponse

    return ApplicationMatchExplanationResponse(
        application_id=application_id,
        overall_score=80.0,
        score_breakdown={
            "overall_score": 80.0,
            "cosine_similarity": 0.7,
            "skill_coverage_score": 0.5,
            "preferred_skill_coverage_score": 0.2,
            "experience_match_score": 0.8,
            "education_score": 0.5,
            "project_score": 0.4,
        },
        summary="Fresh AI narrative.",
        summary_source="ai_generated",
        generated_at=utc_now(),
        cache_state="not_cached",
    )


class _FakeRedis:
    def __init__(self, values=None, *, ping_result=True):
        self.values = dict(values or {})
        self.ping_result = ping_result
        self.set_calls = []
        self.eval_calls = []
        self.eval_result = 1
        self.get_error = None
        self.set_error = None

    async def ping(self):
        return self.ping_result

    async def set(self, key, value, nx=False, ex=None):
        self.set_calls.append((key, value, nx, ex))
        if self.set_error is not None:
            raise self.set_error
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True

    async def get(self, key):
        if self.get_error is not None:
            raise self.get_error
        return self.values.get(key)

    async def eval(self, script, numkeys, *args):
        self.eval_calls.append((script, numkeys, args))
        return self.eval_result


class _Result:
    def __init__(self, *, scalar=None, rowcount=1):
        self._scalar = scalar
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._scalar


class _Transaction:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        self.session.begin_entered = True

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.session.commits += 1
        else:
            self.session.rollbacks += 1
        return False


class _Session:
    def __init__(self, results):
        self.results = list(results)
        self.commits = 0
        self.rollbacks = 0
        self.execute = AsyncMock(side_effect=self._execute)

    async def _execute(self, stmt):
        return self.results.pop(0)

    def begin(self):
        return _Transaction(self)


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestHeartbeatSQLRenewal:
    def test_both_leases_commit_atomically(self):
        session = _Session([_Result(rowcount=1), _Result(rowcount=1)])
        factory = lambda: _SessionContext(session)

        result = asyncio.run(
            _renew_sql_leases(
                factory,
                record_id=uuid.uuid4(),
                application_id=uuid.uuid4(),
                owner_token="token",
                lease_seconds=120,
            )
        )

        assert result is True
        assert session.commits == 1
        assert session.rollbacks == 0

    @pytest.mark.parametrize("idem_count,lease_count", [(1, 0), (0, 1)])
    def test_partial_renewal_rolls_back_and_returns_false(
        self, idem_count, lease_count
    ):
        session = _Session(
            [
                _Result(rowcount=idem_count),
                _Result(rowcount=lease_count),
            ]
        )
        factory = lambda: _SessionContext(session)

        result = asyncio.run(
            _renew_sql_leases(
                factory,
                record_id=uuid.uuid4(),
                application_id=uuid.uuid4(),
                owner_token="token",
                lease_seconds=120,
            )
        )

        assert result is False
        assert session.commits == 0
        assert session.rollbacks == 1


class TestIdempotencyCache:
    def test_user_scoped_hash_differs(self):
        key = "same-key"
        assert hash_idempotency_key(uuid.uuid4(), key) != hash_idempotency_key(
            uuid.uuid4(), key
        )
        assert len(hash_idempotency_key(uuid.uuid4(), key)) == 64

    def test_valid_cached_response_is_reported_as_cached(self):
        user_id = uuid.uuid4()
        application_id = uuid.uuid4()
        key_hash = hash_idempotency_key(user_id, "key")
        redis = _FakeRedis(
            {
                build_idempotency_key(user_id, key_hash): _response(
                    application_id
                ).model_dump_json()
            }
        )
        coordinator = MatchExplanationCoordinator(redis)

        result = asyncio.run(
            coordinator.read_idempotency_cache(
                user_id, key_hash, application_id
            )
        )

        assert result is not None
        assert result.cache_state == "cached"

    def test_malformed_cache_never_calls_provider(self):
        user_id = uuid.uuid4()
        key_hash = hash_idempotency_key(user_id, "key")
        redis = _FakeRedis(
            {build_idempotency_key(user_id, key_hash): "{not-json"}
        )
        coordinator = MatchExplanationCoordinator(redis)

        with pytest.raises(MatchExplanationRefreshError) as exc_info:
            asyncio.run(
                coordinator.read_idempotency_cache(
                    user_id, key_hash, uuid.uuid4()
                )
            )

        assert exc_info.value.http_status == 500
        assert exc_info.value.reason == "invalid_idempotency_cache"

    def test_cached_key_for_another_application_is_422(self):
        user_id = uuid.uuid4()
        cached_app = uuid.uuid4()
        key_hash = hash_idempotency_key(user_id, "key")
        redis = _FakeRedis(
            {
                build_idempotency_key(user_id, key_hash): _response(
                    cached_app
                ).model_dump_json()
            }
        )
        coordinator = MatchExplanationCoordinator(redis)

        with pytest.raises(MatchExplanationIdempotencyConflictError) as exc:
            asyncio.run(
                coordinator.read_idempotency_cache(
                    user_id, key_hash, uuid.uuid4()
                )
            )

        assert exc.value.http_status == 422


class TestFencedPublication:
    def test_publish_checks_owner_token_and_writes_both_keys(self):
        redis = _FakeRedis()
        coordinator = MatchExplanationCoordinator(
            redis,
            idempotency_ttl_seconds=86400,
        )
        application_id = uuid.uuid4()
        user_id = uuid.uuid4()
        key_hash = "hash"

        published = asyncio.run(
            coordinator.publish_fenced_cache(
                application_id=application_id,
                content_key="match_explanation:content",
                user_id=user_id,
                key_hash=key_hash,
                owner_token="owner",
                response=_response(application_id),
            )
        )

        assert published is True
        script, numkeys, args = redis.eval_calls[0]
        assert script == LUA_FENCED_CACHE_PUBLISH
        assert numkeys == 3
        assert args[0] == build_lock_key(application_id)
        assert args[1] == "match_explanation:content"
        assert args[2] == build_idempotency_key(user_id, key_hash)
        assert args[3] == "owner"
        assert args[5] == coordinator.cache.ttl_seconds
        assert args[6] == 86400

    def test_stale_worker_publish_result_zero_is_false(self):
        redis = _FakeRedis()
        redis.eval_result = 0
        coordinator = MatchExplanationCoordinator(redis)
        application_id = uuid.uuid4()

        published = asyncio.run(
            coordinator.publish_fenced_cache(
                application_id=application_id,
                content_key="content",
                user_id=uuid.uuid4(),
                key_hash="hash",
                owner_token="stale",
                response=_response(application_id),
            )
        )

        assert published is False

    def test_release_lock_uses_atomic_compare_and_delete(self):
        redis = _FakeRedis()
        coordinator = MatchExplanationCoordinator(redis)
        application_id = uuid.uuid4()

        asyncio.run(coordinator.release_lock(application_id, "owner"))

        script, numkeys, args = redis.eval_calls[0]
        assert "DEL" in script
        assert numkeys == 1
        assert args == (build_lock_key(application_id), "owner")

    def test_lock_conflict_is_409(self):
        redis = _FakeRedis({build_lock_key(uuid.uuid4()): "other"})
        coordinator = MatchExplanationCoordinator(redis)
        application_id = uuid.uuid4()
        redis.values[build_lock_key(application_id)] = "other"

        with pytest.raises(MatchExplanationRefreshError) as exc:
            asyncio.run(
                coordinator.acquire_lock(application_id, "mine")
            )

        assert exc.value.http_status == 409
        assert exc.value.retry_after == 5


class TestRedisDegradation:
    def test_missing_redis_skips_lock_for_sql_lease(self):
        coordinator = MatchExplanationCoordinator(None)

        acquired = asyncio.run(
            coordinator.acquire_lock(uuid.uuid4(), "owner")
        )

        assert acquired is False

    def test_redis_error_skips_lock_for_sql_lease(self):
        redis = _FakeRedis()
        redis.set_error = ConnectionError("redis unavailable")
        coordinator = MatchExplanationCoordinator(redis)

        acquired = asyncio.run(
            coordinator.acquire_lock(uuid.uuid4(), "owner")
        )

        assert acquired is False

    @pytest.mark.asyncio
    async def test_heartbeat_keeps_worker_when_redis_renewal_fails(self):
        def factory():
            return _SessionContext(
                _Session([_Result(rowcount=1), _Result(rowcount=1)])
            )

        coordinator = MatchExplanationCoordinator(
            None,
            session_factory=factory,
            heartbeat_interval_seconds=0.01,
        )
        worker = asyncio.create_task(asyncio.sleep(60))
        heartbeat = asyncio.create_task(
            coordinator._heartbeat_loop(
                worker_task=worker,
                record_id=uuid.uuid4(),
                application_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                key_hash="hash",
                owner_token="owner",
            )
        )

        try:
            await asyncio.sleep(0.1)
            assert not worker.done()
            assert not worker.cancelled()
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker


class TestRegistration:
    def _session(self, result):
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        session.get = AsyncMock(return_value=None)
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.rollback = AsyncMock()
        return session

    def test_new_key_registers_in_progress_and_application_lease(self):
        session = self._session(_Result(scalar=None))
        coordinator = MatchExplanationCoordinator(
            _FakeRedis(), schema_version="v1"
        )
        user_id = uuid.uuid4()
        application_id = uuid.uuid4()

        record_id, replay = asyncio.run(
            coordinator.register_refresh(
                session,
                user_id=user_id,
                key_hash="hash",
                application_id=application_id,
                owner_token="owner",
            )
        )

        assert isinstance(record_id, uuid.UUID)
        assert replay is None
        added = [call.args[0] for call in session.add.call_args_list]
        assert any(
            isinstance(item, AIMatchExplanationIdempotency)
            for item in added
        )
        assert any(
            isinstance(item, AIMatchExplanationApplicationLease)
            for item in added
        )
        session.flush.assert_awaited()

    def test_completed_tombstone_replays_without_lease_or_quota(self):
        application_id = uuid.uuid4()
        record = AIMatchExplanationIdempotency(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            key_hash="hash",
            application_id=application_id,
            status="COMPLETED",
            owner_token="old",
            lease_expires_at=utc_now() + timedelta(minutes=5),
            schema_version="v1",
            response_payload=_response(application_id).model_dump_json(),
        )
        session = self._session(_Result(scalar=record))
        coordinator = MatchExplanationCoordinator(
            _FakeRedis(), schema_version="v1"
        )

        record_id, replay = asyncio.run(
            coordinator.register_refresh(
                session,
                user_id=record.user_id,
                key_hash=record.key_hash,
                application_id=application_id,
                owner_token="new",
            )
        )

        assert record_id == record.id
        assert replay is not None
        assert replay.cache_state == "db_replay"
        session.add.assert_not_called()
        session.get.assert_not_awaited()

    def test_key_reused_for_another_application_is_422(self):
        record = AIMatchExplanationIdempotency(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            key_hash="hash",
            application_id=uuid.uuid4(),
            status="COMPLETED",
            owner_token="old",
            lease_expires_at=utc_now() + timedelta(minutes=5),
            schema_version="v1",
            response_payload="{}",
        )
        session = self._session(_Result(scalar=record))
        coordinator = MatchExplanationCoordinator(
            _FakeRedis(), schema_version="v1"
        )

        with pytest.raises(MatchExplanationIdempotencyConflictError):
            asyncio.run(
                coordinator.register_refresh(
                    session,
                    user_id=record.user_id,
                    key_hash=record.key_hash,
                    application_id=uuid.uuid4(),
                    owner_token="new",
                )
            )

        session.add.assert_not_called()

    def test_incompatible_schema_is_409(self):
        record = AIMatchExplanationIdempotency(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            key_hash="hash",
            application_id=uuid.uuid4(),
            status="IN_PROGRESS",
            owner_token="old",
            lease_expires_at=utc_now() + timedelta(minutes=5),
            schema_version="v0",
        )
        session = self._session(_Result(scalar=record))
        coordinator = MatchExplanationCoordinator(
            _FakeRedis(), schema_version="v1"
        )

        with pytest.raises(MatchExplanationRefreshError) as exc:
            asyncio.run(
                coordinator.register_refresh(
                    session,
                    user_id=record.user_id,
                    key_hash=record.key_hash,
                    application_id=record.application_id,
                    owner_token="new",
                )
            )

        assert exc.value.http_status == 409
        assert exc.value.reason == "idempotency_schema_incompatible"

    def test_active_in_progress_key_is_409(self):
        application_id = uuid.uuid4()
        record = AIMatchExplanationIdempotency(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            key_hash="hash",
            application_id=application_id,
            status="IN_PROGRESS",
            owner_token="old",
            lease_expires_at=utc_now() + timedelta(minutes=5),
            schema_version="v1",
        )
        session = self._session(_Result(scalar=record))
        coordinator = MatchExplanationCoordinator(
            _FakeRedis(), schema_version="v1"
        )

        with pytest.raises(MatchExplanationRefreshError) as exc:
            asyncio.run(
                coordinator.register_refresh(
                    session,
                    user_id=record.user_id,
                    key_hash=record.key_hash,
                    application_id=application_id,
                    owner_token="new",
                )
            )

        assert exc.value.http_status == 409
        assert exc.value.reason == "idempotency_in_progress"

    def test_active_application_lease_blocks_different_key(self):
        application_id = uuid.uuid4()
        record = AIMatchExplanationIdempotency(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            key_hash="new-hash",
            application_id=application_id,
            status="FAILED",
            owner_token="old",
            lease_expires_at=utc_now() + timedelta(minutes=5),
            schema_version="v1",
        )
        lease = AIMatchExplanationApplicationLease(
            application_id=application_id,
            owner_token="other",
            idempotency_key_hash="other-hash",
            lease_expires_at=utc_now() + timedelta(minutes=5),
        )
        session = MagicMock()
        session.execute = AsyncMock(
            side_effect=[
                _Result(scalar=record),
                _Result(rowcount=0),
            ]
        )
        session.get = AsyncMock(return_value=lease)
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.rollback = AsyncMock()
        coordinator = MatchExplanationCoordinator(
            _FakeRedis(), schema_version="v1"
        )

        with pytest.raises(MatchExplanationRefreshError) as exc:
            asyncio.run(
                coordinator.register_refresh(
                    session,
                    user_id=record.user_id,
                    key_hash=record.key_hash,
                    application_id=application_id,
                    owner_token="new",
                )
            )

        assert exc.value.http_status == 409
        assert exc.value.reason == "application_refresh_in_progress"
