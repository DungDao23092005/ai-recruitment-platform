"""Real-time "account.locked" signal for forced logout.

When an admin locks an account that is currently in use, the locked user's
browser must be evicted immediately and shown a one-time notice on the public
homepage. This module mirrors ``subscription_realtime``: it publishes a minimal
payload to the user's *private* channel (never the shared admin channel), only
after the surrounding transaction durably commits, and it never raises into the
caller.

Security notes:

* The event is published on ``notifications:user:{user_id}`` so only that user's
  authenticated SSE stream can receive it.
* The payload carries no email address, token or admin identity - only the
  target user id, the validated lock reason and the authoritative lock time.
* The client-side eviction is a convenience; the backend ``is_active`` guard in
  ``get_current_active_user`` remains the authoritative enforcement.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pubsub import pubsub_manager

logger = logging.getLogger(__name__)

# SSE event name emitted on the locked user's private channel. The frontend
# listens for this named event, stores a one-time notice and clears its session.
ACCOUNT_LOCKED_EVENT = "account.locked"


def _isoformat(value: datetime | None) -> Optional[str]:
    """Render a possibly naive UTC datetime as an ISO-8601 string."""
    if value is None:
        return None
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware.isoformat()


def build_account_locked_event(
    *,
    user_id: uuid.UUID | str,
    reason: Optional[str] = None,
    locked_at: datetime | None = None,
) -> dict:
    """Build the minimal lock payload published to the user's private channel."""
    return {
        "type": ACCOUNT_LOCKED_EVENT,
        "user_id": str(user_id),
        "reason": reason,
        "locked_at": _isoformat(locked_at),
    }


def schedule_account_locked_event(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | str,
    reason: Optional[str] = None,
    locked_at: datetime | None = None,
) -> None:
    """Publish an account-locked event to the user's stream after ``session`` commits.

    The callback is registered on ``after_commit`` so a rolled-back lock never
    notifies the user. Registration is defensive: a session that cannot host
    event listeners (for example a mock in a unit test) must never make the
    admin operation fail. Publication is fire-and-forget and
    ``PubSubManager.publish`` swallows Redis failures, so a Redis outage can
    never roll back the committed lock.
    """
    channel = pubsub_manager.get_user_channel(str(user_id))
    message = build_account_locked_event(
        user_id=user_id, reason=reason, locked_at=locked_at
    )

    async def _publish_safely() -> None:
        try:
            await pubsub_manager.publish(channel, message)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to publish account-locked event: %s", exc)

    def _publish_after_commit(sync_session) -> None:  # noqa: ARG001
        try:
            asyncio.create_task(_publish_safely())
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to schedule account-locked event: %s", exc)

    try:
        event.listen(
            session.sync_session, "after_commit", _publish_after_commit, once=True
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Failed to register after-commit hook for account-locked event: %s", exc
        )
