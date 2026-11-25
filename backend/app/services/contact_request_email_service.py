"""Transactional emails for candidate contact authorization requests.

Every message is enqueued through the shared durable outbox inside the caller's
transaction (via :func:`enqueue_email`), so the email intent commits atomically
with the contact request state change.

Strict privacy rules:
- Raw candidate email and phone are NEVER included in email subjects, bodies, or outbox metadata.
- Idempotency keys follow deterministic patterns:
    * contact_request:received:{request_id}
    * contact_request:accepted:{request_id}[:{recipient_user_id}]
    * contact_request:declined:{request_id}[:{recipient_user_id}]
    * contact_request:revoked:{request_id}[:{recipient_user_id}]
    * contact_request:expired:{request_id}
"""

from __future__ import annotations

import html as html_module
import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_outbox import EmailOutbox
from app.services.email_outbox_service import enqueue_email
from app.services.email_outbox_worker import signal_dispatch_after_commit

logger = logging.getLogger(__name__)

EVENT_CONTACT_REQUEST_RECEIVED = "contact_request_received"
EVENT_CONTACT_REQUEST_ACCEPTED = "contact_request_accepted"
EVENT_CONTACT_REQUEST_DECLINED = "contact_request_declined"
EVENT_CONTACT_REQUEST_REVOKED = "contact_request_revoked"
EVENT_CONTACT_REQUEST_EXPIRED = "contact_request_expired"

_FONT = "Arial,Helvetica,sans-serif"


def _esc(value: object) -> str:
    return html_module.escape(str(value), quote=True)


def _render(
    *,
    header_bg: str,
    badge_bg: str,
    badge_text: str,
    badge_label: str,
    title: str,
    intro: str,
    rows: list[tuple[str, str]],
    closing: str,
) -> tuple[str, str]:
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
    ]
    text_lines.extend(f"{label}: {value}" for label, value in rows)
    text_lines.extend(["", closing, "", "AI Recruitment Platform"])
    return html, "\n".join(text_lines)


