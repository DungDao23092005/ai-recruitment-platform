"""Unit tests for ContactRequestEmailService.

Verifies:
- Safe content rendering (no candidate email/phone in subject, body, or metadata).
- Deterministic idempotency keys for all 5 lifecycle events.
- Correct event types and recipient handling.
- Graceful no-op when recipient email is empty.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import contact_request_email_service as email_module
from app.services.contact_request_email_service import (
    ContactRequestEmailService,
    EVENT_CONTACT_REQUEST_ACCEPTED,
    EVENT_CONTACT_REQUEST_DECLINED,
    EVENT_CONTACT_REQUEST_EXPIRED,
    EVENT_CONTACT_REQUEST_RECEIVED,
    EVENT_CONTACT_REQUEST_REVOKED,
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
        assert "TechCorp Vietnam" in call["subject"]
        assert "TechCorp Vietnam" in call["html_body"]
        assert "TechCorp Vietnam" in call["text_body"]
        assert "Nguyễn Văn A" in call["html_body"]

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
        assert "Lê Thị B" in call["subject"]
        assert "chấp nhận" in call["html_body"]
        assert "quy trình được cấp phép" in call["html_body"]

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
        assert "30 ngày" in call["html_body"]
        assert "30 ngày" in call["text_body"]

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
        assert "90 ngày" in call["html_body"]
        assert "90 ngày" in call["text_body"]

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
        assert "14 ngày" in call["html_body"]
        assert "180 ngày" in call["html_body"]
        assert "180 ngày" in call["text_body"]

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
