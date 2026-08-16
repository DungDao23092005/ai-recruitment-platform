import uuid

import pytest
from sqlalchemy import func, select

from app.database.session import async_session_factory
from app.models import CandidateProfile, RecruiterProfile
from tests.integration.api.conftest import API_V1

COMPANY_BODY = {
    "name": "Acme Corp",
    "slug": "acme-corp",
    "tax_code": "123456789",
    "size": "startup",
}

PROFILE_BODY = {
    "full_name": "John Doe",
    "position": "Hiring Manager",
    "company_id": None,
}

CANDIDATE_PROFILE_BODY = {
    "full_name": "Jane Doe",
    "phone": "0123456789",
    "title": "Software Engineer",
}


async def count_candidate_profiles_for_user(user_id: str) -> int:
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count())
            .select_from(CandidateProfile)
            .where(CandidateProfile.user_id == user_id)
        )
        return int(result.scalar_one())


async def count_profiles_for_user(user_id: str) -> int:
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count())
            .select_from(RecruiterProfile)
            .where(RecruiterProfile.user_id == user_id)
        )
        return int(result.scalar_one())


async def get_profile_by_id(profile_id: str) -> RecruiterProfile | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(RecruiterProfile).where(RecruiterProfile.id == profile_id)
        )
        return result.scalar_one_or_none()


