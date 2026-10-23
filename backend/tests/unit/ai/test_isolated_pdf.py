from __future__ import annotations

import asyncio
import threading

import pytest

from app.ai.extractors.isolated_pdf import (
    IsolatedPDFProcessor,
    _read_source_bytes,
)
from app.ai.extractors.pdf_extractor import PDF_MAGIC_HEADER
from app.core.exceptions import (
    EmptyDocumentError,
    InvalidDocumentError,
    PDFWorkerUnavailableError,
)

VALID_PDF_BYTES = PDF_MAGIC_HEADER + b"-1.7\n%Fake PDF content\n"


class FakeConnection:
    def __init__(self, *, payload=None, error=None, blocker=None) -> None:
        self.payload = payload
        self.error = error
        self.blocker = blocker
        self.closed = False

    def recv(self):
        if self.blocker is not None:
            self.blocker.wait(timeout=2)
        if self.error is not None:
            raise self.error
        return self.payload

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(
        self,
        target,
        args,
        *,
        exits: bool = True,
        exitcode: int = 0,
        terminable: bool = True,
    ) -> None:
        self.target = target
        self.args = args
        self.alive = False
        self.exitcode = None
        self.started = False
        self.closed = False
        self.terminated = 0
        self.killed = 0
        self._exits = exits
        self._exitcode = exitcode
        self._terminable = terminable

    def start(self):
        self.started = True
        self.alive = not self._exits
        if self._exits:
            self.exitcode = self._exitcode

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        if self.alive and self._terminable:
            self.alive = False
            self.exitcode = -15
        return None

    def terminate(self):
        self.terminated += 1
        if self._terminable:
            self.alive = False
            self.exitcode = -15

    def kill(self):
        self.killed += 1
        if self._terminable:
            self.alive = False
            self.exitcode = -9

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, parent: FakeConnection, process: FakeProcess) -> None:
        self.parent = parent
        self.child = FakeConnection()
        self.process = process
        self.pipe_calls = 0
        self.process_calls = 0

    def Pipe(self, duplex=True):
        self.pipe_calls += 1
        return self.parent, self.child

    def Process(self, target, args, daemon=True):
        self.process_calls += 1
        assert target is not None
        assert daemon is True
        return self.process


def _processor(context, **overrides):
    return IsolatedPDFProcessor(
        context_factory=lambda: context,
        timeout_seconds=overrides.pop("timeout_seconds", 0.2),
        terminate_grace_seconds=overrides.pop("terminate_grace_seconds", 0.05),
        **overrides,
    )


@pytest.mark.asyncio
async def test_successful_child_result_is_returned():
    parent = FakeConnection(payload=("ok", "Extracted text"))
    process = FakeProcess(None, None, exits=True, exitcode=0)
    context = FakeContext(parent, process)
    result = await _processor(context).extract(VALID_PDF_BYTES)
    assert result == "Extracted text"
    assert process.started is True
    assert process.closed is True
    assert parent.closed is True
    assert context.child.closed is True


@pytest.mark.asyncio
async def test_worker_startup_runs_real_spawned_process():
    processor = IsolatedPDFProcessor(timeout_seconds=30, max_concurrency=1)
    with pytest.raises((InvalidDocumentError, EmptyDocumentError, PDFWorkerUnavailableError)):
        await processor.extract(VALID_PDF_BYTES)


@pytest.mark.asyncio
async def test_empty_and_invalid_child_results_map_to_domain_errors():
    for payload, error_type in (
        (("empty", "no text"), EmptyDocumentError),
        (("invalid", "bad pdf"), InvalidDocumentError),
    ):
        context = FakeContext(
            FakeConnection(payload=payload),
            FakeProcess(None, None, exits=True),
        )
        with pytest.raises(error_type):
            await _processor(context).extract(VALID_PDF_BYTES)


@pytest.mark.asyncio
async def test_malformed_payload_is_rejected():
    context = FakeContext(
        FakeConnection(payload=("ok",)),
        FakeProcess(None, None, exits=True),
    )
    with pytest.raises(PDFWorkerUnavailableError):
        await _processor(context).extract(VALID_PDF_BYTES)


@pytest.mark.asyncio
async def test_nonzero_exit_invalidates_result_even_with_payload():
    context = FakeContext(
        FakeConnection(payload=("ok", "untrusted")),
        FakeProcess(None, None, exits=True, exitcode=1),
    )
    with pytest.raises(PDFWorkerUnavailableError):
        await _processor(context).extract(VALID_PDF_BYTES)


