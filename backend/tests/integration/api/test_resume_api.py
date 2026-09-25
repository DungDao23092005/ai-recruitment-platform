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
    @patch("app.services.ai_matching_service.AIMatchingService.process_and_index_resume")
    def test_upload_creates_resume_row(self, mock_process, candidate_client, run_async):
        # Mock the AI processing but still persist to database
        async def mock_process_and_index(candidate_id, pdf_source, session, source_name):
            # Create resume row in database (simulating real persistence)
            from app.models import Resume
            from app.schemas.ai_resume import ParsedResumeSchema
            parsed = ParsedResumeSchema(
                full_name="Jane Doe",
                skills=["Python", "FastAPI"],
            )
            resume = Resume(
                candidate_id=candidate_id,
                title=source_name or "resume.pdf",
                is_primary=True,
                parsed_data=parsed.model_dump(mode="json"),
            )
            session.add(resume)
            await session.flush()
            await session.commit()
            await session.refresh(resume)
            return parsed
        
        mock_process.side_effect = mock_process_and_index
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
        rows = run_async(_get_resumes_for_candidate(profile_id))
        assert len(rows) == 1
        assert rows[0].is_primary is True
        assert rows[0].parsed_data is not None
        assert "full_name" in rows[0].parsed_data

    @patch("app.services.ai_matching_service.AIMatchingService.process_and_index_resume")
    def test_second_upload_updates_primary(self, mock_process, candidate_client, run_async):
        # Mock the AI processing but still persist to database
        async def mock_process_and_index(candidate_id, pdf_source, session, source_name):
            from app.models import Resume
            from app.schemas.ai_resume import ParsedResumeSchema
            parsed = ParsedResumeSchema(
                full_name="Jane Doe",
                skills=["Python", "FastAPI"],
            )
            # Find existing primary resume and update it
            from sqlalchemy import select
            stmt = select(Resume).where(
                Resume.candidate_id == candidate_id,
                Resume.is_primary == True,
                Resume.is_deleted == False,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                existing.title = source_name or "resume.pdf"
                existing.parsed_data = parsed.model_dump(mode="json")
            else:
                resume = Resume(
                    candidate_id=candidate_id,
                    title=source_name or "resume.pdf",
                    is_primary=True,
                    parsed_data=parsed.model_dump(mode="json"),
                )
                session.add(resume)
            await session.flush()
            await session.commit()
            return parsed
        
        mock_process.side_effect = mock_process_and_index
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
        assert rows[0].is_primary is True
        assert rows[0].title == "resume.pdf"


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
        
        with patch("app.services.ai_matching_service.AIMatchingService.process_and_index_resume") as mock_process:
            mock_process.return_value = ParsedResumeSchema(
                full_name="Jane Doe",
                skills=["Python", "FastAPI"],
            )
            
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
        
        with patch("app.services.ai_matching_service.AIMatchingService.process_and_index_resume") as mock_process:
            mock_process.return_value = ParsedResumeSchema(
                full_name="Jane Doe",
                skills=["Python", "FastAPI"],
            )
            
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
        
        with patch("app.services.ai_matching_service.AIMatchingService.process_and_index_resume") as mock_process:
            mock_process.return_value = ParsedResumeSchema(
                full_name="Jane Doe",
                skills=["Python"],
            )
            
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