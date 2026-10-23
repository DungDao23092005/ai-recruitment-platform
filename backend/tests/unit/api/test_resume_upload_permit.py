from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

from app.api.v1.endpoints import ai as ai_endpoint
from app.ai.extractors.pdf_extractor import PDF_MAGIC_HEADER
from app.core.exceptions import PDFWorkerUnavailableError
from app.core.request_limits import UploadConcurrencyGuard

VALID_PDF = PDF_MAGIC_HEADER + b"-1.7\n%test"


class AwaitableValue:
    def __init__(self, value) -> None:
        self.value = value

    def __await__(self):
        async def resolve():
            return self.value

        return resolve().__await__()


class FakeUser:
    def __init__(self) -> None:
        profile = SimpleNamespace(id=uuid.uuid4())
        self.awaitable_attrs = SimpleNamespace(
            candidate_profile=AwaitableValue(profile)
        )


class FakeService:
    def __init__(self, *, permit=None, error: Exception | None = None) -> None:
        self.permit = permit
        self.error = error
        self.called = False
        self.permit_released_at_call = None

    async def parse_and_save_resume_draft(
        self, *, candidate_id, pdf_source, session, source_name
    ):
        self.called = True
        if self.permit is not None:
            self.permit_released_at_call = self.permit.released
        if self.error is not None:
            raise self.error
        now = datetime.now(timezone.utc)
        return SimpleNamespace(
            id=uuid.uuid4(),
            candidate_id=candidate_id,
            title=None,
            is_primary=False,
            is_confirmed=False,
            confirmed_at=None,
            parsed_data=None,
            created_at=now,
            updated_at=now,
        )


def _upload() -> UploadFile:
    return UploadFile(file=io.BytesIO(VALID_PDF), filename="cv.pdf")


def _request_with_permit(permit):
    return SimpleNamespace(scope={"state": {"upload_permit": permit}})


async def _acquire():
    guard = UploadConcurrencyGuard(
        max_active=1, max_waiting=1, queue_timeout=0.1
    )
    permit = await guard.acquire()
    assert permit is not None
    return guard, permit


@pytest.mark.asyncio
async def test_permit_is_released_before_ai_work():
    guard, permit = await _acquire()
    service = FakeService(permit=permit)

    result = await ai_endpoint.parse_resume(
        file=_upload(),
        request=_request_with_permit(permit),
        current_user=FakeUser(),
        db=SimpleNamespace(),
        service=service,
        _=SimpleNamespace(),
    )

    assert result.id is not None
    assert service.called is True
    assert service.permit_released_at_call is True
    assert permit.released is True
    assert permit.release() is False
    assert guard._state().semaphore._value == 1


@pytest.mark.asyncio
async def test_worker_unavailable_maps_to_503_with_retry_after():
    _, permit = await _acquire()
    service = FakeService(
        permit=permit,
        error=PDFWorkerUnavailableError("worker down", retry_after=7),
    )

    with pytest.raises(HTTPException) as excinfo:
        await ai_endpoint.parse_resume(
            file=_upload(),
            request=_request_with_permit(permit),
            current_user=FakeUser(),
            db=SimpleNamespace(),
            service=service,
            _=SimpleNamespace(),
        )

    assert excinfo.value.status_code == 503
    assert excinfo.value.headers["Retry-After"] == "7"
    assert permit.released is True
