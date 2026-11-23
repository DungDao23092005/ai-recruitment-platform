"""Integration tests for the notification stream endpoint and jobs:public multiplexing."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.notifications import notification_stream
from app.services.job_realtime import (
    ACTION_PUBLISHED,
    JOB_LISTING_UPDATED_EVENT,
    JOBS_PUBLIC_CHANNEL,
    build_job_listing_event,
)


class _MockPubSub:
    def __init__(self, messages: list[dict] | None = None) -> None:
        self.messages = list(messages or [])
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.closed = False

    async def subscribe(self, *channels: str) -> None:
        self.subscribed.extend(channels)

    async def get_message(self, ignore_subscribe_messages: bool = True, timeout: float = 1.0):
        if self.messages:
            return self.messages.pop(0)
        raise asyncio.CancelledError

    async def unsubscribe(self, *channels: str) -> None:
        self.unsubscribed.extend(channels)

    async def close(self) -> None:
        self.closed = True


class _MockRedis:
    def __init__(self, ticket_data: dict | None, pubsub: _MockPubSub) -> None:
        self._store = {}
        self._pubsub = pubsub
        if ticket_data is not None:
            self._store["notification:stream_ticket:test-ticket"] = json.dumps(ticket_data)

    async def get(self, key: str):
        return self._store.get(key)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def pubsub(self) -> _MockPubSub:
        return self._pubsub


class _MockPubSubManager:
    def __init__(self, ticket_data: dict | None, pubsub: _MockPubSub) -> None:
        self._redis = _MockRedis(ticket_data, pubsub)


@pytest.mark.asyncio
async def test_stream_enforces_single_use_ticket():
    user_id = uuid.uuid4()
    ticket_payload = {"user_id": str(user_id), "is_admin": False}
    pubsub = _MockPubSub()
    manager = _MockPubSubManager(ticket_payload, pubsub)

    # First consumption: ticket is valid and consumed
    resp = await notification_stream(ticket="test-ticket", pubsub=manager)
    assert resp.status_code == 200

    # Second consumption with same ticket: fails with 401
    with pytest.raises(HTTPException) as exc_info:
        await notification_stream(ticket="test-ticket", pubsub=manager)
    assert exc_info.value.status_code == 401
    assert "Invalid or expired ticket" in exc_info.value.detail


@pytest.mark.asyncio
async def test_stream_invalid_ticket_raises_401():
    pubsub = _MockPubSub()
    manager = _MockPubSubManager(None, pubsub)

    with pytest.raises(HTTPException) as exc_info:
        await notification_stream(ticket="non-existent-ticket", pubsub=manager)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_candidate_receives_job_listing_updated_without_private_data():
    candidate_id = uuid.uuid4()
    job_id = uuid.uuid4()

    event_payload = build_job_listing_event(
        action=ACTION_PUBLISHED,
        job_id=job_id,
        affected_count=1,
    )

    raw_message = {
        "type": "message",
        "channel": JOBS_PUBLIC_CHANNEL,
        "data": json.dumps(event_payload),
    }

    pubsub = _MockPubSub([raw_message])
    manager = _MockPubSubManager(
        {"user_id": str(candidate_id), "is_admin": False},
        pubsub,
    )

    response = await notification_stream(ticket="test-ticket", pubsub=manager)
    assert response.status_code == 200

    # Read events from the generator
    chunks: list[str] = []
    try:
        async for chunk in response.body_iterator:
            chunks.append(chunk)
    except asyncio.CancelledError:
        pass

    # Candidate stream must be subscribed to JOBS_PUBLIC_CHANNEL
    assert JOBS_PUBLIC_CHANNEL in pubsub.subscribed
    assert f"notifications:user:{candidate_id}" in pubsub.subscribed

    full_output = "".join(chunks)
    assert "event: connected" in full_output
    assert f"event: {JOB_LISTING_UPDATED_EVENT}" in full_output
    assert str(job_id) in full_output
    assert ACTION_PUBLISHED in full_output

    # Verify no private data leaked
    lowered = full_output.lower()
    for forbidden in ("candidate_name", "applicant", "recruiter_email", "resume_url", "salary"):
        assert forbidden not in lowered
