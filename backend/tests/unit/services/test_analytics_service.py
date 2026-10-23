from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.exceptions import EntityNotFoundException
from app.domain.enums import JobStatus
from app.schemas.analytics import AnalyticsQuotaStatus
from app.services.analytics_service import AnalyticsService
from app.services.analytics_time import vietnam_today


class FakeSession:
    def __init__(self, *scalars) -> None:
        self._scalars = list(scalars)
        self.scalar_calls = []
        self.get_calls = []

    async def scalar(self, statement, params=None):
        self.scalar_calls.append(statement)
        if not self._scalars:
            return None
        return self._scalars.pop(0)

    async def get(self, model, key):
        self.get_calls.append((model, key))
        return None


class FakeRepository:
    def __init__(
        self,
        *,
        aggregates=None,
        raw=None,
        funnel=None,
        hires=None,
        avg=None,
        jobs=None,
    ) -> None:
        self.aggregates = aggregates or []
        self.raw = raw or []
        self.funnel = funnel or []
        self.hires = hires or {}
        self.avg = avg
        self.jobs = jobs or {}
        self.calls = []

    async def aggregate_view_counts(self, company_id, start, end):
        self.calls.append(("aggregate", company_id, start, end))
        return self.aggregates

    async def raw_view_counts(self, company_id, start, end):
        self.calls.append(("raw", company_id, start, end))
        return self.raw

    async def funnel_rows(self, company_id, start, end):
        self.calls.append(("funnel", company_id, start, end))
        return self.funnel

    async def hires_by_job(self, company_id, start, end):
        self.calls.append(("hires", company_id, start, end))
        return self.hires

    async def avg_time_to_hire_days(self, company_id, start, end, job_id=None):
        self.calls.append(("avg", company_id, start, end, job_id))
        return self.avg

    async def job_metadata(self, job_ids):
        self.calls.append(("jobs", tuple(job_ids)))
        return {job_id: self.jobs[job_id] for job_id in job_ids if job_id in self.jobs}


class FakeUser:
    id = uuid.uuid4()


def _view_row(job_id, day, total, unique, unverified=0):
    return {
        "job_id": job_id,
        "view_date": day,
        "total_views": total,
        "unique_views": unique,
        "unverified_views": unverified,
    }


def _funnel_row(job_id, status="applied", **flags):
    return {
        "job_id": job_id,
        "status": status,
        "reached_review": 1 if flags.get("review") else 0,
        "reached_interviewing": 1 if flags.get("interviewing") else 0,
        "reached_offered": 1 if flags.get("offered") else 0,
        "reached_accepted": 1 if flags.get("accepted") else 0,
    }


def _service(repository, *, session_scalars=(uuid.uuid4(),), quota=None):
    service = AnalyticsService(FakeSession(*session_scalars))
    service.repository = repository

    async def fake_quota(user_id):
        return quota or AnalyticsQuotaStatus()

    service._quota_status = fake_quota
    return service


@pytest.mark.asyncio
async def test_today_uses_raw_events_and_historical_days_use_aggregates():
    company_id = uuid.uuid4()
    job_id = uuid.uuid4()
    today = vietnam_today()
    yesterday = today - timedelta(days=1)
    older = today - timedelta(days=2)

    repository = FakeRepository(
        aggregates=[
            _view_row(job_id, today, 1, 1),
            _view_row(job_id, yesterday, 10, 6),
        ],
        raw=[
            _view_row(job_id, today, 5, 3, 1),
            _view_row(job_id, yesterday, 10, 6),
            _view_row(job_id, older, 4, 2, 2),
        ],
        funnel=[
            _funnel_row(job_id, "accepted", accepted=True, interviewing=True),
            _funnel_row(job_id, "rejected"),
        ],
        hires={job_id: 1},
        avg=2.5,
        jobs={job_id: SimpleNamespace(title="Backend", status=JobStatus.PUBLISHED)},
    )
    service = _service(
        repository,
        session_scalars=(company_id,),
    )

    response = await service.get_recruiter_dashboard(FakeUser())

    assert response.kpis.total_views == 5 + 10 + 4
    assert response.kpis.unique_views == 3 + 6 + 2
    assert response.kpis.unverified_views == 1 + 0 + 2
    assert response.kpis.total_applications == 2
    assert response.kpis.hires == 1
    assert response.kpis.avg_time_to_hire_days == 2.5
    assert response.kpis.conversion_rate == 50.0
    assert older in response.data_quality.raw_fallback_dates
    assert response.data_quality.unique_views_reliable is False
    assert len(response.daily_views) == 30
    assert response.jobs[0].job_title == "Backend"
    assert response.jobs[0].total_views == 19
    assert response.jobs[0].applications == 2
    assert response.jobs[0].hires == 1


