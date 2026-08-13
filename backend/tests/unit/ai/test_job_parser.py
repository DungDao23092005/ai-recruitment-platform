from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.ai.interfaces.base_provider import BaseLLMProvider
from app.ai.parsers.job_parser import JOB_PARSER_SYSTEM_INSTRUCTION, JobParser
from app.core.exceptions import EmptyDocumentError, InvalidDocumentError
from app.schemas.ai_job import ParsedJobSchema

SAMPLE_JD = """\
Senior Python Backend Engineer

We are looking for a backend engineer to build and scale our services.

Requirements:
- 3+ years of experience with Python
- Strong knowledge of FastAPI
- Experience with SQL Server

Nice to have:
- Docker
- Kubernetes

Bachelor's degree in Computer Science preferred.
"""


@pytest.mark.asyncio
async def test_parse_valid_job_returns_parsed_schema():
    mock_provider = AsyncMock(spec=BaseLLMProvider)
    expected_schema = ParsedJobSchema(
        title="Python Backend Engineer",
        summary="Build backend services",
        required_skills=["Python", "FastAPI"],
        preferred_skills=["Docker"],
        minimum_years_experience=3.0,
        education_level="Bachelor",
    )
    mock_provider.generate_structured_output.return_value = expected_schema

    parser = JobParser(llm_provider=mock_provider)
    result = await parser.parse(SAMPLE_JD)

    assert isinstance(result, ParsedJobSchema)
    assert result == expected_schema
    assert result.title == "Python Backend Engineer"
    assert result.required_skills == ["Python", "FastAPI"]
    assert result.preferred_skills == ["Docker"]
    assert result.minimum_years_experience == 3.0
    assert result.education_level == "Bachelor"

    mock_provider.generate_structured_output.assert_awaited_once()
    call_kwargs = mock_provider.generate_structured_output.call_args.kwargs
    assert call_kwargs["response_schema"] is ParsedJobSchema
    assert call_kwargs["system_instruction"] == JOB_PARSER_SYSTEM_INSTRUCTION
    assert SAMPLE_JD.strip() in call_kwargs["prompt"]


@pytest.mark.asyncio
async def test_parse_empty_text_raises_empty_document_error():
    mock_provider = AsyncMock(spec=BaseLLMProvider)
    parser = JobParser(llm_provider=mock_provider)

    with pytest.raises(
        EmptyDocumentError,
        match="Job description text for parsing cannot be empty",
    ):
        await parser.parse("")

    with pytest.raises(
        EmptyDocumentError,
        match="Job description text for parsing cannot be empty",
    ):
        await parser.parse("   \n\t  ")

    mock_provider.generate_structured_output.assert_not_awaited()
    mock_provider.generate_structured_output.assert_not_called()


@pytest.mark.asyncio
async def test_parse_missing_optional_fields_keeps_nulls():
    mock_provider = AsyncMock(spec=BaseLLMProvider)
    minimal_schema = ParsedJobSchema(
        title="Backend Developer",
        required_skills=["Python"],
        preferred_skills=[],
        minimum_years_experience=None,
        education_level=None,
    )
    mock_provider.generate_structured_output.return_value = minimal_schema

    parser = JobParser(llm_provider=mock_provider)
    result = await parser.parse("Backend Developer position requiring Python")

    assert isinstance(result, ParsedJobSchema)
    assert result.title == "Backend Developer"
    assert result.required_skills == ["Python"]
    assert result.preferred_skills == []
    assert result.minimum_years_experience is None
    assert result.education_level is None


@pytest.mark.asyncio
async def test_parse_provider_failure_raises_invalid_document_error():
    mock_provider = AsyncMock(spec=BaseLLMProvider)
    mock_provider.generate_structured_output.side_effect = RuntimeError(
        "connection reset"
    )

    parser = JobParser(llm_provider=mock_provider)
    with pytest.raises(InvalidDocumentError):
        await parser.parse(SAMPLE_JD)

    error_message = None
    try:
        await parser.parse(SAMPLE_JD)
    except InvalidDocumentError as exc:
        error_message = str(exc)
    assert "connection reset" not in (error_message or "")
    assert "GEMINI_API_KEY" not in (error_message or "")


@pytest.mark.asyncio
async def test_parse_provider_invalid_document_error_propagates():
    mock_provider = AsyncMock(spec=BaseLLMProvider)
    mock_provider.generate_structured_output.side_effect = InvalidDocumentError(
        "Gemini request failed"
    )

    parser = JobParser(llm_provider=mock_provider)
    with pytest.raises(InvalidDocumentError, match="Gemini request failed"):
        await parser.parse(SAMPLE_JD)