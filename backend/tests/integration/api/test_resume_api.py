import socket
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.database.session import async_session_factory
from app.models import Resume
from app.repositories import ResumeRepository
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
    is_confirmed: bool = True,
) -> Resume:
    async with async_session_factory() as session:
        resume = Resume(
            candidate_id=candidate_profile_id,
            title=title,
            is_primary=is_primary,
            is_confirmed=is_confirmed,
            confirmed_at=(
                datetime.now(timezone.utc) if is_confirmed else None
            ),
            parsed_data=parsed_data or _resume_payload(),
        )
        session.add(resume)
        await session.commit()
        await session.refresh(resume)
        return resume


def _draft_response() -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid.uuid4(),
        candidate_id=uuid.uuid4(),
        title="resume.pdf",
        is_primary=False,
        is_confirmed=False,
        confirmed_at=None,
        parsed_data=_resume_payload(),
        created_at=now,
        updated_at=now,
    )


async def _parse_draft_side_effect(
    candidate_id,
    pdf_source,
    session,
    source_name,
):
    parsed = ParsedResumeSchema(
        full_name="Jane Doe",
        skills=["Python", "FastAPI"],
    )
    repository = ResumeRepository(session, Resume)
    draft = await repository.upsert_draft(
        candidate_id=candidate_id,
        title=source_name or "resume.pdf",
        parsed_data=parsed.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(draft)
    return draft


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


async def _get_resume(resume_id: str) -> Resume | None:
    async with async_session_factory() as session:
        return await session.get(Resume, resume_id)


async def _get_candidate_profile(candidate_profile_id: str):
    from app.models import CandidateProfile

    async with async_session_factory() as session:
        return await session.get(CandidateProfile, candidate_profile_id)


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
        assert body["is_confirmed"] is True
        assert body["confirmed_at"] is not None
        assert body["parsed_data"]["full_name"] == "Jane Doe"
        assert body["parsed_data"]["skills"] == ["Python", "FastAPI"]
        assert "file_path" not in body

    def test_candidate_with_only_unconfirmed_resume_returns_404(
        self, candidate_client, run_async
    ):
        profile_id = _create_profile(candidate_client, run_async)
        run_async(
            _seed_resume(
                profile_id,
                title="draft.pdf",
                is_primary=False,
                is_confirmed=False,
            )
        )

        resp = run_async(candidate_client.get(f"{API_V1}/users/me/resume"))

        assert resp.status_code == 404

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
    @patch(
        "app.services.ai_matching_service.AIMatchingService.parse_and_save_resume_draft",
        new_callable=AsyncMock,
    )
    def test_upload_creates_unconfirmed_draft(
        self, mock_parse, candidate_client, run_async
    ):
        mock_parse.side_effect = _parse_draft_side_effect
        profile_id = _create_profile(candidate_client, run_async)

        resp = run_async(
            candidate_client.post(
                f"{API_V1}/ai/parse-resume",
                files={
                    "file": (
                        "resume.pdf",
                        b"%PDF-1.4 Valid PDF content",
                        "application/pdf",
                    )
                },
            )
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["is_confirmed"] is False
        assert body["is_primary"] is False
        assert body["confirmed_at"] is None
        rows = run_async(_get_resumes_for_candidate(profile_id))
        assert len(rows) == 1
        assert rows[0].is_primary is False
        assert rows[0].is_confirmed is False
        assert rows[0].parsed_data is not None
        assert "full_name" in rows[0].parsed_data

    @patch(
        "app.services.ai_matching_service.AIMatchingService.parse_and_save_resume_draft",
        new_callable=AsyncMock,
    )
    def test_second_upload_updates_existing_draft(
        self, mock_parse, candidate_client, run_async
    ):
        mock_parse.side_effect = _parse_draft_side_effect
        profile_id = _create_profile(candidate_client, run_async)

        for _ in range(2):
            resp = run_async(
                candidate_client.post(
                    f"{API_V1}/ai/parse-resume",
                    files={
                        "file": (
                            "resume.pdf",
                            b"%PDF-1.4 Valid PDF content",
                            "application/pdf",
                        )
                    },
                )
            )
            assert resp.status_code == 200

        assert run_async(_count_resumes_for_candidate(profile_id)) == 1
        rows = run_async(_get_resumes_for_candidate(profile_id))
        assert rows[0].is_primary is False
        assert rows[0].is_confirmed is False
        assert rows[0].title == "resume.pdf"

    @patch(
        "app.services.ai_matching_service.AIMatchingService.index_confirmed_resume",
        new_callable=AsyncMock,
    )
    @patch(
        "app.services.ai_matching_service.AIMatchingService.parse_and_save_resume_draft",
        new_callable=AsyncMock,
    )
    def test_parse_does_not_index_unconfirmed_draft(
        self, mock_parse, mock_index, candidate_client, run_async
    ):
        mock_parse.side_effect = _parse_draft_side_effect
        _create_profile(candidate_client, run_async)

        resp = run_async(
            candidate_client.post(
                f"{API_V1}/ai/parse-resume",
                files={
                    "file": (
                        "resume.pdf",
                        b"%PDF-1.4 Valid PDF content",
                        "application/pdf",
                    )
                },
            )
        )

        assert resp.status_code == 200
        mock_index.assert_not_awaited()


class TestResumeDraftLifecycle:
    def test_get_draft_returns_unconfirmed_resume(
        self, candidate_client, run_async
    ):
        profile_id = _create_profile(candidate_client, run_async)
        run_async(
            _seed_resume(profile_id, title="active.pdf", is_primary=True)
        )
        draft = run_async(
            _seed_resume(
                profile_id,
                title="draft.pdf",
                is_primary=False,
                is_confirmed=False,
            )
        )

        resp = run_async(
            candidate_client.get(f"{API_V1}/users/me/resume/draft")
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(draft.id)
        assert body["is_confirmed"] is False
        assert body["is_primary"] is False

    def test_update_draft_persists_edits(self, candidate_client, run_async):
        profile_id = _create_profile(candidate_client, run_async)
        draft = run_async(
            _seed_resume(
                profile_id,
                title="draft.pdf",
                is_primary=False,
                is_confirmed=False,
            )
        )
        parsed = ParsedResumeSchema(
            full_name="Jane Updated",
            phone="0999999999",
            title="Staff Engineer",
            skills=["Python", "FastAPI", "SQL Server"],
        ).model_dump(mode="json")

        resp = run_async(
            candidate_client.put(
                f"{API_V1}/users/me/resume/{draft.id}",
                json={"title": "edited.pdf", "parsed_data": parsed},
            )
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["title"] == "edited.pdf"
        assert body["is_confirmed"] is False
        stored = run_async(_get_resume(str(draft.id)))
        assert stored.title == "edited.pdf"
        assert stored.parsed_data["full_name"] == "Jane Updated"
        assert stored.parsed_data["skills"] == [
            "Python",
            "FastAPI",
            "SQL Server",
        ]

    def test_cannot_update_confirmed_resume(
        self, candidate_client, run_async
    ):
        profile_id = _create_profile(candidate_client, run_async)
        confirmed = run_async(
            _seed_resume(profile_id, title="active.pdf", is_primary=True)
        )

        resp = run_async(
            candidate_client.put(
                f"{API_V1}/users/me/resume/{confirmed.id}",
                json={"parsed_data": _resume_payload()},
            )
        )

        assert resp.status_code == 409

    def test_cannot_update_another_candidates_draft(
        self, candidate_client, candidate_b_client, run_async
    ):
        _create_profile(candidate_client, run_async)
        profile_b = _create_profile(candidate_b_client, run_async)
        draft_b = run_async(
            _seed_resume(
                profile_b,
                title="draft-b.pdf",
                is_primary=False,
                is_confirmed=False,
            )
        )

        resp = run_async(
            candidate_client.put(
                f"{API_V1}/users/me/resume/{draft_b.id}",
                json={"parsed_data": _resume_payload()},
            )
        )

        assert resp.status_code == 404


class TestResumeConfirmation:
    @patch(
        "app.services.ai_matching_service.AIMatchingService.index_confirmed_resume",
        new_callable=AsyncMock,
    )
    def test_confirm_activates_resume_and_syncs_profile(
        self, mock_index, candidate_client, run_async
    ):
        profile_id = _create_profile(candidate_client, run_async)
        run_async(
            _seed_resume(
                profile_id,
                title="old.pdf",
                is_primary=True,
                parsed_data={"full_name": "Old Name", "skills": ["Python"]},
            )
        )
        draft = run_async(
            _seed_resume(
                profile_id,
                title="draft.pdf",
                is_primary=False,
                is_confirmed=False,
                parsed_data={
                    "full_name": "New Name",
                    "phone": "0999999999",
                    "title": "Staff Engineer",
                    "skills": ["Python", "FastAPI"],
                },
            )
        )

        resp = run_async(
            candidate_client.post(
                f"{API_V1}/users/me/resume/{draft.id}/confirm"
            )
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["indexing_status"] == "indexed"
        assert body["resume"]["is_confirmed"] is True
        assert body["resume"]["is_primary"] is True
        assert body["resume"]["confirmed_at"] is not None
        mock_index.assert_awaited_once()
        stored = run_async(_get_resume(str(draft.id)))
        assert stored.is_confirmed is True
        assert stored.is_primary is True
        profile = run_async(_get_candidate_profile(profile_id))
        assert profile.full_name == "New Name"
        assert profile.phone == "0999999999"
        assert profile.title == "Staff Engineer"

    @patch(
        "app.services.ai_matching_service.AIMatchingService.index_confirmed_resume",
        new_callable=AsyncMock,
    )
    def test_confirm_is_idempotent(
        self, mock_index, candidate_client, run_async
    ):
        profile_id = _create_profile(candidate_client, run_async)
        draft = run_async(
            _seed_resume(
                profile_id,
                title="draft.pdf",
                is_primary=False,
                is_confirmed=False,
            )
        )

        first = run_async(
            candidate_client.post(
                f"{API_V1}/users/me/resume/{draft.id}/confirm"
            )
        )
        second = run_async(
            candidate_client.post(
                f"{API_V1}/users/me/resume/{draft.id}/confirm"
            )
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert (
            first.json()["resume"]["confirmed_at"]
            == second.json()["resume"]["confirmed_at"]
        )

    @patch(
        "app.services.ai_matching_service.AIMatchingService.index_confirmed_resume",
        new_callable=AsyncMock,
    )
    def test_index_failure_keeps_sql_confirmation(
        self, mock_index, candidate_client, run_async
    ):
        mock_index.side_effect = RuntimeError("qdrant unavailable")
        profile_id = _create_profile(candidate_client, run_async)
        draft = run_async(
            _seed_resume(
                profile_id,
                title="draft.pdf",
                is_primary=False,
                is_confirmed=False,
            )
        )

        resp = run_async(
            candidate_client.post(
                f"{API_V1}/users/me/resume/{draft.id}/confirm"
            )
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["indexing_status"] == "failed"
        assert body["resume"]["is_confirmed"] is True
        stored = run_async(_get_resume(str(draft.id)))
        assert stored.is_confirmed is True
        assert stored.is_primary is True

    def test_cannot_confirm_another_candidates_draft(
        self, candidate_client, candidate_b_client, run_async
    ):
        _create_profile(candidate_client, run_async)
        profile_b = _create_profile(candidate_b_client, run_async)
        draft_b = run_async(
            _seed_resume(
                profile_b,
                title="draft-b.pdf",
                is_primary=False,
                is_confirmed=False,
            )
        )

        resp = run_async(
            candidate_client.post(
                f"{API_V1}/users/me/resume/{draft_b.id}/confirm"
            )
        )

        assert resp.status_code == 404


@_SKIP_NO_QDRANT
class TestParseResumeFileValidation:
    """Tests for file upload hardening (SECURITY-06)."""

    def _make_pdf(self, pages: int = 1) -> bytes:
        """Generate a minimal PDF with specified number of pages."""
        # Minimal PDF with one page
        base_pdf = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n"
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\n"
            b"endobj\n"
            b"4 0 obj\n<< /Length 44 >>\nstream\n"
            b"BT\n/F1 12 Tf\n72 720 Td\n"
            b"(Test Page) Tj\n"
            b"ET\nendstream\nendobj\n"
            b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
            b"trailer\n<< /Size 6 /Root 1 0 R >>\n%%EOF\n"
        )
        if pages == 1:
            return base_pdf
        
        # For multi-page, we need a more complex PDF
        # This is a simplified version - real multi-page PDFs are more complex
        # For testing page limit, we'll rely on the extractor logic
        return base_pdf

    def test_valid_pdf_accepted(self, candidate_client, run_async):
        """Valid PDF under 10MB is accepted."""
        from unittest.mock import patch
        
        profile_id = _create_profile(candidate_client, run_async)
        
        with patch(
            "app.services.ai_matching_service.AIMatchingService.parse_and_save_resume_draft",
            new_callable=AsyncMock,
        ) as mock_parse:
            mock_parse.return_value = _draft_response()
            
            resp = run_async(
                candidate_client.post(
                    f"{API_V1}/ai/parse-resume",
                    files={
                        "file": (
                            "resume.pdf",
                            self._make_pdf(),
                            "application/pdf",
                        )
                    },
                )
            )
        
        assert resp.status_code == 200

    def test_uppercase_pdf_extension_accepted(self, candidate_client, run_async):
        """Uppercase .PDF extension is accepted."""
        from unittest.mock import patch
        
        profile_id = _create_profile(candidate_client, run_async)
        
        with patch(
            "app.services.ai_matching_service.AIMatchingService.parse_and_save_resume_draft",
            new_callable=AsyncMock,
        ) as mock_parse:
            mock_parse.return_value = _draft_response()
            
            resp = run_async(
                candidate_client.post(
                    f"{API_V1}/ai/parse-resume",
                    files={
                        "file": (
                            "resume.PDF",
                            self._make_pdf(),
                            "application/pdf",
                        )
                    },
                )
            )
        
        assert resp.status_code == 200

    def test_large_valid_pdf_above_general_limit_accepted(
        self, candidate_client, run_async
    ):
        """A valid CV above 1 MiB but below 10 MiB reaches the endpoint."""
        from unittest.mock import patch

        _create_profile(candidate_client, run_async)
        content = b"%PDF-1.7\n" + (b"x" * (2 * 1024 * 1024))

        with patch(
            "app.services.ai_matching_service.AIMatchingService.parse_and_save_resume_draft",
            new_callable=AsyncMock,
        ) as mock_parse:
            mock_parse.return_value = _draft_response()

            resp = run_async(
                candidate_client.post(
                    f"{API_V1}/ai/parse-resume",
                    files={
                        "file": (
                            "large-resume.pdf",
                            content,
                            "application/pdf",
                        )
                    },
                )
            )

        assert resp.status_code == 200, resp.text
        mock_parse.assert_awaited_once()

    def test_trailing_slash_redirects_without_size_penalty(
        self, candidate_client, run_async
    ):
        """The trailing-slash variant must redirect, not reject at 1 MiB."""
        _create_profile(candidate_client, run_async)
        content = b"%PDF-1.7\n" + (b"x" * (2 * 1024 * 1024))

        resp = run_async(
            candidate_client.post(
                f"{API_V1}/ai/parse-resume/",
                files={
                    "file": (
                        "large-resume.pdf",
                        content,
                        "application/pdf",
                    )
                },
            )
        )

        assert resp.status_code == 307, resp.text
        assert resp.headers["location"].endswith(f"{API_V1}/ai/parse-resume")

    def test_oversized_upload_rejected(self, candidate_client, run_async):
        """Oversized upload (>10MB) is rejected before full processing."""
        profile_id = _create_profile(candidate_client, run_async)
        
        # Create a file larger than 10MB
        oversized_content = b"X" * (11 * 1024 * 1024)
        
        resp = run_async(
            candidate_client.post(
                f"{API_V1}/ai/parse-resume",
                files={
                    "file": (
                        "large.pdf",
                        oversized_content,
                        "application/pdf",
                    )
                },
            )
        )
        
        # Should be rejected with 413
        assert resp.status_code == 413

    def test_non_pdf_extension_rejected(self, candidate_client, run_async):
        """Non-PDF extension is rejected even if content starts with %PDF."""
        profile_id = _create_profile(candidate_client, run_async)
        
        # Content starts with %PDF but extension is .txt
        resp = run_async(
            candidate_client.post(
                f"{API_V1}/ai/parse-resume",
                files={
                    "file": (
                        "resume.txt",
                        b"%PDF-1.7 Fake PDF content",
                        "text/plain",
                    )
                },
            )
        )
        
        assert resp.status_code == 400
        assert "Only .pdf files are allowed" in resp.text

    def test_invalid_magic_bytes_rejected(self, candidate_client, run_async):
        """File with invalid magic bytes is rejected."""
        profile_id = _create_profile(candidate_client, run_async)
        
        resp = run_async(
            candidate_client.post(
                f"{API_V1}/ai/parse-resume",
                files={
                    "file": (
                        "resume.pdf",
                        b"Not a PDF file",
                        "application/pdf",
                    )
                },
            )
        )
        
        assert resp.status_code == 422
        assert "Invalid PDF header" in resp.text

    def test_filename_too_long_rejected(self, candidate_client, run_async):
        """Filename exceeding 255 characters is rejected."""
        profile_id = _create_profile(candidate_client, run_async)
        
        long_filename = "a" * 256 + ".pdf"
        
        resp = run_async(
            candidate_client.post(
                f"{API_V1}/ai/parse-resume",
                files={
                    "file": (
                        long_filename,
                        b"%PDF-1.7 Short PDF content",
                        "application/pdf",
                    )
                },
            )
        )
        
        assert resp.status_code == 400
        assert "exceeds maximum length of 255 characters" in resp.text

    def test_path_traversal_filename_treated_as_metadata(self, candidate_client, run_async):
        """Path traversal filenames are treated as metadata only, not filesystem paths."""
        from unittest.mock import patch
        
        profile_id = _create_profile(candidate_client, run_async)
        
        with patch(
            "app.services.ai_matching_service.AIMatchingService.parse_and_save_resume_draft",
            new_callable=AsyncMock,
        ) as mock_parse:
            mock_parse.return_value = _draft_response()
            
            # These should be treated as metadata only, not actual paths
            for traversal_name in ["../../evil.pdf", "..\\evil.pdf"]:
                resp = run_async(
                    candidate_client.post(
                        f"{API_V1}/ai/parse-resume",
                        files={
                            "file": (
                                traversal_name,
                                self._make_pdf(),
                                "application/pdf",
                            )
                        },
                    )
                )
                # Should be accepted (treated as filename metadata)
                assert resp.status_code == 200, f"Failed for {traversal_name}: {resp.text}"

    def test_malformed_pdf_returns_controlled_error(self, candidate_client, run_async):
        """Malformed PDF returns controlled 4xx, not 500."""
        profile_id = _create_profile(candidate_client, run_async)
        
        # Valid header but corrupted structure
        resp = run_async(
            candidate_client.post(
                f"{API_V1}/ai/parse-resume",
                files={
                    "file": (
                        "corrupted.pdf",
                        b"%PDF-1.7 This is not a valid PDF structure",
                        "application/pdf",
                    )
                },
            )
        )
        
        # Should return a controlled 4xx, not 500
        assert resp.status_code in (400, 422)
        assert resp.status_code != 500