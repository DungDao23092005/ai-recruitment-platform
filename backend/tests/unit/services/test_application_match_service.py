import asyncio
import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.matching.matching_engine import MatchingEngine
from app.core.exceptions import AIError, EntityNotFoundException
from app.domain.enums import ApplicationStatus, UserRole
from app.models import Application, Job, Resume, Skill
from app.repositories import ApplicationRepository, JobRepository, ResumeRepository
from app.schemas.ai_explanation import (
    ApplicationMatchExplanationResponse,
    ScoreBreakdown,
)
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.application_service import ApplicationService
from app.services.match_explanation_cache import MatchExplanationCache
from app.services.match_explanation_service import MatchExplanationService


def make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    return session


def make_user(
    role: UserRole = UserRole.RECRUITER,
) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), role=role, is_active=True)


def make_application(
    application_id: uuid.UUID | None = None,
    status: ApplicationStatus = ApplicationStatus.APPLIED,
) -> Application:
    return Application(
        id=application_id or uuid.uuid4(),
        candidate_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        status=status,
    )


def make_job() -> Job:
    job = Job(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        title="Backend Engineer",
        description="Build APIs",
        status="published",
        job_type="full_time",
        workplace_type="remote",
        location="",
        minimum_years_experience=None,
        education_level=None,
    )
    skill_python = Skill(name="Python")
    skill_docker = Skill(name="Docker")
    # Set skills for backward compatibility
    job.skills = [skill_python, skill_docker]
    # Set required_skills and preferred_skills for new structured criteria
    job.required_skills = [skill_python, skill_docker]
    job.preferred_skills = []
    return job


def make_resume(
    candidate_id: uuid.UUID,
    parsed_data: dict | None = None,
) -> Resume:
    return Resume(
        id=uuid.uuid4(),
        candidate_id=candidate_id,
        title="cv.pdf",
        is_primary=True,
        parsed_data=parsed_data
        or {
            "full_name": "Jane Doe",
            "skills": ["Python", "FastAPI"],
        },
    )


def make_service(session) -> ApplicationService:
    service = ApplicationService(session)
    service.applications = AsyncMock(spec=ApplicationRepository)
    service.jobs = AsyncMock(spec=JobRepository)
    return service


def make_matching_service(
    resume_vector: list[float] | None = None,
    job_vector: list[float] | None = None,
) -> SimpleNamespace:
    vector_repo = AsyncMock()
    vector_repo.retrieve_vector = AsyncMock(
        return_value={"vector": [1.0, 0.0]}
    )
    embedding = SimpleNamespace(
        embed_resume=AsyncMock(return_value=resume_vector or [1.0, 0.0]),
        embed_job=AsyncMock(return_value=job_vector or [1.0, 0.0]),
    )
    return SimpleNamespace(
        vector_repository=vector_repo,
        embedding_service=embedding,
        matching_engine=MatchingEngine(),
    )