@pytest.mark.asyncio
async def test_company_is_resolved_from_the_recruiter_profile():
    company_id = uuid.uuid4()
    repository = FakeRepository()
    service = _service(repository, session_scalars=(company_id,))

    await service.get_recruiter_dashboard(FakeUser())

    aggregate_call = next(call for call in repository.calls if call[0] == "aggregate")
    assert aggregate_call[1] == company_id


@pytest.mark.asyncio
async def test_missing_recruiter_company_raises_not_found():
    repository = FakeRepository()
    service = _service(repository, session_scalars=(None,))

    with pytest.raises(EntityNotFoundException):
        await service.get_recruiter_dashboard(FakeUser())
    assert repository.calls == []


@pytest.mark.asyncio
async def test_foreign_job_filter_is_rejected_by_tenant_check():
    company_id = uuid.uuid4()
    job_id = uuid.uuid4()
    repository = FakeRepository()
    service = _service(repository, session_scalars=(company_id, None))

    with pytest.raises(EntityNotFoundException):
        await service.get_recruiter_dashboard(FakeUser(), job_id=job_id)
    assert repository.calls == []


@pytest.mark.asyncio
async def test_job_filter_restricts_views_funnel_hires_and_metadata():
    company_id = uuid.uuid4()
    job_a, job_b = uuid.uuid4(), uuid.uuid4()
    today = vietnam_today()
    repository = FakeRepository(
        aggregates=[
            _view_row(job_a, today, 2, 2),
            _view_row(job_b, today, 9, 9),
        ],
        raw=[
            _view_row(job_a, today, 2, 2),
            _view_row(job_b, today, 9, 9),
        ],
        funnel=[
            _funnel_row(job_a, "applied"),
            _funnel_row(job_b, "applied"),
        ],
        hires={job_a: 1, job_b: 4},
        avg=1.5,
        jobs={
            job_a: SimpleNamespace(title="A", status=JobStatus.PUBLISHED),
            job_b: SimpleNamespace(title="B", status=JobStatus.PUBLISHED),
        },
    )
    service = _service(
        repository,
        session_scalars=(company_id, job_a),
    )

    response = await service.get_recruiter_dashboard(FakeUser(), job_id=job_a)

    assert [row.job_id for row in response.jobs] == [job_a]
    assert response.kpis.total_views == 2
    assert response.kpis.total_applications == 1
    assert response.kpis.hires == 1
    assert response.kpis.avg_time_to_hire_days == 1.5
    avg_call = next(call for call in repository.calls if call[0] == "avg")
    assert avg_call[-1] == job_a


@pytest.mark.asyncio
async def test_aggregate_wins_over_raw_for_completed_days_even_if_raw_differs():
    company_id = uuid.uuid4()
    job_id = uuid.uuid4()
    day = vietnam_today() - timedelta(days=1)
    repository = FakeRepository(
        aggregates=[_view_row(job_id, day, 20, 10, 0)],
        raw=[_view_row(job_id, day, 7, 7, 7)],
    )
    service = _service(
        repository,
        session_scalars=(company_id,),
    )

    response = await service.get_recruiter_dashboard(FakeUser())

    assert response.kpis.total_views == 20
    assert response.kpis.unverified_views == 0
    assert response.data_quality.unique_views_reliable is True
    assert response.data_quality.raw_fallback_dates == []


@pytest.mark.asyncio
async def test_zero_quota_limit_is_exhausted_not_unlimited():
    company_id = uuid.uuid4()
    plan = SimpleNamespace(name="Starter")
    subscription = SimpleNamespace(
        id=uuid.uuid4(),
        plan_id=uuid.uuid4(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=5),
        max_job_posts=0,
        job_posts_used=0,
        max_candidate_searches=3,
        candidate_searches_used=3,
        max_ai_features=10,
        ai_features_used=1,
    )
    session = FakeSession(subscription)

    async def fake_get(model, key):
        return plan

    session.get = fake_get
    service = AnalyticsService(session)

    quota = await service._quota_status(FakeUser().id)

    assert quota.subscription_status == "active"
    assert quota.job_posts.limit == 0
    assert quota.job_posts.remaining == 0
    assert quota.job_posts.limit is not None
    assert quota.candidate_searches.remaining == 0
    assert quota.ai_features.remaining == 9
    assert quota.plan_name == "Starter"
