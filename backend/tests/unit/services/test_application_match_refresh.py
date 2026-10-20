from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import (
    AIProviderUnavailableError,
    EntityNotFoundException,
    ForbiddenException,
    MatchExplanationRefreshError,
    MatchExplanationRefreshInputError,
)
from app.domain.enums import UserRole
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.application_service import ApplicationService
from app.services.match_explanation_cache import MatchExplanationCache
from app.services.match_explanation_service import MatchExplanationService
from app.services.quota_enforcement_service import ReservationResult
from tests.unit.services.test_application_match_service import (
    _FakeCacheRedis,
    _parsed_job_for,
    make_application,
    make_job,
    make_matching_service,
    make_resume,
    make_service,
    make_session,
    make_user,
)


class _RecordingRedis(_FakeCacheRedis):
    def __init__(self, events: list[str] | None = None) -> None:
        super().__init__()
        self.events = events if events is not None else []

    async def set(self, key: str, value: str, ex: int | None = None):
        self.events.append("cache")
        return await super().set(key, value, ex)


class _ExplodingCache:
    def build_key(self, application_id, parsed_resume, parsed_job):
        return f"match_explanation:{application_id}:test"

    async def store(self, key, response, *, application_id=None):
        raise RuntimeError("redis unavailable")

    async def get(self, key, *, application_id=None):
        return None


class _UncacheableCache:
    def build_key(self, application_id, parsed_resume, parsed_job):
        raise ValueError("cannot canonicalize trusted data")

    async def store(self, key, response, *, application_id=None):
        raise AssertionError("store must not be called")


def make_quota(
    *,
    reservation: ReservationResult | None = None,
    reserve_error: Exception | None = None,
    finalize_error: Exception | None = None,
    release_error: Exception | None = None,
):
    quota = SimpleNamespace()
    quota.reservation = reservation or ReservationResult(
        usage_id=uuid.uuid4(),
        remaining=4,
        limit=5,
        used=1,
    )
    quota.reserve_ai_quota = AsyncMock(return_value=quota.reservation)
    if reserve_error is not None:
        quota.reserve_ai_quota.side_effect = reserve_error
    quota.finalize_reservation = AsyncMock()
    if finalize_error is not None:
        quota.finalize_reservation.side_effect = finalize_error
    quota.release_reservation = AsyncMock()
    if release_error is not None:
        quota.release_reservation.side_effect = release_error
    return quota


def make_narrative(
    *,
    summary: str = "AI refreshed narrative.",
    model_name: str | None = "gemini-test-model",
    error: BaseException | None = None,
    match_score: float | None = None,
):
    response = SimpleNamespace(summary=summary)
    if match_score is not None:
        response.match_score = match_score
    explain = AsyncMock(return_value=response)
    if error is not None:
        explain.side_effect = error
    return SimpleNamespace(
        explain_match=explain,
        llm_provider=SimpleNamespace(model_name=model_name),
    )


def make_cache(redis=None) -> MatchExplanationCache:
    return MatchExplanationCache(
        redis or _FakeCacheRedis(),
        enabled=True,
        ttl_seconds=604800,
        version="v1",
    )


