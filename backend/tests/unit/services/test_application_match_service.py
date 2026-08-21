import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.matching.matching_engine import MatchingEngine
from app.core.exceptions import AIError, EntityNotFoundException
from app.domain.enums import ApplicationStatus, UserRole
from app.models import Application, Job, Resume, Skill
from app.repositories import ApplicationRepository, JobRepository, ResumeRepository
from app.schemas.ai_match import MatchResultSchema
from app.services.application_service import ApplicationService


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
    )
    job.skills = [Skill(name="Python"), Skill(name="Docker")]
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
        embed_resume=MagicMock(return_value=resume_vector or [1.0, 0.0]),
        embed_job=MagicMock(return_value=job_vector or [1.0, 0.0]),
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
        assert "Python" in result.matching_skills
        assert "Docker" in result.skill_gap
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
        assert result.skill_coverage_score == 0.0

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
        assert result.skill_gap == ["Python", "Docker"]
        matching_service.vector_repository.retrieve_vector.assert_any_await(
            collection_name="jobs", point_id=application.job_id
        )

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