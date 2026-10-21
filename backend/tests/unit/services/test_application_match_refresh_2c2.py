from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import MatchExplanationRefreshError
from app.schemas.ai_explanation import ApplicationMatchExplanationResponse
from app.services.application_service import ApplicationService
from app.services.match_explanation_service import MatchExplanationService
from tests.unit.services.test_application_match_refresh import (
    make_cache,
    make_narrative,
    make_quota,
)
from tests.unit.services.test_application_match_service import (
    make_application,
    make_job,
    make_matching_service,
    make_resume,
    make_service,
    make_session,
    make_user,
)


def _response(application_id: uuid.UUID) -> ApplicationMatchExplanationResponse:
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
        summary="Replayed narrative.",
        summary_source="ai_generated",
        generated_at="2026-01-01T00:00:00+00:00",
        cache_state="cached",
    )


class _Coordinator:
    def __init__(
        self,
        *,
        replay=None,
        active=None,
        publish_result=False,
        record_id=None,
    ):
        self.replay = replay
        self.active = active
        self.publish_result = publish_result
        self.record_id = record_id or uuid.uuid4()
        self.read_idempotency_cache = AsyncMock(return_value=replay)
        self.acquire_lock = AsyncMock()
        self.register_refresh = AsyncMock(
            return_value=(self.record_id, replay)
        )
        self.publish_fenced_cache = AsyncMock(
            return_value=publish_result
        )
        self.release_lock = AsyncMock()
        self.start_heartbeat_calls = 0

    def get_active_task(self, application_id):
        return self.active

    def start_heartbeat(self, **kwargs):
        self.start_heartbeat_calls += 1
        return None


def _setup(
    *,
    coordinator,
    reservation=None,
    scalar_side_effect=None,
    execute_rowcount=1,
    narrative_error=None,
    publish_result=None,
):
    session = make_session()
    session.scalar = AsyncMock(side_effect=scalar_side_effect)
    session.execute = AsyncMock(
        return_value=SimpleNamespace(rowcount=execute_rowcount)
    )
    service = make_service(session)
    application = make_application()
    job = make_job()
    resume = make_resume(application.candidate_id)
    service.applications.get_by_id_with_candidate.return_value = application
    matching = make_matching_service()
    quota = make_quota(reservation=reservation)
    cache = make_cache()
    narrative = make_narrative(error=narrative_error)
    explanation = MatchExplanationService(narrative_service=narrative)
    if publish_result is not None:
        coordinator.publish_fenced_cache.return_value = publish_result
    return (
        session,
        service,
        application,
        job,
        resume,
        matching,
        quota,
        cache,
        explanation,
        narrative,
    )


def _run(
    service,
    application,
    job,
    resume,
    matching,
    quota,
    cache,
    explanation,
    coordinator,
    *,
    user=None,
):
    with patch(
        "app.services.application_service.JobService"
    ) as mock_job_service, patch(
        "app.services.application_service.ResumeRepository"
    ) as mock_resume_repo:
        mock_job_service.return_value.get_recruiter_job_by_id = AsyncMock(
            return_value=job
        )
        mock_resume_repo.return_value.get_primary_by_candidate = AsyncMock(
            return_value=resume
        )
        return asyncio.run(
            service.refresh_application_match_explanation(
                current_user=user or make_user(),
                application_id=application.id,
                idempotency_key="key-alpha",
                matching_service=matching,
                explanation_service=explanation,
                cache_service=cache,
                quota_service=quota,
                coordinator=coordinator,
            )
        )


