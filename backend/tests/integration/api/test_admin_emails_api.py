from __future__ import annotations

import uuid

import pytest

from tests.integration.api.conftest import API_V1
from tests.integration.conftest import run

from app.database.base_class import utc_now
from app.database.session import async_session_factory
from app.domain.enums import OutboxStatus
from app.models import EmailOutbox

pytestmark = pytest.mark.integration


def _seed_row(
    *,
    status: str = OutboxStatus.PENDING.value,
    event_type: str = "payment_receipt",
    to_email: str | None = None,
) -> uuid.UUID:
    email = to_email or f"{uuid.uuid4().hex[:8]}@example.com"

    async def _create():
        async with async_session_factory() as session:
            row = EmailOutbox(
                event_type=event_type,
                to_email=email,
                subject="Chủ đề",
                html_body="<p>secret body</p>",
                text_body="secret body",
                status=status,
                attempts=0,
                max_attempts=3,
                next_attempt_at=utc_now(),
                last_error="boom" if status == OutboxStatus.FAILED.value else None,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    return run(_create())


class TestAdminEmailsAuthorization:
    def test_anonymous_401(self, client):
        for method, url in [
            ("GET", f"{API_V1}/admin/emails"),
            ("GET", f"{API_V1}/admin/emails/stats"),
            ("POST", f"{API_V1}/admin/emails/{uuid.uuid4()}/retry"),
        ]:
            resp = run(client.request(method, url))
            assert resp.status_code == 401, resp.text

    def test_candidate_forbidden(self, candidate_client):
        assert (
            run(candidate_client.get(f"{API_V1}/admin/emails")).status_code == 403
        )

    def test_recruiter_forbidden(self, recruiter_client):
        assert (
            run(recruiter_client.get(f"{API_V1}/admin/emails")).status_code == 403
        )


class TestAdminEmailsList:
    def test_lists_rows_without_body_content(self, admin_client):
        message_id = _seed_row()

        resp = run(admin_client.get(f"{API_V1}/admin/emails"))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["id"] == str(message_id)
        assert item["event_type"] == "payment_receipt"
        assert item["status"] == OutboxStatus.PENDING.value
        # Raw content must never be exposed.
        assert "html_body" not in item
        assert "text_body" not in item
        assert "secret body" not in resp.text

    def test_filter_by_status(self, admin_client):
        _seed_row(status=OutboxStatus.SENT.value)
        _seed_row(status=OutboxStatus.FAILED.value)

        resp = run(
            admin_client.get(
                f"{API_V1}/admin/emails", params={"status": OutboxStatus.FAILED.value}
            )
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == OutboxStatus.FAILED.value

    def test_stats(self, admin_client):
        _seed_row(status=OutboxStatus.PENDING.value)
        _seed_row(status=OutboxStatus.SENT.value)
        _seed_row(status=OutboxStatus.FAILED.value)

        resp = run(admin_client.get(f"{API_V1}/admin/emails/stats"))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["pending"] == 1
        assert data["sent"] == 1
        assert data["failed"] == 1
        assert data["processing"] == 0
        assert data["total"] == 3


class TestAdminEmailsRetry:
    def test_retry_unknown_404(self, admin_client):
        resp = run(
            admin_client.post(f"{API_V1}/admin/emails/{uuid.uuid4()}/retry")
        )
        assert resp.status_code == 404

    def test_retry_processing_conflict(self, admin_client):
        message_id = _seed_row(status=OutboxStatus.PROCESSING.value)
        resp = run(
            admin_client.post(f"{API_V1}/admin/emails/{message_id}/retry")
        )
        assert resp.status_code == 409

    def test_retry_failed_resets_to_pending(self, admin_client):
        message_id = _seed_row(status=OutboxStatus.FAILED.value)
        resp = run(
            admin_client.post(f"{API_V1}/admin/emails/{message_id}/retry")
        )
        assert resp.status_code == 200, resp.text
        item = resp.json()
        assert item["status"] == OutboxStatus.PENDING.value
        assert item["attempts"] == 0

        verify = run(admin_client.get(f"{API_V1}/admin/emails"))
        assert verify.json()["items"][0]["status"] == OutboxStatus.PENDING.value
