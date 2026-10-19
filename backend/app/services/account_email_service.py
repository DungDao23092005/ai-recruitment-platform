"""Transactional account-lifecycle emails (admin lock and permanent deletion).

Two polished Vietnamese templates are provided:

* an account-lock notification (amber warning treatment), and
* an account-deletion / anonymization notification (muted red treatment).

Delivery is durable: :func:`schedule_account_locked_email` and
:func:`schedule_account_deleted_email` render the message and enqueue it in the
caller's transaction via the shared transactional outbox, so the intent commits
atomically with the account change. The outbox worker delivers it after commit
and retries with backoff across process restarts. The templates and the
best-effort sender (:class:`AccountEmailService`) are retained for rendering and
direct use.
"""

from __future__ import annotations

import asyncio
import html as html_module
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.email_outbox_service import enqueue_email
from app.services.email_outbox_worker import signal_dispatch_after_commit
from app.services.email_service import EmailService
from app.services.notification_service import VIETNAM_TZ
# Best-effort delivery bounds are shared with the subscription lifecycle emails
# so every transactional email uses the same retry/backoff behaviour.
from app.services.subscription_email_service import (
    MAX_EMAIL_ATTEMPTS,
    RETRY_BACKOFF_SECONDS,
)

logger = logging.getLogger(__name__)

# Outbox event types (stable identifiers used by the worker and admin API).
EVENT_ACCOUNT_LOCKED = "account_locked"
EVENT_ACCOUNT_DELETED = "account_deleted"

# Fixed subjects (Vietnamese, matching the existing product copy).
SUBJECT_ACCOUNT_LOCKED = "[AI Recruitment Platform] Thông báo khóa tài khoản"
SUBJECT_ACCOUNT_DELETED = "[AI Recruitment Platform] Thông báo xóa tài khoản"

# Display fallback for an optional value that is not available.
MISSING_VALUE = "—"

# Palette: calm amber for the temporary lock, muted dark red for the permanent
# deletion. Values are inlined so the layout survives Gmail/Outlook stripping.
_LOCK_HEADER_BG = "#b45309"
_LOCK_HEADER_TEXT = "#ffffff"
_LOCK_BADGE_BG = "#fef3c7"
_LOCK_BADGE_TEXT = "#92400e"

_DELETE_HEADER_BG = "#7f1d1d"
_DELETE_HEADER_TEXT = "#ffffff"
_DELETE_BADGE_BG = "#fee2e2"
_DELETE_BADGE_TEXT = "#991b1b"

_FONT = "Arial,Helvetica,sans-serif"


def _esc(value: object) -> str:
    """HTML-escape untrusted values injected into templates."""
    return html_module.escape(str(value), quote=True)


def _to_vietnam(value: datetime | None) -> datetime | None:
    """Convert a stored (possibly naive UTC) datetime to Asia/Ho_Chi_Minh."""
    if value is None:
        return None
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(VIETNAM_TZ)


def _format_datetime(value: datetime | None) -> str:
    """Render a lifecycle timestamp as ``HH:mm DD/MM/YYYY`` in Vietnam time."""
    local = _to_vietnam(value)
    if local is None:
        return MISSING_VALUE
    return local.strftime("%H:%M %d/%m/%Y")


def _detail_row(label: str, value_html: str) -> str:
    """One table row of the detail block; inline styles keep it email-safe."""
    return (
        "<tr>"
        '<td style="padding:10px 0;border-bottom:1px solid #e5e7eb;'
        f'font-family:{_FONT};font-size:14px;color:#6b7280;vertical-align:top;">'
        f"{_esc(label)}"
        "</td>"
        '<td style="padding:10px 0;border-bottom:1px solid #e5e7eb;'
        f'font-family:{_FONT};font-size:14px;color:#111827;font-weight:600;'
        'text-align:right;word-break:break-word;">'
        f"{value_html}"
        "</td>"
        "</tr>"
    )


