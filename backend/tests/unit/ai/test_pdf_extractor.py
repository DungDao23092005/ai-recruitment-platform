from __future__ import annotations

import io
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import EmptyDocumentError, InvalidDocumentError
from app.ai.extractors.pdf_extractor import (
    MAX_FILE_SIZE_BYTES,
    PDF_MAGIC_HEADER,
    PDFTextExtractor,
)

VALID_PDF_BYTES = PDF_MAGIC_HEADER + b"-1.7\n%Fake PDF content for test\n"


def test_normalize_text_full():
    raw_text = "  Hello   World  \r\n\r\n  Senior   Python   Developer  \n\n\x00"
    normalized = PDFTextExtractor.normalize_text(raw_text)

    assert normalized == "Hello World\nSenior Python Developer"


def test_extract_valid_pdf_bytes():
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "John Doe\nSoftware Engineer"

    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__.return_value = mock_pdf

    with patch("pdfplumber.open", return_value=mock_pdf):
        result = PDFTextExtractor.extract(VALID_PDF_BYTES)
        assert result == "John Doe\nSoftware Engineer"


def test_extract_valid_pdf_stream():
    stream = io.BytesIO(VALID_PDF_BYTES)

    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Jane Doe\nData Scientist"

    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__.return_value = mock_pdf

    with patch("pdfplumber.open", return_value=mock_pdf):
        result = PDFTextExtractor.extract(stream)
        assert result == "Jane Doe\nData Scientist"


def test_extract_valid_pdf_file_path():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(VALID_PDF_BYTES)
        tmp_path = tmp.name

    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Backend Architect"

    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__.return_value = mock_pdf

    try:
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = PDFTextExtractor.extract(tmp_path)
            assert result == "Backend Architect"
    finally:
        import os
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_extract_missing_magic_header():
    invalid_bytes = b"NOT_A_PDF_HEADER_CONTENT"
    with pytest.raises(InvalidDocumentError, match="Invalid PDF header"):
        PDFTextExtractor.extract(invalid_bytes)


def test_extract_oversized_bytes():
    large_bytes = PDF_MAGIC_HEADER + b"x" * (MAX_FILE_SIZE_BYTES + 1)
    with pytest.raises(InvalidDocumentError, match="exceeds maximum limit"):
        PDFTextExtractor.extract(large_bytes)


def test_extract_file_not_found():
    with pytest.raises(InvalidDocumentError, match="File not found"):
        PDFTextExtractor.extract("non_existent_file_12345.pdf")


def test_extract_unsupported_source_type():
    with pytest.raises(InvalidDocumentError, match="Unsupported source type"):
        PDFTextExtractor.extract(12345)  # type: ignore


def test_extract_empty_or_scanned_pdf():
    mock_page = MagicMock()
    mock_page.extract_text.return_value = ""  # Scanned image with no text

    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__.return_value = mock_pdf

    with patch("pdfplumber.open", return_value=mock_pdf):
        with pytest.raises(EmptyDocumentError, match="No extractable text found"):
            PDFTextExtractor.extract(VALID_PDF_BYTES)


def test_extract_corrupted_pdf_exception():
    with patch("pdfplumber.open", side_effect=RuntimeError("Corrupted stream")):
        with pytest.raises(InvalidDocumentError, match="Failed to parse PDF document"):
            PDFTextExtractor.extract(VALID_PDF_BYTES)
