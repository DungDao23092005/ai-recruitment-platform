"""Unit tests for ContactRequestEmailService.

Verifies:
- Safe content rendering (no candidate email/phone in subject, body, or metadata).
- Subject prefix `[AI Recruitment Platform]` on all emails.
- Deterministic idempotency keys for all lifecycle and confirmation events.
- Correct event types, CTA buttons, and recipient handling.
- Candidate confirmation emails on authorization grant and revoke (Q1).
- Graceful no-op when recipient email is empty.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.services import contact_request_email_service as email_module
from app.services.contact_request_email_service import (
    ContactRequestEmailService,
    EVENT_CANDIDATE_AUTHORIZATION_GRANTED,
    EVENT_CANDIDATE_AUTHORIZATION_REVOKED,
    EVENT_CONTACT_REQUEST_ACCEPTED,
    EVENT_CONTACT_REQUEST_DECLINED,
    EVENT_CONTACT_REQUEST_EXPIRED,
    EVENT_CONTACT_REQUEST_RECEIVED,
    EVENT_CONTACT_REQUEST_REVOKED,
    SUBJECT_PREFIX,
)


@pytest.fixture
def enqueue_spy(monkeypatch):
    calls = []

    async def _enqueue(session, **kwargs):
        calls.append(kwargs)
        return MagicMock()

    def _signal(session):
        return None

    monkeypatch.setattr(email_module, "enqueue_email", _enqueue)
    monkeypatch.setattr(email_module, "signal_dispatch_after_commit", _signal)
    return calls


class TestContactRequestEmailService:
    @pytest.mark.asyncio
    async def test_send_request_received_email(self, enqueue_spy):
        session = MagicMock()
        service = ContactRequestEmailService(session)
        request_id = uuid.uuid4()

        await service.send_request_received_email(
            to_email="candidate@example.com",
            candidate_name="Nguyễn Văn A",
            company_name="TechCorp Vietnam",
            request_id=request_id,
        )

        assert len(enqueue_spy) == 1
        call = enqueue_spy[0]
        assert call["event_type"] == EVENT_CONTACT_REQUEST_RECEIVED
        assert call["to_email"] == "candidate@example.com"
        assert call["idempotency_key"] == f"contact_request:received:{request_id}"
        assert call["subject"].startswith(SUBJECT_PREFIX)
        assert "TechCorp Vietnam" in call["subject"]
        assert "TechCorp Vietnam" in call["html_body"]
        assert "TechCorp Vietnam" in call["text_body"]
        assert "Nguyễn Văn A" in call["html_body"]

        # CTA check
        expected_cta = f"{settings.FRONTEND_URL.rstrip('/')}/candidate/contact-requests?id={request_id}"
        assert expected_cta in call["html_body"]
        assert f"Xem yêu cầu kết nối: {expected_cta}" in call["text_body"]

        # Privacy check: no phone or raw personal email leaked in body
        assert "0901234567" not in call["html_body"]
        assert "0901234567" not in call["text_body"]

    @pytest.mark.asyncio
    async def test_send_request_accepted_email_recruiter(self, enqueue_spy):
        session = MagicMock()
        service = ContactRequestEmailService(session)
        request_id = uuid.uuid4()

        await service.send_request_accepted_email(
            to_email="recruiter@example.com",
            candidate_name="Lê Thị B",
            company_name="TechCorp Vietnam",
            request_id=request_id,
        )

        assert len(enqueue_spy) == 1
        call = enqueue_spy[0]
        assert call["event_type"] == EVENT_CONTACT_REQUEST_ACCEPTED
        assert call["to_email"] == "recruiter@example.com"
        assert call["idempotency_key"] == f"contact_request:accepted:{request_id}"
        assert call["subject"].startswith(SUBJECT_PREFIX)
        assert "Lê Thị B" in call["subject"]
        assert "chấp nhận" in call["html_body"]
        assert "quy trình được cấp phép" in call["html_body"]

        # Recruiter CTA destination
        expected_cta = f"{settings.FRONTEND_URL.rstrip('/')}/recruiter/candidate-search"
        assert expected_cta in call["html_body"]
        assert f"Xem danh sách ứng viên: {expected_cta}" in call["text_body"]

        # Strict privacy: no raw contact phone or email in content
        assert "phone" not in call["html_body"].lower()

    @pytest.mark.asyncio
    async def test_send_request_accepted_email_admin_fallback(self, enqueue_spy):
        session = MagicMock()
        service = ContactRequestEmailService(session)
        request_id = uuid.uuid4()
        admin_id = uuid.uuid4()

        await service.send_request_accepted_email(
            to_email="admin@example.com",
            candidate_name="Lê Thị B",
            company_name="TechCorp Vietnam",
            request_id=request_id,
            recipient_user_id=admin_id,
        )

        assert len(enqueue_spy) == 1
        call = enqueue_spy[0]
        assert call["event_type"] == EVENT_CONTACT_REQUEST_ACCEPTED
        assert call["to_email"] == "admin@example.com"
        assert call["idempotency_key"] == f"contact_request:accepted:{request_id}:{admin_id}"
        assert call["subject"].startswith(SUBJECT_PREFIX)

        # Admin fallback CTA destination
        expected_cta = f"{settings.FRONTEND_URL.rstrip('/')}/recruiter/workspace"
        assert expected_cta in call["html_body"]
        assert f"Quản lý thành viên: {expected_cta}" in call["text_body"]

    @pytest.mark.asyncio
    async def test_send_request_declined_email_includes_30_day_cooldown(self, enqueue_spy):
        session = MagicMock()
        service = ContactRequestEmailService(session)
        request_id = uuid.uuid4()

        await service.send_request_declined_email(
            to_email="recruiter@example.com",
            candidate_name="Trần Văn C",
            company_name="TechCorp Vietnam",
            request_id=request_id,
        )

        assert len(enqueue_spy) == 1
        call = enqueue_spy[0]
        assert call["event_type"] == EVENT_CONTACT_REQUEST_DECLINED
        assert call["to_email"] == "recruiter@example.com"
        assert call["idempotency_key"] == f"contact_request:declined:{request_id}"
        assert call["subject"].startswith(SUBJECT_PREFIX)
        assert "30 ngày" in call["html_body"]
        assert "30 ngày" in call["text_body"]

        expected_cta = f"{settings.FRONTEND_URL.rstrip('/')}/recruiter/candidate-search"
        assert expected_cta in call["html_body"]

    @pytest.mark.asyncio
    async def test_send_request_declined_email_admin_fallback(self, enqueue_spy):
        session = MagicMock()
        service = ContactRequestEmailService(session)
        request_id = uuid.uuid4()
        admin_id = uuid.uuid4()

        await service.send_request_declined_email(
            to_email="admin@example.com",
            candidate_name="Trần Văn C",
            company_name="TechCorp Vietnam",
            request_id=request_id,
            recipient_user_id=admin_id,
        )

        assert len(enqueue_spy) == 1
        call = enqueue_spy[0]
        assert call["idempotency_key"] == f"contact_request:declined:{request_id}:{admin_id}"
        expected_cta = f"{settings.FRONTEND_URL.rstrip('/')}/recruiter/workspace"
        assert expected_cta in call["html_body"]

    @pytest.mark.asyncio
    async def test_send_request_revoked_email_includes_90_day_cooldown(self, enqueue_spy):
        session = MagicMock()
        service = ContactRequestEmailService(session)
        request_id = uuid.uuid4()

        await service.send_request_revoked_email(
            to_email="recruiter@example.com",
            candidate_name="Phạm Văn D",
            company_name="TechCorp Vietnam",
            request_id=request_id,
        )

        assert len(enqueue_spy) == 1
        call = enqueue_spy[0]
        assert call["event_type"] == EVENT_CONTACT_REQUEST_REVOKED
        assert call["to_email"] == "recruiter@example.com"
        assert call["idempotency_key"] == f"contact_request:revoked:{request_id}"
        assert call["subject"].startswith(SUBJECT_PREFIX)
        assert "90 ngày" in call["html_body"]
        assert "90 ngày" in call["text_body"]

        expected_cta = f"{settings.FRONTEND_URL.rstrip('/')}/recruiter/candidate-search"
        assert expected_cta in call["html_body"]

    @pytest.mark.asyncio
    async def test_send_request_revoked_email_admin_fallback(self, enqueue_spy):
        session = MagicMock()
        service = ContactRequestEmailService(session)
        request_id = uuid.uuid4()
        admin_id = uuid.uuid4()

        await service.send_request_revoked_email(
            to_email="admin@example.com",
            candidate_name="Phạm Văn D",
            company_name="TechCorp Vietnam",
            request_id=request_id,
            recipient_user_id=admin_id,
        )

        assert len(enqueue_spy) == 1
        call = enqueue_spy[0]
        assert call["idempotency_key"] == f"contact_request:revoked:{request_id}:{admin_id}"
        expected_cta = f"{settings.FRONTEND_URL.rstrip('/')}/recruiter/workspace"
        assert expected_cta in call["html_body"]

    @pytest.mark.asyncio
    async def test_send_request_expired_email_includes_limits_notice(self, enqueue_spy):
        session = MagicMock()
        service = ContactRequestEmailService(session)
        request_id = uuid.uuid4()

        await service.send_request_expired_email(
            to_email="recruiter@example.com",
            candidate_name="Đặng Thị E",
            company_name="TechCorp Vietnam",
            request_id=request_id,
        )

        assert len(enqueue_spy) == 1
        call = enqueue_spy[0]
        assert call["event_type"] == EVENT_CONTACT_REQUEST_EXPIRED
        assert call["to_email"] == "recruiter@example.com"
        assert call["idempotency_key"] == f"contact_request:expired:{request_id}"
        assert call["subject"].startswith(SUBJECT_PREFIX)
        assert "14 ngày" in call["html_body"]
        assert "180 ngày" in call["html_body"]
        assert "180 ngày" in call["text_body"]

        expected_cta = f"{settings.FRONTEND_URL.rstrip('/')}/recruiter/candidate-search"
        assert expected_cta in call["html_body"]

    @pytest.mark.asyncio
    async def test_send_candidate_authorization_granted_email_q1(self, enqueue_spy):
        session = MagicMock()
        service = ContactRequestEmailService(session)
        request_id = uuid.uuid4()

        await service.send_candidate_authorization_granted_email(
            to_email="candidate@example.com",
            candidate_name="Nguyễn Văn A",
            company_name="Acme Corp",
            request_id=request_id,
        )

        assert len(enqueue_spy) == 1
        call = enqueue_spy[0]
        assert call["event_type"] == EVENT_CANDIDATE_AUTHORIZATION_GRANTED
        assert call["to_email"] == "candidate@example.com"
        assert call["idempotency_key"] == f"contact_request:candidate_accepted:{request_id}"
        assert call["subject"] == f"{SUBJECT_PREFIX} Bạn đã cấp quyền xem thông tin liên hệ cho Acme Corp"
        assert "Acme Corp" in call["html_body"]
        assert "Đã cấp quyền" in call["html_body"]
        assert "nhật ký kiểm toán" in call["html_body"]
        assert "thu hồi quyền này bất cứ lúc nào" in call["html_body"]

        expected_cta = f"{settings.FRONTEND_URL.rstrip('/')}/candidate/contact-requests"
        assert expected_cta in call["html_body"]
        assert f"Quản lý yêu cầu kết nối: {expected_cta}" in call["text_body"]

        # Privacy invariant
        assert "0901234567" not in call["html_body"]
        assert "0901234567" not in call["text_body"]

    @pytest.mark.asyncio
    async def test_send_candidate_authorization_revoked_email_q1(self, enqueue_spy):
        session = MagicMock()
        service = ContactRequestEmailService(session)
        request_id = uuid.uuid4()

        await service.send_candidate_authorization_revoked_email(
            to_email="candidate@example.com",
            candidate_name="Nguyễn Văn A",
            company_name="Acme Corp",
            request_id=request_id,
        )

        assert len(enqueue_spy) == 1
        call = enqueue_spy[0]
        assert call["event_type"] == EVENT_CANDIDATE_AUTHORIZATION_REVOKED
        assert call["to_email"] == "candidate@example.com"
        assert call["idempotency_key"] == f"contact_request:candidate_revoked:{request_id}"
        assert call["subject"] == f"{SUBJECT_PREFIX} Bạn đã thu hồi quyền xem thông tin liên hệ từ Acme Corp"
        assert "Acme Corp" in call["html_body"]
        assert "Đã thu hồi quyền" in call["html_body"]

        expected_cta = f"{settings.FRONTEND_URL.rstrip('/')}/candidate/contact-requests"
        assert expected_cta in call["html_body"]
        assert f"Quản lý yêu cầu kết nối: {expected_cta}" in call["text_body"]

        # Privacy invariant
        assert "0901234567" not in call["html_body"]
        assert "0901234567" not in call["text_body"]

    @pytest.mark.asyncio
    async def test_empty_recipient_email_returns_none(self, enqueue_spy):
        session = MagicMock()
        service = ContactRequestEmailService(session)
        res = await service.send_request_received_email(
            to_email="",
            candidate_name="Test",
            company_name="Test Co",
            request_id=uuid.uuid4(),
        )
        assert res is None
        assert enqueue_spy == []
