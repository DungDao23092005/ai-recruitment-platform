import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.email_outbox import EmailOutbox
from app.services.company_email_service import (
    EVENT_COMPANY_PROFILE_UPDATED,
    SUBJECT_PREFIX,
    CompanyEmailService,
    _esc,
    _format_datetime,
    _render_company_updated_email,
)


class TestCompanyEmailRendering:
    def test_format_datetime_converts_to_vietnam_time(self):
        utc_dt = datetime(2026, 11, 26, 7, 30, tzinfo=timezone.utc)
        formatted = _format_datetime(utc_dt)
        # 07:30 UTC -> 14:30 Asia/Ho_Chi_Minh
        assert formatted == "14:30 26/11/2026"

    def test_format_datetime_none_returns_dash(self):
        assert _format_datetime(None) == "—"

    def test_html_escaping(self):
        unsafe = '<script>alert("xss")</script> & "quotes"'
        escaped = _esc(unsafe)
        assert "<script>" not in escaped
        assert "&lt;script&gt;" in escaped
        assert "&quot;" in escaped

    def test_render_company_updated_email_content(self):
        company_name = "TechNova AI"
        updater_name = "Quản trị viên hệ thống"
        updated_at = datetime(2026, 11, 26, 7, 30, tzinfo=timezone.utc)
        changed_fields = "tên công ty, quy mô"
        action_url = "http://localhost:5173/recruiter/company"

        html, text = _render_company_updated_email(
            company_name=company_name,
            updater_name=updater_name,
            updated_at=updated_at,
            changed_fields_summary=changed_fields,
            action_url=action_url,
        )

        # Check HTML assertions
        assert company_name in html
        assert updater_name in html
        assert "14:30 26/11/2026" in html
        assert changed_fields in html
        assert action_url in html
        assert "Thông tin công ty đã được cập nhật" in html
        assert "Hồ sơ công ty" in html

        # Check Text assertions
        assert company_name in text
        assert updater_name in text
        assert "14:30 26/11/2026" in text
        assert changed_fields in text
        assert action_url in text


class TestCompanyEmailScheduling:
    def test_schedule_company_profile_updated_email_calls_enqueue_and_signal(self):
        session = MagicMock()
        company_id = uuid.uuid4()
        recipient_user_id = uuid.uuid4()
        event_uuid = uuid.uuid4()
        company_name = "Innovatech"
        updater_name = "Trần Thị B"
        recipient_email = "member@innovatech.vn"

        expected_key = f"company_profile_updated:{company_id}:{event_uuid}:{recipient_user_id}"
        expected_subject = f"{SUBJECT_PREFIX} Thông tin công ty {company_name} đã được cập nhật"

        fake_outbox = EmailOutbox(
            id=uuid.uuid4(),
            event_type=EVENT_COMPANY_PROFILE_UPDATED,
            to_email=recipient_email,
            subject=expected_subject,
            idempotency_key=expected_key,
        )

        with (
            patch(
                "app.services.company_email_service.enqueue_email",
                new_callable=AsyncMock,
            ) as mock_enqueue,
            patch(
                "app.services.company_email_service.signal_dispatch_after_commit"
            ) as mock_signal,
        ):
            mock_enqueue.return_value = fake_outbox

            result = asyncio.run(
                CompanyEmailService.schedule_company_profile_updated_email(
                    session=session,
                    company_id=company_id,
                    company_name=company_name,
                    updater_name=updater_name,
                    recipient_user_id=recipient_user_id,
                    recipient_email=recipient_email,
                    event_uuid=event_uuid,
                    changed_fields_summary="mã số thuế",
                )
            )

            assert result is fake_outbox
            mock_enqueue.assert_awaited_once()
            call_kwargs = mock_enqueue.call_args.kwargs
            assert call_kwargs["session"] is session
            assert call_kwargs["event_type"] == EVENT_COMPANY_PROFILE_UPDATED
            assert call_kwargs["to_email"] == recipient_email
            assert call_kwargs["subject"] == expected_subject
            assert call_kwargs["idempotency_key"] == expected_key
            assert "Innovatech" in call_kwargs["html_body"]
            assert "mã số thuế" in call_kwargs["html_body"]
            assert "Trần Thị B" in call_kwargs["html_body"]

            mock_signal.assert_called_once_with(session)
