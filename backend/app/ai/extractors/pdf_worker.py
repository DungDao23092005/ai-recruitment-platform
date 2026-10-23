"""Child-process entry point for isolated PDF text extraction.

This module is deliberately tiny: a spawned child only needs ``pdfplumber`` and
the extractor, not the FastAPI application, database or AI providers. The child
reports a structured status over a pipe and never raises across the process
boundary.
"""

from __future__ import annotations

from typing import Any

from app.ai.extractors.pdf_extractor import PDFTextExtractor
from app.core.exceptions import EmptyDocumentError, InvalidDocumentError


def extract_pdf_worker(conn: Any, pdf_bytes: bytes) -> None:
    """Extract PDF text and send ``(status, payload)`` to the parent."""
    try:
        text = PDFTextExtractor.extract(pdf_bytes)
        payload: tuple[str, str] = ("ok", text)
    except EmptyDocumentError as exc:
        payload = ("empty", str(exc))
    except InvalidDocumentError as exc:
        payload = ("invalid", str(exc))
    except BaseException as exc:  # noqa: BLE001 - crash containment boundary
        payload = ("error", type(exc).__name__)
    try:
        conn.send(payload)
    except BaseException:  # noqa: BLE001 - parent may have gone away
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