def _shell(
    *,
    header_bg: str,
    header_text: str,
    badge_bg: str,
    badge_text: str,
    badge_label: str,
    title: str,
    intro_html: str,
    rows_html: str,
    closing_html: str,
) -> str:
    """Responsive, table-based email shell with inline styles."""
    return (
        '<!DOCTYPE html>'
        '<html lang="vi">'
        "<head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        "</head>"
        '<body style="margin:0;padding:0;background-color:#f3f4f6;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background-color:#f3f4f6;padding:24px 12px;">'
        '<tr><td align="center">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;width:100%;background-color:#ffffff;'
        'border-radius:8px;overflow:hidden;">'
        # Header
        "<tr>"
        f'<td style="background-color:{header_bg};padding:24px;">'
        f'<h1 style="margin:0 0 8px;font-family:{_FONT};font-size:20px;'
        f'font-weight:bold;color:{header_text};">{_esc(title)}</h1>'
        f'<span style="display:inline-block;background-color:{badge_bg};'
        f'color:{badge_text};font-family:{_FONT};font-size:12px;'
        'font-weight:bold;padding:4px 10px;border-radius:12px;">'
        f"{_esc(badge_label)}</span>"
        "</td>"
        "</tr>"
        # Body
        "<tr>"
        f'<td style="padding:24px;">'
        f"{intro_html}"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="margin:8px 0 0;">'
        f"{rows_html}"
        "</table>"
        f"{closing_html}"
        "</td>"
        "</tr>"
        # Footer
        "<tr>"
        '<td style="padding:16px 24px;border-top:1px solid #e5e7eb;'
        'background-color:#f9fafb;">'
        f'<p style="margin:0;font-family:{_FONT};font-size:12px;color:#6b7280;">'
        "AI Recruitment Platform — Nền tảng tuyển dụng ứng dụng AI.</p>"
        f'<p style="margin:4px 0 0;font-family:{_FONT};font-size:12px;'
        'color:#9ca3af;">Đây là email tự động, vui lòng không trả lời.</p>'
        "</td>"
        "</tr>"
        "</table>"
        "</td></tr>"
        "</table>"
        "</body>"
        "</html>"
    )


def _render_account_locked(
    reason: Optional[str], locked_at: datetime | None
) -> tuple[str, str]:
    """Build the amber account-lock notification (HTML + plain text)."""
    locked_text = _format_datetime(locked_at)
    reason_text = reason if reason else MISSING_VALUE

    rows_html = "".join(
        [
            _detail_row("Trạng thái tài khoản", _esc("Đã khóa")),
            _detail_row("Thời điểm khóa", _esc(locked_text)),
            _detail_row("Lý do", _esc(reason_text)),
        ]
    )
    intro_html = (
        f'<p style="margin:0 0 12px;font-family:{_FONT};font-size:15px;'
        'color:#111827;">Xin chào,</p>'
        f'<p style="margin:0;font-family:{_FONT};font-size:15px;color:#374151;">'
        "Tài khoản của bạn tại <strong>AI Recruitment Platform</strong> "
        "đã bị quản trị viên khóa.</p>"
    )
    closing_html = (
        f'<p style="margin:16px 0 0;font-family:{_FONT};font-size:14px;'
        'color:#374151;">Trong thời gian tài khoản bị khóa, bạn không thể '
        "đăng nhập hoặc sử dụng các tính năng của hệ thống.</p>"
        f'<p style="margin:8px 0 0;font-family:{_FONT};font-size:14px;'
        'color:#374151;">Hồ sơ, CV, đơn ứng tuyển và các dữ liệu liên quan '
        "khác của bạn vẫn được lưu giữ. Tài khoản có thể được mở khóa khi có "
        "yêu cầu phù hợp.</p>"
        f'<p style="margin:8px 0 0;font-family:{_FONT};font-size:14px;'
        'color:#374151;">Nếu bạn cho rằng đây là nhầm lẫn, vui lòng liên hệ '
        "bộ phận quản trị của nền tảng để được hỗ trợ.</p>"
    )
    html = _shell(
        header_bg=_LOCK_HEADER_BG,
        header_text=_LOCK_HEADER_TEXT,
        badge_bg=_LOCK_BADGE_BG,
        badge_text=_LOCK_BADGE_TEXT,
        badge_label="Tài khoản đã khóa",
        title="Thông báo khóa tài khoản",
        intro_html=intro_html,
        rows_html=rows_html,
        closing_html=closing_html,
    )

    text = (
        "Xin chào,\n\n"
        "Tài khoản của bạn tại AI Recruitment Platform đã bị quản trị viên khóa.\n\n"
        "Trạng thái tài khoản: Đã khóa\n"
        f"Thời điểm khóa: {locked_text}\n"
        f"Lý do: {reason_text}\n\n"
        "Trong thời gian tài khoản bị khóa, bạn không thể đăng nhập hoặc sử "
        "dụng các tính năng của hệ thống.\n"
        "Hồ sơ, CV, đơn ứng tuyển và các dữ liệu liên quan khác của bạn vẫn "
        "được lưu giữ. Tài khoản có thể được mở khóa khi có yêu cầu phù hợp.\n\n"
        "Nếu bạn cho rằng đây là nhầm lẫn, vui lòng liên hệ bộ phận quản trị "
        "của nền tảng để được hỗ trợ.\n\n"
        "AI Recruitment Platform"
    )
    return html, text