class TestRefreshPreconditions:
    def _setup(self, *, resume_parsed_data=None):
        session = make_session()
        service = make_service(session)
        application = make_application()
        job = make_job()
        resume = make_resume(application.candidate_id, resume_parsed_data)
        service.applications.get_by_id_with_candidate.return_value = application
        matching = make_matching_service()
        return session, service, application, job, resume, matching

    def _run(
        self,
        service,
        application,
        job,
        resume,
        matching,
        *,
        quota,
        cache,
        explanation_service,
        user=None,
        job_error=None,
        resume_result="unset",
    ):
        with patch(
            "app.services.application_service.JobService"
        ) as mock_job_service, patch(
            "app.services.application_service.ResumeRepository"
        ) as mock_resume_repo:
            mock_job_service.return_value.get_recruiter_job_by_id = AsyncMock(
                side_effect=job_error, return_value=None if job_error else job
            )
            mock_resume_repo.return_value.get_primary_by_candidate = (
                AsyncMock(return_value=resume if resume_result == "unset" else resume_result)
            )
            return asyncio.run(
                service.refresh_application_match_explanation(
                    current_user=user or make_user(),
                    application_id=application.id,
                    idempotency_key="refresh-key-1",
                    matching_service=matching,
                    explanation_service=explanation_service,
                    cache_service=cache,
                    quota_service=quota,
                )
            )

    def test_missing_application_is_rejected_before_quota_or_provider(self):
        session, service, application, job, resume, matching = self._setup()
        service.applications.get_by_id_with_candidate.return_value = None
        quota = make_quota()
        cache = make_cache()
        narrative = make_narrative()
        explanation = MatchExplanationService(narrative_service=narrative)

        with pytest.raises(EntityNotFoundException):
            self._run(
                service,
                application,
                job,
                resume,
                matching,
                quota=quota,
                cache=cache,
                explanation_service=explanation,
            )

        quota.reserve_ai_quota.assert_not_awaited()
        narrative.explain_match.assert_not_awaited()
        session.commit.assert_not_awaited()
        assert cache.redis.set_calls == []

    def test_foreign_application_returns_404_before_quota_or_provider(self):
        session, service, application, job, resume, matching = self._setup()
        quota = make_quota()
        cache = make_cache()
        narrative = make_narrative()
        explanation = MatchExplanationService(narrative_service=narrative)

        with pytest.raises(EntityNotFoundException):
            self._run(
                service,
                application,
                job,
                resume,
                matching,
                quota=quota,
                cache=cache,
                explanation_service=explanation,
                job_error=EntityNotFoundException("Application not found"),
            )

        quota.reserve_ai_quota.assert_not_awaited()
        narrative.explain_match.assert_not_awaited()
        session.commit.assert_not_awaited()
        assert cache.redis.set_calls == []

    def test_missing_parsed_cv_is_rejected_before_quota(self):
        session, service, application, job, resume, matching = self._setup()
        resume.parsed_data = None
        quota = make_quota()
        cache = make_cache()
        narrative = make_narrative()
        explanation = MatchExplanationService(narrative_service=narrative)

        with pytest.raises(MatchExplanationRefreshInputError):
            self._run(
                service,
                application,
                job,
                resume,
                matching,
                quota=quota,
                cache=cache,
                explanation_service=explanation,
            )

        quota.reserve_ai_quota.assert_not_awaited()
        narrative.explain_match.assert_not_awaited()
        session.commit.assert_not_awaited()
        assert cache.redis.set_calls == []

    def test_invalid_parsed_cv_is_rejected_before_quota(self):
        session, service, application, job, resume, matching = self._setup(
            resume_parsed_data={"skills": "not-a-list"}
        )
        quota = make_quota()
        cache = make_cache()
        narrative = make_narrative()
        explanation = MatchExplanationService(narrative_service=narrative)

        with pytest.raises(MatchExplanationRefreshInputError):
            self._run(
                service,
                application,
                job,
                resume,
                matching,
                quota=quota,
                cache=cache,
                explanation_service=explanation,
            )

        quota.reserve_ai_quota.assert_not_awaited()
        narrative.explain_match.assert_not_awaited()
        session.commit.assert_not_awaited()
        assert cache.redis.set_calls == []

    def test_blank_idempotency_key_is_rejected_before_any_work(self):
        session, service, application, job, resume, matching = self._setup()
        quota = make_quota()
        cache = make_cache()
        explanation = MatchExplanationService(
            narrative_service=make_narrative()
        )

        with pytest.raises(MatchExplanationRefreshInputError):
            asyncio.run(
                service.refresh_application_match_explanation(
                    current_user=make_user(),
                    application_id=application.id,
                    idempotency_key="   ",
                    matching_service=matching,
                    explanation_service=explanation,
                    cache_service=cache,
                    quota_service=quota,
                )
            )

        service.applications.get_by_id_with_candidate.assert_not_awaited()
        quota.reserve_ai_quota.assert_not_awaited()
        assert cache.redis.set_calls == []

    def test_internal_signature_has_no_client_supplied_resume_or_job(self):
        parameters = inspect.signature(
            ApplicationService.refresh_application_match_explanation
        ).parameters
        for forbidden in (
            "resume",
            "parsed_resume",
            "job",
            "parsed_job",
            "resume_hash",
            "job_hash",
            "owner_id",
        ):
            assert forbidden not in parameters
        assert "idempotency_key" in parameters


