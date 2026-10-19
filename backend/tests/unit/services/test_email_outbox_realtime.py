"""Unit tests for the admin email-outbox realtime event payload and publisher."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.services import email_outbox_realtime as realtime
from app.services.email_outbox_realtime import (
    ACTION_ADMIN_RETRY,
    ACTION_CLAIMED,
    ACTION_ENQUEUED,
    ACTION_FAILED,
    ACTION_LEASE_RECOVERED,
    ACTION_RETRY_SCHEDULED,
    ACTION_SENT,
    ADMIN_EMAILS_CHANNEL,
    ALLOWED_EVENT_KEYS,
    EMAIL_OUTBOX_UPDATED_EVENT,
    VALID_ACTIONS,
    VALID_STATUSES,
    build_email_outbox_event,
    publish_email_outbox_event,
    schedule_email_outbox_event,
)

_NOW = datetime(2026, 1, 15, 3, 30, tzinfo=timezone.utc)


class _SessionStub:
    """Minimal stand-in exposing the ``sync_session`` the publisher registers on."""

    def __init__(self, sync_session) -> None:
        self.sync_session = sync_session


def test_payload_exposes_only_allowed_keys_and_no_sensitive_fields():
    message_id = uuid.uuid4()

    payload = build_email_outbox_event(
        message_id=message_id,
        status="failed",
        action=ACTION_FAILED,
        attempts=3,
        max_attempts=3,
        next_attempt_at=_NOW,
        sent_at=None,
        has_error=True,
    )

    assert set(payload.keys()) == ALLOWED_EVENT_KEYS
    assert payload["type"] == EMAIL_OUTBOX_UPDATED_EVENT
    assert payload["message_id"] == str(message_id)
    assert payload["status"] == "failed"
    assert payload["action"] == ACTION_FAILED
    assert payload["attempts"] == 3
    assert payload["max_attempts"] == 3
    assert payload["next_attempt_at"] == _NOW.isoformat()
    assert payload["sent_at"] is None
    assert payload["has_error"] is True
    assert payload["timestamp"]

    # Forbidden fields must never be present.
    for forbidden in (
        "to_email",
        "email",
        "subject",
        "html_body",
        "text_body",
        "last_error",
        "error",
        "user_id",
        "otp",
        "token",
    ):
        assert forbidden not in payload


def test_payload_contains_no_recipient_address_or_body_text():
    payload = build_email_outbox_event(
        message_id=uuid.uuid4(),
        status="sent",
        action=ACTION_SENT,
        sent_at=_NOW,
    )

    serialized = str(payload)
    assert "buyer@example.com" not in serialized
    assert "password" not in serialized.lower()
    assert "<html" not in serialized.lower()


def test_payload_supports_aggregate_signal_without_message_id():
    payload = build_email_outbox_event(
        message_id=None,
        status="pending",
        action=ACTION_LEASE_RECOVERED,
    )

    assert payload["message_id"] is None
    assert payload["status"] == "pending"
    assert payload["action"] == ACTION_LEASE_RECOVERED


def test_vocabularies_are_closed():
    assert VALID_ACTIONS == {
        ACTION_ENQUEUED,
        ACTION_CLAIMED,
        ACTION_SENT,
        ACTION_RETRY_SCHEDULED,
        ACTION_FAILED,
        ACTION_LEASE_RECOVERED,
        ACTION_ADMIN_RETRY,
    }
    assert VALID_STATUSES == {"pending", "processing", "sent", "failed"}


async def test_publish_targets_admin_channel_and_swallows_errors():
    with patch.object(
        realtime.pubsub_manager, "publish", new=AsyncMock(return_value=2)
    ) as publish:
        await publish_email_outbox_event({"action": ACTION_SENT})
        publish.assert_awaited_once_with(
            ADMIN_EMAILS_CHANNEL, {"action": ACTION_SENT}
        )

    with patch.object(
        realtime.pubsub_manager,
        "publish",
        new=AsyncMock(side_effect=RuntimeError("redis down")),
    ):
        # A Redis outage must never propagate to the caller.
        await publish_email_outbox_event({"action": ACTION_SENT})


def test_schedule_publishes_only_after_commit():
    async def _run():
        engine = create_engine("sqlite://")
        with Session(engine) as sync_session:
            session = _SessionStub(sync_session)
            sync_session.execute(text("SELECT 1"))

            with patch.object(
                realtime.pubsub_manager, "publish", new=AsyncMock(return_value=1)
            ) as publish:
                schedule_email_outbox_event(
                    session,  # type: ignore[arg-type]
                    message_id=uuid.uuid4(),
                    status="pending",
                    action=ACTION_ENQUEUED,
                )
                # Nothing is published before the transaction commits.
                publish.assert_not_awaited()

                sync_session.commit()
                await asyncio.sleep(0)

            publish.assert_awaited_once()
            channel, message = publish.await_args.args
            assert channel == ADMIN_EMAILS_CHANNEL
            assert message["action"] == ACTION_ENQUEUED

    asyncio.run(_run())


def test_schedule_is_defensive_with_non_listener_session():
    # A test double that cannot host SQLAlchemy events must never break the
    # caller's mutation.
    schedule_email_outbox_event(
        MagicMock(),  # type: ignore[arg-type]
        message_id=uuid.uuid4(),
        status="pending",
        action=ACTION_ENQUEUED,
    )