def _render_account_deleted(deleted_at: datetime | None) -> tuple[str, str]:
    """Build the muted-red account-deletion notification (HTML + plain text)."""
    deleted_text = _format_datetime(deleted_at)

    rows_html = "".join(
        [
            _detail_row("Trạng thái tài khoản", _esc("Đã xóa vĩnh viễn")),
            _detail_row("Thời điểm xóa", _esc(deleted_text)),
        ]
    )
    intro_html = (
        f'<p style="margin:0 0 12px;font-family:{_FONT};font-size:15px;'
        'color:#111827;">Xin chào,</p>'
        f'<p style="margin:0;font-family:{_FONT};font-size:15px;color:#374151;">'
        "Tài khoản của bạn tại <strong>AI Recruitment Platform</strong> "
        "đã được xóa.</p>"
    )
    closing_html = (
        f'<p style="margin:16px 0 0;font-family:{_FONT};font-size:14px;'
        'color:#374151;">Tài khoản đã được ẩn danh và đánh dấu xóa. Bạn không '
        "thể đăng nhập và không thể khôi phục tài khoản này nữa.</p>"
        f'<p style="margin:8px 0 0;font-family:{_FONT};font-size:14px;'
        'color:#374151;">Địa chỉ email gắn với tài khoản đã được ẩn danh. Một '
        "số dữ liệu liên quan (như lịch sử đơn ứng tuyển, gói dịch vụ và giao "
        "dịch) được lưu trữ cho mục đích vận hành và pháp lý theo quy định "
        "hiện hành.</p>"
        f'<p style="margin:8px 0 0;font-family:{_FONT};font-size:14px;'
        'color:#374151;">Nếu tài khoản có CV được dùng cho tính năng gợi ý '
        "việc làm bằng AI, dữ liệu vector tương ứng đã được xóa khỏi hệ thống "
        "tìm kiếm AI.</p>"
    )
    html = _shell(
        header_bg=_DELETE_HEADER_BG,
        header_text=_DELETE_HEADER_TEXT,
        badge_bg=_DELETE_BADGE_BG,
        badge_text=_DELETE_BADGE_TEXT,
        badge_label="Tài khoản đã xóa",
        title="Thông báo xóa tài khoản",
        intro_html=intro_html,
        rows_html=rows_html,
        closing_html=closing_html,
    )

    text = (
        "Xin chào,\n\n"
        "Tài khoản của bạn tại AI Recruitment Platform đã được xóa.\n\n"
        "Trạng thái tài khoản: Đã xóa vĩnh viễn\n"
        f"Thời điểm xóa: {deleted_text}\n\n"
        "Tài khoản đã được ẩn danh và đánh dấu xóa. Bạn không thể đăng nhập "
        "và không thể khôi phục tài khoản này nữa.\n"
        "Địa chỉ email gắn với tài khoản đã được ẩn danh. Một số dữ liệu liên "
        "quan (như lịch sử đơn ứng tuyển, gói dịch vụ và giao dịch) được lưu "
        "trữ cho mục đích vận hành và pháp lý theo quy định hiện hành.\n"
        "Nếu tài khoản có CV được dùng cho tính năng gợi ý việc làm bằng AI, "
        "dữ liệu vector tương ứng đã được xóa khỏi hệ thống tìm kiếm AI.\n\n"
        "AI Recruitment Platform"
    )
    return html, text


