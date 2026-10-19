"""Unit tests for subscription lifecycle emails.

These focus on rendering, HTML escaping, payload hygiene, retry/backoff and the
durable outbox enqueue contract. Provider transports are exercised separately in
``test_email_service.py``; here ``EmailService`` is replaced with a recorder.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import subscription_email_service as module
from app.services.subscription_email_service import (
    SUBJECT_ACTIVATED,
    SUBJECT_PAYMENT_RECEIPT,
    SUBJECT_PLAN_CHANGED,
    SUBJECT_REVOKED,
    PaymentReceipt,
    SubscriptionEmailService,
)


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


EXPIRES_AT = datetime(2026, 1, 15, 3, 30, tzinfo=timezone.utc)


def _service(effects: list[object] | None = None):
    recorder = _RecorderEmailService(effects)
    return recorder, SubscriptionEmailService(email_service=recorder)  # type: ignore[arg-type]


async def test_activation_email_has_expected_subject_and_body():
    recorder, service = _service()

    await service.send_activation_email(
        to_email="buyer@example.com",
        plan_name="Professional",
        expires_at=EXPIRES_AT,
    )

    assert len(recorder.calls) == 1
    to_email, subject, html, text = recorder.calls[0]
    assert to_email == "buyer@example.com"
    assert subject == SUBJECT_ACTIVATED.format(plan_name="Professional")
    assert "Professional" in html
    # Expiry rendered in Vietnam local time (dd/mm/yyyy).
    assert "15/01/2026" in html
    assert "Professional" in text and "15/01/2026" in text


async def test_plan_changed_email_lists_old_and_new_plan():
    recorder, service = _service()

    await service.send_plan_changed_email(
        to_email="buyer@example.com",
        previous_plan_name="Starter",
        new_plan_name="Enterprise",
        expires_at=EXPIRES_AT,
        reason="Khách hàng nâng cấp",
    )

    _, subject, html, text = recorder.calls[0]
    assert subject == SUBJECT_PLAN_CHANGED
    assert "Starter" in html and "Enterprise" in html
    assert "Khách hàng nâng cấp" in html
    assert "Starter" in text and "Enterprise" in text


async def test_revoked_email_states_status_and_reason():
    recorder, service = _service()

    await service.send_revoked_email(
        to_email="buyer@example.com",
        plan_name="Professional",
        reason="Vi phạm điều khoản",
        effective_at=EXPIRES_AT,
    )

    _, subject, html, text = recorder.calls[0]
    assert subject == SUBJECT_REVOKED
    assert "Professional" in html
    assert "Đã hủy" in html
    assert "Vi phạm điều khoản" in html
    assert "Vi phạm điều khoản" in text


async def test_html_escaping_prevents_injection():
    recorder, service = _service()

    await service.send_plan_changed_email(
        to_email="buyer@example.com",
        previous_plan_name="<b>Old</b>",
        new_plan_name='<script>alert("xss")</script>',
        expires_at=EXPIRES_AT,
        reason='<img src=x onerror="steal()">',
    )

    _, _, html, _ = recorder.calls[0]
    assert "<script>" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img src=x" in html


async def test_email_body_contains_no_support_placeholder_or_payment_metadata():
    recorder, service = _service()

    await service.send_activation_email(
        to_email="buyer@example.com",
        plan_name="Professional",
        expires_at=EXPIRES_AT,
    )

    _, _, html, text = recorder.calls[0]
    combined = (html + text).lower()
    assert "support@" not in combined
    assert "example.com" not in combined
    assert "vnpay" not in combined
    assert "giao dịch" not in combined


async def test_retry_succeeds_after_transient_failure():
    recorder, service = _service(effects=[RuntimeError("smtp down")])

    with patch.object(module.asyncio, "sleep", new=AsyncMock()):
        await service.send_activation_email(
            to_email="buyer@example.com",
            plan_name="Professional",
            expires_at=EXPIRES_AT,
        )

    assert len(recorder.calls) == 2


async def test_retry_is_bounded_and_swallows_failures():
    recorder, service = _service(
        effects=[RuntimeError("1"), RuntimeError("2"), RuntimeError("3")]
    )

    with patch.object(module.asyncio, "sleep", new=AsyncMock()):
        # Must not raise even though every attempt fails.
        await service.send_revoked_email(
            to_email="buyer@example.com",
            plan_name="Professional",
            reason="reason",
            effective_at=EXPIRES_AT,
        )

    assert len(recorder.calls) == module.MAX_EMAIL_ATTEMPTS == 3


def test_scheduler_noops_without_recipient():
    with patch.object(module, "enqueue_email", new=AsyncMock()) as enqueue:
        asyncio.run(
            module.schedule_activation_email(
                MagicMock(),
                to_email=None,
                plan_name="Professional",
                expires_at=EXPIRES_AT,
            )
        )
        enqueue.assert_not_awaited()


def test_activation_scheduler_enqueues_with_idempotency_key():
    with patch.object(module, "enqueue_email", new=AsyncMock()) as enqueue, patch.object(
        module, "signal_dispatch_after_commit"
    ) as signal:
        asyncio.run(
            module.schedule_activation_email(
                MagicMock(),
                to_email="buyer@example.com",
                plan_name="Professional",
                expires_at=EXPIRES_AT,
                idempotency_key="subscription_activated:abc",
            )
        )

    enqueue.assert_awaited_once()
    kwargs = enqueue.call_args.kwargs
    assert kwargs["event_type"] == module.EVENT_ACTIVATION
    assert kwargs["to_email"] == "buyer@example.com"
    assert kwargs["subject"] == SUBJECT_ACTIVATED.format(plan_name="Professional")
    assert kwargs["idempotency_key"] == "subscription_activated:abc"
    assert "Professional" in kwargs["html_body"]
    signal.assert_called_once()


# 2026-05-05 03:15:30 UTC == 10:15 05/05/2026 Asia/Ho_Chi_Minh.
PAID_AT = datetime(2026, 5, 5, 3, 15, 30, tzinfo=timezone.utc)
ORDER_REFERENCE = "VNPAY_20260505_031530_ABCD1234"


def _receipt(**overrides) -> PaymentReceipt:
    values = {
        "amount": 1_000_000,
        "currency": "VND",
        "order_reference": ORDER_REFERENCE,
        "provider_transaction_id": "13524458",
        "paid_at": PAID_AT,
    }
    values.update(overrides)
    return PaymentReceipt(**values)


async def test_payment_receipt_has_expected_subject_and_fields():
    recorder, service = _service()

    await service.send_payment_receipt_email(
        to_email="buyer@example.com",
        plan_name="Professional",
        expires_at=EXPIRES_AT,
        receipt=_receipt(),
    )

    assert len(recorder.calls) == 1
    to_email, subject, html, text = recorder.calls[0]
    assert to_email == "buyer@example.com"
    assert subject == SUBJECT_PAYMENT_RECEIPT.format(plan_name="Professional")
    assert subject == "Thanh toán thành công — Professional | AI Recruitment Platform"

    for body in (html, text):
        assert "Professional" in body
        assert "1.000.000 ₫" in body
        assert "Đã thanh toán" in body
        assert "Đang hoạt động" in body
        assert ORDER_REFERENCE in body
        assert "13524458" in body
        # Payment timestamp in Vietnam local time (HH:mm DD/MM/YYYY).
        assert "10:15 05/05/2026" in body
        # Expiry date in Vietnam local time (DD/MM/YYYY).
        assert "15/01/2026" in body


async def test_payment_receipt_renders_vietnam_local_time_across_date_boundary():
    recorder, service = _service()
    # 2026-06-04 17:00 UTC == 2026-06-05 00:00 Asia/Ho_Chi_Minh.
    boundary_expiry = datetime(2026, 6, 4, 17, 0, tzinfo=timezone.utc)

    await service.send_payment_receipt_email(
        to_email="buyer@example.com",
        plan_name="Professional",
        expires_at=boundary_expiry,
        receipt=_receipt(),
    )

    _, _, html, text = recorder.calls[0]
    assert "05/06/2026" in html and "05/06/2026" in text


async def test_payment_receipt_missing_transaction_id_renders_placeholder():
    recorder, service = _service()

    await service.send_payment_receipt_email(
        to_email="buyer@example.com",
        plan_name="Professional",
        expires_at=EXPIRES_AT,
        receipt=_receipt(provider_transaction_id=None),
    )

    _, _, html, text = recorder.calls[0]
    assert "—" in html
    assert "Mã giao dịch VNPAY: —" in text


def test_payment_receipt_unknown_currency_falls_back_to_iso_code():
    assert module._format_currency(1_000_000, "JPY") == "1.000.000 JPY"
    assert module._format_currency(1_000_000, None) == "1.000.000"


async def test_payment_receipt_escapes_dynamic_values():
    recorder, service = _service()

    await service.send_payment_receipt_email(
        to_email="buyer@example.com",
        plan_name='<script>alert("xss")</script>',
        expires_at=EXPIRES_AT,
        receipt=_receipt(
            order_reference='<img src=x onerror="steal()">',
            provider_transaction_id="<b>txn</b>",
        ),
    )

    _, _, html, _ = recorder.calls[0]
    assert "<script>" not in html
    assert "<img src=x" not in html
    assert "<b>txn</b>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img src=x" in html
    assert "&lt;b&gt;txn&lt;/b&gt;" in html


def test_payment_receipt_scheduler_noops_without_recipient():
    with patch.object(module, "enqueue_email", new=AsyncMock()) as enqueue:
        asyncio.run(
            module.schedule_payment_receipt_email(
                MagicMock(),
                to_email=None,
                plan_name="Professional",
                expires_at=EXPIRES_AT,
                receipt=_receipt(),
            )
        )
        enqueue.assert_not_awaited()