class TestRefreshQuotaLifecycle:
    def _setup(self, *, resume_parsed_data=None):
        session = make_session()
        service = make_service(session)
        application = make_application()
        job = make_job()
        resume = make_resume(application.candidate_id, resume_parsed_data)
        service.applications.get_by_id_with_candidate.return_value = application
        matching = make_matching_service()
        return session, service, application, job, resume, matching

    def _run(
        self,
        service,
        application,
        job,
        resume,
        matching,
        *,
        quota,
        cache,
        explanation_service,
        user=None,
        application_id=None,
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
                    application_id=application_id or application.id,
                    idempotency_key="refresh-key-1",
                    matching_service=matching,
                    explanation_service=explanation_service,
                    cache_service=cache,
                    quota_service=quota,
                )
            )

    def test_recruiter_success_reserves_generates_finalizes_and_caches(self):
        session, service, application, job, resume, matching = self._setup()
        user = make_user()
        quota = make_quota()
        events: list[str] = []
        redis = _RecordingRedis(events)
        cache = make_cache(redis)
        narrative = make_narrative()
        explanation = MatchExplanationService(narrative_service=narrative)
        quota.reserve_ai_quota.side_effect = lambda **kwargs: (
            events.append("reserve") or quota.reservation
        )
        session.commit.side_effect = lambda: events.append("commit")
        narrative.explain_match.side_effect = lambda **kwargs: (
            events.append("provider") or SimpleNamespace(summary="AI refreshed narrative.")
        )
        quota.finalize_reservation.side_effect = lambda *args, **kwargs: (
            events.append("finalize")
        )

        result = self._run(
            service,
            application,
            job,
            resume,
            matching,
            quota=quota,
            cache=cache,
            explanation_service=explanation,
            user=user,
        )

        assert events == ["reserve", "commit", "provider", "finalize", "commit", "cache"]
        quota.reserve_ai_quota.assert_awaited_once_with(
            user_id=user.id,
            idempotency_key="refresh-key-1",
            reference_id=application.id,
            is_admin=False,
        )
        quota.finalize_reservation.assert_awaited_once_with(
            quota.reservation.usage_id, success=True
        )
        quota.release_reservation.assert_not_awaited()
        session.rollback.assert_not_awaited()

        assert result.summary_source == "ai_generated"
        assert result.summary == "AI refreshed narrative."
        assert result.model_version == "gemini-test-model"
        assert result.cache_state == "cached"
        assert result.application_id == application.id

        parsed_resume = ParsedResumeSchema.model_validate(resume.parsed_data)
        parsed_job = _parsed_job_for(job)
        expected_key = cache.build_key(application.id, parsed_resume, parsed_job)
        assert len(redis.set_calls) == 1
        assert redis.set_calls[0][0] == expected_key
        assert redis.set_calls[0][2] == 604800

        deterministic = asyncio.run(
            MatchExplanationService().build_deterministic_explanation(
                application_id=application.id,
                match_result=matching.matching_engine.match_resume_to_job(
                    resume=parsed_resume,
                    job=parsed_job,
                    resume_vector=[1.0, 0.0],
                    job_vector=[1.0, 0.0],
                ),
                parsed_resume=parsed_resume,
                parsed_job=parsed_job,
            )
        )
        assert result.overall_score == deterministic.overall_score
        assert result.score_breakdown == deterministic.score_breakdown
        assert result.skill_evaluations == deterministic.skill_evaluations
        assert result.experience_evaluations == deterministic.experience_evaluations
        assert result.evidence == deterministic.evidence

        assert narrative.explain_match.await_args.kwargs["candidate"] == parsed_resume

    def test_no_active_subscription_fails_without_provider_call(self):
        session, service, application, job, resume, matching = self._setup()
        quota = make_quota(
            reserve_error=ForbiddenException("no active subscription")
        )
        cache = make_cache()
        narrative = make_narrative()

        with pytest.raises(ForbiddenException):
            self._run(
                service,
                application,
                job,
                resume,
                matching,
                quota=quota,
                cache=cache,
                explanation_service=MatchExplanationService(
                    narrative_service=narrative
                ),
            )

        narrative.explain_match.assert_not_awaited()
        session.commit.assert_not_awaited()
        assert cache.redis.set_calls == []

    def test_admin_bypass_uses_server_side_role_and_still_generates(self):
        session, service, application, job, resume, matching = self._setup()
        admin = make_user(UserRole.ADMIN)
        quota = make_quota(
            reservation=ReservationResult(
                usage_id=None,
                remaining=-1,
                limit=-1,
                used=-1,
                bypassed=True,
            )
        )
        cache = make_cache()
        narrative = make_narrative()
        explanation = MatchExplanationService(narrative_service=narrative)

        result = self._run(
            service,
            application,
            job,
            resume,
            matching,
            quota=quota,
            cache=cache,
            explanation_service=explanation,
            user=admin,
        )

        quota.reserve_ai_quota.assert_awaited_once_with(
            user_id=admin.id,
            idempotency_key="refresh-key-1",
            reference_id=application.id,
            is_admin=True,
        )
        quota.finalize_reservation.assert_awaited_once_with(None, success=True)
        quota.release_reservation.assert_not_awaited()
        assert result.summary_source == "ai_generated"
        assert result.cache_state == "cached"

    @pytest.mark.parametrize(
        ("error", "reason", "http_status"),
        [
            (
                AIProviderUnavailableError("down", retry_after=60),
                "provider_unavailable",
                503,
            ),
            (TimeoutError("timed out"), "provider_error", 502),
        ],
    )
    def test_provider_failure_releases_reservation_and_writes_no_cache(
        self, error, reason, http_status
    ):
        session, service, application, job, resume, matching = self._setup()
        quota = make_quota()
        cache = make_cache()
        narrative = make_narrative(error=error)

        with pytest.raises(MatchExplanationRefreshError) as exc_info:
            self._run(
                service,
                application,
                job,
                resume,
                matching,
                quota=quota,
                cache=cache,
                explanation_service=MatchExplanationService(
                    narrative_service=narrative
                ),
            )

        assert exc_info.value.reason == reason
        assert exc_info.value.http_status == http_status
        quota.release_reservation.assert_awaited_once_with(
            quota.reservation.usage_id
        )
        quota.finalize_reservation.assert_not_awaited()
        assert cache.redis.set_calls == []
        assert session.commit.await_count == 2

    @pytest.mark.parametrize(
        ("summary", "match_score", "reason"),
        [
            ("   ", None, "empty_narrative"),
            ("Strong match.", 999.0, "score_contradiction"),
        ],
    )
    def test_invalid_narrative_is_not_a_successful_refresh(
        self, summary, match_score, reason
    ):
        session, service, application, job, resume, matching = self._setup()
        quota = make_quota()
        cache = make_cache()
        narrative = make_narrative(summary=summary, match_score=match_score)

        with pytest.raises(MatchExplanationRefreshError) as exc_info:
            self._run(
                service,
                application,
                job,
                resume,
                matching,
                quota=quota,
                cache=cache,
                explanation_service=MatchExplanationService(
                    narrative_service=narrative
                ),
            )

        assert exc_info.value.reason == reason
        quota.release_reservation.assert_awaited_once()
        quota.finalize_reservation.assert_not_awaited()
        assert cache.redis.set_calls == []

    def test_explanation_service_returning_fallback_releases_reservation(self):
        session, service, application, job, resume, matching = self._setup()
        quota = make_quota()
        cache = make_cache()
        narrative = make_narrative()
        explanation = MatchExplanationService(narrative_service=narrative)

        async def fallback(**kwargs):
            return await MatchExplanationService().build_deterministic_explanation(
                **kwargs
            )

        explanation.build_refresh_explanation = fallback

        with pytest.raises(MatchExplanationRefreshError) as exc_info:
            self._run(
                service,
                application,
                job,
                resume,
                matching,
                quota=quota,
                cache=cache,
                explanation_service=explanation,
            )

        assert exc_info.value.reason == "narrative_rejected"
        quota.release_reservation.assert_awaited_once()
        quota.finalize_reservation.assert_not_awaited()
        assert cache.redis.set_calls == []

    def test_cache_set_failure_still_consumes_quota_and_returns_not_cached(self):
        session, service, application, job, resume, matching = self._setup()
        quota = make_quota()
        redis = _FakeCacheRedis(set_error=TimeoutError("redis down"))
        cache = make_cache(redis)
        narrative = make_narrative()

        result = self._run(
            service,
            application,
            job,
            resume,
            matching,
            quota=quota,
            cache=cache,
            explanation_service=MatchExplanationService(
                narrative_service=narrative
            ),
        )

        quota.finalize_reservation.assert_awaited_once_with(
            quota.reservation.usage_id, success=True
        )
        quota.release_reservation.assert_not_awaited()
        assert result.summary_source == "ai_generated"
        assert result.cache_state == "not_cached"
        assert len(redis.set_calls) == 1

    def test_unexpected_cache_store_exception_does_not_refund_quota(self):
        session, service, application, job, resume, matching = self._setup()
        quota = make_quota()
        narrative = make_narrative()

        result = self._run(
            service,
            application,
            job,
            resume,
            matching,
            quota=quota,
            cache=_ExplodingCache(),
            explanation_service=MatchExplanationService(
                narrative_service=narrative
            ),
        )

        quota.finalize_reservation.assert_awaited_once()
        quota.release_reservation.assert_not_awaited()
        assert result.summary_source == "ai_generated"
        assert result.cache_state == "not_cached"

    def test_finalize_failure_releases_and_surfaces_controlled_error(self):
        session, service, application, job, resume, matching = self._setup()
        quota = make_quota(finalize_error=RuntimeError("db commit failed"))
        cache = make_cache()
        narrative = make_narrative()

        with pytest.raises(MatchExplanationRefreshError) as exc_info:
            self._run(
                service,
                application,
                job,
                resume,
                matching,
                quota=quota,
                cache=cache,
                explanation_service=MatchExplanationService(
                    narrative_service=narrative
                ),
            )

        assert exc_info.value.reason == "quota_finalize_failed"
        quota.release_reservation.assert_awaited_once()
        assert cache.redis.set_calls == []
        assert narrative.explain_match.await_count == 1
        session.rollback.assert_awaited()

    def test_release_failure_is_surfaced_without_a_second_provider_call(self):
        session, service, application, job, resume, matching = self._setup()
        quota = make_quota(
            release_error=RuntimeError("release commit failed")
        )
        cache = make_cache()
        narrative = make_narrative(error=TimeoutError("provider timeout"))

        with pytest.raises(MatchExplanationRefreshError) as exc_info:
            self._run(
                service,
                application,
                job,
                resume,
                matching,
                quota=quota,
                cache=cache,
                explanation_service=MatchExplanationService(
                    narrative_service=narrative
                ),
            )

        assert exc_info.value.reason == "quota_release_failed"
        assert exc_info.value.http_status == 503
        quota.release_reservation.assert_awaited_once()
        narrative.explain_match.assert_awaited_once()
        assert cache.redis.set_calls == []
        session.rollback.assert_awaited()

    def test_unexpected_failure_before_reservation_has_no_quota_side_effects(self):
        session, service, application, job, resume, matching = self._setup()
        matching.matching_engine = SimpleNamespace(
            match_resume_to_job=MagicMock(side_effect=RuntimeError("engine bug"))
        )
        quota = make_quota()
        cache = make_cache()
        narrative = make_narrative()

        with pytest.raises(RuntimeError):
            self._run(
                service,
                application,
                job,
                resume,
                matching,
                quota=quota,
                cache=cache,
                explanation_service=MatchExplanationService(
                    narrative_service=narrative
                ),
            )

        quota.reserve_ai_quota.assert_not_awaited()
        narrative.explain_match.assert_not_awaited()
        session.commit.assert_not_awaited()
        assert cache.redis.set_calls == []

    def test_cancellation_releases_reservation_and_propagates(self):
        session, service, application, job, resume, matching = self._setup()
        quota = make_quota()
        cache = make_cache()
        narrative = make_narrative(error=asyncio.CancelledError())

        with pytest.raises(asyncio.CancelledError):
            self._run(
                service,
                application,
                job,
                resume,
                matching,
                quota=quota,
                cache=cache,
                explanation_service=MatchExplanationService(
                    narrative_service=narrative
                ),
            )

        quota.release_reservation.assert_awaited_once()
        quota.finalize_reservation.assert_not_awaited()
        assert cache.redis.set_calls == []

    def test_reservation_commit_failure_skips_provider_and_rolls_back(self):
        session, service, application, job, resume, matching = self._setup()
        session.commit.side_effect = RuntimeError("reservation commit failed")
        quota = make_quota()
        cache = make_cache()
        narrative = make_narrative()

        with pytest.raises(RuntimeError):
            self._run(
                service,
                application,
                job,
                resume,
                matching,
                quota=quota,
                cache=cache,
                explanation_service=MatchExplanationService(
                    narrative_service=narrative
                ),
            )

        quota.release_reservation.assert_not_awaited()
        narrative.explain_match.assert_not_awaited()
        session.rollback.assert_awaited()
        assert cache.redis.set_calls == []

    def test_finalize_commit_failure_releases_reservation(self):
        session, service, application, job, resume, matching = self._setup()
        session.commit.side_effect = [
            None,
            RuntimeError("finalize commit failed"),
            None,
        ]
        quota = make_quota()
        cache = make_cache()
        narrative = make_narrative()

        with pytest.raises(MatchExplanationRefreshError) as exc_info:
            self._run(
                service,
                application,
                job,
                resume,
                matching,
                quota=quota,
                cache=cache,
                explanation_service=MatchExplanationService(
                    narrative_service=narrative
                ),
            )

        assert exc_info.value.reason == "quota_finalize_failed"
        quota.release_reservation.assert_awaited_once()
        assert cache.redis.set_calls == []
        session.rollback.assert_awaited()

    def test_release_commit_failure_is_surfaced_truthfully(self):
        session, service, application, job, resume, matching = self._setup()
        session.commit.side_effect = [
            None,
            RuntimeError("release commit failed"),
        ]
        quota = make_quota()
        cache = make_cache()
        narrative = make_narrative(error=TimeoutError("provider timeout"))

        with pytest.raises(MatchExplanationRefreshError) as exc_info:
            self._run(
                service,
                application,
                job,
                resume,
                matching,
                quota=quota,
                cache=cache,
                explanation_service=MatchExplanationService(
                    narrative_service=narrative
                ),
            )

        assert exc_info.value.reason == "quota_release_failed"
        assert exc_info.value.http_status == 503
        quota.release_reservation.assert_awaited_once()
        session.rollback.assert_awaited()
        assert cache.redis.set_calls == []

    def test_uncacheable_trusted_input_is_rejected_before_quota(self):
        session, service, application, job, resume, matching = self._setup()
        quota = make_quota()
        narrative = make_narrative()

        with pytest.raises(MatchExplanationRefreshInputError):
            self._run(
                service,
                application,
                job,
                resume,
                matching,
                quota=quota,
                cache=_UncacheableCache(),
                explanation_service=MatchExplanationService(
                    narrative_service=narrative
                ),
            )

        quota.reserve_ai_quota.assert_not_awaited()
        narrative.explain_match.assert_not_awaited()
        session.commit.assert_not_awaited()


