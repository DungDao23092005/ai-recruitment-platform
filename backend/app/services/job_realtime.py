"""Transaction-safe invalidation events for public job listings.

Job seekers and candidates watching public job listings need to see when jobs
are published, closed, deleted, or expired without a manual page reload.
This module schedules compact, PII-free invalidation events on the current
database session and publishes them only after that session commits.

Redis publication is best-effort and ephemeral. The authoritative REST
resources remain the source of truth; missed events are recovered on SSE
reconnect or when the page becomes visible again.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pubsub import pubsub_manager
from app.domain.models.base import utc_now

logger = logging.getLogger(__name__)

# Dedicated public channel for job listing updates.
# All authenticated notification streams subscribe to this channel.
JOBS_PUBLIC_CHANNEL = "jobs:public"

# SSE event name emitted for public job listing updates.
JOB_LISTING_UPDATED_EVENT = "job.listing.updated"

# Action vocabulary for job listing invalidations.
ACTION_PUBLISHED = "published"
ACTION_CLOSED = "closed"
ACTION_DELETED = "deleted"
ACTION_EXPIRED = "expired"

VALID_ACTIONS = frozenset(
    {ACTION_PUBLISHED, ACTION_CLOSED, ACTION_DELETED, ACTION_EXPIRED}
)

_QUEUE_STATE_KEY = "job_realtime_queue"


def build_job_listing_event(
    *,
    action: str,
    job_id: Optional[uuid.UUID | str] = None,
    affected_count: int = 1,
) -> dict[str, Any]:
    """Build the minimal, PII-free invalidation payload for public job listings."""
    if action not in VALID_ACTIONS:
        raise ValueError(f"Unsupported job listing action: {action!r}")
    if affected_count < 1:
        raise ValueError("affected_count must be at least 1")

    job_id_str: str | None = None
    if job_id is not None:
        try:
            job_id_str = str(uuid.UUID(str(job_id)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError(f"job_id must be a valid UUID: {job_id!r}") from exc

    return {
        "type": JOB_LISTING_UPDATED_EVENT,
        "action": action,
        "job_id": job_id_str,
        "affected_count": affected_count,
        "timestamp": utc_now().isoformat(),
    }


@dataclass
class _JobEventQueue:
    events: dict[str, dict[str, Any]] = field(default_factory=dict)
    listeners_installed: bool = False


def _get_sync_session(session: Any) -> Any:
    return getattr(session, "sync_session", session)


def _queue_for(sync_session: Any) -> _JobEventQueue:
    if not hasattr(sync_session, "info"):
        sync_session.info = {}
    queue = sync_session.info.get(_QUEUE_STATE_KEY)
    if queue is None:
        queue = _JobEventQueue()
        sync_session.info[_QUEUE_STATE_KEY] = queue
    return queue


def _on_after_commit(sync_session: Any) -> None:
    queue = sync_session.info.get(_QUEUE_STATE_KEY)
    if queue is None:
        return
    pending = list(queue.events.values())
    queue.events.clear()
    for message in pending:
        _schedule_publication(JOBS_PUBLIC_CHANNEL, message)


def _on_rollback(sync_session: Any) -> None:
    queue = sync_session.info.get(_QUEUE_STATE_KEY)
    if queue is not None:
        queue.events.clear()


def _on_soft_rollback(sync_session: Any, previous_transaction: Any = None) -> None:
    _on_rollback(sync_session)


def _install_listeners(sync_session: Any) -> None:
    queue = _queue_for(sync_session)
    if queue.listeners_installed:
        return
    listeners = (
        ("after_commit", _on_after_commit),
        ("after_rollback", _on_rollback),
        ("after_soft_rollback", _on_soft_rollback),
    )
    for name, callback in listeners:
        try:
            if not event.contains(sync_session, name, callback):
                event.listen(sync_session, name, callback)
        except Exception as exc:
            logger.debug("Could not register %s listener on session: %s", name, exc)
    queue.listeners_installed = True


async def _publish_safely(channel: str, message: dict[str, Any]) -> None:
    try:
        await pubsub_manager.publish(channel, message)
    except Exception as exc:  # pragma: no cover - defensive boundary
        logger.warning(
            "Failed to publish job listing invalidation on %s: %s", channel, exc
        )


def _schedule_publication(channel: str, message: dict[str, Any]) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_publish_safely(channel, message))
    except RuntimeError:
        logger.warning(
            "Could not schedule job listing invalidation on %s: no running loop",
            channel,
        )
    except Exception as exc:  # pragma: no cover - defensive boundary
        logger.warning(
            "Could not schedule job listing invalidation on %s: %s", channel, exc
        )


def schedule_job_listing_event(
    session: AsyncSession,
    *,
    action: str,
    job_id: Optional[uuid.UUID | str] = None,
    affected_count: int = 1,
) -> None:
    """Schedule a job listing invalidation to publish after ``session`` commits.

    Events are cleared on rollback (including savepoint rollback) and multiple
    expirations in the same transaction are coalesced into a single event with
    an aggregated affected_count.
    """
    sync_session = _get_sync_session(session)
    _install_listeners(sync_session)
    queue = _queue_for(sync_session)

    payload = build_job_listing_event(
        action=action, job_id=job_id, affected_count=affected_count
    )

    if action == ACTION_EXPIRED:
        key = "action:expired"
        if key in queue.events:
            existing = queue.events[key]
            existing["affected_count"] += affected_count
            existing["timestamp"] = payload["timestamp"]
        else:
            queue.events[key] = payload
    else:
        key = f"job:{action}:{payload['job_id']}"
        queue.events[key] = payload
