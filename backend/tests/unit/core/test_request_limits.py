import asyncio
import json

import pytest

from app.core.config import settings
from app.core.request_limits import (
    RequestBodyLimitMiddleware,
    UploadConcurrencyGuard,
    release_upload_permit,
)

API = settings.API_V1_STR
UPLOAD_PATH = f"{API}/ai/parse-resume"


def _scope(
    *,
    method: str = "POST",
    path: str = "/api/v1/jobs",
    content_length: int | None = None,
    state: dict | None = None,
) -> dict:
    headers = [(b"host", b"testserver")]
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode()))
    return {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
        "state": state or {},
    }


def _messages(*chunks: bytes) -> list[dict]:
    return [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]


async def _run(middleware, scope, messages, *, stall_after: bool = False):
    sent: list[dict] = []
    queue = list(messages)

    async def receive():
        if queue:
            return queue.pop(0)
        if stall_after:
            await asyncio.Event().wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    await middleware(scope, receive, send)
    return sent


def _status(sent: list[dict]) -> int:
    starts = [message for message in sent if message["type"] == "http.response.start"]
    assert starts, sent
    return starts[0]["status"]


def _body(sent: list[dict]) -> dict:
    payload = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    return json.loads(payload.decode())


def _capture_app(calls: list, *, release: bool = False, status: int = 200):
    async def app(scope, receive, send):
        calls.append(scope)
        if release:
            release_upload_permit(scope)
        body = b""
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            body += message.get("body", b"") or b""
            if not message.get("more_body", False):
                break
        response = json.dumps({"body_length": len(body)}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": response})

    return app


@pytest.fixture
def limits(monkeypatch):
    monkeypatch.setattr(settings, "MAX_REQUEST_BODY_BYTES", 10)
    monkeypatch.setattr(settings, "MAX_RESUME_REQUEST_BYTES", 20)
    monkeypatch.setattr(settings, "UPLOAD_TOTAL_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(settings, "UPLOAD_CHUNK_TIMEOUT_SECONDS", 0.05)
    return settings


@pytest.mark.asyncio
async def test_content_length_over_general_limit_is_rejected(limits):
    calls: list = []
    middleware = RequestBodyLimitMiddleware(_capture_app(calls))
    sent = await _run(
        middleware,
        _scope(path="/api/v1/jobs", content_length=11),
        _messages(b"x" * 11),
    )
    assert _status(sent) == 413
    assert calls == []


@pytest.mark.asyncio
async def test_upload_route_uses_larger_limit_than_general(limits):
    calls: list = []
    middleware = RequestBodyLimitMiddleware(_capture_app(calls))
    sent = await _run(
        middleware,
        _scope(path=UPLOAD_PATH, content_length=15),
        _messages(b"x" * 15),
    )
    assert _status(sent) == 200
    assert _body(sent)["body_length"] == 15
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_upload_route_still_enforces_its_own_limit(limits):
    calls: list = []
    middleware = RequestBodyLimitMiddleware(_capture_app(calls))
    sent = await _run(
        middleware,
        _scope(path=UPLOAD_PATH),
        _messages(b"x" * 21),
    )
    assert _status(sent) == 413


@pytest.mark.asyncio
async def test_upload_route_trailing_slash_uses_upload_limit(limits):
    calls: list = []
    middleware = RequestBodyLimitMiddleware(_capture_app(calls))
    sent = await _run(
        middleware,
        _scope(path=f"{UPLOAD_PATH}/", content_length=15),
        _messages(b"x" * 15),
    )
    assert _status(sent) == 200
    assert _body(sent)["body_length"] == 15
    assert len(calls) == 1
    assert "upload_permit" in calls[0]["state"]


@pytest.mark.asyncio
async def test_upload_route_trailing_slash_enforces_upload_limit(limits):
    calls: list = []
    middleware = RequestBodyLimitMiddleware(_capture_app(calls))
    sent = await _run(
        middleware,
        _scope(path=f"{UPLOAD_PATH}/"),
        _messages(b"x" * 21),
    )
    assert _status(sent) == 413


@pytest.mark.asyncio
async def test_upload_route_wrong_method_uses_general_limit(limits):
    calls: list = []
    middleware = RequestBodyLimitMiddleware(_capture_app(calls))
    sent = await _run(
        middleware,
        _scope(method="PUT", path=UPLOAD_PATH, content_length=15),
        _messages(b"x" * 15),
    )
    assert _status(sent) == 413
    assert calls == []

    allowed: list = []
    middleware = RequestBodyLimitMiddleware(_capture_app(allowed))
    sent = await _run(
        middleware,
        _scope(method="PUT", path=f"{UPLOAD_PATH}/", content_length=5),
        _messages(b"x" * 5),
    )
    assert _status(sent) == 200
    assert "upload_permit" not in allowed[0]["state"]


@pytest.mark.asyncio
async def test_large_valid_upload_body_is_accepted(limits, monkeypatch):
    monkeypatch.setattr(settings, "MAX_RESUME_REQUEST_BYTES", 5 * 1024 * 1024)
    payload = b"%PDF-1.7\n" + b"x" * (2 * 1024 * 1024)
    calls: list = []
    middleware = RequestBodyLimitMiddleware(_capture_app(calls))
    sent = await _run(
        middleware,
        _scope(path=UPLOAD_PATH, content_length=len(payload)),
        _messages(payload),
    )
    assert _status(sent) == 200
    assert _body(sent)["body_length"] == len(payload)


@pytest.mark.asyncio
async def test_streamed_body_without_content_length_is_counted(limits):
    calls: list = []
    middleware = RequestBodyLimitMiddleware(_capture_app(calls))
    sent = await _run(
        middleware,
        _scope(path="/api/v1/jobs"),
        _messages(b"12345", b"67890", b"x"),
    )
    assert _status(sent) == 413


@pytest.mark.asyncio
async def test_invalid_content_length_is_rejected(limits):
    calls: list = []
    middleware = RequestBodyLimitMiddleware(_capture_app(calls))
    scope = _scope(path="/api/v1/jobs")
    scope["headers"].append((b"content-length", b"not-a-number"))
    sent = await _run(middleware, scope, _messages(b"x"))
    assert _status(sent) == 400
    assert calls == []


@pytest.mark.asyncio
async def test_stalled_upload_deadline_returns_408(limits, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_CHUNK_TIMEOUT_SECONDS", 0.01)
    calls: list = []
    middleware = RequestBodyLimitMiddleware(_capture_app(calls))
    sent = await _run(
        middleware,
        _scope(path=UPLOAD_PATH),
        [],
        stall_after=True,
    )
    assert _status(sent) == 408
    assert sent[0]["headers"] and (b"connection", b"close") in sent[0]["headers"]


@pytest.mark.asyncio
async def test_queue_full_returns_503_with_retry_after(limits):
    guard = UploadConcurrencyGuard(max_active=1, max_waiting=0, queue_timeout=0.05)
    held = await guard.acquire()
    assert held is not None
    calls: list = []
    middleware = RequestBodyLimitMiddleware(_capture_app(calls), guard=guard)
    sent = await _run(
        middleware,
        _scope(path=UPLOAD_PATH),
        _messages(b"x"),
    )
    assert _status(sent) == 503
    assert (b"retry-after", b"5") in sent[0]["headers"]
    assert calls == []
    held.release()


@pytest.mark.asyncio
async def test_queue_wait_timeout_returns_503(limits):
    guard = UploadConcurrencyGuard(
        max_active=1, max_waiting=1, queue_timeout=0.01
    )
    held = await guard.acquire()
    assert held is not None
    middleware = RequestBodyLimitMiddleware(_capture_app([]), guard=guard)
    sent = await _run(
        middleware,
        _scope(path=UPLOAD_PATH),
        _messages(b"x"),
    )
    assert _status(sent) == 503
    held.release()


@pytest.mark.asyncio
async def test_permit_is_released_once_and_freed_for_next_upload(limits):
    guard = UploadConcurrencyGuard(max_active=1, max_waiting=1, queue_timeout=0.2)
    calls: list = []
    middleware = RequestBodyLimitMiddleware(
        _capture_app(calls, release=True), guard=guard
    )
    scope = _scope(path=UPLOAD_PATH)
    sent = await _run(middleware, scope, _messages(b"hello"))
    assert _status(sent) == 200
    permit = scope["state"]["upload_permit"]
    assert permit.released is True
    assert permit.release() is False

    second = await _run(
        middleware, _scope(path=UPLOAD_PATH), _messages(b"again")
    )
    assert _status(second) == 200


@pytest.mark.asyncio
async def test_middleware_releases_permit_on_app_error(limits):
    guard = UploadConcurrencyGuard(max_active=1, max_waiting=0, queue_timeout=0.05)

    async def failing_app(scope, receive, send):
        await receive()
        raise RuntimeError("boom")

    middleware = RequestBodyLimitMiddleware(failing_app, guard=guard)
    scope = _scope(path=UPLOAD_PATH)
    async def receive():
        return {"type": "http.request", "body": b"x", "more_body": False}

    with pytest.raises(RuntimeError):
        await middleware(scope, receive, _noop_send)
    assert scope["state"]["upload_permit"].released is True

    # The only slot must be available again.
    assert await guard.acquire() is not None


async def _noop_send(message):
    return None


@pytest.mark.asyncio
async def test_upload_permit_is_not_created_for_other_routes(limits):
    guard = UploadConcurrencyGuard(max_active=1, max_waiting=0, queue_timeout=0.05)
    middleware = RequestBodyLimitMiddleware(_capture_app([]), guard=guard)
    scope = _scope(path="/api/v1/jobs")
    await _run(middleware, scope, _messages(b"x"))
    assert "upload_permit" not in scope["state"]


@pytest.mark.asyncio
async def test_get_requests_are_not_body_limited(limits):
    calls: list = []
    middleware = RequestBodyLimitMiddleware(_capture_app(calls))
    sent = await _run(
        middleware,
        _scope(method="GET", path="/api/v1/jobs", content_length=9999),
        _messages(b""),
    )
    assert _status(sent) == 200
    assert len(calls) == 1
