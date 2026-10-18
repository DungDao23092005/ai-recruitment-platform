from __future__ import annotations

import asyncio
import html as html_module
import logging
from datetime import datetime
from typing import Callable, Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.email_service import EmailService
from app.services.notification_service import _format_expiry_date

logger = logging.getLogger(__name__)

# Fixed subjects (Vietnamese, matching the existing product copy).
SUBJECT_ACTIVATED = (
    "[AI Recruitment Platform] Kích hoạt gói dịch vụ {plan_name} thành công"
)
SUBJECT_PLAN_CHANGED = "[AI Recruitment Platform] Thông báo thay đổi gói dịch vụ"
SUBJECT_REVOKED = "[AI Recruitment Platform] Thông báo thu hồi gói dịch vụ"

# Best-effort delivery: initial attempt + up to 2 additional attempts with backoff.
MAX_EMAIL_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (1.0, 2.0)


def _esc(value: object) -> str:
    """HTML-escape untrusted values injected into templates."""
    return html_module.escape(str(value), quote=True)


def _wrap(title: str, body_html: str) -> str:
    """Responsive email shell consistent with the existing OTP template."""
    return f'''
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2563eb;">{title}</h2>
                {body_html}
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
                <p style="font-size: 12px; color: #6b7280;">AI Recruitment Platform</p>
            </div>
        </body>
        </html>
        '''


def _render_activation(plan_name: str, expires_at: datetime | None) -> tuple[str, str]:
    safe_plan = _esc(plan_name)
    expiry = _format_expiry_date(expires_at)
    html = _wrap(
        "Kích hoạt gói dịch vụ thành công",
        f'''
                <p>Xin chào,</p>
                <p>Gói dịch vụ <strong>{safe_plan}</strong> của bạn đã được kích hoạt thành công.</p>
                <ul>
                    <li>Trạng thái: Đang hoạt động</li>
                    <li>Ngày hết hạn: {_esc(expiry)}</li>
                </ul>
                <p>Bạn có thể đăng nhập để sử dụng các quyền lợi của gói ngay bây giờ.</p>
        ''',
    )
    text = (
        "Xin chào,\n\n"
        f"Gói dịch vụ {plan_name} của bạn đã được kích hoạt thành công.\n"
        "Trạng thái: Đang hoạt động\n"
        f"Ngày hết hạn: {expiry}\n\n"
        "Bạn có thể đăng nhập để sử dụng các quyền lợi của gói ngay bây giờ.\n\n"
        "AI Recruitment Platform"
    )
    return html, text


def _render_plan_changed(
    previous_plan_name: Optional[str],
    new_plan_name: str,
    expires_at: datetime | None,
    reason: Optional[str],
) -> tuple[str, str]:
    safe_old = _esc(previous_plan_name or "—")
    safe_new = _esc(new_plan_name)
    safe_reason = _esc(reason or "—")
    expiry = _format_expiry_date(expires_at)
    html = _wrap(
        "Thông báo thay đổi gói dịch vụ",
        f'''
                <p>Xin chào,</p>
                <p>Gói dịch vụ trên tài khoản của bạn đã được quản trị viên cập nhật.</p>
                <ul>
                    <li>Gói trước đây: {safe_old}</li>
                    <li>Gói hiện tại: {safe_new}</li>
                    <li>Ngày hết hạn mới: {_esc(expiry)}</li>
                    <li>Lý do: {safe_reason}</li>
                </ul>
                <p>Bạn có thể đăng nhập để xem chi tiết quyền lợi hiện tại của mình.</p>
        ''',
    )
    text = (
        "Xin chào,\n\n"
        "Gói dịch vụ trên tài khoản của bạn đã được quản trị viên cập nhật.\n"
        f"Gói trước đây: {previous_plan_name or '—'}\n"
        f"Gói hiện tại: {new_plan_name}\n"
        f"Ngày hết hạn mới: {expiry}\n"
        f"Lý do: {reason or '—'}\n\n"
        "Bạn có thể đăng nhập để xem chi tiết quyền lợi hiện tại của mình.\n\n"
        "AI Recruitment Platform"
    )
    return html, text


def _render_revoked(
    plan_name: str,
    reason: Optional[str],
    effective_at: datetime | None,
) -> tuple[str, str]:
    safe_plan = _esc(plan_name)
    safe_reason = _esc(reason or "—")
    effective = _format_expiry_date(effective_at)
    html = _wrap(
        "Thông báo thu hồi gói dịch vụ",
        f'''
                <p>Xin chào,</p>
                <p>Gói dịch vụ <strong>{safe_plan}</strong> trên tài khoản của bạn đã bị thu hồi.</p>
                <ul>
                    <li>Trạng thái: Đã hủy</li>
                    <li>Thời điểm có hiệu lực: {_esc(effective)}</li>
                    <li>Lý do: {safe_reason}</li>
                </ul>
                <p>Tài khoản của bạn vẫn hoạt động bình thường. Bạn có thể đăng nhập và đăng ký gói mới bất cứ lúc nào.</p>
        ''',
    )
    text = (
        "Xin chào,\n\n"
        f"Gói dịch vụ {plan_name} trên tài khoản của bạn đã bị thu hồi.\n"
        "Trạng thái: Đã hủy\n"
        f"Thời điểm có hiệu lực: {effective}\n"
        f"Lý do: {reason or '—'}\n\n"
        "Tài khoản của bạn vẫn hoạt động bình thường. Bạn có thể đăng nhập và đăng ký gói mới bất cứ lúc nào.\n\n"
        "AI Recruitment Platform"
    )
    return html, text


