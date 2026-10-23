"""Route-aware request-body limits and bounded CV-upload concurrency.

This is a pure ASGI middleware. It enforces the limit both from
``Content-Length`` (cheap rejection before the app runs) and while the body is
streamed, so a client that omits ``Content-Length`` cannot bypass it. Body
delivery is also bounded by a per-chunk and an overall deadline.

The CV upload route additionally acquires a bounded "upload permit". The permit
is held while Starlette parses and spools the multipart body and is released by
the endpoint as soon as the file has been read, i.e. before any AI work starts.
The middleware releases it idempotently as a fallback for every error path.
"""

from __future__ import annotations

import asyncio
import weakref
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, MutableMapping

from starlette.responses import JSONResponse

from app.core.config import settings

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

UPLOAD_PATH = f"{settings.API_V1_STR}/ai/parse-resume"
UPLOAD_METHOD = "POST"
BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
NON_UPLOAD_TOTAL_TIMEOUT_SECONDS = 30.0


def _normalize_path(path: str) -> str:
    """Collapse trailing slashes so ``/route`` and ``/route/`` compare equal.

    Starlette redirects the trailing-slash variant to the canonical route
    (307). Treating both as the upload route keeps the 11 MiB limit and the
    upload permit in effect during that redirect, so an oversized body can
    never slip through under the general 1 MiB limit.
    """
    normalized = path.rstrip("/")
    return normalized or "/"


def is_upload_request(method: str, path: str) -> bool:
    return (
        method.upper() == UPLOAD_METHOD
        and _normalize_path(path) == UPLOAD_PATH
    )


class _BodyLimitRejection(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


@dataclass
class _LoopUploadState:
    semaphore: asyncio.Semaphore
    waiting: int = 0


class UploadConcurrencyGuard:
    """Bound active and waiting CV uploads per event loop.

    State is kept per event loop because an ``asyncio.Semaphore`` must only be
    awaited from the loop that created it. Tests (and, in theory, embedded
    servers) can therefore create more than one loop safely.
    """

    def __init__(self, max_active: int, max_waiting: int, queue_timeout: float) -> None:
        self.max_active = max(1, int(max_active))
        self.max_waiting = max(0, int(max_waiting))
        self.queue_timeout = max(0.0, float(queue_timeout))
        self._states: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _LoopUploadState]" = (
            weakref.WeakKeyDictionary()
        )

    def _state(self) -> _LoopUploadState:
        loop = asyncio.get_running_loop()
        state = self._states.get(loop)
        if state is None:
            state = _LoopUploadState(
                semaphore=asyncio.Semaphore(self.max_active)
            )
            self._states[loop] = state
        return state

    async def acquire(self) -> "UploadPermit | None":
        state = self._state()
        # ``max_waiting`` caps the queue behind busy slots. A free slot must
        # always be acquirable, including when waiting is configured as zero.
        if state.semaphore.locked() and state.waiting >= self.max_waiting:
            return None
        state.waiting += 1
        try:
            try:
                await asyncio.wait_for(
                    state.semaphore.acquire(), timeout=self.queue_timeout
                )
            except (asyncio.TimeoutError, TimeoutError):
                return None
        finally:
            state.waiting -= 1
        return UploadPermit(state.semaphore)


@dataclass
class UploadPermit:
    """Idempotent handle to one upload slot."""

    _semaphore: asyncio.Semaphore
    _released: bool = field(default=False)

    def release(self) -> bool:
        if self._released:
            return False
        self._released = True
        self._semaphore.release()
        return True

    @property
    def released(self) -> bool:
        return self._released


def release_upload_permit(scope_or_request: Any) -> bool:
    """Release the permit attached to an ASGI scope / Starlette request."""
    scope = getattr(scope_or_request, "scope", scope_or_request)
    if not isinstance(scope, MutableMapping):
        return False
    state = scope.get("state")
    if not isinstance(state, MutableMapping):
        return False
    permit = state.get("upload_permit")
    if isinstance(permit, UploadPermit):
        return permit.release()
    return False


def _header(scope: Scope, name: bytes) -> bytes | None:
    values = [value for key, value in scope.get("headers", []) if key.lower() == name]
    return values[-1] if values else None


