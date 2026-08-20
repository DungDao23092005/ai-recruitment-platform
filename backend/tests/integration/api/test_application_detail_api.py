import uuid

import pytest

from tests.integration.api.conftest import API_V1, PASSWORD

from app.database.session import async_session_factory
from app.models import Resume

COMPANY_BODY = {
    "name": "Acme Corp",
    "slug": "acme-corp",
    "tax_code": "123456789",
    "size": "startup",
}

JOB_BODY = {
    "title": "Backend Engineer",
    "description": "Build robust APIs",
    "job_type": "full_time",
    "workplace_type": "remote",
    "location": "Ho Chi Minh",
    "status": "published",
}

PARSED_RESUME = {
    "full_name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "0901234567",
    "title": "Senior Engineer",
    "summary": "8 years building backend systems.",
    "total_years_experience": 8.0,
    "skills": ["Python", "FastAPI", "SQL"],
    "experiences": [
        {
            "company": "Acme",
            "position": "Senior Engineer",
            "start_date": "2018/01",
            "end_date": "Present",
            "is_current": True,
            "description": "Led API platform.",
            "skills_used": ["Python"],
        }
    ],
    "education": [
        {
            "institution": "HUST",
            "degree": "Bachelor",
            "field_of_study": "CS",
            "start_year": 2010,
            "end_year": 2014,
        }
    ],
    "certifications": ["AWS SAA"],
    "languages": ["English", "Vietnamese"],
}


async def _seed_resume(candidate_id, parsed_data: dict | None):
    async with async_session_factory() as session:
        resume = Resume(
            candidate_id=candidate_id,
            title="cv.pdf",
            is_primary=True,
            parsed_data=parsed_data,
        )
        session.add(resume)
        await session.commit()
        return resume.id


def create_candidate_profile(candidate_client, run_async):
    return run_async(
        candidate_client.post(
            f"{API_V1}/users/me/candidate-profile",
            json={"full_name": "Jane Doe", "title": "Engineer"},
        )
    )


def create_company(client, run_async, slug, tax_code):
    body = {**COMPANY_BODY, "slug": slug, "tax_code": tax_code}
    resp = run_async(client.post(f"{API_V1}/companies", json=body))
    assert resp.status_code == 201, resp.text
    return resp.json()