class TestCandidateProfileLifecycle:
    def test_anonymous_cannot_access(self, client, run_async):
        get_resp = run_async(client.get(f"{API_V1}/users/me/candidate-profile"))
        put_resp = run_async(
            client.put(f"{API_V1}/users/me/candidate-profile", json={})
        )

        assert get_resp.status_code == 401
        assert put_resp.status_code == 401

    def test_recruiter_cannot_access(self, recruiter_client, run_async):
        get_resp = run_async(
            recruiter_client.get(f"{API_V1}/users/me/candidate-profile")
        )
        put_resp = run_async(
            recruiter_client.put(
                f"{API_V1}/users/me/candidate-profile", json=CANDIDATE_PROFILE_BODY
            )
        )

        assert get_resp.status_code == 403
        assert put_resp.status_code == 403

    def test_fresh_candidate_get_returns_404(self, candidate_client, run_async):
        resp = run_async(
            candidate_client.get(f"{API_V1}/users/me/candidate-profile")
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Candidate profile not found"

    def test_fresh_candidate_put_creates_profile(self, candidate_client, run_async):
        resp = run_async(
            candidate_client.put(
                f"{API_V1}/users/me/candidate-profile", json=CANDIDATE_PROFILE_BODY
            )
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["full_name"] == "Jane Doe"
        assert body["phone"] == "0123456789"
        assert body["title"] == "Software Engineer"
        assert body["id"]
        assert body["user_id"]
        assert run_async(count_candidate_profiles_for_user(body["user_id"])) == 1

    def test_existing_candidate_get_returns_profile(
        self, candidate_client, run_async
    ):
        created = run_async(
            candidate_client.put(
                f"{API_V1}/users/me/candidate-profile", json=CANDIDATE_PROFILE_BODY
            )
        ).json()

        resp = run_async(
            candidate_client.get(f"{API_V1}/users/me/candidate-profile")
        )

        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]
        assert resp.json()["full_name"] == "Jane Doe"

    def test_put_updates_same_profile_and_no_duplicate(
        self, candidate_client, run_async
    ):
        created = run_async(
            candidate_client.put(
                f"{API_V1}/users/me/candidate-profile", json=CANDIDATE_PROFILE_BODY
            )
        ).json()

        updated_body = {
            "full_name": "Janet Doe",
            "phone": "0987654321",
            "title": "Senior Software Engineer",
        }
        updated = run_async(
            candidate_client.put(
                f"{API_V1}/users/me/candidate-profile", json=updated_body
            )
        ).json()

        assert updated["id"] == created["id"]
        assert updated["user_id"] == created["user_id"]
        assert updated["full_name"] == "Janet Doe"
        assert updated["phone"] == "0987654321"
        assert updated["title"] == "Senior Software Engineer"
        assert run_async(count_candidate_profiles_for_user(created["user_id"])) == 1

    def test_candidate_cannot_read_or_update_other_candidates_profile(
        self, candidate_client, candidate_b_client, run_async
    ):
        created = run_async(
            candidate_client.put(
                f"{API_V1}/users/me/candidate-profile", json=CANDIDATE_PROFILE_BODY
            )
        ).json()

        get_resp = run_async(
            candidate_b_client.get(f"{API_V1}/users/me/candidate-profile")
        )
        assert get_resp.status_code == 404

        put_resp = run_async(
            candidate_b_client.put(
                f"{API_V1}/users/me/candidate-profile", json=CANDIDATE_PROFILE_BODY
            )
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["id"] != created["id"]
        assert run_async(count_candidate_profiles_for_user(created["user_id"])) == 1
        assert run_async(count_candidate_profiles_for_user(put_resp.json()["user_id"])) == 1

    def test_existing_post_behavior_unchanged(self, candidate_client, run_async):
        create = run_async(
            candidate_client.post(
                f"{API_V1}/users/me/candidate-profile", json=CANDIDATE_PROFILE_BODY
            )
        )
        assert create.status_code == 201

        duplicate = run_async(
            candidate_client.post(
                f"{API_V1}/users/me/candidate-profile", json=CANDIDATE_PROFILE_BODY
            )
        )
        assert duplicate.status_code == 400
        assert "already has a candidate profile" in duplicate.json()["detail"]


class TestRecruiterProfileLifecycle:
    def test_anonymous_cannot_access(self, client, run_async):
        get_resp = run_async(client.get(f"{API_V1}/users/me/recruiter-profile"))
        put_resp = run_async(client.put(f"{API_V1}/users/me/recruiter-profile", json={}))

        assert get_resp.status_code == 401
        assert put_resp.status_code == 401

    def test_candidate_cannot_access(self, candidate_client, run_async):
        get_resp = run_async(
            candidate_client.get(f"{API_V1}/users/me/recruiter-profile")
        )
        put_resp = run_async(
            candidate_client.put(
                f"{API_V1}/users/me/recruiter-profile", json=PROFILE_BODY
            )
        )

        assert get_resp.status_code == 403
        assert put_resp.status_code == 403

    def test_fresh_recruiter_get_returns_404(self, recruiter_client, run_async):
        resp = run_async(
            recruiter_client.get(f"{API_V1}/users/me/recruiter-profile")
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Recruiter profile not found"

    def test_fresh_recruiter_put_creates_profile(self, recruiter_client, run_async):
        resp = run_async(
            recruiter_client.put(
                f"{API_V1}/users/me/recruiter-profile", json=PROFILE_BODY
            )
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["full_name"] == "John Doe"
        assert body["position"] == "Hiring Manager"
        assert body["company_id"] is None
        assert body["id"]
        assert body["user_id"]

    def test_existing_recruiter_get_returns_profile(
        self, recruiter_client, run_async
    ):
        created = run_async(
            recruiter_client.put(
                f"{API_V1}/users/me/recruiter-profile", json=PROFILE_BODY
            )
        ).json()

        resp = run_async(
            recruiter_client.get(f"{API_V1}/users/me/recruiter-profile")
        )

        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]
        assert resp.json()["full_name"] == "John Doe"

    def test_put_updates_same_profile_and_no_duplicate(
        self, recruiter_client, run_async
    ):
        created = run_async(
            recruiter_client.put(
                f"{API_V1}/users/me/recruiter-profile", json=PROFILE_BODY
            )
        ).json()

        updated_body = {
            "full_name": "Jane Doe",
            "position": "Talent Lead",
            "company_id": None,
        }
        updated = run_async(
            recruiter_client.put(
                f"{API_V1}/users/me/recruiter-profile", json=updated_body
            )
        ).json()

        assert updated["id"] == created["id"]
        assert updated["user_id"] == created["user_id"]
        assert updated["full_name"] == "Jane Doe"
        assert updated["position"] == "Talent Lead"
        assert run_async(count_profiles_for_user(created["user_id"])) == 1

        db_profile = run_async(get_profile_by_id(created["id"]))
        assert db_profile is not None
        assert db_profile.full_name == "Jane Doe"
        assert db_profile.position == "Talent Lead"

    def test_existing_post_behavior_unchanged(self, recruiter_client, run_async):
        create = run_async(
            recruiter_client.post(
                f"{API_V1}/users/me/recruiter-profile", json=PROFILE_BODY
            )
        )
        assert create.status_code == 201

        duplicate = run_async(
            recruiter_client.post(
                f"{API_V1}/users/me/recruiter-profile", json=PROFILE_BODY
            )
        )
        assert duplicate.status_code == 400
        assert "already has a recruiter profile" in duplicate.json()["detail"]


class TestRecruiterProfileCompanyOwnership:
    @staticmethod
    def create_company(client, run_async, slug, tax_code):
        body = {**COMPANY_BODY, "slug": slug, "tax_code": tax_code}
        resp = run_async(client.post(f"{API_V1}/companies", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_recruiter_a_put_with_own_company_succeeds(
        self, recruiter_a_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )

        resp = run_async(
            recruiter_a_client.put(
                f"{API_V1}/users/me/recruiter-profile",
                json={
                    "full_name": "John Doe",
                    "position": "Hiring Manager",
                    "company_id": company_a["id"],
                },
            )
        )

        assert resp.status_code == 200
        assert resp.json()["company_id"] == company_a["id"]

    def test_recruiter_a_cannot_link_recruiter_b_company(
        self, recruiter_a_client, recruiter_b_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        company_b = self.create_company(
            recruiter_b_client, run_async, "acme-b", "222222222"
        )
        assert company_a["id"] != company_b["id"]

        resp = run_async(
            recruiter_a_client.put(
                f"{API_V1}/users/me/recruiter-profile",
                json={
                    "full_name": "John Doe",
                    "position": "Hiring Manager",
                    "company_id": company_b["id"],
                },
            )
        )

        assert resp.status_code == 403
        assert "not allowed to link" in resp.json()["detail"]

    def test_recruiter_without_company_cannot_claim_existing_company(
        self, recruiter_client, recruiter_b_client, run_async
    ):
        company_b = self.create_company(
            recruiter_b_client, run_async, "acme-b", "222222222"
        )

        resp = run_async(
            recruiter_client.put(
                f"{API_V1}/users/me/recruiter-profile",
                json={
                    "full_name": "John Doe",
                    "position": "Hiring Manager",
                    "company_id": company_b["id"],
                },
            )
        )

        assert resp.status_code == 403
        assert "not allowed to link" in resp.json()["detail"]

    def test_nonexistent_company_returns_404(self, recruiter_client, run_async):
        resp = run_async(
            recruiter_client.put(
                f"{API_V1}/users/me/recruiter-profile",
                json={
                    "full_name": "John Doe",
                    "position": "Hiring Manager",
                    "company_id": str(uuid.uuid4()),
                },
            )
        )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_company_creation_flow_get_returns_owned_company(
        self, recruiter_client, run_async
    ):
        company = self.create_company(
            recruiter_client, run_async, "acme-c", "333333333"
        )

        resp = run_async(
            recruiter_client.get(f"{API_V1}/users/me/recruiter-profile")
        )

        assert resp.status_code == 200
        assert resp.json()["company_id"] == company["id"]
        assert resp.json()["full_name"] is None
        assert resp.json()["position"] is None