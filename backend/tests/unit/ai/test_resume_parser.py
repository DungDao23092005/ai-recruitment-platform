from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.interfaces.base_provider import BaseLLMProvider
from app.ai.parsers.resume_parser import ResumeParser
from app.core.exceptions import EmptyDocumentError, InvalidDocumentError
from app.schemas.ai_resume import (
    EducationSchema,
    ParsedResumeSchema,
    WorkExperienceSchema,
)


@pytest.mark.asyncio
async def test_parse_empty_text_raises_empty_document_error():
    parser = ResumeParser(llm_provider=AsyncMock(spec=BaseLLMProvider))
    with pytest.raises(EmptyDocumentError, match="cannot be empty"):
        await parser.parse("")

    with pytest.raises(EmptyDocumentError, match="cannot be empty"):
        await parser.parse("   \n\t  ")


@pytest.mark.asyncio
async def test_parse_valid_text_calls_provider():
    mock_provider = AsyncMock(spec=BaseLLMProvider)
    expected_schema = ParsedResumeSchema(
        full_name="Nguyen Van A",
        email="nguyenvana@example.com",
        phone="0912345678",
        title="Senior Python Developer",
        summary="Experienced Python Developer with 5 years in FastAPI and SQL Server.",
        total_years_experience=5.0,
        skills=["Python", "FastAPI", "SQL Server", "Docker"],
        experiences=[
            WorkExperienceSchema(
                company="Tech Corp",
                position="Senior Python Developer",
                start_date="01/2021",
                end_date="Present",
                is_current=True,
                description="Lead backend development team",
                skills_used=["Python", "FastAPI"],
            )
        ],
        education=[
            EducationSchema(
                institution="Hanoi University of Science and Technology",
                degree="Bachelor of Science",
                field_of_study="Computer Science",
                start_year=2016,
                end_year=2020,
            )
        ],
        certifications=["AWS Certified Developer"],
        languages=["Vietnamese", "English"],
    )
    mock_provider.generate_structured_output.return_value = expected_schema

    parser = ResumeParser(llm_provider=mock_provider)
    sample_cv = """
    Nguyen Van A
    Email: nguyenvana@example.com | Phone: 0912345678
    Title: Senior Python Developer
    Summary: Experienced Python Developer with 5 years in FastAPI and SQL Server.

    Work Experience:
    Senior Python Developer at Tech Corp (01/2021 - Present)
    - Lead backend development team using Python, FastAPI.

    Education:
    Bachelor of Science in Computer Science, Hanoi University of Science and Technology (2016 - 2020)
    """

    result = await parser.parse(sample_cv)

    assert result == expected_schema
    assert result.full_name == "Nguyen Van A"
    assert result.total_years_experience == 5.0
    assert "Python" in result.skills
    mock_provider.generate_structured_output.assert_awaited_once()


@pytest.mark.asyncio
async def test_parse_missing_optional_fields_returns_nulls():
    mock_provider = AsyncMock(spec=BaseLLMProvider)
    minimal_schema = ParsedResumeSchema(
        full_name="Minimal Candidate",
        skills=["Python"],
    )
    mock_provider.generate_structured_output.return_value = minimal_schema

    parser = ResumeParser(llm_provider=mock_provider)
    result = await parser.parse("Minimal Candidate - Python dev")

    assert result.full_name == "Minimal Candidate"
    assert result.email is None
    assert result.phone is None
    assert result.total_years_experience is None
    assert result.experiences == []
    assert result.education == []


@pytest.mark.asyncio
async def test_parse_provider_failure_raises_invalid_document_error():
    mock_provider = AsyncMock(spec=BaseLLMProvider)
    mock_provider.generate_structured_output.side_effect = InvalidDocumentError(
        "Gemini request failed"
    )

    parser = ResumeParser(llm_provider=mock_provider)
    with pytest.raises(InvalidDocumentError, match="Gemini request failed"):
        await parser.parse("Valid CV text sample")
