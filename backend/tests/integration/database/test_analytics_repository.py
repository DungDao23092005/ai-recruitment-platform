from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import app.models  # noqa: F401
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
    Job,
    JobViewDailyAggregate,
    JobViewEvent,
    User,
)
from app.repositories.analytics_repository import AnalyticsRepository
from app.services.analytics_rollup_worker import AnalyticsRollupWorker
from app.services.analytics_time import (
    day_end_exclusive_utc,
    day_start_utc,
)

VN_JAN_1 = date(2026, 1, 1)
VN_JAN_2 = date(2026, 1, 2)


async def _seed_company_and_jobs(session, *, job_count=1):
    company = Company(
        id=uuid.uuid4(),
        name="Analytics Co",
        slug=f"analytics-co-{uuid.uuid4()}",
        tax_code=str(uuid.uuid4().int)[:12],
        size=CompanySize.STARTUP,
    )
    session.add(company)
    await session.flush()
    jobs = []
    for index in range(job_count):
        job = Job(
            id=uuid.uuid4(),
            company_id=company.id,
            title=f"Analytics Job {index}",
            description="desc",
            status=JobStatus.PUBLISHED,
            job_type=JobType.FULL_TIME,
            workplace_type=WorkplaceType.REMOTE,
            location="Remote",
        )
        jobs.append(job)
    session.add_all(jobs)
    await session.flush()
    return company, jobs