class TestSuccessfulRefresh:
    def test_generates_once_finalizes_and_returns_not_cached(self):
        record_id = uuid.uuid4()
        coordinator = _Coordinator(
            record_id=record_id, publish_result=True
        )
        (
            session,
            service,
            application,
            job,
            resume,
            matching,
            quota,
            cache,
            explanation,
            narrative,
        ) = _setup(
            coordinator=coordinator,
            scalar_side_effect=[record_id, record_id, record_id, record_id],
        )

        result = _run(
            service,
            application,
            job,
            resume,
            matching,
            quota,
            cache,
            explanation,
            coordinator,
        )

        assert result.summary_source == "ai_generated"
        assert result.cache_state == "not_cached"
        quota.reserve_ai_quota.assert_awaited_once()
        quota.finalize_reservation.assert_awaited_once_with(
            quota.reservation.usage_id, success=True
        )
        quota.release_reservation.assert_not_awaited()
        narrative.explain_match.assert_awaited_once()
        coordinator.acquire_lock.assert_awaited_once()
        coordinator.register_refresh.assert_awaited_once()
        coordinator.publish_fenced_cache.assert_awaited_once()
        coordinator.release_lock.assert_awaited_once()
        assert coordinator.start_heartbeat_calls == 1
        assert session.commit.await_count == 3

    def test_redis_idempotency_replay_skips_quota_provider_and_lock(self):
        application = make_application()
        cached = _response(application.id)
        coordinator = _Coordinator(replay=cached)
        (
            session,
            service,
            application,
            job,
            resume,
            matching,
            quota,
            cache,
            explanation,
            narrative,
        ) = _setup(
            coordinator=coordinator,
            scalar_side_effect=[],
        )

        result = _run(
            service,
            application,
            job,
            resume,
            matching,
            quota,
            cache,
            explanation,
            coordinator,
        )

        assert result.cache_state == "cached"
        quota.reserve_ai_quota.assert_not_awaited()
        narrative.explain_match.assert_not_awaited()
        coordinator.acquire_lock.assert_not_awaited()
        coordinator.register_refresh.assert_not_awaited()
        coordinator.publish_fenced_cache.assert_not_awaited()

    def test_sql_tombstone_replay_skips_quota_and_provider(self):
        application = make_application()
        record_id = uuid.uuid4()
        sql_replay = _response(application.id).model_copy(
            update={"cache_state": "db_replay"}
        )
        coordinator = _Coordinator(record_id=record_id)
        coordinator.register_refresh.return_value = (
            record_id,
            sql_replay,
        )
        (
            session,
            service,
            application,
            job,
            resume,
            matching,
            quota,
            cache,
            explanation,
            narrative,
        ) = _setup(
            coordinator=coordinator,
            scalar_side_effect=[],
        )

        result = _run(
            service,
            application,
            job,
            resume,
            matching,
            quota,
            cache,
            explanation,
            coordinator,
        )

        assert result.cache_state == "db_replay"
        quota.reserve_ai_quota.assert_not_awaited()
        narrative.explain_match.assert_not_awaited()
        coordinator.publish_fenced_cache.assert_not_awaited()
        coordinator.release_lock.assert_awaited_once()
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()

    def test_publish_failure_after_commit_still_returns_success(self):
        record_id = uuid.uuid4()
        coordinator = _Coordinator(
            record_id=record_id, publish_result=False
        )
        (
            session,
            service,
            application,
            job,
            resume,
            matching,
            quota,
            cache,
            explanation,
            narrative,
        ) = _setup(
            coordinator=coordinator,
            scalar_side_effect=[record_id, record_id, record_id, record_id],
        )

        result = _run(
            service,
            application,
            job,
            resume,
            matching,
            quota,
            cache,
            explanation,
            coordinator,
        )

        assert result.cache_state == "not_cached"
        quota.finalize_reservation.assert_awaited_once()
        quota.release_reservation.assert_not_awaited()
        assert session.rollback.await_count == 0


