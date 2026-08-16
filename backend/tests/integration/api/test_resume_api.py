import socket
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.database.session import async_session_factory
from app.models import Resume
from app.schemas.ai_resume import ParsedResumeSchema
from tests.integration.api.conftest import API_V1

PASSWORD = "password123"


def _resume_payload() -> dict:
    return ParsedResumeSchema(
        full_name="Jane Doe",
        email="jane@example.com",
        skills=["Python", "FastAPI"],
        languages=["Vietnamese"],
    ).model_dump(mode="json")


async def _seed_resume(
    candidate_profile_id: str,
    title: str = "cv.pdf",
    is_primary: bool = True,
    parsed_data: dict | None = None,
) -> Resume:
    async with async_session_factory() as session:
        resume = Resume(
            candidate_id=candidate_profile_id,
            title=title,
            is_primary=is_primary,
            parsed_data=parsed_data or _resume_payload(),
        )
        session.add(resume)
        await session.commit()
        await session.refresh(resume)
        return resume


async def _count_resumes_for_candidate(candidate_profile_id: str) -> int:
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count())
            .select_from(Resume)
            .where(Resume.candidate_id == candidate_profile_id)
        )
        return int(result.scalar_one())


async def _get_resumes_for_candidate(candidate_profile_id: str) -> list[Resume]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Resume).where(Resume.candidate_id == candidate_profile_id)
        )
        return list(result.scalars().all())


def _create_profile(candidate_client, run_async) -> str:
    profile = run_async(
        candidate_client.post(
            f"{API_V1}/users/me/candidate-profile",
            json={
                "full_name": "Jane Doe",
                "phone": "0123456789",
                "title": "Software Engineer",
            },
        )
    )
    assert profile.status_code == 201, profile.text
    return profile.json()["id"]


def _qdrant_available() -> bool:
    try:
        with socket.create_connection(("localhost", 6333), timeout=1):
            return True
    except OSError:
        return False


QDRANT_AVAILABLE = _qdrant_available()

_SKIP_NO_QDRANT = pytest.mark.skipif(
    not QDRANT_AVAILABLE,
    reason="BLOCKED BY ENVIRONMENT: Qdrant not available on localhost:6333",
)


class TestGetMyResume:
    def test_anonymous_returns_401(self, client, run_async):
        resp = run_async(client.get(f"{API_V1}/users/me/resume"))
        assert resp.status_code == 401

    def test_recruiter_returns_403(self, recruiter_client, run_async):
        resp = run_async(recruiter_client.get(f"{API_V1}/users/me/resume"))
        assert resp.status_code == 403

    def test_candidate_without_profile_returns_404(
        self, candidate_client, run_async
    ):
        resp = run_async(candidate_client.get(f"{API_V1}/users/me/resume"))
        assert resp.status_code == 404

    def test_candidate_without_resume_returns_404(
        self, candidate_client, run_async
    ):
        _create_profile(candidate_client, run_async)
        resp = run_async(candidate_client.get(f"{API_V1}/users/me/resume"))
        assert resp.status_code == 404

    def test_candidate_returns_primary_resume(
        self, candidate_client, run_async
    ):
        profile_id = _create_profile(candidate_client, run_async)
        run_async(_seed_resume(profile_id, title="cv.pdf"))

        resp = run_async(candidate_client.get(f"{API_V1}/users/me/resume"))

        assert resp.status_code == 200
        body = resp.json()
        assert body["candidate_id"] == profile_id
        assert body["title"] == "cv.pdf"
        assert body["is_primary"] is True
        assert body["parsed_data"]["full_name"] == "Jane Doe"
        assert body["parsed_data"]["skills"] == ["Python", "FastAPI"]
        assert "file_path" not in body

    def test_response_does_not_expose_file_path(
        self, candidate_client, run_async
    ):
        profile_id = _create_profile(candidate_client, run_async)
        run_async(_seed_resume(profile_id))
        body = run_async(
            candidate_client.get(f"{API_V1}/users/me/resume")
        ).json()
        assert "file_path" not in body

    def test_selects_primary_when_multiple_rows_exist(
        self, candidate_client, run_async
    ):
        profile_id = _create_profile(candidate_client, run_async)
        run_async(_seed_resume(profile_id, title="legacy.pdf", is_primary=False))
        run_async(_seed_resume(profile_id, title="primary.pdf", is_primary=True))

        body = run_async(
            candidate_client.get(f"{API_V1}/users/me/resume")
        ).json()

        assert body["title"] == "primary.pdf"
        assert body["is_primary"] is True

    def test_candidate_a_cannot_read_candidate_b(
        self, candidate_client, candidate_b_client, run_async
    ):
        profile_a = _create_profile(candidate_client, run_async)
        profile_b = _create_profile(candidate_b_client, run_async)
        run_async(_seed_resume(profile_b, title="b-cv.pdf"))

        resp_a = run_async(candidate_client.get(f"{API_V1}/users/me/resume"))
        resp_b = run_async(candidate_b_client.get(f"{API_V1}/users/me/resume"))

        assert resp_a.status_code == 404
        assert resp_b.status_code == 200
        assert resp_b.json()["candidate_id"] == profile_b


@_SKIP_NO_QDRANT
class TestParseResumePersistence:
    @patch("app.services.ai_matching_service.PDFTextExtractor.extract")
    def test_upload_creates_resume_row(self, mock_extract, candidate_client, run_async):
        mock_extract.return_value = "Fake CV with Python skills"
        profile_id = _create_profile(candidate_client, run_async)

        resp = run_async(
            candidate_client.post(
                f"{API_V1}/ai/parse-resume",
                files={
                    "file": (
                        "resume.pdf",
                        b"%PDF-1.7 Fake CV with Python skills",
                        "application/pdf",
                    )
                },
            )
        )

        assert resp.status_code == 200
        rows = run_async(_get_resumes_for_candidate(profile_id))
        assert len(rows) == 1
        assert rows[0].is_primary is True
        assert rows[0].parsed_data is not None
        assert "full_name" in rows[0].parsed_data

    @patch("app.services.ai_matching_service.PDFTextExtractor.extract")
    def test_second_upload_updates_primary(self, mock_extract, candidate_client, run_async):
        mock_extract.return_value = "Fake CV with Python skills"
        profile_id = _create_profile(candidate_client, run_async)

        for _ in range(2):
            resp = run_async(
                candidate_client.post(
                    f"{API_V1}/ai/parse-resume",
                    files={
                        "file": (
                            "resume.pdf",
                            b"%PDF-1.7 Fake CV with Python skills",
                            "application/pdf",
                        )
                    },
                )
            )
            assert resp.status_code == 200

        assert run_async(_count_resumes_for_candidate(profile_id)) == 1
        rows = run_async(_get_resumes_for_candidate(profile_id))
        assert rows[0].is_primary is True
        assert rows[0].title == "resume.pdf"