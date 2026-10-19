"""Transactional hiring-pipeline emails (application outcomes and interviews).

Only the messages the candidate is entitled to receive are produced here:

* an application outcome (offer / accepted / rejected), and
* an interview invitation, a meaningful reschedule, or a cancellation.

Every message is enqueued through the shared durable outbox inside the caller's
transaction (via :func:`enqueue_email`), so the email intent commits atomically
with the state change that produced it and is delivered later by the worker.
Nothing here ever contacts the provider directly.

Privacy: these helpers accept only already-captured primitives (job title,
status, interview time). Internal notes, private evaluations and rejection
reasons are never passed in and therefore can never appear in a candidate
email.
"""

from __future__ import annotations

import html as html_module
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ApplicationStatus
from app.services.email_outbox_service import enqueue_email
from app.services.email_outbox_worker import signal_dispatch_after_commit
from app.services.notification_service import VIETNAM_TZ

EVENT_APPLICATION_STATUS = "application_status_changed"
EVENT_INTERVIEW_LIFECYCLE = "interview_lifecycle"

_FONT = "Arial,Helvetica,sans-serif"

# Statuses that trigger a candidate email. Anything else is intentionally
# silent (internal pipeline moves are not candidate-facing events).
EMAILED_STATUSES = frozenset(
    {
        ApplicationStatus.OFFERED,
        ApplicationStatus.ACCEPTED,
        ApplicationStatus.REJECTED,
    }
)

_STATUS_COPY: dict[ApplicationStatus, tuple[str, str, str]] = {
    ApplicationStatus.OFFERED: (
        "Bạn nhận được thư mời làm việc",
        "Chúc mừng! Nhà tuyển dụng đã gửi cho bạn một thư mời làm việc.",
        "Vui lòng phản hồi lại nhà tuyển dụng trong thời gian sớm nhất.",
    ),
    ApplicationStatus.ACCEPTED: (
        "Đơn ứng tuyển đã được chấp nhận",
        "Đơn ứng tuyển của bạn đã được chấp nhận.",
        "Nhà tuyển dụng sẽ liên hệ với bạn để trao đổi các bước tiếp theo.",
    ),
    ApplicationStatus.REJECTED: (
        "Kết quả đơn ứng tuyển",
        "Cảm ơn bạn đã quan tâm và ứng tuyển vào vị trí này.",
        "Sau khi xem xét, nhà tuyển dụng quyết định chưa phù hợp ở thời điểm hiện tại.",
    ),
}

_INTERVIEW_COPY: dict[str, tuple[str, str, str]] = {
    "scheduled": (
        "Lời mời phỏng vấn",
        "Bạn đã được mời tham gia một buổi phỏng vấn.",
        "Vui lòng xác nhận hoặc phản hồi lại nhà tuyển dụng.",
    ),
    "rescheduled": (
        "Lịch phỏng vấn đã thay đổi",
        "Lịch phỏng vấn của bạn đã được cập nhật.",
        "Vui lòng kiểm tra lại thời gian và xác nhận tham gia.",
    ),
    "cancelled": (
        "Phỏng vấn đã bị hủy",
        "Buổi phỏng vấn đã bị hủy.",
        "Nhà tuyển dụng sẽ liên hệ lại nếu có lịch mới.",
    ),
}


def _esc(value: object) -> str:
    return html_module.escape(str(value), quote=True)


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(VIETNAM_TZ).strftime("%H:%M %d/%m/%Y")


