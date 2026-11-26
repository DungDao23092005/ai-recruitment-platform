"""Transactional emails for company profile updates.

Every message is enqueued through the shared durable outbox inside the caller's
transaction (via :func:`enqueue_email`), so the email intent commits atomically
with the company update.

Idempotency keys follow deterministic patterns:
    * company_profile_updated:{company_id}:{event_uuid}:{recipient_user_id}
"""

from __future__ import annotations

import html as html_module
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.email_outbox import EmailOutbox
from app.services.email_outbox_service import enqueue_email
from app.services.email_outbox_worker import signal_dispatch_after_commit
from app.services.notification_service import VIETNAM_TZ

logger = logging.getLogger(__name__)

EVENT_COMPANY_PROFILE_UPDATED = "company_profile_updated"
SUBJECT_PREFIX = "[AI Recruitment Platform]"
_FONT = "Arial,Helvetica,sans-serif"


def _esc(value: object) -> str:
    return html_module.escape(str(value), quote=True)


def _build_action_url(path: str = "/recruiter/company") -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    clean_path = path if path.startswith("/") else f"/{path}"
    return f"{base}{clean_path}"


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(VIETNAM_TZ).strftime("%H:%M %d/%m/%Y")


def _render_company_updated_email(
    *,
    company_name: str,
    updater_name: str,
    updated_at: datetime | None,
    changed_fields_summary: str | None = None,
    action_url: str,
) -> tuple[str, str]:
    title = "Thông tin công ty đã được cập nhật"
    intro = f"Thông tin hồ sơ công ty {company_name} vừa được cập nhật."
    formatted_time = _format_datetime(updated_at)

    rows: list[tuple[str, str]] = [
        ("Công ty", company_name),
        ("Người thực hiện", updater_name),
        ("Thời gian", formatted_time),
    ]
    if changed_fields_summary:
        rows.append(("Nội dung thay đổi", changed_fields_summary))

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

    cta_html = (
        '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:20px 0 0;">'
        "<tr>"
        '<td align="center" style="border-radius:6px;background-color:#2563eb;">'
        f'<a href="{_esc(action_url)}" target="_blank" '
        f'style="display:inline-block;padding:10px 20px;font-family:{_FONT};font-size:14px;'
        f'font-weight:600;color:#ffffff;text-decoration:none;border-radius:6px;">'
        "Xem thông tin công ty</a>"
        "</td>"
        "</tr>"
        "</table>"
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
        '<td style="background-color:#1e40af;padding:24px;">'
        f'<h1 style="margin:0 0 8px;font-family:{_FONT};font-size:20px;'
        f'font-weight:bold;color:#ffffff;">{_esc(title)}</h1>'
        '<span style="display:inline-block;background-color:#dbeafe;'
        'color:#1e40af;font-family:'
        f'{_FONT};font-size:12px;font-weight:bold;'
        'padding:4px 10px;border-radius:12px;">Hồ sơ công ty</span>'
        "</td></tr>"
        '<tr><td style="padding:24px;">'
        f'<p style="margin:0;font-family:{_FONT};font-size:15px;color:#374151;">'
        f"{_esc(intro)}</p>"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin:12px 0 0;">{rows_html}</table>'
        f"{cta_html}"
        '<p style="margin:16px 0 0;font-family:{_FONT};font-size:14px;'
        'color:#374151;">Vui lòng kiểm tra lại thông tin công ty nếu có bất kỳ thắc mắc nào.</p>'
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
    ]
    text_lines.extend(f"{label}: {value}" for label, value in rows)
    text_lines.extend([
        "",
        f"Xem thông tin công ty tại: {action_url}",
        "",
        "AI Recruitment Platform",
    ])
    return html, "\n".join(text_lines)


class CompanyEmailService:
    @staticmethod
    async def schedule_company_profile_updated_email(
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        company_name: str,
        updater_name: str,
        recipient_user_id: uuid.UUID,
        recipient_email: str,
        event_uuid: uuid.UUID,
        updated_at: datetime | None = None,
        changed_fields_summary: str | None = None,
    ) -> EmailOutbox:
        if updated_at is None:
            updated_at = datetime.now(timezone.utc)

        action_url = _build_action_url("/recruiter/company")
        html_body, text_body = _render_company_updated_email(
            company_name=company_name,
            updater_name=updater_name,
            updated_at=updated_at,
            changed_fields_summary=changed_fields_summary,
            action_url=action_url,
        )

        subject = f"{SUBJECT_PREFIX} Thông tin công ty {company_name} đã được cập nhật"
        idempotency_key = f"company_profile_updated:{company_id}:{event_uuid}:{recipient_user_id}"

        outbox_entry = await enqueue_email(
            session=session,
            event_type=EVENT_COMPANY_PROFILE_UPDATED,
            to_email=recipient_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            idempotency_key=idempotency_key,
        )

        signal_dispatch_after_commit(session)
        return outbox_entry