class TestGetApplicationMatch:
    def test_returns_match_result_with_correct_resume_and_job(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        job = make_job()
        resume = make_resume(application.candidate_id)
        service.applications.get_by_id_with_candidate.return_value = application
        matching_service = make_matching_service()

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
            result = asyncio.run(
                service.get_application_match(
                    current_user=make_user(),
                    application_id=application.id,
                    matching_service=matching_service,
                )
            )

        assert isinstance(result, MatchResultSchema)
        assert 0.0 <= result.overall_score <= 100.0
        # DATA-01: ParsedJobSchema now includes required_skills from Job.skills
        # Job has skills ["Python", "Docker"], resume has skills ["Python", "FastAPI"]
        # Matching should find "Python" as a matching skill
        assert "Python" in result.matching_skills
        assert result.skill_gap == ["Docker"]
        service.applications.get_by_id_with_candidate.assert_awaited_once_with(
            application.id
        )
        mock_job_service.return_value.get_recruiter_job_by_id.assert_awaited_once()
        mock_resume_repo.return_value.get_primary_by_candidate.assert_awaited_once_with(
            application.candidate_id
        )
        matching_service.vector_repository.retrieve_vector.assert_any_await(
            collection_name="resumes", point_id=application.candidate_id
        )
        matching_service.vector_repository.retrieve_vector.assert_any_await(
            collection_name="jobs", point_id=application.job_id
        )

    def test_matching_skills_reflect_candidate_resume(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        job = make_job()
        resume = make_resume(
            application.candidate_id,
            {"skills": ["Go", "Kubernetes"]},
        )
        service.applications.get_by_id_with_candidate.return_value = application
        matching_service = make_matching_service()

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
            result = asyncio.run(
                service.get_application_match(
                    current_user=make_user(),
                    application_id=application.id,
                    matching_service=matching_service,
                )
            )

        assert result.matching_skills == []
        assert result.skill_gap == ["Python", "Docker"]
        # DATA-01: With required_skills populated, skill_coverage_score reflects
        # required_coverage * 0.8 + preferred_coverage * 0.2
        # required_coverage = 0.0 (no matching required skills)
        # preferred_coverage = 1.0 (empty preferred_skills list)
        # skill_score = 0.0 * 0.8 + 1.0 * 0.2 = 0.2
        assert result.skill_coverage_score == 0.2

    def test_missing_resume_degrades_gracefully(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        job = make_job()
        service.applications.get_by_id_with_candidate.return_value = application
        matching_service = make_matching_service()

        with patch(
            "app.services.application_service.JobService"
        ) as mock_job_service, patch(
            "app.services.application_service.ResumeRepository"
        ) as mock_resume_repo:
            mock_job_service.return_value.get_recruiter_job_by_id = AsyncMock(
                return_value=job
            )
            mock_resume_repo.return_value.get_primary_by_candidate = AsyncMock(
                return_value=None
            )
            result = asyncio.run(
                service.get_application_match(
                    current_user=make_user(),
                    application_id=application.id,
                    matching_service=matching_service,
                )
            )

        assert isinstance(result, MatchResultSchema)
        assert result.matching_skills == []
        # DATA-01: Even without resume, skill_gap shows missing required skills from job
        assert result.skill_gap == ["Python", "Docker"]

    def test_resume_with_null_parsed_data_degrades_gracefully(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        job = make_job()
        resume = make_resume(application.candidate_id, None)
        resume.parsed_data = None
        service.applications.get_by_id_with_candidate.return_value = application
        matching_service = make_matching_service()

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
            result = asyncio.run(
                service.get_application_match(
                    current_user=make_user(),
                    application_id=application.id,
                    matching_service=matching_service,
                )
            )

        assert isinstance(result, MatchResultSchema)
        assert result.matching_skills == []

    def test_malformed_parsed_data_degrades_gracefully(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        job = make_job()
        resume = make_resume(application.candidate_id, None)
        resume.parsed_data = {"skills": "not-a-list"}
        service.applications.get_by_id_with_candidate.return_value = application
        matching_service = make_matching_service()

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
            result = asyncio.run(
                service.get_application_match(
                    current_user=make_user(),
                    application_id=application.id,
                    matching_service=matching_service,
                )
            )

        assert isinstance(result, MatchResultSchema)
        assert result.matching_skills == []
        matching_service.embedding_service.embed_resume.assert_not_called()

    def test_missing_resume_vector_falls_back_to_embedding(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        job = make_job()
        resume = make_resume(application.candidate_id)
        service.applications.get_by_id_with_candidate.return_value = application
        matching_service = make_matching_service()
        matching_service.vector_repository.retrieve_vector = AsyncMock(
            side_effect=lambda collection_name, point_id: None
        )

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
                service.get_application_match(
                    current_user=make_user(),
                    application_id=application.id,
                    matching_service=matching_service,
                )
            )

        matching_service.embedding_service.embed_resume.assert_called_once()
        matching_service.embedding_service.embed_job.assert_called_once()

    def test_qdrant_failure_propagates_ai_error(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        job = make_job()
        resume = make_resume(application.candidate_id)
        service.applications.get_by_id_with_candidate.return_value = application
        matching_service = make_matching_service()
        matching_service.vector_repository.retrieve_vector = AsyncMock(
            side_effect=AIError("Qdrant is down")
        )

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
            with pytest.raises(AIError):
                asyncio.run(
                    service.get_application_match(
                        current_user=make_user(),
                        application_id=application.id,
                        matching_service=matching_service,
                    )
                )

    def test_application_not_found_raises(self):
        session = make_session()
        service = make_service(session)
        service.applications.get_by_id_with_candidate.return_value = None
        matching_service = make_matching_service()

        with patch(
            "app.services.application_service.JobService"
        ) as mock_job_service:
            mock_job_service.return_value.get_recruiter_job_by_id = AsyncMock()
            with pytest.raises(EntityNotFoundException):
                asyncio.run(
                    service.get_application_match(
                        current_user=make_user(),
                        application_id=uuid.uuid4(),
                        matching_service=matching_service,
                    )
                )

        mock_job_service.return_value.get_recruiter_job_by_id.assert_not_awaited()

    def test_unowned_application_raises_not_found(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        service.applications.get_by_id_with_candidate.return_value = application
        matching_service = make_matching_service()

        with patch(
            "app.services.application_service.JobService"
        ) as mock_job_service, patch(
            "app.services.application_service.ResumeRepository"
        ) as mock_resume_repo:
            mock_job_service.return_value.get_recruiter_job_by_id = AsyncMock(
                side_effect=EntityNotFoundException("Application not found")
            )
            with pytest.raises(EntityNotFoundException):
                asyncio.run(
                    service.get_application_match(
                        current_user=make_user(),
                        application_id=application.id,
                        matching_service=matching_service,
                    )
                )

            mock_resume_repo.return_value.get_primary_by_candidate = AsyncMock()
            mock_resume_repo.return_value.get_primary_by_candidate.assert_not_awaited()
        matching_service.vector_repository.retrieve_vector.assert_not_awaited()

    def test_no_status_mutation(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        job = make_job()
        resume = make_resume(application.candidate_id)
        service.applications.get_by_id_with_candidate.return_value = application
        matching_service = make_matching_service()

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
                service.get_application_match(
                    current_user=make_user(),
                    application_id=application.id,
                    matching_service=matching_service,
                )
            )

        assert application.status == ApplicationStatus.APPLIED
        session.commit.assert_not_awaited()
        session.add.assert_not_called()


class TestGetApplicationMatchExplanation:
    def _run(self, service, application, job, resume, matching_service):
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
                service.get_application_match_explanation(
                    current_user=make_user(),
                    application_id=application.id,
                    matching_service=matching_service,
                )
            )

    def test_returns_grounded_explanation_with_copied_score(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        job = make_job()
        resume = make_resume(application.candidate_id)
        service.applications.get_by_id_with_candidate.return_value = application
        matching_service = make_matching_service()

        result = self._run(
            service, application, job, resume, matching_service
        )

        assert isinstance(result, ApplicationMatchExplanationResponse)
        assert result.application_id == application.id
        # Overall score is the engine's value; never recalculated here.
        engine_result = matching_service.matching_engine.match_resume_to_job(
            resume=ParsedResumeSchema.model_validate(resume.parsed_data),
            job=ParsedJobSchema(
                title=job.title,
                summary=job.description,
                required_skills=[s.name for s in job.required_skills],
            ),
            resume_vector=[1.0, 0.0],
            job_vector=[1.0, 0.0],
        )
        assert result.overall_score == engine_result.overall_score

    def test_explanation_does_not_mutate_status_or_session(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        job = make_job()
        resume = make_resume(application.candidate_id)
        service.applications.get_by_id_with_candidate.return_value = application
        matching_service = make_matching_service()

        self._run(service, application, job, resume, matching_service)

        assert application.status == ApplicationStatus.APPLIED
        session.commit.assert_not_awaited()
        session.add.assert_not_called()

    def test_missing_application_raises(self):
        session = make_session()
        service = make_service(session)
        service.applications.get_by_id_with_candidate.return_value = None
        matching_service = make_matching_service()

        with pytest.raises(EntityNotFoundException):
            asyncio.run(
                service.get_application_match_explanation(
                    current_user=make_user(),
                    application_id=uuid.uuid4(),
                    matching_service=matching_service,
                )
            )

    def test_unowned_application_raises_not_found(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        service.applications.get_by_id_with_candidate.return_value = application
        matching_service = make_matching_service()

        with patch(
            "app.services.application_service.JobService"
        ) as mock_job_service:
            mock_job_service.return_value.get_recruiter_job_by_id = AsyncMock(
                side_effect=EntityNotFoundException("Application not found")
            )
            with pytest.raises(EntityNotFoundException):
                asyncio.run(
                    service.get_application_match_explanation(
                        current_user=make_user(),
                        application_id=application.id,
                        matching_service=matching_service,
                    )
                )

        matching_service.vector_repository.retrieve_vector.assert_not_awaited()
class _FakeCacheRedis:
    def __init__(
        self,
        values: dict | None = None,
        *,
        get_error: Exception | None = None,
        set_error: Exception | None = None,
    ) -> None:
        self.values = dict(values or {})
        self.get_error = get_error
        self.set_error = set_error
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, str, int | None]] = []

    async def get(self, key: str):
        self.get_calls.append(key)
        if self.get_error is not None:
            raise self.get_error
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.set_calls.append((key, value, ex))
        if self.set_error is not None:
            raise self.set_error
        self.values[key] = value
        return True


def _parsed_job_for(job) -> ParsedJobSchema:
    return ParsedJobSchema(
        title=job.title,
        summary=job.description,
        required_skills=(
            [skill.name for skill in job.required_skills]
            if job.required_skills
            else []
        ),
        preferred_skills=(
            [skill.name for skill in job.preferred_skills]
            if job.preferred_skills
            else []
        ),
        minimum_years_experience=job.minimum_years_experience,
        education_level=job.education_level,
        employment_type=(
            job.job_type.value
            if hasattr(job.job_type, "value")
            else job.job_type
        ),
        workplace_type=(
            job.workplace_type.value
            if hasattr(job.workplace_type, "value")
            else job.workplace_type
        ),
        location=job.location,
        city=job.location,
    )


def _cached_explanation(
    application_id: uuid.UUID,
    overall_score: float,
) -> ApplicationMatchExplanationResponse:
    return ApplicationMatchExplanationResponse(
        application_id=application_id,
        overall_score=overall_score,
        score_breakdown=ScoreBreakdown(
            overall_score=overall_score,
            cosine_similarity=0.5,
            skill_coverage_score=0.5,
            preferred_skill_coverage_score=0.0,
            experience_match_score=0.5,
            education_score=0.5,
            project_score=0.5,
        ),
        summary="Cached deterministic result.",
        summary_source="ai_generated",
        model_version="gemini-cached",
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        cache_state="not_cached",
    )


class TestGetApplicationMatchExplanationCache:
    def _run(
        self,
        service,
        application,
        job,
        resume,
        matching_service,
        cache_service,
        explanation_service=None,
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
            kwargs = {
                "current_user": make_user(),
                "application_id": application.id,
                "matching_service": matching_service,
                "cache_service": cache_service,
            }
            if explanation_service is not None:
                kwargs["explanation_service"] = explanation_service
            return asyncio.run(
                service.get_application_match_explanation(**kwargs)
            )

    def _setup(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        job = make_job()
        resume = make_resume(application.candidate_id)
        service.applications.get_by_id_with_candidate.return_value = application
        matching_service = make_matching_service()
        return application, job, resume, matching_service, service

    def _narrative_spy(self):
        narrative = SimpleNamespace(
            explain_match=AsyncMock(
                return_value=SimpleNamespace(summary="AI narrative")
            )
        )
        return narrative, MatchExplanationService(narrative_service=narrative)

    def test_cache_miss_is_deterministic_and_stores(self):
        application, job, resume, matching_service, service = self._setup()
        redis = _FakeCacheRedis()
        cache = MatchExplanationCache(
            redis, enabled=True, ttl_seconds=604800, version="v1"
        )
        narrative, explanation_service = self._narrative_spy()

        result = self._run(
            service,
            application,
            job,
            resume,
            matching_service,
            cache,
            explanation_service,
        )

        narrative.explain_match.assert_not_awaited()
        assert result.cache_state == "not_cached"
        assert result.summary_source == "deterministic"
        assert result.overall_score == matching_service.matching_engine.match_resume_to_job(
            resume=ParsedResumeSchema.model_validate(resume.parsed_data),
            job=_parsed_job_for(job),
            resume_vector=[1.0, 0.0],
            job_vector=[1.0, 0.0],
        ).overall_score
        by_name = {item.skill_name: item for item in result.skill_evaluations}
        assert by_name["Python"].status == "matched_evidenced"
        assert by_name["Docker"].status == "not_evidenced_in_cv"
        assert by_name["Python"].evidence[0].quote == "Python"
        assert len(redis.set_calls) == 1
        assert redis.set_calls[0][2] == 604800

    def test_second_request_is_served_from_cache_without_provider(self):
        application, job, resume, matching_service, service = self._setup()
        redis = _FakeCacheRedis()
        cache = MatchExplanationCache(
            redis, enabled=True, ttl_seconds=604800, version="v1"
        )
        narrative, explanation_service = self._narrative_spy()

        first = self._run(
            service,
            application,
            job,
            resume,
            matching_service,
            cache,
            explanation_service,
        )
        matching_service.vector_repository.retrieve_vector.reset_mock()
        matching_service.embedding_service.embed_resume.reset_mock()
        matching_service.embedding_service.embed_job.reset_mock()

        second = self._run(
            service,
            application,
            job,
            resume,
            matching_service,
            cache,
            explanation_service,
        )

        narrative.explain_match.assert_not_awaited()
        matching_service.vector_repository.retrieve_vector.assert_not_awaited()
        matching_service.embedding_service.embed_resume.assert_not_awaited()
        matching_service.embedding_service.embed_job.assert_not_awaited()
        assert first.cache_state == "not_cached"
        assert second.cache_state == "cached"
        assert second.generated_at == first.generated_at
        assert second.summary_source == first.summary_source
        assert second.model_version == first.model_version
        assert second.overall_score == first.overall_score
        assert second.evidence == first.evidence
        assert len(redis.set_calls) == 1

    def test_redis_outage_is_deterministic_and_never_calls_provider(self):
        application, job, resume, matching_service, service = self._setup()
        redis = _FakeCacheRedis(
            get_error=ConnectionError("down"),
            set_error=TimeoutError("timeout"),
        )
        cache = MatchExplanationCache(
            redis, enabled=True, ttl_seconds=604800, version="v1"
        )
        narrative, explanation_service = self._narrative_spy()

        result = self._run(
            service,
            application,
            job,
            resume,
            matching_service,
            cache,
            explanation_service,
        )

        narrative.explain_match.assert_not_awaited()
        assert result.cache_state == "not_cached"
        assert result.summary_source == "deterministic"
        assert len(redis.get_calls) == 1
        assert len(redis.set_calls) == 1

    def test_disabled_cache_bypasses_redis_and_provider(self):
        application, job, resume, matching_service, service = self._setup()
        redis = _FakeCacheRedis()
        cache = MatchExplanationCache(
            redis, enabled=False, ttl_seconds=604800, version="v1"
        )
        narrative, explanation_service = self._narrative_spy()

        result = self._run(
            service,
            application,
            job,
            resume,
            matching_service,
            cache,
            explanation_service,
        )

        narrative.explain_match.assert_not_awaited()
        assert result.cache_state == "not_cached"
        assert redis.get_calls == []
        assert redis.set_calls == []

    def test_missing_parsed_resume_bypasses_cache(self):
        application, job, resume, matching_service, service = self._setup()
        resume.parsed_data = None
        redis = _FakeCacheRedis()
        cache = MatchExplanationCache(
            redis, enabled=True, ttl_seconds=604800, version="v1"
        )
        narrative, explanation_service = self._narrative_spy()

        result = self._run(
            service,
            application,
            job,
            resume,
            matching_service,
            cache,
            explanation_service,
        )

        narrative.explain_match.assert_not_awaited()
        assert result.cache_state == "not_cached"
        assert redis.get_calls == []
        assert redis.set_calls == []
        assert result.data_limitations

    def test_ownership_is_verified_before_cache_and_provider(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        service.applications.get_by_id_with_candidate.return_value = application
        matching_service = make_matching_service()
        cache = SimpleNamespace(
            build_key=MagicMock(return_value="key"),
            get=AsyncMock(),
            store=AsyncMock(),
        )

        with patch(
            "app.services.application_service.JobService"
        ) as mock_job_service:
            mock_job_service.return_value.get_recruiter_job_by_id = AsyncMock(
                side_effect=EntityNotFoundException("Application not found")
            )
            with pytest.raises(EntityNotFoundException):
                asyncio.run(
                    service.get_application_match_explanation(
                        current_user=make_user(),
                        application_id=application.id,
                        matching_service=matching_service,
                        cache_service=cache,
                    )
                )

        cache.build_key.assert_not_called()
        cache.get.assert_not_awaited()
        cache.store.assert_not_awaited()
        matching_service.vector_repository.retrieve_vector.assert_not_awaited()

    def test_cached_response_for_another_application_is_a_miss(self):
        application, job, resume, matching_service, service = self._setup()
        parsed_resume = ParsedResumeSchema.model_validate(resume.parsed_data)
        parsed_job = _parsed_job_for(job)
        cache = MatchExplanationCache(
            _FakeCacheRedis(), enabled=True, ttl_seconds=604800, version="v1"
        )
        key = cache.build_key(application.id, parsed_resume, parsed_job)
        assert key is not None
        foreign = _cached_explanation(uuid.uuid4(), overall_score=1.0)
        cache.redis.values[key] = json.dumps(foreign.model_dump(mode="json"))
        narrative, explanation_service = self._narrative_spy()

        result = self._run(
            service,
            application,
            job,
            resume,
            matching_service,
            cache,
            explanation_service,
        )

        narrative.explain_match.assert_not_awaited()
        assert result.application_id == application.id
        assert result.cache_state == "not_cached"
        assert len(cache.redis.set_calls) == 1
    def test_preloaded_ai_explanation_is_served_from_cache(self):
        application, job, resume, matching_service, service = self._setup()
        parsed_resume = ParsedResumeSchema.model_validate(resume.parsed_data)
        parsed_job = _parsed_job_for(job)
        cache = MatchExplanationCache(
            _FakeCacheRedis(), enabled=True, ttl_seconds=604800, version="v1"
        )
        key = cache.build_key(application.id, parsed_resume, parsed_job)
        assert key is not None
        ai_response = _cached_explanation(application.id, overall_score=77.5)
        cache.redis.values[key] = json.dumps(
            ai_response.model_dump(mode="json")
        )
        narrative, explanation_service = self._narrative_spy()

        result = self._run(
            service,
            application,
            job,
            resume,
            matching_service,
            cache,
            explanation_service,
        )

        narrative.explain_match.assert_not_awaited()
        matching_service.vector_repository.retrieve_vector.assert_not_awaited()
        assert result.cache_state == "cached"
        assert result.summary_source == "ai_generated"
        assert result.model_version == "gemini-cached"
        assert result.generated_at == ai_response.generated_at
        assert cache.redis.set_calls == []
