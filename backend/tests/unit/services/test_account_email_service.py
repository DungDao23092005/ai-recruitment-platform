"""Unit tests for account lifecycle emails (admin lock and deletion).

These focus on rendering, HTML escaping, payload hygiene, retry/backoff and the
durable outbox enqueue contract. Provider transports are exercised separately in
``test_email_service.py``; here ``EmailService`` is replaced with a recorder.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import account_email_service as module
from app.services.account_email_service import (
    SUBJECT_ACCOUNT_DELETED,
    SUBJECT_ACCOUNT_LOCKED,
    AccountEmailService,
)

# 2026-01-15 03:30 UTC == 10:30 15/01/2026 Asia/Ho_Chi_Minh.
LOCKED_AT = datetime(2026, 1, 15, 3, 30, tzinfo=timezone.utc)
# 2026-05-05 03:15 UTC == 10:15 05/05/2026 Asia/Ho_Chi_Minh.
DELETED_AT = datetime(2026, 5, 5, 3, 15, tzinfo=timezone.utc)


class _RecorderEmailService:
    """Minimal stand-in for EmailService that records ``send_email`` calls."""

    def __init__(self, effects: list[object] | None = None) -> None:
        self.calls: list[tuple[str, str, str, str]] = []
        self._effects = list(effects or [])

    async def send_email(
        self, to_email: str, subject: str, html: str, text: str
    ) -> None:
        self.calls.append((to_email, subject, html, text))
        if self._effects:
            effect = self._effects.pop(0)
            if isinstance(effect, Exception):
                raise effect


def _service(effects: list[object] | None = None):
    recorder = _RecorderEmailService(effects)
    return recorder, AccountEmailService(email_service=recorder)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Account lock email
# ---------------------------------------------------------------------------


async def test_lock_email_has_expected_subject_and_body():
    recorder, service = _service()

    await service.send_account_locked_email(
        to_email="user@example.com",
        reason="Vi phạm điều khoản sử dụng",
        locked_at=LOCKED_AT,
    )

    assert len(recorder.calls) == 1
    to_email, subject, html, text = recorder.calls[0]
    assert to_email == "user@example.com"
    assert subject == SUBJECT_ACCOUNT_LOCKED
    assert subject == "[AI Recruitment Platform] Thông báo khóa tài khoản"

    for body in (html, text):
        assert "Xin chào" in body
        assert "bị quản trị viên khóa" in body
        assert "Vi phạm điều khoản sử dụng" in body
        # Timestamp formatted in Vietnam local time (HH:mm DD/MM/YYYY).
        assert "10:30 15/01/2026" in body
        # Login is unavailable while locked, data is retained.
        assert "không thể đăng nhập" in body
        assert "vẫn được lưu giữ" in body
        assert "AI Recruitment Platform" in body

    # Distinct calm amber treatment vs. the deletion email.
    assert "#b45309" in html


async def test_lock_email_escapes_script_and_quotes():
    recorder, service = _service()

    await service.send_account_locked_email(
        to_email="user@example.com",
        reason='<script>alert("x")</script> "quoted" & <img src=x onerror="steal()">',
        locked_at=LOCKED_AT,
    )

    _, _, html, text = recorder.calls[0]
    assert "<script>" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img src=x" in html
    # Quotes are escaped with quote=True.
    assert "&quot;quoted&quot;" in html
    assert "&amp;" in html
    # Plain text keeps the raw reason (no HTML context).
    assert "<script>" in text


async def test_lock_email_renders_vietnam_local_time_across_date_boundary():
    recorder, service = _service()
    # 2026-06-04 17:00 UTC == 2026-06-05 00:00 Asia/Ho_Chi_Minh.
    boundary = datetime(2026, 6, 4, 17, 0, tzinfo=timezone.utc)

    await service.send_account_locked_email(
        to_email="user@example.com",
        reason="Lý do",
        locked_at=boundary,
    )

    _, _, html, text = recorder.calls[0]
    assert "00:00 05/06/2026" in html
    assert "00:00 05/06/2026" in text


async def test_lock_email_missing_reason_and_timestamp_render_safely():
    recorder, service = _service()

    await service.send_account_locked_email(
        to_email="user@example.com",
        reason=None,
        locked_at=None,
    )

    _, _, html, text = recorder.calls[0]
    assert "—" in html
    assert "Lý do: —" in text
    assert "Thời điểm khóa: —" in text


async def test_lock_email_contains_no_unconfigured_support_address():
    recorder, service = _service()

    await service.send_account_locked_email(
        to_email="user@example.com",
        reason="Lý do",
        locked_at=LOCKED_AT,
    )

    _, _, html, text = recorder.calls[0]
    combined = (html + text).lower()
    # No support mailbox is configured in the application settings, so the
    # template must not invent one.
    assert "admin@tuyendungai.me" not in combined
    assert "support@" not in combined
    assert "example.com" not in combined


# ---------------------------------------------------------------------------
# Account deletion email
# ---------------------------------------------------------------------------


async def test_delete_email_has_expected_subject_and_body():
    recorder, service = _service()

    await service.send_account_deleted_email(
        to_email="user@example.com",
        deleted_at=DELETED_AT,
    )

    assert len(recorder.calls) == 1
    to_email, subject, html, text = recorder.calls[0]
    assert to_email == "user@example.com"
    assert subject == SUBJECT_ACCOUNT_DELETED
    assert subject == "[AI Recruitment Platform] Thông báo xóa tài khoản"

    for body in (html, text):
        assert "Xin chào" in body
        assert "đã được xóa" in body
        assert "ẩn danh" in body
        # Deletion timestamp formatted in Vietnam local time.
        assert "10:15 05/05/2026" in body
        assert "không thể khôi phục" in body
        # Vector cleanup description.
        assert "vector" in body
        assert "AI Recruitment Platform" in body

    # Distinct muted dark-red treatment vs. the lock email.
    assert "#7f1d1d" in html


async def test_delete_email_missing_timestamp_renders_placeholder():
    recorder, service = _service()

    await service.send_account_deleted_email(
        to_email="user@example.com",
        deleted_at=None,
    )

    _, _, html, text = recorder.calls[0]
    assert "—" in html
    assert "Thời điểm xóa: —" in text


async def test_delete_email_contains_no_permanent_recovery_claim():
    recorder, service = _service()

    await service.send_account_deleted_email(
        to_email="user@example.com",
        deleted_at=DELETED_AT,
    )

    _, _, html, text = recorder.calls[0]
    assert "không thể" in html and "không thể" in text
    assert "deleted_" not in html and "deleted_" not in text
    assert "@anonymized.local" not in html and "@anonymized.local" not in text


# ---------------------------------------------------------------------------
# Retry / best-effort delivery
# ---------------------------------------------------------------------------


async def test_retry_succeeds_after_transient_failure():
    recorder, service = _service(effects=[RuntimeError("smtp down")])

    with patch.object(module.asyncio, "sleep", new=AsyncMock()):
        await service.send_account_locked_email(
            to_email="user@example.com",
            reason="Lý do",
            locked_at=LOCKED_AT,
        )

    assert len(recorder.calls) == 2


async def test_retry_is_bounded_and_swallows_failures():
    recorder, service = _service(
        effects=[RuntimeError("1"), RuntimeError("2"), RuntimeError("3")]
    )

    with patch.object(module.asyncio, "sleep", new=AsyncMock()):
        # Must not raise even though every attempt fails.
        await service.send_account_deleted_email(
            to_email="user@example.com",
            deleted_at=DELETED_AT,
        )

    assert len(recorder.calls) == module.MAX_EMAIL_ATTEMPTS == 3


# ---------------------------------------------------------------------------
# Outbox enqueue contract
# ---------------------------------------------------------------------------


def test_lock_scheduler_noops_without_recipient():
    with patch.object(module, "enqueue_email", new=AsyncMock()) as enqueue:
        asyncio.run(
            module.schedule_account_locked_email(
                MagicMock(),
                to_email=None,
                reason="Lý do",
                locked_at=LOCKED_AT,
            )
        )
        enqueue.assert_not_awaited()


def test_delete_scheduler_noops_without_recipient():
    with patch.object(module, "enqueue_email", new=AsyncMock()) as enqueue:
        asyncio.run(
            module.schedule_account_deleted_email(
                MagicMock(),
                to_email=None,
                deleted_at=DELETED_AT,
            )
        )
        enqueue.assert_not_awaited()


def test_lock_scheduler_enqueues_rendered_primitives():
    with patch.object(module, "enqueue_email", new=AsyncMock()) as enqueue, patch.object(
        module, "signal_dispatch_after_commit"
    ) as signal:
        asyncio.run(
            module.schedule_account_locked_email(
                MagicMock(),
                to_email="user@example.com",
                reason="Lý do",
                locked_at=LOCKED_AT,
                idempotency_key="account_locked:1",
            )
        )

    enqueue.assert_awaited_once()
    kwargs = enqueue.call_args.kwargs
    assert kwargs["event_type"] == module.EVENT_ACCOUNT_LOCKED
    assert kwargs["to_email"] == "user@example.com"
    assert kwargs["subject"] == SUBJECT_ACCOUNT_LOCKED
    assert kwargs["idempotency_key"] == "account_locked:1"
    # The rendered payload carries the reason, and only primitives are captured.
    assert not hasattr(kwargs["to_email"], "is_active")
    for body in (kwargs["html_body"], kwargs["text_body"]):
        assert "Lý do" in body
    signal.assert_called_once()


def test_delete_scheduler_enqueues_rendered_primitives():
    with patch.object(module, "enqueue_email", new=AsyncMock()) as enqueue, patch.object(
        module, "signal_dispatch_after_commit"
    ) as signal:
        asyncio.run(
            module.schedule_account_deleted_email(
                MagicMock(),
                to_email="original@example.com",
                deleted_at=DELETED_AT,
                idempotency_key="account_deleted:1",
            )
        )

    enqueue.assert_awaited_once()
    kwargs = enqueue.call_args.kwargs
    assert kwargs["event_type"] == module.EVENT_ACCOUNT_DELETED
    assert kwargs["to_email"] == "original@example.com"
    assert kwargs["subject"] == SUBJECT_ACCOUNT_DELETED
    assert kwargs["idempotency_key"] == "account_deleted:1"
    signal.assert_called_once()
