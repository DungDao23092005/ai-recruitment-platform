from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pubsub import pubsub_manager
from app.domain.models.base import utc_now

logger = logging.getLogger(__name__)

# Dedicated admin channel. Only admin-authenticated streams subscribe to it.
ADMIN_SUBSCRIPTIONS_CHANNEL = "admin:subscriptions"

# SSE event name emitted for admin subscription invalidations. The frontend
# listens for this named event and rebroadcasts a DOM ``admin:subscription:changed``.
ADMIN_SUBSCRIPTION_CHANGED_EVENT = "admin.subscription.changed"

# Action vocabulary shared with the frontend. Keep this list minimal: events
# only carry enough data to invalidate/refetch, never email addresses, plan
# names, amounts, payment details or audit reasons.
ACTION_ACTIVATED = "activated"
ACTION_PLAN_CHANGED = "plan_changed"
ACTION_REVOKED = "revoked"
ACTION_ORDER_CREATED = "order_created"

VALID_ACTIONS = frozenset(
    {ACTION_ACTIVATED, ACTION_PLAN_CHANGED, ACTION_REVOKED, ACTION_ORDER_CREATED}
)


def build_admin_subscription_event(
    *,
    user_id: uuid.UUID | str,
    subscription_id: Optional[uuid.UUID | str],
    action: str,
) -> dict:
    """Build the minimal invalidation payload published to admins."""
    return {
        "type": ADMIN_SUBSCRIPTION_CHANGED_EVENT,
        "user_id": str(user_id),
        "subscription_id": str(subscription_id) if subscription_id is not None else None,
        "action": action,
        "timestamp": utc_now().isoformat(),
    }


def schedule_admin_subscription_event(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | str,
    subscription_id: Optional[uuid.UUID | str],
    action: str,
) -> None:
    """Publish an admin invalidation event after ``session`` commits.

    The event is registered on ``after_commit`` so it can only fire once the
    subscription/payment mutation is durably committed. Publishing runs in a
    fire-and-forget task; ``PubSubManager.publish`` swallows and logs Redis
    failures, so a Redis outage can never roll back a committed mutation or make
    the mutating API fail.
    """
    message = build_admin_subscription_event(
        user_id=user_id, subscription_id=subscription_id, action=action
    )

    async def _publish_safely() -> None:
        try:
            await pubsub_manager.publish(ADMIN_SUBSCRIPTIONS_CHANNEL, message)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to publish admin subscription event: %s", exc)

    def _publish_after_commit(sync_session) -> None:  # noqa: ARG001
        try:
            asyncio.create_task(_publish_safely())
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to schedule admin subscription event: %s", exc)

    event.listen(
        session.sync_session, "after_commit", _publish_after_commit, once=True
    )
