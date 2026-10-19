"""Atomicity guarantees for hiring-pipeline status mutations.

A status change, its history row and (for outcome statuses) its outbox row must
commit or roll back as one unit. These tests drive the real ``ApplicationService``
against SQL Server and force the second write to fail, proving the status UPDATE
is undone and no partial activity/email row survives.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.core.exceptions import InvalidTransitionException
from app.database.session import async_session_factory
from app.domain.enums import (
    ApplicationStatus,
    CompanySize,
    JobStatus,
    JobType,
    UserRole,
    WorkplaceType,
)
from app.models import (
    Application,
    ApplicationActivity,
    CandidateProfile,
    Company,
    EmailOutbox,
    Job,
    RecruiterProfile,
    User,
)
from app.services.application_service import ApplicationService

pytestmark = pytest.mark.integration


async def _seed(session):
    company = Company(
        id=uuid.uuid4(),
        name="Atomic Co",
        slug=f"atomic-co-{uuid.uuid4().hex[:8]}",
        tax_code=str(uuid.uuid4().int)[:12],
        size=CompanySize.STARTUP,
    )
    session.add(company)
    await session.flush()

    recruiter = User(
        id=uuid.uuid4(),
        email=f"rec-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="hash",
        role=UserRole.RECRUITER,
        is_active=True,
    )
    candidate = User(
        id=uuid.uuid4(),
        email=f"cand-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="hash",
        role=UserRole.CANDIDATE,
        is_active=True,
    )
    session.add_all([recruiter, candidate])
    await session.flush()

    session.add(RecruiterProfile(user_id=recruiter.id, company_id=company.id))
    candidate_profile = CandidateProfile(
        id=uuid.uuid4(), user_id=candidate.id, full_name="Atomic Candidate"
    )
    session.add(candidate_profile)
    await session.flush()

    job = Job(
        id=uuid.uuid4(),
        company_id=company.id,
        title="Atomic Job",
        description="desc",
        status=JobStatus.PUBLISHED,
        job_type=JobType.FULL_TIME,
        workplace_type=WorkplaceType.REMOTE,
        location="Remote",
    )
    session.add(job)
    await session.flush()

    application = Application(
        id=uuid.uuid4(),
        candidate_id=candidate_profile.id,
        job_id=job.id,
        status=ApplicationStatus.APPLIED,
    )
    session.add(application)
    await session.flush()
    await session.commit()
    return application.id, recruiter.id


async def _assert_untouched(application_id, recruiter_id):
    async with async_session_factory() as session:
        application = await session.get(Application, application_id)
        assert application.status == ApplicationStatus.APPLIED

        activity_count = int(
            (
                await session.execute(
                    sa.select(sa.func.count()).select_from(ApplicationActivity)
                )
            ).scalar_one()
        )
        assert activity_count == 0

        outbox_count = int(
            (
                await session.execute(
                    sa.select(sa.func.count()).select_from(EmailOutbox)
                )
            ).scalar_one()
        )
        assert outbox_count == 0


class TestStatusMutationAtomicity:
    def test_outbox_failure_rolls_back_status_and_activity(
        self, run_async, monkeypatch
    ):
        async def _boom(*args, **kwargs):
            raise RuntimeError("outbox unavailable")

        async def _test():
            async with async_session_factory() as session:
                application_id, recruiter_id = await _seed(session)

            monkeypatch.setattr(
                "app.services.application_service.schedule_application_status_email",
                _boom,
            )

            async with async_session_factory() as session:
                recruiter = await session.get(User, recruiter_id)
                with pytest.raises(RuntimeError):
                    await ApplicationService(session).update_application_status(
                        current_user=recruiter,
                        application_id=application_id,
                        new_status=ApplicationStatus.UNDER_REVIEW,
                    )

            await _assert_untouched(application_id, recruiter_id)

        run_async(_test())

    def test_activity_failure_rolls_back_status(self, run_async, monkeypatch):
        async def _boom(*args, **kwargs):
            raise RuntimeError("activity store unavailable")

        async def _test():
            async with async_session_factory() as session:
                application_id, recruiter_id = await _seed(session)

            monkeypatch.setattr(
                "app.services.application_service.record_activity", _boom
            )

            async with async_session_factory() as session:
                recruiter = await session.get(User, recruiter_id)
                with pytest.raises(RuntimeError):
                    await ApplicationService(session).update_application_status(
                        current_user=recruiter,
                        application_id=application_id,
                        new_status=ApplicationStatus.UNDER_REVIEW,
                    )

            await _assert_untouched(application_id, recruiter_id)

        run_async(_test())

    def test_invalid_transition_is_rejected_before_any_write(self, run_async):
        async def _test():
            async with async_session_factory() as session:
                application_id, recruiter_id = await _seed(session)

            async with async_session_factory() as session:
                recruiter = await session.get(User, recruiter_id)
                with pytest.raises(InvalidTransitionException):
                    await ApplicationService(session).update_application_status(
                        current_user=recruiter,
                        application_id=application_id,
                        new_status=ApplicationStatus.OFFERED,
                    )

            await _assert_untouched(application_id, recruiter_id)

        run_async(_test())

    def test_successful_mutation_commits_activity_and_outbox(self, run_async):
        async def _test():
            async with async_session_factory() as session:
                application_id, recruiter_id = await _seed(session)

            async with async_session_factory() as session:
                recruiter = await session.get(User, recruiter_id)
                application = await ApplicationService(
                    session
                ).update_application_status(
                    current_user=recruiter,
                    application_id=application_id,
                    new_status=ApplicationStatus.UNDER_REVIEW,
                )
                assert application.status == ApplicationStatus.UNDER_REVIEW

            async with async_session_factory() as session:
                application = await session.get(Application, application_id)
                assert application.status == ApplicationStatus.UNDER_REVIEW
                activities = list(
                    (
                        await session.execute(sa.select(ApplicationActivity))
                    ).scalars()
                )
                assert len(activities) == 1
                assert activities[0].action_type == "status_changed"
                assert activities[0].from_status == "applied"
                assert activities[0].to_status == "under_review"

        run_async(_test())
