"""Unit tests for public job listing realtime invalidation events."""

from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.services.job_realtime import (
    ACTION_CLOSED,
    ACTION_DELETED,
    ACTION_EXPIRED,
    ACTION_PUBLISHED,
    JOB_LISTING_UPDATED_EVENT,
    JOBS_PUBLIC_CHANNEL,
    VALID_ACTIONS,
    build_job_listing_event,
    schedule_job_listing_event,
)

_PUBSUB_TARGET = "app.services.job_realtime.pubsub_manager"


def _manager() -> MagicMock:
    manager = MagicMock()
    manager.publish = AsyncMock()
    return manager


def _double() -> SimpleNamespace:
    return SimpleNamespace(sync_session=Session())


def _run(coro) -> None:
    asyncio.run(coro)


def test_payload_structure_and_types():
    job_id = uuid.uuid4()
    payload = build_job_listing_event(
        action=ACTION_PUBLISHED,
        job_id=job_id,
        affected_count=1,
    )

    assert set(payload.keys()) == {
        "type",
        "action",
        "job_id",
        "affected_count",
        "timestamp",
    }
    assert payload["type"] == JOB_LISTING_UPDATED_EVENT
    assert payload["action"] == ACTION_PUBLISHED
    assert payload["job_id"] == str(job_id)
    assert payload["affected_count"] == 1
    assert isinstance(payload["timestamp"], str)

    # Invalidation payload must be PII-free and leak no private data
    serialized = json.dumps(payload).lower()
    for forbidden in ("email", "title", "description", "recruiter", "salary", "candidate"):
        assert forbidden not in serialized


def test_channel_name_and_action_constants():
    assert JOBS_PUBLIC_CHANNEL == "jobs:public"
    assert JOB_LISTING_UPDATED_EVENT == "job.listing.updated"
    assert VALID_ACTIONS == {
        ACTION_PUBLISHED,
        ACTION_CLOSED,
        ACTION_DELETED,
        ACTION_EXPIRED,
    }


def test_validation_rejects_invalid_action_count_or_job_id():
    with pytest.raises(ValueError, match="Unsupported job listing action"):
        build_job_listing_event(action="invalid_action")

    with pytest.raises(ValueError, match="affected_count must be at least 1"):
        build_job_listing_event(action=ACTION_EXPIRED, affected_count=0)

    with pytest.raises(ValueError, match="job_id must be a valid UUID"):
        build_job_listing_event(action=ACTION_PUBLISHED, job_id="not-a-uuid")


def test_after_commit_publishes_event():
    manager = _manager()
    session = _double()
    job_id = uuid.uuid4()

    async def _run_test():
        session.sync_session.begin()
        with patch(_PUBSUB_TARGET, manager):
            schedule_job_listing_event(
                session,
                action=ACTION_PUBLISHED,
                job_id=job_id,
            )
            session.sync_session.commit()
            await asyncio.sleep(0.01)

    _run(_run_test())

    assert manager.publish.await_count == 1
    channel, message = manager.publish.await_args.args
    assert channel == JOBS_PUBLIC_CHANNEL
    assert message["type"] == JOB_LISTING_UPDATED_EVENT
    assert message["action"] == ACTION_PUBLISHED
    assert message["job_id"] == str(job_id)
    assert message["affected_count"] == 1


def test_rollback_discards_events():
    manager = _manager()
    session = _double()
    job_id = uuid.uuid4()

    async def _run_test():
        session.sync_session.begin()
        with patch(_PUBSUB_TARGET, manager):
            schedule_job_listing_event(
                session,
                action=ACTION_CLOSED,
                job_id=job_id,
            )
            session.sync_session.rollback()
            session.sync_session.begin()
            session.sync_session.commit()
            await asyncio.sleep(0.01)

    _run(_run_test())

    assert manager.publish.await_count == 0


def test_coalesced_expiration_payload():
    manager = _manager()
    session = _double()

    async def _run_test():
        session.sync_session.begin()
        with patch(_PUBSUB_TARGET, manager):
            schedule_job_listing_event(
                session,
                action=ACTION_EXPIRED,
                affected_count=3,
            )
            schedule_job_listing_event(
                session,
                action=ACTION_EXPIRED,
                affected_count=5,
            )
            session.sync_session.commit()
            await asyncio.sleep(0.01)

    _run(_run_test())

    assert manager.publish.await_count == 1
    channel, message = manager.publish.await_args.args
    assert channel == JOBS_PUBLIC_CHANNEL
    assert message["type"] == JOB_LISTING_UPDATED_EVENT
    assert message["action"] == ACTION_EXPIRED
    assert message["job_id"] is None
    assert message["affected_count"] == 8


def test_redis_error_is_non_fatal():
    manager = _manager()
    manager.publish.side_effect = ConnectionError("Redis is offline")
    session = _double()
    job_id = uuid.uuid4()

    async def _run_test():
        session.sync_session.begin()
        with patch(_PUBSUB_TARGET, manager):
            schedule_job_listing_event(
                session,
                action=ACTION_DELETED,
                job_id=job_id,
            )
            # Should not raise exception
            session.sync_session.commit()
            await asyncio.sleep(0.01)

    _run(_run_test())
    assert manager.publish.await_count == 1
