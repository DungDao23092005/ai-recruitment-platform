"""
Unicode persistence regression tests for NVARCHAR columns.

These tests verify that the 5 NVARCHAR columns can correctly store and retrieve
Unicode characters (Vietnamese, emoji, special characters, etc.).

NOTE: These tests require a running SQL Server database with the NVARCHAR migration applied.
They will be skipped if DATABASE_URL is not configured or database is unavailable.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, Company, KnowledgeDocument, CandidateProfile, RecruiterProfile, User
from app.domain.enums import (
    CompanySize, JobStatus, JobType, WorkplaceType, UserRole,
)
from app.models.knowledge import KnowledgeCategory, KnowledgeVisibility, KnowledgeStatus
from app.database.session import async_session_factory


class TestUnicodePersistence:
    """Test Unicode persistence for all 5 NVARCHAR columns."""

    def test_job_title_unicode_persistence(self, run_async):
        """Test jobs.title NVARCHAR(255) stores Unicode correctly."""

        async def _test():
            async with async_session_factory() as db_session:
                # Create company first (required for job)
                company = Company(
                    id=uuid.uuid4(),
                    name="Test Company 🏢",
                    slug="test-company-unicode",
                    tax_code="123456789",
                    size=CompanySize.STARTUP,
                )
                db_session.add(company)
                await db_session.flush()

                # Create job with Vietnamese Unicode title
                job = Job(
                    id=uuid.uuid4(),
                    company_id=company.id,
                    title="Lập trình viên Backend 🚀",
                    description="Test description",
                    status=JobStatus.PUBLISHED,
                    job_type=JobType.FULL_TIME,
                    workplace_type=WorkplaceType.REMOTE,
                    location="Hà Nội",
                )
                db_session.add(job)
                await db_session.commit()
                await db_session.refresh(job)

                # Verify Unicode round-trip
                assert job.title == "Lập trình viên Backend 🚀"

                # Test Vietnamese characters update
                job.title = "Senior Developer - Tiếng Việt: ă â đ ê ô ơ ư"
                await db_session.commit()
                await db_session.refresh(job)
                assert job.title == "Senior Developer - Tiếng Việt: ă â đ ê ô ơ ư"

        run_async(_test())

    def test_company_name_unicode_persistence(self, run_async):
        """Test companies.name NVARCHAR(255) stores Unicode correctly."""

        async def _test():
            async with async_session_factory() as db_session:
                company = Company(
                    id=uuid.uuid4(),
                    name="Công ty TNHH Đầu Tư 🇻🇳",
                    slug="cong-ty-dau-tu-unicode",
                    tax_code="987654321",
                    size=CompanySize.STARTUP,
                )
                db_session.add(company)
                await db_session.commit()
                await db_session.refresh(company)

                assert company.name == "Công ty TNHH Đầu Tư 🇻🇳"

                # Update with mixed Unicode
                company.name = "Company 中文 日本語 한글 🌟"
                await db_session.commit()
                await db_session.refresh(company)
                assert company.name == "Company 中文 日本語 한글 🌟"

        run_async(_test())

    def test_knowledge_document_title_unicode_persistence(self, run_async):
        """Test knowledge_documents.title NVARCHAR(255) stores Unicode correctly."""

        async def _test():
            async with async_session_factory() as db_session:
                doc = KnowledgeDocument(
                    id=uuid.uuid4(),
                    title="Hướng dẫn phỏng vấn 📋 - Tiếng Việt & English",
                    category=KnowledgeCategory.INTERVIEW,
                    content="Nội dung bài viết...",
                    visibility=KnowledgeVisibility.PUBLIC,
                    status=KnowledgeStatus.PUBLISHED,
                    language="vi",
                )
                db_session.add(doc)
                await db_session.commit()
                await db_session.refresh(doc)

                assert doc.title == "Hướng dẫn phỏng vấn 📋 - Tiếng Việt & English"

                # Update with emoji and special chars
                doc.title = "Interview Guide 🚀 @#$%^&*()"
                await db_session.commit()
                await db_session.refresh(doc)
                assert doc.title == "Interview Guide 🚀 @#$%^&*()"

        run_async(_test())

    def test_candidate_profile_full_name_unicode_persistence(self, run_async):
        """Test candidate_profiles.full_name NVARCHAR(255) stores Unicode correctly."""

        async def _test():
            async with async_session_factory() as db_session:
                user = User(
                    id=uuid.uuid4(),
                    email=f"candidate-{uuid.uuid4()}@test.com",
                    password_hash="hash",
                    role=UserRole.CANDIDATE,
                    is_active=True,
                )
                db_session.add(user)
                await db_session.flush()

                profile = CandidateProfile(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    full_name="Nguyễn Văn An",
                    phone="0123456789",
                    title="Senior Developer",
                )
                db_session.add(profile)
                await db_session.commit()
                await db_session.refresh(profile)

                assert profile.full_name == "Nguyễn Văn An"

                # Update with mixed Unicode
                profile.full_name = "Hồ Chí Minh 🇻🇳"
                await db_session.commit()
                await db_session.refresh(profile)
                assert profile.full_name == "Hồ Chí Minh 🇻🇳"

        run_async(_test())

    def test_recruiter_profile_full_name_unicode_persistence(self, run_async):
        """Test recruiter_profiles.full_name NVARCHAR(255) stores Unicode correctly."""

        async def _test():
            async with async_session_factory() as db_session:
                user = User(
                    id=uuid.uuid4(),
                    email=f"recruiter-{uuid.uuid4()}@test.com",
                    password_hash="hash",
                    role=UserRole.RECRUITER,
                    is_active=True,
                )
                db_session.add(user)
                await db_session.flush()

                company = Company(
                    id=uuid.uuid4(),
                    name="Test Company",
                    slug="test-company-recruiter",
                    tax_code="111222333",
                    size=CompanySize.STARTUP,
                )
                db_session.add(company)
                await db_session.flush()

                profile = RecruiterProfile(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    company_id=company.id,
                    full_name="Trần Thị Bình",
                    position="HR Manager",
                )
                db_session.add(profile)
                await db_session.commit()
                await db_session.refresh(profile)

                assert profile.full_name == "Trần Thị Bình"

                # Update with emoji
                profile.full_name = "Lê Văn Cường 👨‍💼"
                await db_session.commit()
                await db_session.refresh(profile)
                assert profile.full_name == "Lê Văn Cường 👨‍💼"

        run_async(_test())


class TestUnicodeEdgeCases:
    """Test edge cases for Unicode persistence."""

    def test_all_unicode_variants_in_single_transaction(self, run_async):
        """Test all 5 NVARCHAR columns with various Unicode in one transaction."""

        async def _test():
            async with async_session_factory() as db_session:
                company = Company(
                    id=uuid.uuid4(),
                    name="Multi-Unicode Company 中文",
                    slug="multi-unicode-company",
                    tax_code="555666777",
                    size=CompanySize.STARTUP,
                )
                db_session.add(company)
                await db_session.flush()

                # Job with emoji
                job = Job(
                    id=uuid.uuid4(),
                    company_id=company.id,
                    title="Backend Engineer 🚀💻",
                    description="Job with emoji",
                    status=JobStatus.PUBLISHED,
                    job_type=JobType.FULL_TIME,
                    workplace_type=WorkplaceType.REMOTE,
                    location="Hà Nội",
                )
                db_session.add(job)

                # Knowledge document with Vietnamese
                doc = KnowledgeDocument(
                    id=uuid.uuid4(),
                    title="Kiến thức tuyển dụng 📚",
                    category=KnowledgeCategory.RECRUITMENT,
                    content="Nội dung...",
                    visibility=KnowledgeVisibility.PUBLIC,
                    status=KnowledgeStatus.PUBLISHED,
                    language="vi",
                )
                db_session.add(doc)

                # Candidate with Korean name
                candidate_user = User(
                    id=uuid.uuid4(),
                    email=f"candidate-kr-{uuid.uuid4()}@test.com",
                    password_hash="hash",
                    role=UserRole.CANDIDATE,
                    is_active=True,
                )
                db_session.add(candidate_user)
                await db_session.flush()

                candidate_profile = CandidateProfile(
                    id=uuid.uuid4(),
                    user_id=candidate_user.id,
                    full_name="김철수 (Kim Cheol-su)",
                    phone="0123456789",
                )
                db_session.add(candidate_profile)

                # Recruiter with Japanese name
                recruiter_user = User(
                    id=uuid.uuid4(),
                    email=f"recruiter-jp-{uuid.uuid4()}@test.com",
                    password_hash="hash",
                    role=UserRole.RECRUITER,
                    is_active=True,
                )
                db_session.add(recruiter_user)
                await db_session.flush()

                recruiter_profile = RecruiterProfile(
                    id=uuid.uuid4(),
                    user_id=recruiter_user.id,
                    company_id=company.id,
                    full_name="田中太郎 (Tanaka Taro)",
                    position="Tech Lead",
                )
                db_session.add(recruiter_profile)

                await db_session.commit()

                # Refresh all and verify
                await db_session.refresh(company)
                await db_session.refresh(job)
                await db_session.refresh(doc)
                await db_session.refresh(candidate_profile)
                await db_session.refresh(recruiter_profile)

                assert company.name == "Multi-Unicode Company 中文"
                assert job.title == "Backend Engineer 🚀💻"
                assert doc.title == "Kiến thức tuyển dụng 📚"
                assert candidate_profile.full_name == "김철수 (Kim Cheol-su)"
                assert recruiter_profile.full_name == "田中太郎 (Tanaka Taro)"

        run_async(_test())

    def test_unicode_length_limits(self, run_async):
        """Test Unicode strings at/near NVARCHAR(255) limit."""

        async def _test():
            async with async_session_factory() as db_session:
                company = Company(
                    id=uuid.uuid4(),
                    name="Test Company",
                    slug="test-length-limit",
                    tax_code="999888777",
                    size=CompanySize.STARTUP,
                )
                db_session.add(company)
                await db_session.flush()

                # Test job title at 255 chars (using single-byte chars to ensure fit)
                # Emojis can take multiple bytes in UTF-16 (NVARCHAR), so use ASCII for length test
                long_title = "A" * 255
                job = Job(
                    id=uuid.uuid4(),
                    company_id=company.id,
                    title=long_title,
                    description="Test",
                    status=JobStatus.PUBLISHED,
                    job_type=JobType.FULL_TIME,
                    workplace_type=WorkplaceType.REMOTE,
                    location="Remote",
                )
                db_session.add(job)
                await db_session.commit()
                await db_session.refresh(job)

                assert job.title == long_title
                assert len(job.title) == 255

        run_async(_test())

    def test_unicode_with_null_values(self, run_async):
        """Test NVARCHAR columns handle NULL correctly."""

        async def _test():
            async with async_session_factory() as db_session:
                user = User(
                    id=uuid.uuid4(),
                    email=f"candidate-null-{uuid.uuid4()}@test.com",
                    password_hash="hash",
                    role=UserRole.CANDIDATE,
                    is_active=True,
                )
                db_session.add(user)
                await db_session.flush()

                # full_name is nullable
                profile = CandidateProfile(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    full_name=None,  # NULL value
                    phone=None,
                )
                db_session.add(profile)
                await db_session.commit()
                await db_session.refresh(profile)

                assert profile.full_name is None

                # Update to Unicode string
                profile.full_name = "Unicode Name 🌟"
                await db_session.commit()
                await db_session.refresh(profile)
                assert profile.full_name == "Unicode Name 🌟"

        run_async(_test())

    def test_unicode_update_persistence(self, run_async):
        """Test updating NVARCHAR columns preserves Unicode."""

        async def _test():
            async with async_session_factory() as db_session:
                company = Company(
                    id=uuid.uuid4(),
                    name="Original Name",
                    slug="update-test-company",
                    tax_code="444555666",
                    size=CompanySize.STARTUP,
                )
                db_session.add(company)
                await db_session.commit()
                await db_session.refresh(company)

                # Update with Vietnamese
                company.name = "Công ty Cổ phần 🇻🇳"
                await db_session.commit()
                await db_session.refresh(company)
                assert company.name == "Công ty Cổ phần 🇻🇳"

                # Update again with emoji
                company.name = "Updated 🚀💻🌟"
                await db_session.commit()
                await db_session.refresh(company)
                assert company.name == "Updated 🚀💻🌟"

                # Update with Chinese
                company.name = "更新后的公司名称"
                await db_session.commit()
                await db_session.refresh(company)
                assert company.name == "更新后的公司名称"

        run_async(_test())


class TestUnicodeMigrationVerification:
    """Verify the NVARCHAR migration was applied correctly."""

    def test_job_title_column_is_nvarchar(self, run_async):
        """Verify jobs.title column type is NVARCHAR."""

        async def _test():
            async with async_session_factory() as db_session:
                # Query the information schema to check column type
                result = await db_session.execute(
                    text("""
                        SELECT DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
                        FROM INFORMATION_SCHEMA.COLUMNS
                        WHERE TABLE_NAME = 'jobs' AND COLUMN_NAME = 'title'
                    """)
                )
                row = result.fetchone()
                assert row is not None, "jobs.title column not found"
                # In SQL Server, NVARCHAR shows as 'nvarchar'
                assert row[0].lower() in ('nvarchar', 'nvarchar(255)'), f"Expected NVARCHAR, got {row[0]}"
                assert row[1] == 255 or row[1] == -1, f"Expected length 255, got {row[1]}"

        run_async(_test())

    def test_company_name_column_is_nvarchar(self, run_async):
        """Verify companies.name column type is NVARCHAR."""

        async def _test():
            async with async_session_factory() as db_session:
                result = await db_session.execute(
                    text("""
                        SELECT DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
                        FROM INFORMATION_SCHEMA.COLUMNS
                        WHERE TABLE_NAME = 'companies' AND COLUMN_NAME = 'name'
                    """)
                )
                row = result.fetchone()
                assert row is not None, "companies.name column not found"
                assert row[0].lower() in ('nvarchar', 'nvarchar(255)'), f"Expected NVARCHAR, got {row[0]}"
                assert row[1] == 255 or row[1] == -1, f"Expected length 255, got {row[1]}"

        run_async(_test())

    def test_knowledge_title_column_is_nvarchar(self, run_async):
        """Verify knowledge_documents.title column type is NVARCHAR."""

        async def _test():
            async with async_session_factory() as db_session:
                result = await db_session.execute(
                    text("""
                        SELECT DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
                        FROM INFORMATION_SCHEMA.COLUMNS
                        WHERE TABLE_NAME = 'knowledge_documents' AND COLUMN_NAME = 'title'
                    """)
                )
                row = result.fetchone()
                assert row is not None, "knowledge_documents.title column not found"
                assert row[0].lower() in ('nvarchar', 'nvarchar(255)'), f"Expected NVARCHAR, got {row[0]}"
                assert row[1] == 255 or row[1] == -1, f"Expected length 255, got {row[1]}"

        run_async(_test())

    def test_candidate_full_name_column_is_nvarchar(self, run_async):
        """Verify candidate_profiles.full_name column type is NVARCHAR."""

        async def _test():
            async with async_session_factory() as db_session:
                result = await db_session.execute(
                    text("""
                        SELECT DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
                        FROM INFORMATION_SCHEMA.COLUMNS
                        WHERE TABLE_NAME = 'candidate_profiles' AND COLUMN_NAME = 'full_name'
                    """)
                )
                row = result.fetchone()
                assert row is not None, "candidate_profiles.full_name column not found"
                assert row[0].lower() in ('nvarchar', 'nvarchar(255)'), f"Expected NVARCHAR, got {row[0]}"
                assert row[1] == 255 or row[1] == -1, f"Expected length 255, got {row[1]}"

        run_async(_test())

    def test_recruiter_full_name_column_is_nvarchar(self, run_async):
        """Verify recruiter_profiles.full_name column type is NVARCHAR."""

        async def _test():
            async with async_session_factory() as db_session:
                result = await db_session.execute(
                    text("""
                        SELECT DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
                        FROM INFORMATION_SCHEMA.COLUMNS
                        WHERE TABLE_NAME = 'recruiter_profiles' AND COLUMN_NAME = 'full_name'
                    """)
                )
                row = result.fetchone()
                assert row is not None, "recruiter_profiles.full_name column not found"
                assert row[0].lower() in ('nvarchar', 'nvarchar(255)'), f"Expected NVARCHAR, got {row[0]}"
                assert row[1] == 255 or row[1] == -1, f"Expected length 255, got {row[1]}"

        run_async(_test())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