def _reject_response(
    status_code: int, detail: str, *, retry_after: int | None = None
) -> JSONResponse:
    headers = {"Connection": "close"}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(
        {"detail": detail}, status_code=status_code, headers=headers
    )


class RequestBodyLimitMiddleware:
    """Enforce route-aware body size and delivery deadlines."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        guard: UploadConcurrencyGuard | None = None,
    ) -> None:
        self.app = app
        self.guard = guard or UploadConcurrencyGuard(
            max_active=settings.UPLOAD_MAX_ACTIVE,
            max_waiting=settings.UPLOAD_MAX_WAITING,
            queue_timeout=settings.UPLOAD_QUEUE_TIMEOUT_SECONDS,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "")).upper()
        is_upload = is_upload_request(method, str(scope.get("path", "")))
        limit = (
            settings.MAX_RESUME_REQUEST_BYTES
            if is_upload
            else settings.MAX_REQUEST_BODY_BYTES
        )

        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        if method not in BODY_METHODS:
            await self.app(scope, receive, send_wrapper)
            return

        content_length = _header(scope, b"content-length")
        if content_length is not None:
            try:
                declared = int(content_length.strip() or b"0")
            except (TypeError, ValueError):
                await _reject_response(
                    400, "Invalid Content-Length header"
                )(scope, receive, send)
                return
            if declared < 0:
                await _reject_response(
                    400, "Invalid Content-Length header"
                )(scope, receive, send)
                return
            if declared > limit:
                await self._reject(
                    scope, receive, send, 413, self._too_large_detail(is_upload)
                )
                return

        permit: UploadPermit | None = None
        if is_upload:
            permit = await self.guard.acquire()
            if permit is None:
                await _reject_response(
                    503,
                    "Too many CV uploads in progress. Please retry shortly.",
                    retry_after=5,
                )(scope, receive, send)
                return
            scope.setdefault("state", {})
            if isinstance(scope["state"], MutableMapping):
                scope["state"]["upload_permit"] = permit

        loop = asyncio.get_running_loop()
        deadline = loop.time() + (
            settings.UPLOAD_TOTAL_TIMEOUT_SECONDS
            if is_upload
            else NON_UPLOAD_TOTAL_TIMEOUT_SECONDS
        )
        chunk_timeout = settings.UPLOAD_CHUNK_TIMEOUT_SECONDS
        received = 0
        body_done = False

        async def limited_receive() -> Message:
            nonlocal received, body_done
            if body_done:
                return await receive()

            remaining = deadline - loop.time()
            if remaining <= 0:
                raise _BodyLimitRejection(
                    408, "Request body was not delivered in time"
                )
            try:
                message = await asyncio.wait_for(
                    receive(), timeout=min(chunk_timeout, remaining)
                )
            except (asyncio.TimeoutError, TimeoutError):
                raise _BodyLimitRejection(
                    408, "Request body was not delivered in time"
                ) from None

            message_type = message.get("type")
            if message_type == "http.request":
                chunk = message.get("body", b"") or b""
                received += len(chunk)
                if received > limit:
                    raise _BodyLimitRejection(
                        413, self._too_large_detail(is_upload)
                    )
                if not message.get("more_body", False):
                    body_done = True
            elif message_type == "http.disconnect":
                body_done = True
            return message

        try:
            await self.app(scope, limited_receive, send_wrapper)
        except _BodyLimitRejection as exc:
            if not response_started:
                await self._reject(
                    scope,
                    receive,
                    send,
                    exc.status_code,
                    exc.detail,
                    retry_after=5 if exc.status_code == 503 else None,
                )
        finally:
            if permit is not None:
                permit.release()

    @staticmethod
    def _too_large_detail(is_upload: bool) -> str:
        if is_upload:
            return "Request body exceeds the maximum upload size"
        return f"Request body exceeds the maximum size of {settings.MAX_REQUEST_BODY_BYTES} bytes"

    async def _reject(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        status_code: int,
        detail: str,
        *,
        retry_after: int | None = None,
    ) -> None:
        await _reject_response(
            status_code, detail, retry_after=retry_after
        )(scope, receive, send)
