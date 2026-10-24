from __future__ import annotations

import asyncio
import logging
import re
import uuid

import httpx
import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse

from app.core.correlation import (
    CORRELATION_ID_HEADER,
    CorrelationIdMiddleware,
    _install_log_record_factory,
    apply_security_headers,
    bind_correlation_id,
    get_correlation_id,
    handle_unhandled_exception,
    is_valid_request_id,
    resolve_request_id,
)
from starlette.datastructures import MutableHeaders

ALLOWED_ORIGIN = "http://localhost:5173"
DISALLOWED_ORIGIN = "http://disallowed.test"


def _build_app() -> FastAPI:
    app = FastAPI(
        exception_handlers={Exception: handle_unhandled_exception}
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[ALLOWED_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[CORRELATION_ID_HEADER],
    )
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/echo")
    async def echo():
        return {"correlation_id": get_correlation_id()}

    @app.get("/log")
    async def log():
        logging.getLogger("tests.correlation.route").info("route log")
        return {"ok": True}

    @app.get("/slow")
    async def slow(delay: float):
        request_id = get_correlation_id()
        await asyncio.sleep(delay)
        return {"correlation_id": request_id}

    @app.get("/stream")
    async def stream():
        async def chunks():
            yield b"first"
            await asyncio.sleep(0)
            yield b"second"

        return StreamingResponse(chunks(), media_type="text/plain")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("secret-token must not leak")

    return app


def _client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_valid_caller_request_id_is_preserved():
    client = _client(_build_app())
    response = client.get(
        "/echo", headers={CORRELATION_ID_HEADER: "client-request_123"}
    )

    assert response.status_code == 200
    assert response.headers[CORRELATION_ID_HEADER] == "client-request_123"
    assert response.json()["correlation_id"] == "client-request_123"


@pytest.mark.parametrize(
    "value",
    ["short", "has space", "x" * 65, "semi;colon", ""],
)
def test_invalid_caller_request_id_is_replaced(value):
    client = _client(_build_app())
    response = client.get("/echo", headers={CORRELATION_ID_HEADER: value})

    request_id = response.headers[CORRELATION_ID_HEADER]
    assert request_id != value
    assert is_valid_request_id(request_id)
    assert uuid.UUID(request_id)


def test_missing_request_id_is_generated():
    client = _client(_build_app())
    response = client.get("/echo")

    request_id = response.headers[CORRELATION_ID_HEADER]
    assert is_valid_request_id(request_id)
    assert response.json()["correlation_id"] == request_id


def test_context_is_reset_after_request_and_after_binding_error():
    assert get_correlation_id() is None
    _client(_build_app()).get("/echo")
    assert get_correlation_id() is None

    with pytest.raises(RuntimeError):
        with bind_correlation_id("bound-request-1"):
            assert get_correlation_id() == "bound-request-1"
            raise RuntimeError("stop")

    assert get_correlation_id() is None


@pytest.mark.asyncio
async def test_concurrent_requests_do_not_share_context():
    app = _build_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        slow, fast = await asyncio.gather(
            client.get(
                "/slow",
                params={"delay": "0.02"},
                headers={CORRELATION_ID_HEADER: "slow-request-1"},
            ),
            client.get(
                "/slow",
                params={"delay": "0.01"},
                headers={CORRELATION_ID_HEADER: "fast-request-2"},
            ),
        )

    assert slow.json()["correlation_id"] == "slow-request-1"
    assert fast.json()["correlation_id"] == "fast-request-2"


def test_handled_error_response_has_id():
    client = _client(_build_app())
    response = client.get(
        "/missing", headers={CORRELATION_ID_HEADER: "missing-request-1"}
    )

    assert response.status_code == 404
    assert response.headers[CORRELATION_ID_HEADER] == "missing-request-1"


def test_streaming_response_has_id_and_body_is_not_buffered():
    client = _client(_build_app())
    response = client.get(
        "/stream", headers={CORRELATION_ID_HEADER: "stream-request-1"}
    )

    assert response.status_code == 200
    assert response.headers[CORRELATION_ID_HEADER] == "stream-request-1"
    assert response.text == "firstsecond"


def test_unhandled_error_is_sanitized_and_has_headers():
    client = _client(_build_app())
    response = client.get(
        "/boom", headers={CORRELATION_ID_HEADER: "error-request-1"}
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
    assert "secret-token" not in response.text
    assert response.headers[CORRELATION_ID_HEADER] == "error-request-1"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]


def test_unhandled_error_log_includes_correlation_id(caplog):
    client = _client(_build_app())

    with caplog.at_level(logging.ERROR, logger="app.correlation"):
        client.get(
            "/boom", headers={CORRELATION_ID_HEADER: "error-request-log"}
        )

    records = [
        record
        for record in caplog.records
        if record.name == "app.correlation"
        and record.getMessage().startswith("Unhandled server error")
    ]
    assert len(records) == 1
    assert records[0].correlation_id == "error-request-log"


def test_unhandled_error_reflects_allowed_cors_origin():
    client = _client(_build_app())
    response = client.get(
        "/boom",
        headers={
            CORRELATION_ID_HEADER: "error-request-2",
            "Origin": ALLOWED_ORIGIN,
        },
    )

    assert response.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert (
        response.headers["Access-Control-Expose-Headers"]
        == CORRELATION_ID_HEADER
    )
    assert "origin" in response.headers["Vary"].lower()


def test_unhandled_error_does_not_add_cors_for_disallowed_origin():
    client = _client(_build_app())
    response = client.get(
        "/boom", headers={"Origin": DISALLOWED_ORIGIN}
    )

    assert "Access-Control-Allow-Origin" not in response.headers
    assert "Access-Control-Allow-Credentials" not in response.headers


def test_log_records_include_correlation_id(caplog):
    client = _client(_build_app())

    with caplog.at_level(logging.INFO):
        client.get(
            "/log", headers={CORRELATION_ID_HEADER: "log-request-123"}
        )

    records = [
        record
        for record in caplog.records
        if record.name == "tests.correlation.route"
    ]
    assert records
    assert records[-1].correlation_id == "log-request-123"


def test_log_factory_is_chained_and_idempotent():
    original = logging.getLogRecordFactory()

    def custom_factory(*args, **kwargs):
        record = original(*args, **kwargs)
        record.custom_marker = "kept"
        return record

    logging.setLogRecordFactory(custom_factory)
    try:
        _install_log_record_factory()
        first = logging.getLogRecordFactory()
        _install_log_record_factory()
        second = logging.getLogRecordFactory()

        assert first is second
        with bind_correlation_id("factory-request-1"):
            record = logging.getLogger("factory.test").makeRecord(
                "factory.test",
                logging.INFO,
                __file__,
                1,
                "message",
                (),
                None,
            )
        assert record.custom_marker == "kept"
        assert record.correlation_id == "factory-request-1"
    finally:
        logging.setLogRecordFactory(original)


def test_security_header_helper_excludes_csp_for_docs():
    headers = MutableHeaders()
    apply_security_headers(headers, "/docs/oauth2-redirect")

    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" not in headers


def test_resolve_request_id_only_accepts_bounded_identifier():
    assert resolve_request_id("valid_id-123") == "valid_id-123"
    generated = resolve_request_id("not valid")
    assert re.fullmatch(r"[a-f0-9-]{36}", generated)
