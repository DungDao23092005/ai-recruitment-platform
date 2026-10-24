"""Request correlation IDs and shared response-header policy.

The correlation ID is accepted from a strictly validated ``X-Request-ID``
header or generated with UUID4. It lives in both the ASGI request state and a
context variable so route handlers and library loggers can see it without
threading it through every call signature.
"""

from __future__ import annotations

import logging
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

from fastapi import Request, Response
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

CORRELATION_ID_HEADER = "X-Request-ID"
REQUEST_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")

correlation_id_var: ContextVar[str | None] = ContextVar(
    "correlation_id", default=None
)

logger = logging.getLogger("app.correlation")


def get_correlation_id() -> str | None:
    """Return the current request correlation ID, if any."""
    return correlation_id_var.get()


def is_valid_request_id(value: object) -> bool:
    return isinstance(value, str) and REQUEST_ID_PATTERN.fullmatch(value) is not None


def resolve_request_id(value: object) -> str:
    """Keep a valid caller value; otherwise generate a fresh UUID4."""
    return value if is_valid_request_id(value) else str(uuid.uuid4())


@contextmanager
def bind_correlation_id(request_id: str) -> Iterator[None]:
    """Temporarily bind a correlation ID for logging and restore it after."""
    token: Token[str | None] = correlation_id_var.set(request_id)
    try:
        yield
    finally:
        correlation_id_var.reset(token)


def _install_log_record_factory() -> None:
    """Add ``correlation_id`` to every record exactly once.

    The previous factory is always called first, so application- or
    test-supplied record shapes keep working. Re-importing the module or
    calling this function repeatedly does not wrap the factory twice.
    """
    factory = logging.getLogRecordFactory()
    if getattr(factory, "_correlation_id_factory", False):
        return

    previous_factory = factory

    def correlated_factory(*args, **kwargs):
        record = previous_factory(*args, **kwargs)
        if not getattr(record, "correlation_id", None):
            record.correlation_id = correlation_id_var.get() or "-"
        return record

    correlated_factory._correlation_id_factory = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(correlated_factory)


_install_log_record_factory()


def apply_security_headers(headers: MutableHeaders, path: str) -> None:
    """Apply the single shared security-header policy to a response."""
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "DENY")
    headers.setdefault(
        "Referrer-Policy", "strict-origin-when-cross-origin"
    )
    if not path.startswith(("/docs", "/redoc")):
        headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'",
        )


def apply_cors_headers(
    headers: MutableHeaders,
    origin: str | None,
    *,
    allow_origins: list[str],
    allow_credentials: bool,
) -> None:
    """Apply the same simple-response CORS policy for generated responses.

    Unhandled exceptions are rendered by Starlette's outermost error middleware,
    outside ``CORSMiddleware``. Only reflected origins are emitted, and
    ``Vary: Origin`` is added whenever the response depends on the request
    origin.
    """
    if not origin:
        return

    allow_all_origins = "*" in allow_origins
    if not allow_all_origins and origin not in allow_origins:
        return

    if allow_all_origins and not allow_credentials:
        headers["Access-Control-Allow-Origin"] = "*"
    else:
        headers["Access-Control-Allow-Origin"] = origin
        headers.add_vary_header("Origin")

    if allow_credentials:
        headers["Access-Control-Allow-Credentials"] = "true"
    headers["Access-Control-Expose-Headers"] = CORRELATION_ID_HEADER


class CorrelationIdMiddleware:
    """Pure ASGI middleware that scopes and returns a request correlation ID.

    A pure ASGI implementation avoids buffering streaming responses and avoids
    holding a BaseHTTPMiddleware task group open while a stream completes.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = resolve_request_id(
            Headers(scope=scope).get(CORRELATION_ID_HEADER)
        )
        scope.setdefault("state", {})["correlation_id"] = request_id
        token = correlation_id_var.set(request_id)

        async def send_with_correlation_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers[CORRELATION_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation_id)
        finally:
            correlation_id_var.reset(token)


async def handle_unhandled_exception(
    request: Request, exc: Exception
) -> Response:
    """Render a sanitized 500 outside the inner middleware stack."""
    request_id = (
        getattr(request.state, "correlation_id", None)
        or get_correlation_id()
        or str(uuid.uuid4())
    )
    with bind_correlation_id(request_id):
        logger.error(
            "Unhandled server error type=%s",
            type(exc).__name__,
            exc_info=(type(exc), exc, exc.__traceback__),
        )

    response = JSONResponse(
        {"detail": "Internal Server Error"}, status_code=500
    )
    response.headers[CORRELATION_ID_HEADER] = request_id
    apply_security_headers(response.headers, request.url.path)
    apply_cors_headers(
        response.headers,
        request.headers.get("origin"),
        allow_origins=[
            str(origin) for origin in settings.BACKEND_CORS_ORIGINS
        ],
        allow_credentials=True,
    )
    return response
