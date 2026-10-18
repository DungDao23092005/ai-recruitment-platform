from __future__ import annotations

import asyncio
import html as html_module
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.email_service import EmailService
from app.services.notification_service import VIETNAM_TZ, _format_expiry_date

logger = logging.getLogger(__name__)

# Fixed subjects (Vietnamese, matching the existing product copy).
SUBJECT_ACTIVATED = (
    "[AI Recruitment Platform] Kích hoạt gói dịch vụ {plan_name} thành công"
)
SUBJECT_PLAN_CHANGED = "[AI Recruitment Platform] Thông báo thay đổi gói dịch vụ"
SUBJECT_REVOKED = "[AI Recruitment Platform] Thông báo thu hồi gói dịch vụ"
# Enriched VNPAY receipt sent instead of the generic activation email when a
# verified VNPAY payment activates a subscription.
SUBJECT_PAYMENT_RECEIPT = (
    "Thanh toán thành công — {plan_name} | AI Recruitment Platform"
)

# Display fallback for an optional value that is not available (e.g. a VNPAY
# sandbox response without a transaction number). Matches the payment result
# page which hides the row; the email keeps it visible but explicit.
MISSING_VALUE = "—"

_CURRENCY_SYMBOLS = {"VND": "₫", "USD": "US$", "EUR": "€"}


@dataclass(frozen=True)
class PaymentReceipt:
    """Authoritative, primitive-only snapshot of a verified payment.

    Built from persisted backend records on the verified success path and passed
    into the after-commit email task so nothing depends on a live/expired ORM
    instance.
    """

    amount: int
    currency: str
    order_reference: str
    provider_transaction_id: Optional[str]
    paid_at: Optional[datetime]


# Best-effort delivery: initial attempt + up to 2 additional attempts with backoff.
MAX_EMAIL_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (1.0, 2.0)


def _esc(value: object) -> str:
    """HTML-escape untrusted values injected into templates."""
    return html_module.escape(str(value), quote=True)


def _format_currency(amount: object, currency: object) -> str:
    """Format an amount the way the payment result page does.

    Mirrors the frontend's ``Intl.NumberFormat('vi-VN', {style: 'currency',
    currency, minimumFractionDigits: 0, maximumFractionDigits: 0})`` for the
    currencies this platform sells in: ``1.000.000 ₫`` for VND. Unknown
    currencies fall back to the grouped number followed by the ISO code, and a
    missing currency renders the grouped number only (never a fabricated code).
    """
    try:
        number = int(amount)
    except (TypeError, ValueError):
        grouped = str(amount)
    else:
        grouped = f"{number:,}".replace(",", ".")

    code = str(currency).strip().upper() if currency else ""
    symbol = _CURRENCY_SYMBOLS.get(code)
    if symbol:
        return f"{grouped} {symbol}"
    if code:
        return f"{grouped} {code}"
    return grouped


def _to_vietnam(value: datetime | None) -> datetime | None:
    """Convert a stored (possibly naive UTC) datetime to Asia/Ho_Chi_Minh."""
    if value is None:
        return None
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(VIETNAM_TZ)


def _format_receipt_datetime(value: datetime | None) -> str:
    """Render a payment timestamp as ``HH:mm DD/MM/YYYY`` in Vietnam time."""
    local = _to_vietnam(value)
    if local is None:
        return MISSING_VALUE
    return local.strftime("%H:%M %d/%m/%Y")


def _format_receipt_date(value: datetime | None) -> str:
    """Render a calendar date as ``DD/MM/YYYY`` in Vietnam time."""
    local = _to_vietnam(value)
    if local is None:
        return MISSING_VALUE
    return local.strftime("%d/%m/%Y")


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


def _receipt_row(label: str, value_html: str) -> str:
    """One table row of the receipt; inline styles keep it email-client safe."""
    return (
        "<tr>"
        '<td style="padding:10px 0;border-bottom:1px solid #e5e7eb;'
        'font-size:14px;color:#6b7280;vertical-align:top;">'
        f"{_esc(label)}"
        "</td>"
        '<td style="padding:10px 0;border-bottom:1px solid #e5e7eb;'
        'font-size:14px;color:#111827;font-weight:600;text-align:right;'
        'word-break:break-word;">'
        f"{value_html}"
        "</td>"
        "</tr>"
    )