def _render(
    *,
    header_bg: str,
    badge_bg: str,
    badge_text: str,
    badge_label: str,
    title: str,
    intro: str,
    job_title: str,
    extra_rows: list[tuple[str, str]],
    closing: str,
) -> tuple[str, str]:
    rows = [("Vị trí", job_title)] + extra_rows
    rows_html = "".join(
        "<tr>"
        f'<td style="padding:10px 0;border-bottom:1px solid #e5e7eb;'
        f'font-family:{_FONT};font-size:14px;color:#6b7280;">{_esc(label)}</td>'
        f'<td style="padding:10px 0;border-bottom:1px solid #e5e7eb;'
        f'font-family:{_FONT};font-size:14px;color:#111827;font-weight:600;'
        f'text-align:right;">{_esc(value)}</td>'
        "</tr>"
        for label, value in rows
    )
    html = (
        "<!DOCTYPE html>"
        '<html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        "</head>"
        '<body style="margin:0;padding:0;background-color:#f3f4f6;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background-color:#f3f4f6;padding:24px 12px;"><tr><td align="center">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;width:100%;background-color:#ffffff;'
        'border-radius:8px;overflow:hidden;">'
        "<tr>"
        f'<td style="background-color:{header_bg};padding:24px;">'
        f'<h1 style="margin:0 0 8px;font-family:{_FONT};font-size:20px;'
        f'font-weight:bold;color:#ffffff;">{_esc(title)}</h1>'
        f'<span style="display:inline-block;background-color:{badge_bg};'
        f'color:{badge_text};font-family:{_FONT};font-size:12px;font-weight:bold;'
        f'padding:4px 10px;border-radius:12px;">{_esc(badge_label)}</span>'
        "</td></tr>"
        f'<tr><td style="padding:24px;">'
        f'<p style="margin:0;font-family:{_FONT};font-size:15px;color:#374151;">'
        f"{_esc(intro)}</p>"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin:12px 0 0;">{rows_html}</table>'
        f'<p style="margin:16px 0 0;font-family:{_FONT};font-size:14px;'
        f'color:#374151;">{_esc(closing)}</p>'
        "</td></tr>"
        '<tr><td style="padding:16px 24px;border-top:1px solid #e5e7eb;'
        'background-color:#f9fafb;">'
        f'<p style="margin:0;font-family:{_FONT};font-size:12px;color:#6b7280;">'
        "AI Recruitment Platform — Nền tảng tuyển dụng ứng dụng AI.</p>"
        f'<p style="margin:4px 0 0;font-family:{_FONT};font-size:12px;'
        'color:#9ca3af;">Đây là email tự động, vui lòng không trả lời.</p>'
        "</td></tr></table></td></tr></table></body></html>"
    )

    text_lines = [
        "Xin chào,",
        "",
        intro,
        "",
        f"Vị trí: {job_title}",
    ]
    text_lines.extend(f"{label}: {value}" for label, value in extra_rows)
    text_lines.extend(["", closing, "", "AI Recruitment Platform"])
    return html, "\n".join(text_lines)


async def schedule_application_status_email(
    session: AsyncSession,
    *,
    to_email: Optional[str],
    job_title: str,
    new_status: ApplicationStatus,
    idempotency_key: Optional[str] = None,
) -> None:
    """Enqueue an application-outcome email for an emailed status, if any.

    No-ops for statuses the candidate is not emailed about and when there is no
    recipient, so calling it unconditionally on every status change is safe.
    """
    if new_status not in EMAILED_STATUSES:
        return
    if not to_email:
        return

    title, intro, closing = _STATUS_COPY[new_status]
    html, text = _render(
        header_bg="#1d4ed8",
        badge_bg="#dbeafe",
        badge_text="#1e40af",
        badge_label="Cập nhật đơn ứng tuyển",
        title=title,
        intro=intro,
        job_title=job_title,
        extra_rows=[("Trạng thái", new_status.value)],
        closing=closing,
    )
    await enqueue_email(
        session,
        event_type=EVENT_APPLICATION_STATUS,
        to_email=to_email,
        subject=f"[AI Recruitment Platform] {title}",
        html_body=html,
        text_body=text,
        idempotency_key=idempotency_key,
    )
    signal_dispatch_after_commit(session)


async def schedule_interview_email(
    session: AsyncSession,
    *,
    to_email: Optional[str],
    job_title: str,
    scheduled_at: datetime | None,
    event: str,
    idempotency_key: Optional[str] = None,
) -> None:
    """Enqueue an interview lifecycle email (scheduled/rescheduled/cancelled)."""
    if event not in _INTERVIEW_COPY:
        raise ValueError(f"Unsupported interview email event: {event!r}")
    if not to_email:
        return

    title, intro, closing = _INTERVIEW_COPY[event]
    rows: list[tuple[str, str]] = []
    if scheduled_at is not None:
        rows.append(("Thời gian", _format_datetime(scheduled_at)))
    html, text = _render(
        header_bg="#0f766e",
        badge_bg="#ccfbf1",
        badge_text="#115e59",
        badge_label="Lịch phỏng vấn",
        title=title,
        intro=intro,
        job_title=job_title,
        extra_rows=rows,
        closing=closing,
    )
    await enqueue_email(
        session,
        event_type=EVENT_INTERVIEW_LIFECYCLE,
        to_email=to_email,
        subject=f"[AI Recruitment Platform] {title}",
        html_body=html,
        text_body=text,
        idempotency_key=idempotency_key,
    )
    signal_dispatch_after_commit(session)