class AccountEmailService:
    """Sends account lock/deletion emails through the existing EmailService.

    Business flows no longer call this directly; they enqueue a durable outbox
    message instead. This class remains the direct, best-effort sender used for
    rendering/testing and is retained as a low-level utility.
    """

    def __init__(self, email_service: Optional[EmailService] = None) -> None:
        self._email_service = email_service

    @property
    def email_service(self) -> EmailService:
        if self._email_service is None:
            self._email_service = EmailService()
        return self._email_service

    async def send_account_locked_email(
        self,
        *,
        to_email: str,
        reason: Optional[str],
        locked_at: datetime | None,
    ) -> None:
        html, text = _render_account_locked(reason, locked_at)
        await self._deliver(
            to_email, SUBJECT_ACCOUNT_LOCKED, html, text, label="account_locked"
        )

    async def send_account_deleted_email(
        self,
        *,
        to_email: str,
        deleted_at: datetime | None,
    ) -> None:
        html, text = _render_account_deleted(deleted_at)
        await self._deliver(
            to_email, SUBJECT_ACCOUNT_DELETED, html, text, label="account_deleted"
        )

    async def _deliver(
        self, to_email: str, subject: str, html: str, text: str, *, label: str
    ) -> None:
        attempts = MAX_EMAIL_ATTEMPTS
        for attempt in range(1, attempts + 1):
            try:
                await self.email_service.send_email(to_email, subject, html, text)
                return
            except Exception as exc:
                if attempt >= attempts:
                    logger.error(
                        "Account %s email failed after %d attempts: %s",
                        label,
                        attempts,
                        exc,
                    )
                    return
                backoff = RETRY_BACKOFF_SECONDS[attempt - 1]
                logger.warning(
                    "Account %s email attempt %d/%d failed, retrying in %.1fs: %s",
                    label,
                    attempt,
                    attempts,
                    backoff,
                    exc,
                )
                await asyncio.sleep(backoff)


async def schedule_account_locked_email(
    session: AsyncSession,
    *,
    to_email: Optional[str],
    reason: Optional[str],
    locked_at: datetime | None,
    idempotency_key: Optional[str] = None,
) -> None:
    """Durably enqueue the account-lock email in the caller's transaction.

    ``to_email``, ``reason`` and ``locked_at`` are already-captured primitives,
    so nothing here depends on a live ORM instance. The row commits (or rolls
    back) with the account change; delivery is the worker's responsibility.
    """
    if not to_email:
        logger.warning("Skipping account-lock email: user has no email")
        return

    html, text = _render_account_locked(reason, locked_at)
    await enqueue_email(
        session,
        event_type=EVENT_ACCOUNT_LOCKED,
        to_email=to_email,
        subject=SUBJECT_ACCOUNT_LOCKED,
        html_body=html,
        text_body=text,
        idempotency_key=idempotency_key,
    )
    signal_dispatch_after_commit(session)


async def schedule_account_deleted_email(
    session: AsyncSession,
    *,
    to_email: Optional[str],
    deleted_at: datetime | None,
    idempotency_key: Optional[str] = None,
) -> None:
    """Durably enqueue the account-deletion email in the caller's transaction.

    The caller must pass the *original* email captured before anonymization, so
    the queued message never addresses the anonymized placeholder.
    """
    if not to_email:
        logger.warning("Skipping account-deletion email: user has no email")
        return

    html, text = _render_account_deleted(deleted_at)
    await enqueue_email(
        session,
        event_type=EVENT_ACCOUNT_DELETED,
        to_email=to_email,
        subject=SUBJECT_ACCOUNT_DELETED,
        html_body=html,
        text_body=text,
        idempotency_key=idempotency_key,
    )
    signal_dispatch_after_commit(session)
