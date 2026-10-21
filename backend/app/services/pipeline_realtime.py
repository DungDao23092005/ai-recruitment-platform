"""Transaction-safe invalidation events for hiring-pipeline views.

Recruiters watching a job's applicant board and candidates watching their own
applications need to see changes made by the other party without a manual
reload. This module schedules compact, PII-free invalidation events on the
current database session and publishes them only after that session commits.

The session-scoped queue is deliberate: a simple ``after_commit`` listener per
event leaks a queued event across a rollback when the same session is reused,
and can publish duplicate events when a flow schedules the same invalidation
more than once. The queue is cleared on rollback, including savepoint rollback,
and identical invalidations are coalesced per channel/application.

Redis publication is best-effort and ephemeral. The authoritative REST
resources remain the source of truth; a missed event is recovered on SSE
reconnect or when the page becomes visible again.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pubsub import pubsub_manager
from app.domain.enums import ApplicationStatus
from app.domain.models.base import utc_now
from app.models import CandidateProfile

logger = logging.getLogger(__name__)

PIPELINE_UPDATED_EVENT = "pipeline.updated"
CANDIDATE_PIPELINE_UPDATED_EVENT = "candidate.pipeline.updated"

COMPANY_PIPELINE_CHANNEL_PREFIX = "company:"
COMPANY_PIPELINE_CHANNEL_SUFFIX = ":pipeline"

ACTION_APPLICATION_CREATED = "application_created"
ACTION_APPLICATION_WITHDRAWN = "application_withdrawn"
ACTION_APPLICATION_STATUS_CHANGED = "application_status_changed"
ACTION_INTERVIEW_SCHEDULED = "interview_scheduled"
ACTION_INTERVIEW_UPDATED = "interview_updated"
ACTION_INTERVIEW_CANCELLED = "interview_cancelled"
ACTION_INTERVIEW_CONFIRMED = "interview_confirmed"
ACTION_INTERVIEW_DECLINED = "interview_declined"
ACTION_OFFER_ACCEPTED = "offer_accepted"
ACTION_OFFER_DECLINED = "offer_declined"

VALID_ACTIONS = frozenset(
    {
        ACTION_APPLICATION_CREATED,
        ACTION_APPLICATION_WITHDRAWN,
        ACTION_APPLICATION_STATUS_CHANGED,
        ACTION_INTERVIEW_SCHEDULED,
        ACTION_INTERVIEW_UPDATED,
        ACTION_INTERVIEW_CANCELLED,
        ACTION_INTERVIEW_CONFIRMED,
        ACTION_INTERVIEW_DECLINED,
        ACTION_OFFER_ACCEPTED,
        ACTION_OFFER_DECLINED,
    }
)

VALID_STATUSES = frozenset(status.value for status in ApplicationStatus)

COMPANY_EVENT_KEYS = frozenset(
    {
        "type",
        "company_id",
        "job_id",
        "application_id",
        "action",
        "from_status",
        "to_status",
        "timestamp",
    }
)

CANDIDATE_EVENT_KEYS = frozenset(
    {
        "type",
        "job_id",
        "application_id",
        "action",
        "from_status",
        "to_status",
        "timestamp",
    }
)

_QUEUE_STATE_KEY = "pipeline_realtime_queue"


def company_pipeline_channel(company_id: uuid.UUID | str) -> str:
    return (
        f"{COMPANY_PIPELINE_CHANNEL_PREFIX}{company_id}"
        f"{COMPANY_PIPELINE_CHANNEL_SUFFIX}"
    )


def user_pipeline_channel(user_id: uuid.UUID | str) -> str:
    return f"notifications:user:{user_id}"


def _uuid_string(value: Any, field_name: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a UUID") from exc


def _status_value(value: Any) -> str | None:
    if value is None:
        return None
    raw = value.value if hasattr(value, "value") else str(value)
    if raw not in VALID_STATUSES:
        raise ValueError(f"Unsupported application status: {raw!r}")
    return raw


def _validate_action(action: str) -> None:
    if action not in VALID_ACTIONS:
        raise ValueError(f"Unsupported pipeline action: {action!r}")


def build_company_pipeline_event(
    *,
    company_id: uuid.UUID | str,
    job_id: uuid.UUID | str,
    application_id: uuid.UUID | str,
    action: str,
    from_status: Any = None,
    to_status: Any = None,
) -> dict:
    _validate_action(action)
    return {
        "type": PIPELINE_UPDATED_EVENT,
        "company_id": _uuid_string(company_id, "company_id"),
        "job_id": _uuid_string(job_id, "job_id"),
        "application_id": _uuid_string(application_id, "application_id"),
        "action": action,
        "from_status": _status_value(from_status),
        "to_status": _status_value(to_status),
        "timestamp": utc_now().isoformat(),
    }


def build_candidate_pipeline_event(
    *,
    job_id: uuid.UUID | str,
    application_id: uuid.UUID | str,
    action: str,
    from_status: Any = None,
    to_status: Any = None,
) -> dict:
    _validate_action(action)
    return {
        "type": CANDIDATE_PIPELINE_UPDATED_EVENT,
        "job_id": _uuid_string(job_id, "job_id"),
        "application_id": _uuid_string(application_id, "application_id"),
        "action": action,
        "from_status": _status_value(from_status),
        "to_status": _status_value(to_status),
        "timestamp": utc_now().isoformat(),
    }


def parse_pipeline_payload(raw: object) -> dict | None:
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return None
    return raw if isinstance(raw, dict) else None


def _has_valid_ids(payload: dict, keys: tuple[str, ...]) -> bool:
    for key in keys:
        try:
            uuid.UUID(str(payload.get(key)))
        except (TypeError, ValueError, AttributeError):
            return False
    return True


def _has_valid_statuses(payload: dict) -> bool:
    return all(
        payload.get(key) is None or payload.get(key) in VALID_STATUSES
        for key in ("from_status", "to_status")
    )


def is_company_pipeline_message(
    raw: object,
    *,
    company_id: uuid.UUID | str | None = None,
) -> bool:
    payload = parse_pipeline_payload(raw)
    if payload is None or set(payload.keys()) != COMPANY_EVENT_KEYS:
        return False
    if payload.get("type") != PIPELINE_UPDATED_EVENT:
        return False
    if payload.get("action") not in VALID_ACTIONS:
        return False
    if not _has_valid_ids(
        payload, ("company_id", "job_id", "application_id")
    ):
        return False
    if not _has_valid_statuses(payload):
        return False
    if not isinstance(payload.get("timestamp"), str) or not payload["timestamp"]:
        return False
    if company_id is not None and payload.get("company_id") != str(company_id):
        return False
    return True


def is_candidate_pipeline_message(raw: object) -> bool:
    payload = parse_pipeline_payload(raw)
    if payload is None or set(payload.keys()) != CANDIDATE_EVENT_KEYS:
        return False
    if payload.get("type") != CANDIDATE_PIPELINE_UPDATED_EVENT:
        return False
    if payload.get("action") not in VALID_ACTIONS:
        return False
    if not _has_valid_ids(payload, ("job_id", "application_id")):
        return False
    if not _has_valid_statuses(payload):
        return False
    if not isinstance(payload.get("timestamp"), str) or not payload["timestamp"]:
        return False
    return True


@dataclass
class _PipelineEventQueue:
    events: dict[tuple[str, str, str], tuple[str, dict]] = field(
        default_factory=dict
    )
    listeners_installed: bool = False


def _queue_for(sync_session: Any) -> _PipelineEventQueue:
    queue = sync_session.info.get(_QUEUE_STATE_KEY)
    if queue is None:
        queue = _PipelineEventQueue()
        sync_session.info[_QUEUE_STATE_KEY] = queue
    return queue


def _on_after_commit(sync_session: Any) -> None:
    queue = sync_session.info.get(_QUEUE_STATE_KEY)
    if queue is None:
        return
    pending = list(queue.events.values())
    queue.events.clear()
    for channel, message in pending:
        _schedule_publication(channel, message)


def _on_rollback(sync_session: Any) -> None:
    queue = sync_session.info.get(_QUEUE_STATE_KEY)
    if queue is not None:
        queue.events.clear()


def _on_soft_rollback(sync_session: Any, previous_transaction: Any) -> None:
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
        if not event.contains(sync_session, name, callback):
            event.listen(sync_session, name, callback)
    queue.listeners_installed = True


async def _publish_safely(channel: str, message: dict) -> None:
    try:
        await pubsub_manager.publish(channel, message)
    except Exception as exc:  # pragma: no cover - defensive boundary
        logger.warning(
            "Failed to publish pipeline invalidation on %s: %s", channel, exc
        )


def _schedule_publication(channel: str, message: dict) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_publish_safely(channel, message))
    except RuntimeError:
        logger.warning(
            "Could not schedule pipeline invalidation on %s: no running loop",
            channel,
        )
    except Exception as exc:  # pragma: no cover - defensive boundary
        logger.warning(
            "Could not schedule pipeline invalidation on %s: %s", channel, exc
        )


def _enqueue(session: AsyncSession, channel: str, message: dict) -> None:
    try:
        sync_session = session.sync_session
        _install_listeners(sync_session)
        queue = _queue_for(sync_session)
        key = (
            channel,
            str(message.get("type")),
            str(message.get("application_id")),
        )
        queue.events[key] = (channel, message)
    except Exception as exc:  # pragma: no cover - defensive boundary
        logger.warning("Could not queue pipeline invalidation: %s", exc)


def schedule_company_pipeline_event(
    session: AsyncSession, message: dict
) -> None:
    _enqueue(
        session,
        company_pipeline_channel(message["company_id"]),
        message,
    )


def schedule_candidate_pipeline_event(
    session: AsyncSession,
    *,
    candidate_user_id: uuid.UUID | str,
    message: dict,
) -> None:
    _enqueue(
        session,
        user_pipeline_channel(candidate_user_id),
        message,
    )


async def _resolve_candidate_user_id(
    session: AsyncSession,
    candidate_id: uuid.UUID,
) -> uuid.UUID | None:
    return await session.scalar(
        select(CandidateProfile.user_id).where(
            CandidateProfile.id == candidate_id
        )
    )


async def schedule_application_pipeline_event(
    session: AsyncSession,
    *,
    application: Any,
    action: str,
    from_status: Any = None,
    to_status: Any = None,
    candidate_user_id: uuid.UUID | str | None = None,
) -> None:
    """Queue company and candidate invalidations for one application mutation.

    Callers invoke this inside the same transaction as the mutation. Nothing is
    published until commit; rollback discards every queued invalidation. The
    helper is defensive so a malformed object or Redis boundary can never fail
    the underlying business operation.
    """
    try:
        job = getattr(application, "job", None)
        job_id = getattr(application, "job_id", None)
        if job_id is None and job is not None:
            job_id = getattr(job, "id", None)
        company_id = getattr(job, "company_id", None)
        if company_id is None:
            company = getattr(job, "company", None)
            company_id = getattr(company, "id", None)
        application_id = getattr(application, "id", None)

        if company_id is not None and job_id is not None and application_id is not None:
            company_event = build_company_pipeline_event(
                company_id=company_id,
                job_id=job_id,
                application_id=application_id,
                action=action,
                from_status=from_status,
                to_status=to_status,
            )
            schedule_company_pipeline_event(session, company_event)

        if job_id is None or application_id is None:
            return

        if candidate_user_id is None:
            candidate_id = getattr(application, "candidate_id", None)
            if candidate_id is not None:
                candidate_user_id = await _resolve_candidate_user_id(
                    session, candidate_id
                )
        if candidate_user_id is not None:
            candidate_event = build_candidate_pipeline_event(
                job_id=job_id,
                application_id=application_id,
                action=action,
                from_status=from_status,
                to_status=to_status,
            )
            schedule_candidate_pipeline_event(
                session,
                candidate_user_id=candidate_user_id,
                message=candidate_event,
            )
    except Exception as exc:  # pragma: no cover - defensive boundary
        logger.warning("Could not schedule pipeline invalidation: %s", exc)
