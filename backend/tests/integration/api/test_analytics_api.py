from __future__ import annotations

import uuid
from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.database.session import async_session_factory
from app.main import app
from app.models import JobViewEvent
from tests.integration.api.conftest import API_V1, PASSWORD

COMPANY_BODY = {
    "name": "Analytics API Co",
    "slug": "analytics-api-co",
    "tax_code": "999888777",
    "size": "startup",
}

JOB_BODY = {
    "title": "Data Engineer",
    "description": "Build pipelines",
    "job_type": "full_time",
    "workplace_type": "remote",
    "location": "Ho Chi Minh",
    "status": "published",
}


def _company_body(suffix: str) -> dict:
    return {
        **COMPANY_BODY,
        "name": f"Analytics API Co {suffix}",
        "slug": f"analytics-api-{suffix}",
        "tax_code": f"9{uuid.uuid4().int}"[:12],
    }


def _dashboard_url() -> str:
    return f"{API_V1}/analytics/recruiter-dashboard"


def _create_company_and_job(client, run_async, suffix: str) -> tuple[dict, dict]:
    company = run_async(
        client.post(f"{API_V1}/companies", json=_company_body(suffix))
    )
    assert company.status_code == 201, company.text
    company_body = company.json()
    job = run_async(
        client.post(
            f"{API_V1}/jobs",
            json={**JOB_BODY, "company_id": company_body["id"]},
        )
    )
    assert job.status_code == 201, job.text
    return company_body, job.json()


def _register_recruiter(client, run_async) -> httpx.AsyncClient:
    email = f"analytics-no-plan-{uuid.uuid4()}@example.com"
    register = run_async(
        client.post(
            f"{API_V1}/auth/register",
            json={"email": email, "password": PASSWORD, "role": "recruiter"},
        )
    )
    assert register.status_code == 201, register.text
    login = run_async(
        client.post(
            f"{API_V1}/auth/login",
            data={"username": email, "password": PASSWORD},
        )
    )
    assert login.status_code == 200, login.text
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )


async def _events_for_job(job_id: str) -> list[JobViewEvent]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(JobViewEvent).where(
                JobViewEvent.job_id == uuid.UUID(job_id)
            )
        )
        return list(result.scalars().all())


def test_job_view_records_raw_event_and_dashboard_sees_it(
    client, recruiter_client, run_async
):
    company, job = _create_company_and_job(
        recruiter_client, run_async, uuid.uuid4().hex[:6]
    )

    view = run_async(
        client.get(
            f"{API_V1}/jobs/{job['id']}",
            headers={"User-Agent": "analytics-test-agent"},
        )
    )
    assert view.status_code == 200, view.text

    events = run_async(_events_for_job(job["id"]))
    assert len(events) == 1
    assert str(events[0].company_id) == company["id"]
    assert events[0].is_unique is not None

    today = date.today()
    response = run_async(
        recruiter_client.get(
            _dashboard_url(),
            params={
                "start_date": str(today - timedelta(days=1)),
                "end_date": str(today + timedelta(days=1)),
            },
        )
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kpis"]["total_views"] == 1
    assert body["jobs"][0]["job_id"] == job["id"]
    assert body["data_quality"]["unique_views_reliable"] is True


def test_repeated_job_view_is_deduplicated_for_the_same_visitor(
    client, recruiter_client, run_async
):
    _, job = _create_company_and_job(
        recruiter_client, run_async, uuid.uuid4().hex[:6]
    )
    headers = {"User-Agent": "same-analytics-visitor"}
    for _ in range(2):
        response = run_async(
            client.get(f"{API_V1}/jobs/{job['id']}", headers=headers)
        )
        assert response.status_code == 200

    events = run_async(_events_for_job(job["id"]))
    assert len(events) == 2
    assert sorted(event.is_unique for event in events) == [False, True]


def test_recruiter_self_view_is_not_recorded(recruiter_client, run_async):
    _, job = _create_company_and_job(
        recruiter_client, run_async, uuid.uuid4().hex[:6]
    )

    response = run_async(recruiter_client.get(f"{API_V1}/jobs/{job['id']}"))

    assert response.status_code == 200, response.text
    assert run_async(_events_for_job(job["id"])) == []


def test_candidate_view_is_recorded(
    recruiter_client, candidate_client, run_async
):
    company, job = _create_company_and_job(
        recruiter_client, run_async, uuid.uuid4().hex[:6]
    )

    response = run_async(candidate_client.get(f"{API_V1}/jobs/{job['id']}"))

    assert response.status_code == 200, response.text
    events = run_async(_events_for_job(job["id"]))
    assert len(events) == 1
    assert str(events[0].company_id) == company["id"]


def test_anonymous_view_is_recorded(client, recruiter_client, run_async):
    _, job = _create_company_and_job(
        recruiter_client, run_async, uuid.uuid4().hex[:6]
    )

    response = run_async(client.get(f"{API_V1}/jobs/{job['id']}"))

    assert response.status_code == 200, response.text
    assert len(run_async(_events_for_job(job["id"]))) == 1


def test_recruiter_viewing_another_company_job_is_recorded(
    recruiter_a_client, recruiter_b_client, run_async
):
    company_a, job_a = _create_company_and_job(
        recruiter_a_client, run_async, uuid.uuid4().hex[:6]
    )
    _create_company_and_job(
        recruiter_b_client, run_async, uuid.uuid4().hex[:6]
    )

    response = run_async(
        recruiter_b_client.get(f"{API_V1}/jobs/{job_a['id']}")
    )

    assert response.status_code == 200, response.text
    events = run_async(_events_for_job(job_a["id"]))
    assert len(events) == 1
    assert str(events[0].company_id) == company_a["id"]


def test_company_isolation_rejects_foreign_job_filter(
    recruiter_a_client, recruiter_b_client, run_async
):
    _, job_a = _create_company_and_job(
        recruiter_a_client, run_async, uuid.uuid4().hex[:6]
    )
    _create_company_and_job(
        recruiter_b_client, run_async, uuid.uuid4().hex[:6]
    )

    response = run_async(
        recruiter_b_client.get(_dashboard_url(), params={"job_id": job_a["id"]})
    )
    assert response.status_code == 404, response.text


def test_recruiter_without_company_gets_404(recruiter_a_client, run_async):
    response = run_async(recruiter_a_client.get(_dashboard_url()))
    assert response.status_code == 404, response.text


def test_candidate_cannot_access_recruiter_analytics(
    candidate_client, run_async
):
    response = run_async(candidate_client.get(_dashboard_url()))
    assert response.status_code == 403


def test_invalid_date_range_returns_422(recruiter_client, run_async):
    _create_company_and_job(
        recruiter_client, run_async, uuid.uuid4().hex[:6]
    )
    response = run_async(
        recruiter_client.get(
            _dashboard_url(),
            params={"start_date": "2026-02-01", "end_date": "2026-01-01"},
        )
    )
    assert response.status_code == 422


def test_recruiter_without_subscription_gets_empty_quota(
    client, run_async
):
    recruiter = _register_recruiter(client, run_async)
    try:
        run_async(
            recruiter.post(
                f"{API_V1}/companies",
                json=_company_body(uuid.uuid4().hex[:6]),
            )
        )
        response = run_async(recruiter.get(_dashboard_url()))
        assert response.status_code == 200, response.text
        quota = response.json()["quota"]
        assert quota["subscription_status"] == "none"
        assert quota["plan_name"] is None
        assert quota["job_posts"]["limit"] is None
    finally:
        run_async(recruiter.aclose())