class SubscriptionEmailService:
    """Sends subscription lifecycle emails through the existing EmailService.

    Delivery is best-effort: it runs after the surrounding transaction commits,
    retries a bounded number of times, and never raises into the caller. There
    is no durable outbox, so a process restart can drop a pending send.
    """

    def __init__(self, email_service: Optional[EmailService] = None) -> None:
        self._email_service = email_service

    @property
    def email_service(self) -> EmailService:
        if self._email_service is None:
            self._email_service = EmailService()
        return self._email_service

    async def send_activation_email(
        self,
        *,
        to_email: str,
        plan_name: str,
        expires_at: datetime | None,
    ) -> None:
        subject = SUBJECT_ACTIVATED.format(plan_name=plan_name)
        html, text = _render_activation(plan_name, expires_at)
        await self._deliver(to_email, subject, html, text, label="activation")

    async def send_plan_changed_email(
        self,
        *,
        to_email: str,
        previous_plan_name: Optional[str],
        new_plan_name: str,
        expires_at: datetime | None,
        reason: Optional[str],
    ) -> None:
        html, text = _render_plan_changed(
            previous_plan_name, new_plan_name, expires_at, reason
        )
        await self._deliver(
            to_email, SUBJECT_PLAN_CHANGED, html, text, label="plan_changed"
        )

    async def send_revoked_email(
        self,
        *,
        to_email: str,
        plan_name: str,
        reason: Optional[str],
        effective_at: datetime | None,
    ) -> None:
        html, text = _render_revoked(plan_name, reason, effective_at)
        await self._deliver(to_email, SUBJECT_REVOKED, html, text, label="revoked")

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
                        "Subscription %s email failed after %d attempts: %s",
                        label,
                        attempts,
                        exc,
                    )
                    return
                backoff = RETRY_BACKOFF_SECONDS[attempt - 1]
                logger.warning(
                    "Subscription %s email attempt %d/%d failed, retrying in %.1fs: %s",
                    label,
                    attempt,
                    attempts,
                    backoff,
                    exc,
                )
                await asyncio.sleep(backoff)


def _schedule_email_after_commit(
    session: AsyncSession, factory: Callable[[], object], label: str
) -> None:
    """Schedule a best-effort email task once ``session`` commits."""

    def _run_after_commit(sync_session) -> None:  # noqa: ARG001
        try:
            asyncio.create_task(factory())
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to schedule subscription %s email: %s", label, exc)

    event.listen(session.sync_session, "after_commit", _run_after_commit, once=True)


def schedule_activation_email(
    session: AsyncSession,
    *,
    to_email: Optional[str],
    plan_name: str,
    expires_at: datetime | None,
) -> None:
    if not to_email:
        logger.warning("Skipping activation email: subscription owner has no email")
        return

    def _factory() -> object:
        return SubscriptionEmailService().send_activation_email(
            to_email=to_email, plan_name=plan_name, expires_at=expires_at
        )

    _schedule_email_after_commit(session, _factory, "activation")


def schedule_plan_changed_email(
    session: AsyncSession,
    *,
    to_email: Optional[str],
    previous_plan_name: Optional[str],
    new_plan_name: str,
    expires_at: datetime | None,
    reason: Optional[str],
) -> None:
    if not to_email:
        logger.warning("Skipping plan-change email: subscription owner has no email")
        return

    def _factory() -> object:
        return SubscriptionEmailService().send_plan_changed_email(
            to_email=to_email,
            previous_plan_name=previous_plan_name,
            new_plan_name=new_plan_name,
            expires_at=expires_at,
            reason=reason,
        )

    _schedule_email_after_commit(session, _factory, "plan_changed")


def schedule_revoked_email(
    session: AsyncSession,
    *,
    to_email: Optional[str],
    plan_name: str,
    reason: Optional[str],
    effective_at: datetime | None,
) -> None:
    if not to_email:
        logger.warning("Skipping revoke email: subscription owner has no email")
        return

    def _factory() -> object:
        return SubscriptionEmailService().send_revoked_email(
            to_email=to_email,
            plan_name=plan_name,
            reason=reason,
            effective_at=effective_at,
        )

    _schedule_email_after_commit(session, _factory, "revoked")