def _render_payment_receipt(
    *,
    plan_name: str,
    amount: object,
    currency: object,
    order_reference: str,
    provider_transaction_id: Optional[str],
    paid_at: datetime | None,
    expires_at: datetime | None,
) -> tuple[str, str]:
    """Build a responsive, table-based VNPAY payment receipt.

    The dynamic values are escaped before they are injected. The body mirrors
    the information shown on the payment result page: package, paid amount,
    payment status, subscription status, order reference, VNPAY transaction id,
    paid timestamp and entitlement expiry.
    """
    amount_text = _format_currency(amount, currency)
    transaction_text = provider_transaction_id or MISSING_VALUE
    paid_text = _format_receipt_datetime(paid_at)
    expires_text = _format_receipt_date(expires_at)

    rows = [
        ("Gói dịch vụ", plan_name),
        ("Số tiền", amount_text),
        ("Trạng thái thanh toán", "Đã thanh toán"),
        ("Trạng thái gói", "Đang hoạt động"),
        ("Mã đơn hàng", order_reference),
        ("Mã giao dịch VNPAY", transaction_text),
        ("Thời gian thanh toán", paid_text),
        ("Hiệu lực đến", expires_text),
    ]
    rows_html = "".join(_receipt_row(label, _esc(value)) for label, value in rows)

    html = (
        '<!DOCTYPE html>'
        '<html lang="vi">'
        '<body style="margin:0;padding:0;background-color:#f3f4f6;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background-color:#f3f4f6;padding:24px 12px;">'
        "<tr><td align=\"center\">"
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;width:100%;background-color:#ffffff;'
        'border-radius:8px;">'
        "<tr><td style=\"padding:24px 24px 8px;\">"
        '<h2 style="margin:0;font-family:Arial,Helvetica,sans-serif;'
        'font-size:20px;color:#2563eb;">Thanh toán thành công</h2>'
        '<p style="margin:8px 0 0;font-family:Arial,Helvetica,sans-serif;'
        'font-size:14px;color:#374151;">Cảm ơn bạn đã thanh toán. '
        "Gói dịch vụ của bạn đã được kích hoạt thành công.</p>"
        "</td></tr>"
        "<tr><td style=\"padding:8px 24px 0;\">"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        f"{rows_html}"
        "</table>"
        "</td></tr>"
        "<tr><td style=\"padding:16px 24px 24px;\">"
        '<p style="margin:0;font-family:Arial,Helvetica,sans-serif;'
        'font-size:12px;color:#6b7280;">AI Recruitment Platform</p>'
        "</td></tr>"
        "</table>"
        "</td></tr>"
        "</table>"
        "</body>"
        "</html>"
    )

    text = (
        "Thanh toán thành công\n\n"
        f"Gói dịch vụ: {plan_name}\n"
        f"Số tiền: {amount_text}\n"
        "Trạng thái thanh toán: Đã thanh toán\n"
        "Trạng thái gói: Đang hoạt động\n"
        f"Mã đơn hàng: {order_reference}\n"
        f"Mã giao dịch VNPAY: {transaction_text}\n"
        f"Thời gian thanh toán: {paid_text}\n"
        f"Hiệu lực đến: {expires_text}\n\n"
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

    async def send_payment_receipt_email(
        self,
        *,
        to_email: str,
        plan_name: str,
        expires_at: datetime | None,
        receipt: PaymentReceipt,
    ) -> None:
        """Send the enriched VNPAY payment receipt for a verified purchase."""
        subject = SUBJECT_PAYMENT_RECEIPT.format(plan_name=plan_name)
        html, text = _render_payment_receipt(
            plan_name=plan_name,
            amount=receipt.amount,
            currency=receipt.currency,
            order_reference=receipt.order_reference,
            provider_transaction_id=receipt.provider_transaction_id,
            paid_at=receipt.paid_at,
            expires_at=expires_at,
        )
        await self._deliver(to_email, subject, html, text, label="payment_receipt")

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


def schedule_payment_receipt_email(
    session: AsyncSession,
    *,
    to_email: Optional[str],
    plan_name: str,
    expires_at: datetime | None,
    receipt: PaymentReceipt,
) -> None:
    """Schedule the enriched VNPAY receipt for after the transaction commits.

    ``receipt`` and the other arguments are already-captured primitives, so the
    deferred task never touches a live ORM instance.
    """
    if not to_email:
        logger.warning("Skipping payment receipt email: subscription owner has no email")
        return

    def _factory() -> object:
        return SubscriptionEmailService().send_payment_receipt_email(
            to_email=to_email,
            plan_name=plan_name,
            expires_at=expires_at,
            receipt=receipt,
        )

    _schedule_email_after_commit(session, _factory, "payment_receipt")
