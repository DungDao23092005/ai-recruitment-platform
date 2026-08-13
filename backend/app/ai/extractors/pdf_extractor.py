from __future__ import annotations

import io
import os
import re
import unicodedata
from typing import BinaryIO

import pdfplumber

from app.core.exceptions import EmptyDocumentError, InvalidDocumentError

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
PDF_MAGIC_HEADER = b"%PDF"


class PDFTextExtractor:
    """PDF text extractor using pdfplumber with text normalization."""

    @staticmethod
    def extract(source: bytes | str | os.PathLike[str] | BinaryIO) -> str:
        """Extract and normalize text from a PDF source.

        Args:
            source: PDF data as bytes, file path (str/PathLike), or BinaryIO stream.

        Returns:
            Normalized extracted text string.

        Raises:
            InvalidDocumentError: If file size exceeds 10MB, source is not a valid PDF,
                magic header is missing, or PDF is corrupted.
            EmptyDocumentError: If PDF has no extractable text (e.g. image-only/blank).
        """
        pdf_bytes = PDFTextExtractor._read_and_validate_bytes(source)

        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                extracted_pages: list[str] = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        extracted_pages.append(text)
        except Exception as exc:
            if isinstance(exc, (InvalidDocumentError, EmptyDocumentError)):
                raise
            raise InvalidDocumentError(f"Failed to parse PDF document: {exc}") from exc

        raw_text = "\n".join(extracted_pages)
        normalized_text = PDFTextExtractor.normalize_text(raw_text)

        if not normalized_text:
            raise EmptyDocumentError("No extractable text found in PDF document")

        return normalized_text

    @staticmethod
    def _read_and_validate_bytes(
        source: bytes | str | os.PathLike[str] | BinaryIO,
    ) -> bytes:
        if isinstance(source, bytes):
            data = source
        elif isinstance(source, (str, os.PathLike)):
            path = str(source)
            if not os.path.exists(path):
                raise InvalidDocumentError(f"File not found: {path}")
            size = os.path.getsize(path)
            if size > MAX_FILE_SIZE_BYTES:
                raise InvalidDocumentError(
                    f"File size ({size} bytes) exceeds maximum limit of {MAX_FILE_SIZE_BYTES} bytes (10MB)"
                )
            with open(path, "rb") as f:
                data = f.read()
        elif hasattr(source, "read"):
            pos = None
            if hasattr(source, "tell") and hasattr(source, "seek"):
                try:
                    pos = source.tell()
                except Exception:
                    pos = None
            data = source.read()
            if pos is not None:
                try:
                    source.seek(pos)
                except Exception:
                    pass
        else:
            raise InvalidDocumentError(f"Unsupported source type: {type(source)}")

        if len(data) > MAX_FILE_SIZE_BYTES:
            raise InvalidDocumentError(
                f"File size ({len(data)} bytes) exceeds maximum limit of {MAX_FILE_SIZE_BYTES} bytes (10MB)"
            )

        if len(data) < len(PDF_MAGIC_HEADER) or not data.startswith(PDF_MAGIC_HEADER):
            raise InvalidDocumentError("Invalid PDF header: missing '%PDF' magic header")

        return data

    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize extracted text string.

        - Normalize Unicode NFKC
        - Convert CRLF / CR to LF
        - Remove control characters except LF (\n)
        - Strip each line and collapse internal whitespace
        - Remove empty lines
        """
        if not text:
            return ""

        normalized = unicodedata.normalize("NFKC", text)
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

        normalized = "".join(
            ch for ch in normalized if ch == "\n" or (ord(ch) >= 32 and ord(ch) != 127)
        )

        lines: list[str] = []
        for line in normalized.split("\n"):
            line_clean = re.sub(r"[ \t]+", " ", line).strip()
            if line_clean:
                lines.append(line_clean)

        return "\n".join(lines)