class ContactRequestEmailService:
    """Service for enqueueing contact request transactional emails atomically."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def send_request_received_email(
        self,
        *,
        to_email: str,
        candidate_name: str,
        company_name: str,
        request_id: uuid.UUID,
    ) -> Optional[EmailOutbox]:
        """Notify Candidate that a company requested contact authorization."""
        if not to_email:
            return None

        idempotency_key = f"contact_request:received:{request_id}"
        subject = f"Yêu cầu kết nối mới từ {company_name}"
        html, text = _render(
            header_bg="#2563eb",
            badge_bg="#dbeafe",
            badge_text="#1e40af",
            badge_label="Yêu cầu kết nối",
            title=f"Doanh nghiệp {company_name} muốn kết nối với bạn",
            intro=f"Xin chào {candidate_name}, doanh nghiệp {company_name} quan tâm đến hồ sơ của bạn và mong muốn được kết nối trực tiếp.",
            rows=[
                ("Doanh nghiệp", company_name),
                ("Mục đích", "Xem thông tin liên hệ và trao đổi cơ hội nghề nghiệp"),
            ],
            closing="Vui lòng đăng nhập vào tài khoản của bạn trên nền tảng để xem xét và phản hồi yêu cầu kết nối này.",
        )

        row = await enqueue_email(
            self.session,
            event_type=EVENT_CONTACT_REQUEST_RECEIVED,
            to_email=to_email,
            subject=subject,
            html_body=html,
            text_body=text,
            idempotency_key=idempotency_key,
        )
        signal_dispatch_after_commit(self.session)
        return row

    async def send_request_accepted_email(
        self,
        *,
        to_email: str,
        candidate_name: str,
        company_name: str,
        request_id: uuid.UUID,
        recipient_user_id: uuid.UUID | None = None,
    ) -> Optional[EmailOutbox]:
        """Notify Recruiter (or fallback Workspace Admin) that Candidate accepted."""
        if not to_email:
            return None

        suffix = f":{recipient_user_id}" if recipient_user_id is not None else ""
        idempotency_key = f"contact_request:accepted:{request_id}{suffix}"
        subject = f"Ứng viên {candidate_name} đã chấp nhận yêu cầu liên hệ"
        html, text = _render(
            header_bg="#16a34a",
            badge_bg="#dcfce7",
            badge_text="#15803d",
            badge_label="Yêu cầu được chấp nhận",
            title="Ứng viên đã cấp quyền xem thông tin liên hệ",
            intro=f"Ứng viên {candidate_name} đã chấp nhận yêu cầu liên hệ từ công ty {company_name}.",
            rows=[
                ("Ứng viên", candidate_name),
                ("Công ty", company_name),
                ("Trạng thái", "Đã chấp nhận"),
            ],
            closing="Vui lòng đăng nhập vào nền tảng để xem thông tin liên hệ của ứng viên thông qua quy trình được cấp phép.",
        )

        row = await enqueue_email(
            self.session,
            event_type=EVENT_CONTACT_REQUEST_ACCEPTED,
            to_email=to_email,
            subject=subject,
            html_body=html,
            text_body=text,
            idempotency_key=idempotency_key,
        )
        signal_dispatch_after_commit(self.session)
        return row

    async def send_request_declined_email(
        self,
        *,
        to_email: str,
        candidate_name: str,
        company_name: str,
        request_id: uuid.UUID,
        recipient_user_id: uuid.UUID | None = None,
    ) -> Optional[EmailOutbox]:
        """Notify Recruiter (or fallback Workspace Admin) that Candidate declined."""
        if not to_email:
            return None

        suffix = f":{recipient_user_id}" if recipient_user_id is not None else ""
        idempotency_key = f"contact_request:declined:{request_id}{suffix}"
        subject = f"Ứng viên {candidate_name} đã từ chối yêu cầu liên hệ"
        html, text = _render(
            header_bg="#dc2626",
            badge_bg="#fee2e2",
            badge_text="#991b1b",
            badge_label="Yêu cầu bị từ chối",
            title="Ứng viên đã từ chối yêu cầu liên hệ",
            intro=f"Ứng viên {candidate_name} đã từ chối yêu cầu liên hệ từ công ty {company_name}.",
            rows=[
                ("Ứng viên", candidate_name),
                ("Công ty", company_name),
                ("Trạng thái", "Đã từ chối"),
            ],
            closing="Theo chính sách nền tảng, công ty có thể gửi lại yêu cầu sau thời gian chờ 30 ngày kể từ ngày từ chối.",
        )

        row = await enqueue_email(
            self.session,
            event_type=EVENT_CONTACT_REQUEST_DECLINED,
            to_email=to_email,
            subject=subject,
            html_body=html,
            text_body=text,
            idempotency_key=idempotency_key,
        )
        signal_dispatch_after_commit(self.session)
        return row

    async def send_request_revoked_email(
        self,
        *,
        to_email: str,
        candidate_name: str,
        company_name: str,
        request_id: uuid.UUID,
        recipient_user_id: uuid.UUID | None = None,
    ) -> Optional[EmailOutbox]:
        """Notify Recruiter (or fallback Workspace Admin) that Candidate revoked authorization."""
        if not to_email:
            return None

        suffix = f":{recipient_user_id}" if recipient_user_id is not None else ""
        idempotency_key = f"contact_request:revoked:{request_id}{suffix}"
        subject = f"Ứng viên {candidate_name} đã thu hồi quyền liên hệ"
        html, text = _render(
            header_bg="#d97706",
            badge_bg="#fef3c7",
            badge_text="#92400e",
            badge_label="Quyền liên hệ bị thu hồi",
            title="Ứng viên đã thu hồi quyền xem thông tin liên hệ",
            intro=f"Ứng viên {candidate_name} đã thu hồi quyền xem thông tin liên hệ đối với công ty {company_name}.",
            rows=[
                ("Ứng viên", candidate_name),
                ("Công ty", company_name),
                ("Trạng thái", "Đã thu hồi"),
            ],
            closing="Theo chính sách nền tảng, công ty có thể gửi lại yêu cầu sau thời gian chờ 90 ngày kể từ ngày thu hồi.",
        )

        row = await enqueue_email(
            self.session,
            event_type=EVENT_CONTACT_REQUEST_REVOKED,
            to_email=to_email,
            subject=subject,
            html_body=html,
            text_body=text,
            idempotency_key=idempotency_key,
        )
        signal_dispatch_after_commit(self.session)
        return row

    async def send_request_expired_email(
        self,
        *,
        to_email: str,
        candidate_name: str,
        company_name: str,
        request_id: uuid.UUID,
    ) -> Optional[EmailOutbox]:
        """Notify initiating Recruiter that the contact request has expired after 14 days."""
        if not to_email:
            return None

        idempotency_key = f"contact_request:expired:{request_id}"
        subject = f"Yêu cầu liên hệ với ứng viên {candidate_name} đã hết hạn"
        html, text = _render(
            header_bg="#4b5563",
            badge_bg="#f3f4f6",
            badge_text="#374151",
            badge_label="Yêu cầu hết hạn",
            title="Yêu cầu liên hệ đã hết hạn sau 14 ngày",
            intro=f"Yêu cầu liên hệ gửi tới ứng viên {candidate_name} từ công ty {company_name} đã hết hạn sau 14 ngày mà chưa nhận được phản hồi.",
            rows=[
                ("Ứng viên", candidate_name),
                ("Công ty", company_name),
                ("Trạng thái", "Đã hết hạn"),
                ("Thời hạn", "14 ngày"),
            ],
            closing="Bạn có thể gửi lại yêu cầu liên hệ khi các chính sách thời gian chờ và giới hạn yêu cầu (tối đa 2 yêu cầu trong vòng 180 ngày) cho phép.",
        )

        row = await enqueue_email(
            self.session,
            event_type=EVENT_CONTACT_REQUEST_EXPIRED,
            to_email=to_email,
            subject=subject,
            html_body=html,
            text_body=text,
            idempotency_key=idempotency_key,
        )
        signal_dispatch_after_commit(self.session)
        return row
