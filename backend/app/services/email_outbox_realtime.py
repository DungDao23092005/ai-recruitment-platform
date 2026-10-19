"""Realtime invalidation events for the admin email-outbox view.

Admins watching ``/admin/emails`` should see delivery state change without a
manual reload. This module publishes the minimal, PII-free signal that drives
those updates: an outbox message identifier, its new status, the transition
that produced it, and delivery metadata (attempts, timestamps).

Publishing is a best-effort optimization layered on top of the durable outbox.
The persisted row is always the source of truth, so a Redis outage can never
change delivery behaviour or fail a mutating request. Events are only scheduled
on ``after_commit`` so a subscriber can never observe a state the database did
not durably record.

Nothing here may ever carry recipient addresses, subjects, message bodies,
provider error text, user identities, OTP material or secrets - those are
forbidden by design (they stay in the outbox row, which only admins read).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pubsub import pubsub_manager
from app.domain.enums import OutboxStatus
from app.domain.models.base import utc_now

logger = logging.getLogger(__name__)

# Dedicated admin channel. Only admin-authenticated streams subscribe to it.
ADMIN_EMAILS_CHANNEL = "admin:emails"

# SSE event name emitted for admin email-outbox updates. The frontend listens
# for this named event and rebroadcasts a DOM ``admin:email_outbox:updated``.
EMAIL_OUTBOX_UPDATED_EVENT = "email.outbox.updated"

# Transition vocabulary shared with the frontend. Keep it closed and minimal.
ACTION_ENQUEUED = "enqueued"
ACTION_CLAIMED = "claimed"
ACTION_SENT = "sent"
ACTION_RETRY_SCHEDULED = "retry_scheduled"
ACTION_FAILED = "failed"
ACTION_LEASE_RECOVERED = "lease_recovered"
ACTION_ADMIN_RETRY = "admin_retry"

VALID_ACTIONS = frozenset(
    {
        ACTION_ENQUEUED,
        ACTION_CLAIMED,
        ACTION_SENT,
        ACTION_RETRY_SCHEDULED,
        ACTION_FAILED,
        ACTION_LEASE_RECOVERED,
        ACTION_ADMIN_RETRY,
    }
)

VALID_STATUSES = frozenset(status.value for status in OutboxStatus)

# Exact key set a payload may expose. Any addition here is a deliberate,
# reviewed decision; the payload is the only email-outbox data sent to clients.
ALLOWED_EVENT_KEYS = frozenset(
    {
        "type",
        "message_id",
        "status",
        "action",
        "attempts",
        "max_attempts",
        "next_attempt_at",
        "sent_at",
        "has_error",
        "timestamp",
    }
)


def _isoformat(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def build_email_outbox_event(
    *,
    message_id: Optional[uuid.UUID | str],
    status: str,
    action: str,
    attempts: Optional[int] = None,
    max_attempts: Optional[int] = None,
    next_attempt_at: Optional[datetime] = None,
    sent_at: Optional[datetime] = None,
    has_error: bool = False,
) -> dict:
    """Build the minimal invalidation payload published to admins.

    ``message_id`` is ``None`` only for an aggregate signal (for example a
    generic lease-recovery notification) where no single message can be named.
    """
    return {
        "type": EMAIL_OUTBOX_UPDATED_EVENT,
        "message_id": str(message_id) if message_id is not None else None,
        "status": status,
        "action": action,
        "attempts": attempts,
        "max_attempts": max_attempts,
        "next_attempt_at": _isoformat(next_attempt_at),
        "sent_at": _isoformat(sent_at),
        "has_error": bool(has_error),
        "timestamp": utc_now().isoformat(),
    }


async def publish_email_outbox_event(message: dict) -> None:
    """Publish one event; Redis failures are logged, never raised."""
    try:
        await pubsub_manager.publish(ADMIN_EMAILS_CHANNEL, message)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to publish email outbox event: %s", exc)


def schedule_email_outbox_event(
    session: AsyncSession,
    *,
    message_id: Optional[uuid.UUID | str],
    status: str,
    action: str,
    attempts: Optional[int] = None,
    max_attempts: Optional[int] = None,
    next_attempt_at: Optional[datetime] = None,
    sent_at: Optional[datetime] = None,
    has_error: bool = False,
) -> None:
    """Publish an outbox status event once ``session`` commits.

    The event is registered on ``after_commit`` so it can only fire after the
    underlying mutation is durably committed. Publishing runs in a
    fire-and-forget task and ``PubSubManager.publish`` swallows Redis failures,
    so a Redis outage can never roll back a committed mutation or fail the
    mutating request. Registration itself is defensive because callers may pass
    a session that cannot host listeners (for example a test double).
    """
    message = build_email_outbox_event(
        message_id=message_id,
        status=status,
        action=action,
        attempts=attempts,
        max_attempts=max_attempts,
        next_attempt_at=next_attempt_at,
        sent_at=sent_at,
        has_error=has_error,
    )

    def _publish_after_commit(sync_session) -> None:  # noqa: ARG001
        try:
            asyncio.create_task(publish_email_outbox_event(message))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to schedule email outbox event: %s", exc)

    try:
        event.listen(
            session.sync_session, "after_commit", _publish_after_commit, once=True
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Could not register email outbox event hook: %s", exc)