class TestRefreshGetIntegration:
    def test_cached_ai_refresh_is_served_by_regular_get_without_provider(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        job = make_job()
        resume = make_resume(application.candidate_id)
        service.applications.get_by_id_with_candidate.return_value = application
        matching = make_matching_service()
        quota = make_quota()
        cache = make_cache()
        narrative = make_narrative(summary="AI refreshed narrative.")

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
            refreshed = asyncio.run(
                service.refresh_application_match_explanation(
                    current_user=make_user(),
                    application_id=application.id,
                    idempotency_key="refresh-key-1",
                    matching_service=matching,
                    explanation_service=MatchExplanationService(
                        narrative_service=narrative
                    ),
                    cache_service=cache,
                    quota_service=quota,
                )
            )
            assert refreshed.cache_state == "cached"

            matching.vector_repository.retrieve_vector.reset_mock()
            narrative.explain_match.reset_mock()
            get_result = asyncio.run(
                service.get_application_match_explanation(
                    current_user=make_user(),
                    application_id=application.id,
                    matching_service=matching,
                    explanation_service=MatchExplanationService(),
                    cache_service=cache,
                )
            )

        narrative.explain_match.assert_not_awaited()
        matching.vector_repository.retrieve_vector.assert_not_awaited()
        assert get_result.summary == "AI refreshed narrative."
        assert get_result.summary_source == "ai_generated"
        assert get_result.model_version == "gemini-test-model"
        assert get_result.cache_state == "cached"
        assert get_result.application_id == application.id

    def test_get_cache_hit_still_has_ai_generated_source(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        job = make_job()
        resume = make_resume(application.candidate_id)
        service.applications.get_by_id_with_candidate.return_value = application
        matching = make_matching_service()
        redis = _FakeCacheRedis()
        cache = make_cache(redis)
        narrative = make_narrative()
        quota = make_quota()

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
            asyncio.run(
                service.refresh_application_match_explanation(
                    current_user=make_user(),
                    application_id=application.id,
                    idempotency_key="refresh-key-1",
                    matching_service=matching,
                    explanation_service=MatchExplanationService(
                        narrative_service=narrative
                    ),
                    cache_service=cache,
                    quota_service=quota,
                )
            )
            raw = next(iter(redis.values.values()))
            payload = json.loads(raw)
            assert payload["summary_source"] == "ai_generated"
            assert payload["cache_state"] == "not_cached"