@pytest.mark.asyncio
async def test_timeout_terminates_child_and_releases_slot():
    blocker = threading.Event()
    parent = FakeConnection(blocker=blocker)
    process = FakeProcess(None, None, exits=False)
    context = FakeContext(parent, process)
    processor = _processor(context, timeout_seconds=0.05, max_concurrency=1)
    try:
        with pytest.raises(PDFWorkerUnavailableError):
            await processor.extract(VALID_PDF_BYTES)
        assert process.terminated >= 1
        assert processor._slots.get()._value == 1
    finally:
        blocker.set()


@pytest.mark.asyncio
async def test_child_crash_is_contained_and_slot_released():
    process = FakeProcess(None, None, exits=False)
    context = FakeContext(FakeConnection(error=EOFError()), process)
    processor = _processor(context, max_concurrency=1)
    with pytest.raises(PDFWorkerUnavailableError):
        await processor.extract(VALID_PDF_BYTES)
    assert process.terminated >= 1
    assert processor._slots.get()._value == 1


@pytest.mark.asyncio
async def test_unconfirmed_termination_does_not_release_slot():
    process = FakeProcess(None, None, exits=False, terminable=False)
    context = FakeContext(FakeConnection(error=EOFError()), process)
    processor = _processor(context, max_concurrency=1)
    with pytest.raises(PDFWorkerUnavailableError):
        await processor.extract(VALID_PDF_BYTES)
    assert process.alive is True
    assert processor._slots.get()._value == 0


@pytest.mark.asyncio
async def test_cancellation_kills_child_and_releases_slot():
    blocker = threading.Event()
    process = FakeProcess(None, None, exits=False)
    context = FakeContext(FakeConnection(blocker=blocker), process)
    processor = _processor(context, max_concurrency=1)

    task = asyncio.create_task(processor.extract(VALID_PDF_BYTES))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        blocker.set()
    assert process.terminated >= 1
    assert processor._slots.get()._value == 1


@pytest.mark.asyncio
async def test_setup_failure_releases_slot_and_maps_to_503():
    class BrokenContext(FakeContext):
        def Pipe(self, duplex=True):
            raise OSError("cannot create pipe")

    context = BrokenContext(FakeConnection(), FakeProcess(None, None))
    processor = _processor(context, max_concurrency=1)
    with pytest.raises(PDFWorkerUnavailableError):
        await processor.extract(VALID_PDF_BYTES)
    assert context.process_calls == 0
    assert processor._slots.get()._value == 1


@pytest.mark.asyncio
async def test_start_failure_releases_slot():
    class FailingProcess(FakeProcess):
        def start(self):
            raise OSError("cannot spawn")

    context = FakeContext(FakeConnection(), FailingProcess(None, None))
    processor = _processor(context, max_concurrency=1)
    with pytest.raises(PDFWorkerUnavailableError):
        await processor.extract(VALID_PDF_BYTES)
    assert processor._slots.get()._value == 1


@pytest.mark.asyncio
async def test_quarantine_short_circuits_after_repeated_failures():
    blocker = threading.Event()
    context = FakeContext(
        FakeConnection(error=EOFError()), FakeProcess(None, None, exits=False)
    )
    processor = _processor(
        context,
        max_concurrency=1,
        max_consecutive_failures=1,
        quarantine_seconds=30,
    )
    with pytest.raises(PDFWorkerUnavailableError):
        await processor.extract(VALID_PDF_BYTES)
    calls = context.process_calls

    with pytest.raises(PDFWorkerUnavailableError) as excinfo:
        await processor.extract(VALID_PDF_BYTES)
    assert "degraded" in str(excinfo.value).lower()
    assert excinfo.value.retry_after is not None
    assert context.process_calls == calls
    blocker.set()

    processor.reset_health()
    with pytest.raises(PDFWorkerUnavailableError):
        await processor.extract(VALID_PDF_BYTES)
    assert context.process_calls == calls + 1


def test_read_source_bytes_rejects_oversized_input():
    from app.ai.extractors.pdf_extractor import MAX_FILE_SIZE_BYTES

    with pytest.raises(InvalidDocumentError):
        _read_source_bytes(PDF_MAGIC_HEADER + b"x" * MAX_FILE_SIZE_BYTES)


def test_read_source_bytes_restores_stream_position():
    import io

    stream = io.BytesIO(VALID_PDF_BYTES)
    stream.seek(5)
    data = _read_source_bytes(stream)
    assert data == VALID_PDF_BYTES[5:]
    assert stream.tell() == 5


def test_timeout_duration_is_bounded_by_settings():
    processor = IsolatedPDFProcessor(timeout_seconds=0.01)
    assert processor.timeout_seconds == 0.01
    assert processor.terminate_grace_seconds >= 0.05
