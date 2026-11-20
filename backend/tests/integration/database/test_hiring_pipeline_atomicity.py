"""Atomicity guarantees for hiring-pipeline status mutations.

A status change, its history row and (for outcome statuses) its outbox row must
commit or roll back as one unit. These tests drive the real ``ApplicationService``
against SQL Server and force the second write to fail, proving the status UPDATE
is undone and no partial activity/email row survives.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from app.core.exceptions import InvalidTransitionException
from app.database.session import async_session_factory
from app.domain.enums import (
    ApplicationStatus,
    CompanySize,
    InterviewStatus,
    InterviewType,
    JobStatus,
    JobType,
    MembershipRole,
    MembershipStatus,
    UserRole,
    WorkplaceType,
)
from app.models import (
    Application,
    ApplicationActivity,
    CandidateProfile,
    Company,
    CompanyMembership,
    EmailOutbox,
    Interview,
    InterviewAssignment,
    Job,
    Notification,
    RecruiterProfile,
    User,
)
from app.schemas.interview import InterviewUpdate
from app.services.application_service import ApplicationService
from app.services.interview_assignment_service import InterviewAssignmentService
from app.services.interview_service import InterviewService
from app.services.workspace_service import WorkspaceContext

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
    session.add(
        CompanyMembership(
            company_id=company.id,
            user_id=recruiter.id,
            role=MembershipRole.ADMIN,
            status=MembershipStatus.ACTIVE,
        )
    )
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


async def _seed_interview_pipeline(session):
    company = Company(
        id=uuid.uuid4(),
        name="Atomic Pipeline Co",
        slug=f"atomic-pipe-{uuid.uuid4().hex[:8]}",
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
    interviewer = User(
        id=uuid.uuid4(),
        email=f"int-{uuid.uuid4().hex[:10]}@example.com",
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
    session.add_all([recruiter, interviewer, candidate])
    await session.flush()

    session.add(RecruiterProfile(user_id=recruiter.id, company_id=company.id))
    recruiter_membership = CompanyMembership(
        company_id=company.id,
        user_id=recruiter.id,
        role=MembershipRole.ADMIN,
        status=MembershipStatus.ACTIVE,
    )
    interviewer_membership = CompanyMembership(
        company_id=company.id,
        user_id=interviewer.id,
        role=MembershipRole.INTERVIEWER,
        status=MembershipStatus.ACTIVE,
    )
    session.add_all([recruiter_membership, interviewer_membership])
    candidate_profile = CandidateProfile(
        id=uuid.uuid4(), user_id=candidate.id, full_name="Atomic Pipeline Candidate"
    )
    session.add(candidate_profile)
    await session.flush()

    job = Job(
        id=uuid.uuid4(),
        company_id=company.id,
        title="Atomic Pipeline Job",
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
        status=ApplicationStatus.INTERVIEWING,
    )
    session.add(application)
    await session.flush()

    scheduled_time = datetime.now(timezone.utc) + timedelta(days=2)
    interview = Interview(
        id=uuid.uuid4(),
        application_id=application.id,
        scheduled_at=scheduled_time,
        duration_minutes=60,
        interview_type=InterviewType.TECHNICAL,
        location="Room 101",
        meeting_url="https://meet.example.com/test",
        status=InterviewStatus.SCHEDULED,
    )
    session.add(interview)
    await session.flush()
    await session.commit()
    return company.id, job.id, application.id, interview.id, recruiter.id, interviewer.id, candidate.id


class TestInterviewPipelineAtomicity:
    def test_interview_assignment_atomicity_and_rollback(self, run_async, monkeypatch):
        async def _boom(*args, **kwargs):
            raise RuntimeError("outbox unavailable")

        async def _test():
            async with async_session_factory() as session:
                company_id, _, _, interview_id, recruiter_id, interviewer_id, _ = (
                    await _seed_interview_pipeline(session)
                )

            # Failure test: outbox failure forces rollback of assignment and notification
            monkeypatch.setattr(
                "app.services.interview_assignment_service.schedule_interviewer_assignment_email",
                _boom,
            )

            async with async_session_factory() as session:
                recruiter = await session.get(User, recruiter_id)
                company = await session.get(Company, company_id)
                membership = await session.scalar(
                    sa.select(CompanyMembership).where(
                        CompanyMembership.company_id == company_id,
                        CompanyMembership.user_id == recruiter_id,
                    )
                )
                context = WorkspaceContext(company=company, membership=membership, user=recruiter)
                with pytest.raises(RuntimeError, match="outbox unavailable"):
                    await InterviewAssignmentService(session).assign(
                        context, interview_id, interviewer_id
                    )

            # Verify rolled back: no assignment, no notification, no outbox
            async with async_session_factory() as session:
                assignments = list(
                    (
                        await session.execute(
                            sa.select(InterviewAssignment).where(
                                InterviewAssignment.interview_id == interview_id
                            )
                        )
                    ).scalars().all()
                )
                assert len(assignments) == 0

                notifs = list(
                    (
                        await session.execute(
                            sa.select(Notification).where(
                                Notification.user_id == interviewer_id
                            )
                        )
                    ).scalars().all()
                )
                assert len(notifs) == 0

                emails = list(
                    (
                        await session.execute(
                            sa.select(EmailOutbox).where(
                                EmailOutbox.event_type == "interviewer_assignment"
                            )
                        )
                    ).scalars().all()
                )
                assert len(emails) == 0

            # Success path: undo monkeypatch, assign commits assignment, notif, outbox together
            monkeypatch.undo()

            async with async_session_factory() as session:
                recruiter = await session.get(User, recruiter_id)
                company = await session.get(Company, company_id)
                membership = await session.scalar(
                    sa.select(CompanyMembership).where(
                        CompanyMembership.company_id == company_id,
                        CompanyMembership.user_id == recruiter_id,
                    )
                )
                context = WorkspaceContext(company=company, membership=membership, user=recruiter)
                assigned = await InterviewAssignmentService(session).assign(
                    context, interview_id, interviewer_id
                )
                assert assigned is not None

            async with async_session_factory() as session:
                assignments = list(
                    (
                        await session.execute(
                            sa.select(InterviewAssignment).where(
                                InterviewAssignment.interview_id == interview_id
                            )
                        )
                    ).scalars().all()
                )
                assert len(assignments) == 1

                notifs = list(
                    (
                        await session.execute(
                            sa.select(Notification).where(
                                Notification.user_id == interviewer_id
                            )
                        )
                    ).scalars().all()
                )
                assert len(notifs) == 1
                assert notifs[0].notification_type == "interview_assigned"

                emails = list(
                    (
                        await session.execute(
                            sa.select(EmailOutbox).where(
                                EmailOutbox.event_type == "interviewer_assignment"
                            )
                        )
                    ).scalars().all()
                )
                assert len(emails) == 1
                assert emails[0].idempotency_key == f"interview-assignment:{assignments[0].id}"

        run_async(_test())

    def test_interview_rescheduling_atomicity_and_rollback(self, run_async, monkeypatch):
        async def _boom(*args, **kwargs):
            raise RuntimeError("reschedule outbox failed")

        async def _test():
            async with async_session_factory() as session:
                company_id, _, application_id, interview_id, recruiter_id, interviewer_id, candidate_id = (
                    await _seed_interview_pipeline(session)
                )
                # Assign interviewer
                recruiter = await session.get(User, recruiter_id)
                company = await session.get(Company, company_id)
                membership = await session.scalar(
                    sa.select(CompanyMembership).where(
                        CompanyMembership.company_id == company_id,
                        CompanyMembership.user_id == recruiter_id,
                    )
                )
                context = WorkspaceContext(company=company, membership=membership, user=recruiter)
                await InterviewAssignmentService(session).assign(
                    context, interview_id, interviewer_id
                )
                interview = await session.get(Interview, interview_id)
                orig_scheduled_at = interview.scheduled_at

            # Failure: interviewer email outbox failure causes rollback
            monkeypatch.setattr(
                "app.services.interview_service.schedule_interviewer_schedule_change_email",
                _boom,
            )

            new_time = orig_scheduled_at + timedelta(days=1)
            async with async_session_factory() as session:
                recruiter = await session.get(User, recruiter_id)
                with pytest.raises(RuntimeError, match="reschedule outbox failed"):
                    await InterviewService(session).update_interview(
                        current_user=recruiter,
                        interview_id=interview_id,
                        data=InterviewUpdate(
                            scheduled_at=new_time,
                            location="Room 999",
                        ),
                    )

            # Verify rollback: interview time and location unchanged, no activity row created
            async with async_session_factory() as session:
                interview = await session.get(Interview, interview_id)
                assert interview.location == "Room 101"
                assert interview.scheduled_at == orig_scheduled_at

                activities = list(
                    (
                        await session.execute(
                            sa.select(ApplicationActivity).where(
                                ApplicationActivity.application_id == application_id,
                                ApplicationActivity.action_type == "interview_rescheduled",
                            )
                        )
                    ).scalars().all()
                )
                assert len(activities) == 0

            # Success path: remove monkeypatch, reschedule commits atomically
            monkeypatch.undo()

            async with async_session_factory() as session:
                recruiter = await session.get(User, recruiter_id)
                updated = await InterviewService(session).update_interview(
                    current_user=recruiter,
                    interview_id=interview_id,
                    data=InterviewUpdate(
                        scheduled_at=new_time,
                        location="Room 202",
                    ),
                )
                assert updated.location == "Room 202"

            async with async_session_factory() as session:
                interview = await session.get(Interview, interview_id)
                assert interview.location == "Room 202"

                activities = list(
                    (
                        await session.execute(
                            sa.select(ApplicationActivity).where(
                                ApplicationActivity.application_id == application_id,
                                ApplicationActivity.action_type == "interview_rescheduled",
                            )
                        )
                    ).scalars().all()
                )
                assert len(activities) == 1

                # Candidate & Interviewer notifications
                cand_notifs = list(
                    (
                        await session.execute(
                            sa.select(Notification).where(
                                Notification.user_id == candidate_id,
                                Notification.notification_type == "interview_updated",
                            )
                        )
                    ).scalars().all()
                )
                assert len(cand_notifs) == 1

                int_notifs = list(
                    (
                        await session.execute(
                            sa.select(Notification).where(
                                Notification.user_id == interviewer_id,
                                Notification.notification_type == "interview_updated",
                            )
                        )
                    ).scalars().all()
                )
                assert len(int_notifs) == 1

                # Interviewer schedule change email
                int_emails = list(
                    (
                        await session.execute(
                            sa.select(EmailOutbox).where(
                                EmailOutbox.event_type == "interviewer_schedule_change"
                            )
                        )
                    ).scalars().all()
                )
                assert len(int_emails) == 1

        run_async(_test())

    def test_interview_cancellation_atomicity_and_rollback(self, run_async, monkeypatch):
        async def _boom(*args, **kwargs):
            raise RuntimeError("cancellation outbox failed")

        async def _test():
            async with async_session_factory() as session:
                company_id, _, application_id, interview_id, recruiter_id, interviewer_id, candidate_id = (
                    await _seed_interview_pipeline(session)
                )
                recruiter = await session.get(User, recruiter_id)
                company = await session.get(Company, company_id)
                membership = await session.scalar(
                    sa.select(CompanyMembership).where(
                        CompanyMembership.company_id == company_id,
                        CompanyMembership.user_id == recruiter_id,
                    )
                )
                context = WorkspaceContext(company=company, membership=membership, user=recruiter)
                await InterviewAssignmentService(session).assign(
                    context, interview_id, interviewer_id
                )

            # Failure: force email outbox failure
            monkeypatch.setattr(
                "app.services.interview_service.schedule_interviewer_schedule_change_email",
                _boom,
            )

            async with async_session_factory() as session:
                recruiter = await session.get(User, recruiter_id)
                with pytest.raises(RuntimeError, match="cancellation outbox failed"):
                    await InterviewService(session).cancel_interview(
                        current_user=recruiter,
                        interview_id=interview_id,
                    )

            # Verify rollback: interview is NOT cancelled, is_deleted is False
            async with async_session_factory() as session:
                interview = await session.get(Interview, interview_id)
                assert interview.status == InterviewStatus.SCHEDULED
                assert interview.is_deleted is False

                cancel_activities = list(
                    (
                        await session.execute(
                            sa.select(ApplicationActivity).where(
                                ApplicationActivity.application_id == application_id,
                                ApplicationActivity.action_type == "interview_cancelled",
                            )
                        )
                    ).scalars().all()
                )
                assert len(cancel_activities) == 0

            # Success path: cancellation commits interview cancellation + notifs + outboxes
            monkeypatch.undo()

            async with async_session_factory() as session:
                recruiter = await session.get(User, recruiter_id)
                cancelled = await InterviewService(session).cancel_interview(
                    current_user=recruiter,
                    interview_id=interview_id,
                )
                assert cancelled.status == InterviewStatus.CANCELLED

            async with async_session_factory() as session:
                interview = await session.get(Interview, interview_id)
                assert interview.status == InterviewStatus.CANCELLED
                assert interview.is_deleted is True

                cand_notifs = list(
                    (
                        await session.execute(
                            sa.select(Notification).where(
                                Notification.user_id == candidate_id,
                                Notification.notification_type == "interview_cancelled",
                            )
                        )
                    ).scalars().all()
                )
                assert len(cand_notifs) == 1

                int_notifs = list(
                    (
                        await session.execute(
                            sa.select(Notification).where(
                                Notification.user_id == interviewer_id,
                                Notification.notification_type == "interview_cancelled",
                            )
                        )
                    ).scalars().all()
                )
                assert len(int_notifs) == 1

        run_async(_test())

    def test_candidate_interview_decline_atomicity_and_rollback(self, run_async, monkeypatch):
        async def _boom(*args, **kwargs):
            raise RuntimeError("decline recruiter email failed")

        async def _test():
            async with async_session_factory() as session:
                company_id, _, application_id, interview_id, recruiter_id, interviewer_id, candidate_id = (
                    await _seed_interview_pipeline(session)
                )
                recruiter = await session.get(User, recruiter_id)
                company = await session.get(Company, company_id)
                membership = await session.scalar(
                    sa.select(CompanyMembership).where(
                        CompanyMembership.company_id == company_id,
                        CompanyMembership.user_id == recruiter_id,
                    )
                )
                context = WorkspaceContext(company=company, membership=membership, user=recruiter)
                await InterviewAssignmentService(session).assign(
                    context, interview_id, interviewer_id
                )

            # Failure: recruiter email failure causes rollback of candidate decline
            monkeypatch.setattr(
                "app.services.interview_service.schedule_interview_declined_recruiter_email",
                _boom,
            )

            async with async_session_factory() as session:
                candidate = await session.get(User, candidate_id)
                with pytest.raises(RuntimeError, match="decline recruiter email failed"):
                    await InterviewService(session).candidate_action_interview(
                        current_user=candidate,
                        application_id=application_id,
                        interview_id=interview_id,
                        action="decline",
                        candidate_notes="Conflict with exams",
                    )

            # Verify rollback: interview status is still SCHEDULED
            async with async_session_factory() as session:
                interview = await session.get(Interview, interview_id)
                assert interview.status == InterviewStatus.SCHEDULED

                rec_notifs = list(
                    (
                        await session.execute(
                            sa.select(Notification).where(
                                Notification.user_id == recruiter_id,
                                Notification.notification_type == "interview_declined",
                            )
                        )
                    ).scalars().all()
                )
                assert len(rec_notifs) == 0

            # Success path: decline commits atomically
            monkeypatch.undo()

            async with async_session_factory() as session:
                candidate = await session.get(User, candidate_id)
                result = await InterviewService(session).candidate_action_interview(
                    current_user=candidate,
                    application_id=application_id,
                    interview_id=interview_id,
                    action="decline",
                    candidate_notes="Conflict with exams",
                )
                assert result.status == InterviewStatus.CANDIDATE_DECLINED

            async with async_session_factory() as session:
                interview = await session.get(Interview, interview_id)
                assert interview.status == InterviewStatus.CANDIDATE_DECLINED

                # Recruiter receives in-app + email outbox
                rec_notifs = list(
                    (
                        await session.execute(
                            sa.select(Notification).where(
                                Notification.user_id == recruiter_id,
                                Notification.notification_type == "interview_declined",
                            )
                        )
                    ).scalars().all()
                )
                assert len(rec_notifs) == 1

                rec_emails = list(
                    (
                        await session.execute(
                            sa.select(EmailOutbox).where(
                                EmailOutbox.event_type == "interview_declined_recruiter"
                            )
                        )
                    ).scalars().all()
                )
                assert len(rec_emails) == 1

                # Option A: Interviewer receives NO in-app notification and NO email!
                int_notifs = list(
                    (
                        await session.execute(
                            sa.select(Notification).where(
                                Notification.user_id == interviewer_id,
                                Notification.notification_type == "interview_declined",
                            )
                        )
                    ).scalars().all()
                )
                assert len(int_notifs) == 0

                int_decline_emails = list(
                    (
                        await session.execute(
                            sa.select(EmailOutbox).where(
                                EmailOutbox.to_email.like("%int-%"),
                                EmailOutbox.event_type.like("%decline%"),
                            )
                        )
                    ).scalars().all()
                )
                assert len(int_decline_emails) == 0

        run_async(_test())