class TestFencing:
    def test_gate_one_failure_reserves_nothing_and_never_calls_provider(self):
        record_id = uuid.uuid4()
        coordinator = _Coordinator(record_id=record_id)
        (
            session,
            service,
            application,
            job,
            resume,
            matching,
            quota,
            cache,
            explanation,
            narrative,
        ) = _setup(
            coordinator=coordinator,
            scalar_side_effect=[None],
        )

        with pytest.raises(MatchExplanationRefreshError) as exc:
            _run(
                service,
                application,
                job,
                resume,
                matching,
                quota,
                cache,
                explanation,
                coordinator,
            )

        assert exc.value.reason == "refresh_ownership_lost"
        quota.reserve_ai_quota.assert_not_awaited()
        narrative.explain_match.assert_not_awaited()
        coordinator.publish_fenced_cache.assert_not_awaited()
        coordinator.release_lock.assert_awaited_once()

    def test_gate_two_failure_refunds_reservation_before_provider(self):
        record_id = uuid.uuid4()
        coordinator = _Coordinator(record_id=record_id)
        (
            session,
            service,
            application,
            job,
            resume,
            matching,
            quota,
            cache,
            explanation,
            narrative,
        ) = _setup(
            coordinator=coordinator,
            scalar_side_effect=[record_id, record_id, record_id, None],
        )

        with pytest.raises(MatchExplanationRefreshError) as exc:
            _run(
                service,
                application,
                job,
                resume,
                matching,
                quota,
                cache,
                explanation,
                coordinator,
            )

        assert exc.value.reason == "refresh_ownership_lost"
        quota.reserve_ai_quota.assert_awaited_once()
        quota.release_reservation.assert_awaited_once_with(
            quota.reservation.usage_id
        )
        quota.finalize_reservation.assert_not_awaited()
        narrative.explain_match.assert_not_awaited()
        coordinator.publish_fenced_cache.assert_not_awaited()

    def test_cancellation_refunds_and_releases_application_lease(self):
        record_id = uuid.uuid4()
        coordinator = _Coordinator(record_id=record_id)
        (
            session,
            service,
            application,
            job,
            resume,
            matching,
            quota,
            cache,
            explanation,
            narrative,
        ) = _setup(
            coordinator=coordinator,
            scalar_side_effect=[record_id, record_id, record_id, record_id],
            narrative_error=asyncio.CancelledError(),
        )

        with pytest.raises(asyncio.CancelledError):
            _run(
                service,
                application,
                job,
                resume,
                matching,
                quota,
                cache,
                explanation,
                coordinator,
            )

        quota.release_reservation.assert_awaited_once_with(
            quota.reservation.usage_id
        )
        quota.finalize_reservation.assert_not_awaited()
        coordinator.publish_fenced_cache.assert_not_awaited()
        coordinator.release_lock.assert_awaited_once()

    def test_cancellation_during_registration_rolls_back_session(self):
        coordinator = _Coordinator()
        coordinator.register_refresh.side_effect = asyncio.CancelledError()
        (
            session,
            service,
            application,
            job,
            resume,
            matching,
            quota,
            cache,
            explanation,
            narrative,
        ) = _setup(
            coordinator=coordinator,
            scalar_side_effect=[],
        )

        with pytest.raises(asyncio.CancelledError):
            _run(
                service,
                application,
                job,
                resume,
                matching,
                quota,
                cache,
                explanation,
                coordinator,
            )

        session.rollback.assert_awaited_once()
        quota.reserve_ai_quota.assert_not_awaited()
        narrative.explain_match.assert_not_awaited()
        coordinator.release_lock.assert_awaited_once()

    def test_stale_cleanup_skips_refund_when_fence_returns_zero(self):
        session = make_session()
        session.execute = AsyncMock(
            return_value=SimpleNamespace(rowcount=0)
        )
        service = ApplicationService(session)
        quota = make_quota()

        released = asyncio.run(
            service._fenced_release_reservation(
                record_id=uuid.uuid4(),
                application_id=uuid.uuid4(),
                owner_token="stale",
                reservation=quota.reservation,
                quota=quota,
            )
        )

        assert released is False
        quota.release_reservation.assert_not_awaited()
        session.commit.assert_not_awaited()

    def test_owned_cleanup_refunds_and_deletes_lease(self):
        session = make_session()
        session.execute = AsyncMock(
            return_value=SimpleNamespace(rowcount=1)
        )
        service = ApplicationService(session)
        quota = make_quota()

        released = asyncio.run(
            service._fenced_release_reservation(
                record_id=uuid.uuid4(),
                application_id=uuid.uuid4(),
                owner_token="owner",
                reservation=quota.reservation,
                quota=quota,
            )
        )

        assert released is True
        quota.release_reservation.assert_awaited_once_with(
            quota.reservation.usage_id
        )
        assert session.execute.await_count == 2
        session.commit.assert_awaited_once()


class TestInProcessConcurrency:
    def test_foreign_active_task_is_409_before_lock_or_quota(self):
        coordinator = _Coordinator(
            active=SimpleNamespace(done=lambda: False)
        )
        (
            session,
            service,
            application,
            job,
            resume,
            matching,
            quota,
            cache,
            explanation,
            narrative,
        ) = _setup(
            coordinator=coordinator,
            scalar_side_effect=[],
        )

        with pytest.raises(MatchExplanationRefreshError) as exc:
            _run(
                service,
                application,
                job,
                resume,
                matching,
                quota,
                cache,
                explanation,
                coordinator,
            )

        assert exc.value.http_status == 409
        assert exc.value.retry_after == 5
        coordinator.acquire_lock.assert_not_awaited()
        coordinator.register_refresh.assert_not_awaited()
        quota.reserve_ai_quota.assert_not_awaited()
        narrative.explain_match.assert_not_awaited()
