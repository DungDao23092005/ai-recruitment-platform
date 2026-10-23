"""Process-isolated PDF text extraction.

``pdfplumber`` parses untrusted documents in the API process. A malformed or
adversarial PDF can therefore consume unbounded CPU or memory. This module runs
the extractor in a short-lived spawned child process with:

* a bounded number of concurrent worker slots,
* an overall extraction timeout,
* a pipe-based, structured result channel,
* cancellation-safe cleanup,
* exit-status verification (the payload is only trusted after a clean exit),
* a quarantine/degraded mode after repeated infrastructure failures.

The slot is acquired *before* any process resources are created and is released
only once the lifecycle has been resolved (success, controlled failure, or a
confirmed kill). If a process cannot be confirmed dead, the slot is
intentionally not returned and the pool enters degraded mode rather than
risking unbounded orphan processes.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import os
import threading
import time
import weakref
from typing import Any, BinaryIO, Callable

from app.ai.extractors.pdf_extractor import (
    MAX_FILE_SIZE_BYTES,
    PDFTextExtractor,
)
from app.ai.extractors.pdf_worker import extract_pdf_worker
from app.core.config import settings
from app.core.exceptions import (
    EmptyDocumentError,
    InvalidDocumentError,
    PDFWorkerUnavailableError,
)

logger = logging.getLogger(__name__)

WorkerTarget = Callable[[Any, bytes], None]

_OK = "ok"
_EMPTY = "empty"
_INVALID = "invalid"


def _read_source_bytes(
    source: bytes | str | os.PathLike[str] | BinaryIO,
) -> bytes:
    """Materialise the upload source without parsing it in the API process."""
    if isinstance(source, bytes):
        data = source
    elif isinstance(source, (str, os.PathLike)):
        path = str(source)
        if not os.path.exists(path):
            raise InvalidDocumentError(f"File not found: {path}")
        size = os.path.getsize(path)
        if size > MAX_FILE_SIZE_BYTES:
            raise InvalidDocumentError(
                f"File size ({size} bytes) exceeds maximum limit of "
                f"{MAX_FILE_SIZE_BYTES} bytes (10MB)"
            )
        with open(path, "rb") as handle:
            data = handle.read()
    elif hasattr(source, "read"):
        position = None
        if hasattr(source, "tell") and hasattr(source, "seek"):
            try:
                position = source.tell()
            except Exception:
                position = None
        data = source.read()
        if position is not None:
            try:
                source.seek(position)
            except Exception:
                pass
    else:
        raise InvalidDocumentError(f"Unsupported source type: {type(source)}")

    if not isinstance(data, (bytes, bytearray)):
        raise InvalidDocumentError("PDF source did not yield bytes")
    data = bytes(data)
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise InvalidDocumentError(
            f"File size ({len(data)} bytes) exceeds maximum limit of "
            f"{MAX_FILE_SIZE_BYTES} bytes (10MB)"
        )
    return data


class _LoopSemaphore:
    """Per-event-loop semaphore holder."""

    def __init__(self, limit: int) -> None:
        self.limit = max(1, int(limit))
        self._semaphores: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = (
            weakref.WeakKeyDictionary()
        )

    def get(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        semaphore = self._semaphores.get(loop)
        if semaphore is None:
            semaphore = asyncio.Semaphore(self.limit)
            self._semaphores[loop] = semaphore
        return semaphore


class IsolatedPDFProcessor:
    """Run :class:`PDFTextExtractor` in a spawned, supervised child process."""

    def __init__(
        self,
        *,
        max_concurrency: int | None = None,
        timeout_seconds: float | None = None,
        terminate_grace_seconds: float | None = None,
        max_consecutive_failures: int | None = None,
        quarantine_seconds: float | None = None,
        context_factory: Callable[[], Any] | None = None,
        worker_target: WorkerTarget | None = None,
    ) -> None:
        self.max_concurrency = max(
            1,
            int(
                max_concurrency
                if max_concurrency is not None
                else settings.PDF_WORKER_MAX_CONCURRENCY
            ),
        )
        self.timeout_seconds = float(
            timeout_seconds
            if timeout_seconds is not None
            else settings.PDF_WORKER_TIMEOUT_SECONDS
        )
        self.terminate_grace_seconds = max(
            0.05,
            float(
                terminate_grace_seconds
                if terminate_grace_seconds is not None
                else settings.PDF_WORKER_TERMINATE_GRACE_SECONDS
            ),
        )
        self.max_consecutive_failures = max(
            1,
            int(
                max_consecutive_failures
                if max_consecutive_failures is not None
                else settings.PDF_WORKER_MAX_CONSECUTIVE_FAILURES
            ),
        )
        self.quarantine_seconds = max(
            0.0,
            float(
                quarantine_seconds
                if quarantine_seconds is not None
                else settings.PDF_WORKER_QUARANTINE_SECONDS
            ),
        )
        self._context_factory = context_factory or (
            lambda: multiprocessing.get_context("spawn")
        )
        self._worker_target = worker_target or extract_pdf_worker
        self._slots = _LoopSemaphore(self.max_concurrency)
        self._state_lock = threading.Lock()
        self._consecutive_failures = 0
        self._degraded_until = 0.0

    # ------------------------------------------------------------------ health

    def _is_degraded(self) -> bool:
        with self._state_lock:
            return self._degraded_until > time.monotonic()

    def _record_success(self) -> None:
        with self._state_lock:
            self._consecutive_failures = 0
            self._degraded_until = 0.0

    def _record_failure(self, reason: str) -> None:
        with self._state_lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.max_consecutive_failures:
                self._degraded_until = time.monotonic() + self.quarantine_seconds
                logger.error(
                    "PDF isolation quarantined after %d consecutive failures (%s)",
                    self._consecutive_failures,
                    reason,
                )

    def reset_health(self) -> None:
        with self._state_lock:
            self._consecutive_failures = 0
            self._degraded_until = 0.0

    # ----------------------------------------------------------------- extract

    async def extract(self, source: bytes | str | os.PathLike[str] | BinaryIO) -> str:
        pdf_bytes = _read_source_bytes(source)

        if self._is_degraded():
            raise PDFWorkerUnavailableError(
                "PDF processing is temporarily degraded. Please retry shortly.",
                retry_after=max(1, int(self.quarantine_seconds)),
            )

        slots = self._slots.get()
        try:
            await asyncio.wait_for(
                slots.acquire(), timeout=min(self.timeout_seconds, 5.0)
            )
        except (asyncio.TimeoutError, TimeoutError):
            raise PDFWorkerUnavailableError(
                "PDF processing is busy. Please retry shortly.", retry_after=5
            ) from None

        release_slot = True
        parent_conn = None
        child_conn = None
        process = None
        started = False

        try:
            try:
                context = self._context_factory()
                parent_conn, child_conn = context.Pipe(duplex=True)
                process = context.Process(
                    target=self._worker_target,
                    args=(child_conn, pdf_bytes),
                    daemon=True,
                )
            except Exception as exc:  # noqa: BLE001 - pre-start failure
                self._record_failure("process_setup")
                logger.warning(
                    "PDF worker setup failed: %s", type(exc).__name__
                )
                raise PDFWorkerUnavailableError(
                    "PDF processing is temporarily unavailable.",
                    retry_after=10,
                ) from exc

            try:
                process.start()
                started = True
            except Exception as exc:  # noqa: BLE001 - start failure
                self._record_failure("process_start")
                logger.warning(
                    "PDF worker start failed: %s", type(exc).__name__
                )
                raise PDFWorkerUnavailableError(
                    "PDF processing is temporarily unavailable.",
                    retry_after=10,
                ) from exc

            # The parent must not keep the child's end open, otherwise a child
            # crash would not surface as EOF on the parent connection.
            try:
                child_conn.close()
            except Exception:
                pass

            try:
                payload = await asyncio.wait_for(
                    asyncio.to_thread(parent_conn.recv),
                    timeout=self.timeout_seconds,
                )
            except (asyncio.TimeoutError, TimeoutError):
                self._record_failure("timeout")
                release_slot = self._terminate(process)
                raise PDFWorkerUnavailableError(
                    "PDF processing timed out. Please retry.", retry_after=10
                ) from None
            except (EOFError, OSError) as exc:
                self._record_failure("worker_crashed")
                release_slot = self._terminate(process)
                logger.warning(
                    "PDF worker exited without a result: %s",
                    type(exc).__name__,
                )
                raise PDFWorkerUnavailableError(
                    "PDF processing failed unexpectedly.", retry_after=10
                ) from exc

            exit_confirmed = self._join_worker(process)
            if not exit_confirmed:
                self._record_failure("unconfirmed_exit")
                release_slot = False
                raise PDFWorkerUnavailableError(
                    "PDF processing is temporarily unavailable.",
                    retry_after=10,
                )
            if process.exitcode not in (0, None):
                self._record_failure("nonzero_exit")
                raise PDFWorkerUnavailableError(
                    "PDF processing failed unexpectedly.", retry_after=10
                )

            if not isinstance(payload, tuple) or len(payload) != 2:
                self._record_failure("malformed_result")
                raise PDFWorkerUnavailableError(
                    "PDF processing failed unexpectedly.", retry_after=10
                )

            status, value = payload
            if status == _OK:
                self._record_success()
                return str(value)
            if status == _EMPTY:
                self._record_success()
                raise EmptyDocumentError(str(value))
            if status == _INVALID:
                self._record_success()
                raise InvalidDocumentError(str(value))

            self._record_failure("worker_error")
            logger.warning("PDF worker raised %s", value)
            raise PDFWorkerUnavailableError(
                "PDF processing failed unexpectedly.", retry_after=10
            )

        except asyncio.CancelledError:
            if started and process is not None:
                release_slot = self._terminate(process)
            raise
        finally:
            for conn in (parent_conn, child_conn):
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
            if process is not None:
                try:
                    process.close()
                except Exception:
                    pass
            if release_slot:
                slots.release()

    def _join_worker(self, process: Any) -> bool:
        """Return True only when the child is confirmed terminated."""
        try:
            process.join(timeout=self.terminate_grace_seconds)
        except Exception:
            return False
        if process.is_alive():
            return self._terminate(process)
        return True

    def _terminate(self, process: Any) -> bool:
        """Terminate then kill the child. Return True when death is confirmed.

        ``False`` means the slot must not be reused: the process may still be
        alive, so releasing the slot would allow unbounded orphan processes.
        """
        try:
            if process.is_alive():
                process.terminate()
                process.join(timeout=self.terminate_grace_seconds)
            if process.is_alive() and hasattr(process, "kill"):
                process.kill()
                process.join(timeout=self.terminate_grace_seconds)
            return not process.is_alive()
        except Exception:
            return False


_default_processor: IsolatedPDFProcessor | None = None


def get_pdf_processor() -> IsolatedPDFProcessor:
    global _default_processor
    if _default_processor is None:
        _default_processor = IsolatedPDFProcessor()
    return _default_processor


def reset_pdf_processor() -> None:
    global _default_processor
    _default_processor = None


async def extract_pdf_text_isolated(
    source: bytes | str | os.PathLike[str] | BinaryIO,
) -> str:
    """Extract PDF text, isolated by default and with a safe in-process fallback."""
    if not settings.PDF_ISOLATION_ENABLED:
        return await asyncio.to_thread(PDFTextExtractor.extract, source)
    return await get_pdf_processor().extract(source)