def create_job(client, run_async, company_id, title, status="published"):
    body = {
        **JOB_BODY,
        "company_id": company_id,
        "title": title,
        "status": status,
    }
    resp = run_async(client.post(f"{API_V1}/jobs", json=body))
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestGetApplicationDetail:
    """GET /applications/{id} — recruiter-owned application detail + digital CV."""

    def test_anonymous_returns_401(self, client, run_async):
        resp = run_async(
            client.get(f"{API_V1}/applications/{uuid.uuid4()}")
        )

        assert resp.status_code == 401

    def test_candidate_returns_403(self, candidate_client, run_async):
        resp = run_async(
            candidate_client.get(f"{API_V1}/applications/{uuid.uuid4()}")
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Not enough permissions"

    def test_recruiter_gets_own_application_detail(
        self, recruiter_a_client, candidate_client, run_async
    ):
        company = create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = create_job(
            recruiter_a_client, run_async, company["id"], "Job A"
        )
        profile = create_candidate_profile(candidate_client, run_async).json()
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job["id"]}
            )
        ).json()

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}"
            )
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == application["id"]
        assert body["candidate_id"] == profile["id"]
        assert body["job_id"] == job["id"]
        assert body["job_title"] == "Job A"
        assert body["company_name"] == COMPANY_BODY["name"]
        assert body["status"] == "applied"
        assert body["candidate"]["full_name"] == "Jane Doe"
        assert body["resume"] is None

    def test_recruiter_gets_digital_cv_from_resume(
        self, recruiter_a_client, candidate_client, run_async
    ):
        company = create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = create_job(
            recruiter_a_client, run_async, company["id"], "Job A"
        )
        profile = create_candidate_profile(candidate_client, run_async).json()
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job["id"]}
            )
        ).json()
        run_async(_seed_resume(profile["id"], PARSED_RESUME))

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}"
            )
        )

        assert resp.status_code == 200
        resume = resp.json()["resume"]
        assert resume is not None
        assert resume["is_primary"] is True
        assert resume["parsed_data"]["full_name"] == "Jane Doe"
        assert resume["parsed_data"]["skills"] == [
            "Python",
            "FastAPI",
            "SQL",
        ]
        assert len(resume["parsed_data"]["experiences"]) == 1
        assert resume["parsed_data"]["experiences"][0]["company"] == "Acme"
        assert len(resume["parsed_data"]["education"]) == 1
        assert resume["parsed_data"]["certifications"] == ["AWS SAA"]

    def test_resume_null_when_parsed_data_empty(
        self, recruiter_a_client, candidate_client, run_async
    ):
        company = create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = create_job(
            recruiter_a_client, run_async, company["id"], "Job A"
        )
        profile = create_candidate_profile(candidate_client, run_async).json()
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job["id"]}
            )
        ).json()
        run_async(_seed_resume(profile["id"], None))

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}"
            )
        )

        assert resp.status_code == 200
        resume = resp.json()["resume"]
        assert resume is not None
        assert resume["parsed_data"] is None

    def test_recruiter_b_cannot_view_recruiter_a_application(
        self, recruiter_a_client, recruiter_b_client, candidate_client, run_async
    ):
        company_a = create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job_a = create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job_a["id"]}
            )
        ).json()

        resp = run_async(
            recruiter_b_client.get(
                f"{API_V1}/applications/{application['id']}"
            )
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == (
            f"Application {application['id']} not found"
        )

    def test_cross_recruiter_and_nonexistent_responses_indistinguishable(
        self, recruiter_a_client, recruiter_b_client, candidate_client, run_async
    ):
        import re

        company_a = create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job_a = create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job_a["id"]}
            )
        ).json()

        cross_recruiter = run_async(
            recruiter_b_client.get(
                f"{API_V1}/applications/{application['id']}"
            )
        )
        nonexistent = run_async(
            recruiter_b_client.get(
                f"{API_V1}/applications/{uuid.uuid4()}"
            )
        )

        assert cross_recruiter.status_code == 404
        assert nonexistent.status_code == 404
        pattern = r"^Application [0-9a-fA-F-]{36} not found$"
        assert re.match(pattern, cross_recruiter.json()["detail"]) is not None
        assert re.match(pattern, nonexistent.json()["detail"]) is not None

    def test_admin_views_any_application(
        self,
        admin_client,
        recruiter_b_client,
        candidate_client,
        run_async,
    ):
        company_b = create_company(
            recruiter_b_client, run_async, "acme-b", "222222222"
        )
        job_b = create_job(
            recruiter_b_client, run_async, company_b["id"], "Job B"
        )
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job_b["id"]}
            )
        ).json()

        resp = run_async(
            admin_client.get(f"{API_V1}/applications/{application['id']}")
        )

        assert resp.status_code == 200
        assert resp.json()["id"] == application["id"]
        assert resp.json()["job_title"] == "Job B"

    def test_detail_omits_sensitive_candidate_fields(
        self, recruiter_a_client, candidate_client, run_async
    ):
        company = create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = create_job(
            recruiter_a_client, run_async, company["id"], "Job A"
        )
        profile = create_candidate_profile(candidate_client, run_async).json()
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job["id"]}
            )
        ).json()
        run_async(_seed_resume(profile["id"], PARSED_RESUME))

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}"
            )
        )

        assert resp.status_code == 200
        candidate = resp.json()["candidate"]
        assert set(candidate.keys()) == {"id", "full_name", "title"}
        raw = resp.text
        assert "password" not in raw.lower()
        assert "password_hash" not in raw.lower()

    def test_withdrawn_application_still_viewable(
        self, recruiter_a_client, candidate_client, run_async
    ):
        company = create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = create_job(
            recruiter_a_client, run_async, company["id"], "Job A"
        )
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job["id"]}
            )
        ).json()
        withdraw = run_async(
            candidate_client.patch(
                f"{API_V1}/applications/mine/{application['id']}/withdraw"
            )
        )
        assert withdraw.status_code == 200

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}"
            )
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "withdrawn"