async def _seed_application(session, job, *, created_at, status, email=None):
    candidate_user = User(
        id=uuid.uuid4(),
        email=email or f"cand-{uuid.uuid4()}@test.com",
        password_hash="hash",
        role=UserRole.CANDIDATE,
        is_active=True,
    )
    actor = User(
        id=uuid.uuid4(),
        email=f"rec-{uuid.uuid4()}@test.com",
        password_hash="hash",
        role=UserRole.RECRUITER,
        is_active=True,
    )
    session.add_all([candidate_user, actor])
    await session.flush()
    profile = CandidateProfile(
        id=uuid.uuid4(),
        user_id=candidate_user.id,
        full_name="Candidate",
    )
    session.add(profile)
    await session.flush()
    application = Application(
        id=uuid.uuid4(),
        candidate_id=profile.id,
        job_id=job.id,
        status=status,
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(application)
    await session.flush()
    return application, actor


async def _activity(session, application, actor, to_status, created_at):
    session.add(
        ApplicationActivity(
            id=uuid.uuid4(),
            application_id=application.id,
            actor_id=actor.id,
            action_type="status_change",
            from_status=None,
            to_status=to_status,
            created_at=created_at,
        )
    )
    await session.flush()


def test_raw_view_counts_bucket_utc_boundary_to_vietnam_dates(run_async):
    async def _test():
        async with async_session_factory() as session:
            company, jobs = await _seed_company_and_jobs(session)
            session.add_all(
                [
                    JobViewEvent(
                        job_id=jobs[0].id,
                        company_id=company.id,
                        viewed_at=datetime(
                            2026, 1, 1, 16, 59, 59, tzinfo=timezone.utc
                        ),
                        is_unique=True,
                    ),
                    JobViewEvent(
                        job_id=jobs[0].id,
                        company_id=company.id,
                        viewed_at=datetime(
                            2026, 1, 1, 17, 0, 0, tzinfo=timezone.utc
                        ),
                        is_unique=False,
                    ),
                    JobViewEvent(
                        job_id=jobs[0].id,
                        company_id=company.id,
                        viewed_at=datetime(
                            2026, 1, 2, 1, 0, 0, tzinfo=timezone.utc
                        ),
                        is_unique=None,
                    ),
                ]
            )
            await session.commit()

            rows = await AnalyticsRepository(session).raw_view_counts(
                company.id,
                day_start_utc(VN_JAN_1),
                day_end_exclusive_utc(VN_JAN_2),
            )

            by_day = {row["view_date"]: row for row in rows}
            assert set(by_day) == {VN_JAN_1, VN_JAN_2}
            assert by_day[VN_JAN_1]["total_views"] == 1
            assert by_day[VN_JAN_1]["unique_views"] == 1
            assert by_day[VN_JAN_2]["total_views"] == 2
            assert by_day[VN_JAN_2]["unique_views"] == 0
            assert by_day[VN_JAN_2]["unverified_views"] == 1

    run_async(_test())


def test_upsert_daily_aggregate_is_idempotent(run_async):
    async def _test():
        async with async_session_factory() as session:
            company, jobs = await _seed_company_and_jobs(session)
            repository = AnalyticsRepository(session)
            now = datetime(2026, 1, 3, tzinfo=timezone.utc)

            await repository.upsert_daily_aggregate(
                job_id=jobs[0].id,
                company_id=company.id,
                view_date=VN_JAN_1,
                total_views=5,
                unique_views=3,
                unverified_views=1,
                aggregated_at=now,
            )
            await session.commit()
            await repository.upsert_daily_aggregate(
                job_id=jobs[0].id,
                company_id=company.id,
                view_date=VN_JAN_1,
                total_views=9,
                unique_views=6,
                unverified_views=2,
                aggregated_at=now,
            )
            await session.commit()

            rows = (
                await session.execute(
                    select(JobViewDailyAggregate).where(
                        JobViewDailyAggregate.job_id == jobs[0].id
                    )
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].total_views == 9
            assert rows[0].unique_views == 6
            assert rows[0].unverified_views == 2

    run_async(_test())


def test_retention_never_deletes_events_without_a_pruned_aggregate(run_async):
    async def _test():
        async with async_session_factory() as session:
            company, jobs = await _seed_company_and_jobs(session, job_count=2)
            old_day = date(2025, 12, 1)
            cutoff = date(2025, 12, 8)
            old_moment = day_start_utc(old_day) + timedelta(hours=3)
            new_moment = day_start_utc(cutoff) + timedelta(hours=3)
            events = [
                JobViewEvent(
                    job_id=jobs[0].id,
                    company_id=company.id,
                    viewed_at=old_moment,
                    is_unique=True,
                ),
                JobViewEvent(
                    job_id=jobs[1].id,
                    company_id=company.id,
                    viewed_at=old_moment,
                    is_unique=True,
                ),
                JobViewEvent(
                    job_id=jobs[0].id,
                    company_id=company.id,
                    viewed_at=new_moment,
                    is_unique=True,
                ),
            ]
            session.add_all(events)
            await session.commit()

            repository = AnalyticsRepository(session)
            await repository.upsert_daily_aggregate(
                job_id=jobs[0].id,
                company_id=company.id,
                view_date=old_day,
                total_views=1,
                unique_views=1,
                unverified_views=0,
                aggregated_at=datetime.now(timezone.utc),
            )
            await session.commit()

            marked = await repository.mark_raw_pruned(
                cutoff, datetime.now(timezone.utc)
            )
            await session.commit()
            assert marked == 1
            visible = (
                await session.execute(
                    select(JobViewDailyAggregate).where(
                        JobViewDailyAggregate.job_id == jobs[0].id,
                        JobViewDailyAggregate.view_date == old_day,
                    )
                )
            ).scalar_one()
            assert visible.raw_pruned is True

            deleted = await repository.delete_pruned_events(
                day_start_utc(cutoff)
            )
            await session.commit()
            assert deleted == 1

            remaining = (
                await session.execute(select(JobViewEvent))
            ).scalars().all()
            assert {event.job_id for event in remaining} == {
                jobs[1].id,
                jobs[0].id,
            }
            # The only remaining job-0 event is the newer, non-pruned one.
            assert any(
                event.job_id == jobs[0].id and event.viewed_at >= new_moment
                for event in remaining
            )

    run_async(_test())


def test_funnel_hires_and_time_to_hire_use_earliest_accepted_activity(run_async):
    async def _test():
        async with async_session_factory() as session:
            company, jobs = await _seed_company_and_jobs(session, job_count=2)
            day2 = datetime(2026, 1, 2, 3, 0, tzinfo=timezone.utc)
            app_a, actor = await _seed_application(
                session, jobs[0], created_at=day2, status=ApplicationStatus.ACCEPTED
            )
            await _activity(
                session, app_a, actor, "under_review",
                datetime(2026, 1, 3, tzinfo=timezone.utc),
            )
            await _activity(
                session, app_a, actor, "interviewing",
                datetime(2026, 1, 4, tzinfo=timezone.utc),
            )
            await _activity(
                session, app_a, actor, "offered",
                datetime(2026, 1, 5, tzinfo=timezone.utc),
            )
            await _activity(
                session, app_a, actor, "accepted",
                datetime(2026, 1, 8, 3, 0, tzinfo=timezone.utc),
            )

            app_b, actor_b = await _seed_application(
                session, jobs[0], created_at=day2, status=ApplicationStatus.ACCEPTED
            )
            await _activity(
                session, app_b, actor_b, "interviewing",
                datetime(2026, 1, 5, tzinfo=timezone.utc),
            )
            await _activity(
                session, app_b, actor_b, "accepted",
                datetime(2026, 1, 10, 3, 0, tzinfo=timezone.utc),
            )

            app_c, _ = await _seed_application(
                session, jobs[0], created_at=day2, status=ApplicationStatus.APPLIED
            )
            app_d, actor_d = await _seed_application(
                session, jobs[0], created_at=day2, status=ApplicationStatus.REJECTED
            )
            await _activity(
                session, app_d, actor_d, "under_review",
                datetime(2026, 1, 4, tzinfo=timezone.utc),
            )
            app_e, _ = await _seed_application(
                session, jobs[1], created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                status=ApplicationStatus.ACCEPTED,
            )
            _, actor_e = await _seed_application(
                session, jobs[1],
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                status=ApplicationStatus.APPLIED,
            )
            await session.commit()
            # app_e's accepted activity uses a different actor already committed.
            await _activity(
                session, app_e, actor_e, "accepted",
                datetime(2026, 1, 5, tzinfo=timezone.utc),
            )
            await session.commit()

            repository = AnalyticsRepository(session)
            start = day_start_utc(VN_JAN_1)
            end = day_end_exclusive_utc(date(2026, 1, 31))
            funnel = await repository.funnel_rows(company.id, start, end)
            by_job = {}
            for row in funnel:
                by_job.setdefault(row["job_id"], []).append(row)
            assert len(by_job[jobs[0].id]) == 4
            assert len(by_job[jobs[1].id]) == 2
            direct = next(
                row for row in by_job[jobs[0].id]
                if row["application_id"] == app_b.id
            )
            assert direct["reached_accepted"] == 1
            assert direct["reached_offered"] == 0
            rejected = next(
                row for row in by_job[jobs[0].id]
                if row["application_id"] == app_d.id
            )
            assert rejected["reached_review"] == 1

            hires = await repository.hires_by_job(company.id, start, end)
            assert hires[jobs[0].id] == 2
            assert hires[jobs[1].id] == 1

            avg_all = await repository.avg_time_to_hire_days(
                company.id, start, end
            )
            assert avg_all == pytest.approx((6 + 8 + 4) / 3, rel=1e-6)
            avg_job = await repository.avg_time_to_hire_days(
                company.id, start, end, job_id=jobs[0].id
            )
            assert avg_job == pytest.approx(7.0, rel=1e-6)

            assert app_c.status == ApplicationStatus.APPLIED

    run_async(_test())


def test_application_lock_allows_only_one_rollup_owner(run_async):
    async def _test():
        first_factory = async_session_factory
        worker = AnalyticsRollupWorker(session_factory=first_factory)
        async with first_factory() as first, first_factory() as second:
            assert await worker._acquire_lock(first) is True
            assert await worker._acquire_lock(second) is False
            await worker._release_lock(first)
            assert await worker._acquire_lock(second) is True
            await worker._release_lock(second)

    run_async(_test())
