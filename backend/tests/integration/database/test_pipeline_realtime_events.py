"""Real SQL Server tests for hiring-pipeline invalidation events."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.database.session import async_session_factory
from app.domain import hiring
from app.domain.enums import (
    ApplicationStatus,
    CompanySize,
    InterviewStatus,
    InterviewType,
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
    Interview,
    Job,
    Notification,
    RecruiterProfile,
    User,
)
from app.schemas.interview import InterviewCreate
from app.services.application_service import ApplicationService
from app.services.interview_service import InterviewService
from app.services.pipeline_realtime import (
    ACTION_APPLICATION_STATUS_CHANGED,
    ACTION_INTERVIEW_CANCELLED,
    ACTION_INTERVIEW_DECLINED,
    company_pipeline_channel,
    user_pipeline_channel,
)

pytestmark = pytest.mark.integration

_PUBSUB_TARGET = "app.services.pipeline_realtime.pubsub_manager"


def _fake_manager() -> MagicMock:
    manager = MagicMock()
    manager.publish = AsyncMock()
    return manager


async def _seed(session):
    company = Company(
        id=uuid.uuid4(),
        name="Realtime Co",
        slug=f"realtime-co-{uuid.uuid4().hex[:8]}",
        tax_code=str(uuid.uuid4().int)[:12],
        size=CompanySize.STARTUP,
    )
    recruiter = User(
        id=uuid.uuid4(),
        email=f"rt-rec-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="hash",
        role=UserRole.RECRUITER,
        is_active=True,
    )
    candidate = User(
        id=uuid.uuid4(),
        email=f"rt-cand-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="hash",
        role=UserRole.CANDIDATE,
        is_active=True,
    )
    session.add_all([company, recruiter, candidate])
    await session.flush()

    session.add(RecruiterProfile(user_id=recruiter.id, company_id=company.id))
    profile = CandidateProfile(
        id=uuid.uuid4(), user_id=candidate.id, full_name="Realtime Candidate"
    )
    session.add(profile)
    await session.flush()

    job = Job(
        id=uuid.uuid4(),
        company_id=company.id,
        title="Realtime Job",
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
        candidate_id=profile.id,
        job_id=job.id,
        status=ApplicationStatus.APPLIED,
    )
    session.add(application)
    await session.commit()
    return {
        "company_id": company.id,
        "job_id": job.id,
        "application_id": application.id,
        "candidate_user_id": candidate.id,
        "recruiter_id": recruiter.id,
    }


async def _seed_interview(
    application_id,
    *,
    status=InterviewStatus.SCHEDULED,
    is_deleted=False,
):
    async with async_session_factory() as session:
        application = await session.get(Application, application_id)
        assert application is not None
        application.status = ApplicationStatus.INTERVIEWING
        interview = Interview(
            id=uuid.uuid4(),
            application_id=application_id,
            scheduled_at=datetime.now(timezone.utc) + timedelta(days=2),
            duration_minutes=60,
            interview_type=InterviewType.TECHNICAL,
            status=status,
            is_deleted=is_deleted,
        )
        session.add(interview)
        await session.commit()
        return interview.id


def _pipeline_messages(manager):
    return {
        call.args[0]: call.args[1]
        for call in manager.publish.await_args_list
    }


def test_status_change_publishes_company_and_candidate_events(run_async):
    async def _test():
        async with async_session_factory() as setup:
            ids = await _seed(setup)

        manager = _fake_manager()
        with patch(_PUBSUB_TARGET, manager):
            async with async_session_factory() as session:
                recruiter = await session.get(User, ids["recruiter_id"])
                await ApplicationService(session).update_application_status(
                    current_user=recruiter,
                    application_id=ids["application_id"],
                    new_status=ApplicationStatus.UNDER_REVIEW,
                )
                await asyncio.sleep(0.05)

        assert manager.publish.await_count == 2
        calls = {
            call.args[0]: call.args[1]
            for call in manager.publish.await_args_list
        }
        company_message = calls[
            company_pipeline_channel(ids["company_id"])
        ]
        candidate_message = calls[
            user_pipeline_channel(ids["candidate_user_id"])
        ]
        for message in (company_message, candidate_message):
            assert message["action"] == ACTION_APPLICATION_STATUS_CHANGED
            assert message["from_status"] == "applied"
            assert message["to_status"] == "under_review"
            assert message["application_id"] == str(ids["application_id"])
            assert message["job_id"] == str(ids["job_id"])

    run_async(_test())


def test_commit_failure_discards_queued_event(run_async):
    async def _test():
        async with async_session_factory() as setup:
            ids = await _seed(setup)

        manager = _fake_manager()
        with patch(_PUBSUB_TARGET, manager):
            async with async_session_factory() as session:
                recruiter = await session.get(User, ids["recruiter_id"])
                with patch.object(
                    session,
                    "commit",
                    new=AsyncMock(side_effect=RuntimeError("db down")),
                ):
                    with pytest.raises(RuntimeError):
                        await ApplicationService(
                            session
                        ).update_application_status(
                            current_user=recruiter,
                            application_id=ids["application_id"],
                            new_status=ApplicationStatus.UNDER_REVIEW,
                        )
                await asyncio.sleep(0.05)

        manager.publish.assert_not_awaited()

        async with async_session_factory() as check:
            stored = await check.get(Application, ids["application_id"])
            assert stored.status == ApplicationStatus.APPLIED

    run_async(_test())


def test_publish_failure_does_not_fail_committed_mutation(run_async):
    async def _test():
        async with async_session_factory() as setup:
            ids = await _seed(setup)

        manager = _fake_manager()
        manager.publish.side_effect = RuntimeError("redis down")
        with patch(_PUBSUB_TARGET, manager):
            async with async_session_factory() as session:
                recruiter = await session.get(User, ids["recruiter_id"])
                await ApplicationService(session).update_application_status(
                    current_user=recruiter,
                    application_id=ids["application_id"],
                    new_status=ApplicationStatus.UNDER_REVIEW,
                )
                await asyncio.sleep(0.05)

        manager.publish.assert_awaited()
        async with async_session_factory() as check:
            stored = await check.get(Application, ids["application_id"])
            assert stored.status == ApplicationStatus.UNDER_REVIEW

    run_async(_test())

def test_candidate_decline_reconciles_stage_and_publishes_final_status(run_async):
    async def _test():
        async with async_session_factory() as setup:
            ids = await _seed(setup)
        interview_id = await _seed_interview(ids["application_id"])

        manager = _fake_manager()
        with patch(_PUBSUB_TARGET, manager):
            async with async_session_factory() as session:
                candidate = await session.get(User, ids["candidate_user_id"])
                await InterviewService(session).candidate_action_interview(
                    current_user=candidate,
                    application_id=ids["application_id"],
                    interview_id=interview_id,
                    action="decline",
                    candidate_notes="Cannot attend",
                )
                await asyncio.sleep(0.05)

        calls = _pipeline_messages(manager)
        company_message = calls[company_pipeline_channel(ids["company_id"])]
        candidate_message = calls[user_pipeline_channel(ids["candidate_user_id"])]
        for message in (company_message, candidate_message):
            assert message["action"] == ACTION_INTERVIEW_DECLINED
            assert message["from_status"] == "interviewing"
            assert message["to_status"] == "under_review"

        async with async_session_factory() as check:
            application = await check.get(Application, ids["application_id"])
            interview = await check.get(Interview, interview_id)
            assert application.status == ApplicationStatus.UNDER_REVIEW
            assert interview.status == InterviewStatus.CANDIDATE_DECLINED
            assert interview.candidate_notes == "Cannot attend"
            rows = list(
                (
                    await check.execute(
                        select(ApplicationActivity).where(
                            ApplicationActivity.application_id
                            == ids["application_id"]
                        )
                    )
                ).scalars()
            )
            assert {row.action_type for row in rows} == {
                hiring.INTERVIEW_DECLINED,
                hiring.STATUS_CHANGED,
            }

        # A new interview moves the reconciled application back to interviewing.
        with patch(_PUBSUB_TARGET, _fake_manager()):
            async with async_session_factory() as session:
                recruiter = await session.get(User, ids["recruiter_id"])
                await InterviewService(session).schedule_interview(
                    current_user=recruiter,
                    application_id=ids["application_id"],
                    data=InterviewCreate(
                        scheduled_at=(
                            datetime.now(timezone.utc) + timedelta(days=4)
                        ),
                        duration_minutes=60,
                        interview_type="technical",
                    ),
                )
        async with async_session_factory() as check:
            application = await check.get(Application, ids["application_id"])
            assert application.status == ApplicationStatus.INTERVIEWING

    run_async(_test())


def test_recruiter_cancellation_reconciles_stage_and_publishes_final_status(
    run_async,
):
    async def _test():
        async with async_session_factory() as setup:
            ids = await _seed(setup)
        interview_id = await _seed_interview(ids["application_id"])

        manager = _fake_manager()
        with patch(_PUBSUB_TARGET, manager):
            async with async_session_factory() as session:
                recruiter = await session.get(User, ids["recruiter_id"])
                await InterviewService(session).cancel_interview(
                    current_user=recruiter,
                    interview_id=interview_id,
                )
                await asyncio.sleep(0.05)

        calls = _pipeline_messages(manager)
        company_message = calls[company_pipeline_channel(ids["company_id"])]
        candidate_message = calls[user_pipeline_channel(ids["candidate_user_id"])]
        for message in (company_message, candidate_message):
            assert message["action"] == ACTION_INTERVIEW_CANCELLED
            assert message["from_status"] == "interviewing"
            assert message["to_status"] == "under_review"

        async with async_session_factory() as check:
            application = await check.get(Application, ids["application_id"])
            interview = await check.get(Interview, interview_id)
            assert application.status == ApplicationStatus.UNDER_REVIEW
            assert interview.status == InterviewStatus.CANCELLED
            assert interview.is_deleted is True
            rows = list(
                (
                    await check.execute(
                        select(ApplicationActivity).where(
                            ApplicationActivity.application_id
                            == ids["application_id"]
                        )
                    )
                ).scalars()
            )
            assert {row.action_type for row in rows} == {
                hiring.INTERVIEW_CANCELLED,
                hiring.STATUS_CHANGED,
            }

    run_async(_test())


def test_decline_rollback_discards_stage_and_pipeline_event(run_async):
    async def _test():
        async with async_session_factory() as setup:
            ids = await _seed(setup)
        interview_id = await _seed_interview(ids["application_id"])

        manager = _fake_manager()
        with patch(_PUBSUB_TARGET, manager):
            async with async_session_factory() as session:
                candidate = await session.get(User, ids["candidate_user_id"])
                with patch.object(
                    session,
                    "commit",
                    new=AsyncMock(side_effect=RuntimeError("db down")),
                ):
                    with pytest.raises(RuntimeError):
                        await InterviewService(
                            session
                        ).candidate_action_interview(
                            current_user=candidate,
                            application_id=ids["application_id"],
                            interview_id=interview_id,
                            action="decline",
                            candidate_notes="Rollback test",
                        )
                await asyncio.sleep(0.05)

        manager.publish.assert_not_awaited()

        async with async_session_factory() as check:
            application = await check.get(Application, ids["application_id"])
            interview = await check.get(Interview, interview_id)
            assert application.status == ApplicationStatus.INTERVIEWING
            assert interview.status == InterviewStatus.SCHEDULED
            rows = list(
                (
                    await check.execute(
                        select(ApplicationActivity).where(
                            ApplicationActivity.application_id
                            == ids["application_id"]
                        )
                    )
                ).scalars()
            )
            assert rows == []
            notifications = list(
                (
                    await check.execute(
                        select(Notification).where(
                            Notification.entity_id == interview_id
                        )
                    )
                ).scalars()
            )
            assert notifications == []

    run_async(_test())

def test_soft_deleted_active_interview_does_not_block_reconciliation(run_async):
    async def _test():
        async with async_session_factory() as setup:
            ids = await _seed(setup)
        await _seed_interview(ids["application_id"], is_deleted=True)
        interview_id = await _seed_interview(ids["application_id"])

        manager = _fake_manager()
        with patch(_PUBSUB_TARGET, manager):
            async with async_session_factory() as session:
                candidate = await session.get(User, ids["candidate_user_id"])
                await InterviewService(session).candidate_action_interview(
                    current_user=candidate,
                    application_id=ids["application_id"],
                    interview_id=interview_id,
                    action="decline",
                    candidate_notes="Cannot attend",
                )
                await asyncio.sleep(0.05)

        async with async_session_factory() as check:
            application = await check.get(Application, ids["application_id"])
            assert application.status == ApplicationStatus.UNDER_REVIEW

    run_async(_test())
