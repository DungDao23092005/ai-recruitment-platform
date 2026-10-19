"""Unit tests for the SSE notification stream authorization and dispatch.

The stream endpoint is invoked directly with a fake PubSub manager so the
admin-channel authorization and event naming can be asserted without a live
Redis connection or an indefinitely open HTTP stream.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import notifications as notifications_module
from app.api.v1.endpoints.notifications import notification_stream
from app.services.account_lock_realtime import ACCOUNT_LOCKED_EVENT
from app.services.email_outbox_realtime import (
    ADMIN_EMAILS_CHANNEL,
    EMAIL_OUTBOX_UPDATED_EVENT,
)
from app.services.subscription_realtime import (
    ADMIN_SUBSCRIPTIONS_CHANNEL,
    ADMIN_SUBSCRIPTION_CHANGED_EVENT,
)


class _FakePubSub:
    def __init__(self, messages: list[dict] | None = None, *, empty_returns_none: bool = False) -> None:
        self._messages = list(messages or [])
        self._empty_returns_none = empty_returns_none
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.closed = False

    async def subscribe(self, *channels: str) -> None:
        self.subscribed.extend(channels)

    async def get_message(self, ignore_subscribe_messages: bool = True, timeout: float = 1.0):
        if self._messages:
            return self._messages.pop(0)
        if self._empty_returns_none:
            return None
        raise asyncio.CancelledError

    async def unsubscribe(self, *channels: str) -> None:
        self.unsubscribed.extend(channels)

    async def close(self) -> None:
        self.closed = True


class _FakeRedis:
    def __init__(self, value: str | None, pubsub: _FakePubSub) -> None:
        self._value = value
        self._pubsub = pubsub
        self.deleted: list[str] = []

    async def get(self, key: str):
        return self._value

    async def delete(self, key: str) -> None:
        self.deleted.append(key)

    def pubsub(self) -> _FakePubSub:
        return self._pubsub


class _FakePubSubManager:
    def __init__(self, value: str | None, pubsub: _FakePubSub) -> None:
        self._redis = _FakeRedis(value, pubsub)


def _ticket(user_id: uuid.UUID, *, is_admin: bool) -> str:
    return json.dumps({"user_id": str(user_id), "is_admin": is_admin})


def _message(channel: str, payload: dict) -> dict:
    return {"type": "message", "channel": channel, "data": json.dumps(payload)}


async def _next(generator):
    return await generator.__anext__()


async def test_admin_ticket_subscribes_personal_and_admin_channels():
    user_id = uuid.uuid4()
    event = {"user_id": str(user_id), "action": "activated"}
    pubsub = _FakePubSub([_message(ADMIN_SUBSCRIPTIONS_CHANNEL, event)])
    manager = _FakePubSubManager(_ticket(user_id, is_admin=True), pubsub)

    response = await notification_stream(ticket="t", pubsub=manager)  # type: ignore[arg-type]
    generator = response.body_iterator

    connected = await _next(generator)
    assert "event: connected" in connected
    admin_event = await _next(generator)
    await generator.aclose()

    assert set(pubsub.subscribed) == {
        f"notifications:user:{user_id}",
        ADMIN_SUBSCRIPTIONS_CHANNEL,
        ADMIN_EMAILS_CHANNEL,
    }
    assert f"event: {ADMIN_SUBSCRIPTION_CHANGED_EVENT}" in admin_event
    assert '"action": "activated"' in admin_event


async def test_admin_email_outbox_message_uses_named_event():
    user_id = uuid.uuid4()
    payload = {
        "type": EMAIL_OUTBOX_UPDATED_EVENT,
        "message_id": str(uuid.uuid4()),
        "status": "sent",
        "action": "sent",
    }
    pubsub = _FakePubSub([_message(ADMIN_EMAILS_CHANNEL, payload)])
    manager = _FakePubSubManager(_ticket(user_id, is_admin=True), pubsub)

    response = await notification_stream(ticket="t", pubsub=manager)  # type: ignore[arg-type]
    generator = response.body_iterator

    await _next(generator)
    outbox_event = await _next(generator)
    await generator.aclose()

    assert ADMIN_EMAILS_CHANNEL in pubsub.subscribed
    assert f"event: {EMAIL_OUTBOX_UPDATED_EVENT}" in outbox_event
    assert "event: notification.created" not in outbox_event
    assert f"event: {ADMIN_SUBSCRIPTION_CHANGED_EVENT}" not in outbox_event
    data_line = next(
        line for line in outbox_event.splitlines() if line.startswith("data: ")
    )
    parsed = json.loads(data_line[len("data: ") :])
    assert parsed["status"] == "sent"


async def test_non_admin_ticket_never_subscribes_admin_channel():
    user_id = uuid.uuid4()
    pubsub = _FakePubSub([_message(f"notifications:user:{user_id}", {"type": "x"})])
    manager = _FakePubSubManager(_ticket(user_id, is_admin=False), pubsub)

    response = await notification_stream(ticket="t", pubsub=manager)  # type: ignore[arg-type]
    generator = response.body_iterator
    await _next(generator)
    personal_event = await _next(generator)
    await generator.aclose()

    assert pubsub.subscribed == [f"notifications:user:{user_id}"]
    assert ADMIN_SUBSCRIPTIONS_CHANNEL not in pubsub.subscribed
    assert ADMIN_EMAILS_CHANNEL not in pubsub.subscribed
    assert "event: notification.created" in personal_event


async def test_personal_channel_messages_keep_notification_event_name():
    user_id = uuid.uuid4()
    pubsub = _FakePubSub(
        [_message(f"notifications:user:{user_id}", {"notification_type": "x"})]
    )
    manager = _FakePubSubManager(_ticket(user_id, is_admin=True), pubsub)

    response = await notification_stream(ticket="t", pubsub=manager)  # type: ignore[arg-type]
    generator = response.body_iterator
    await _next(generator)
    personal_event = await _next(generator)
    await generator.aclose()

    assert "event: notification.created" in personal_event
    assert ADMIN_SUBSCRIPTION_CHANGED_EVENT not in personal_event


async def test_personal_account_locked_message_uses_named_event():
    user_id = uuid.uuid4()
    payload = {
        "type": ACCOUNT_LOCKED_EVENT,
        "user_id": str(user_id),
        "reason": "Lý do khóa",
        "locked_at": None,
    }
    pubsub = _FakePubSub([_message(f"notifications:user:{user_id}", payload)])
    manager = _FakePubSubManager(_ticket(user_id, is_admin=False), pubsub)

    response = await notification_stream(ticket="t", pubsub=manager)  # type: ignore[arg-type]
    generator = response.body_iterator
    await _next(generator)
    personal_event = await _next(generator)
    await generator.aclose()

    assert f"event: {ACCOUNT_LOCKED_EVENT}" in personal_event
    assert "event: notification.created" not in personal_event
    data_line = next(
        line for line in personal_event.splitlines() if line.startswith("data: ")
    )
    parsed = json.loads(data_line[len("data: ") :])
    assert parsed["type"] == ACCOUNT_LOCKED_EVENT
    assert parsed["reason"] == "Lý do khóa"


def test_personal_event_name_classifier_defaults_safely():
    from app.api.v1.endpoints.notifications import _personal_event_name

    assert _personal_event_name('{"type": "account.locked"}') == ACCOUNT_LOCKED_EVENT
    assert (
        _personal_event_name(b'{"type": "account.locked"}') == ACCOUNT_LOCKED_EVENT
    )
    assert _personal_event_name('{"type": "other"}') == "notification.created"
    assert _personal_event_name('{"notification_type": "x"}') == "notification.created"
    assert _personal_event_name("not-json") == "notification.created"
    assert _personal_event_name(None) == "notification.created"
    assert _personal_event_name([1, 2, 3]) == "notification.created"


async def test_ticket_is_consumed_single_use():
    user_id = uuid.uuid4()
    pubsub = _FakePubSub([])
    manager = _FakePubSubManager(_ticket(user_id, is_admin=False), pubsub)

    await notification_stream(ticket="abc123", pubsub=manager)  # type: ignore[arg-type]

    assert manager._redis.deleted == ["notification:stream_ticket:abc123"]


@pytest.mark.parametrize(
    "raw_ticket",
    [
        None,
        "not-json",
        json.dumps({"is_admin": True}),
        json.dumps({"user_id": "not-a-uuid"}),
    ],
)
async def test_invalid_or_malformed_tickets_are_rejected(raw_ticket):
    pubsub = _FakePubSub([])
    manager = _FakePubSubManager(raw_ticket, pubsub)

    with pytest.raises(HTTPException) as exc_info:
        await notification_stream(ticket="t", pubsub=manager)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 401
    assert pubsub.subscribed == []


async def test_bounded_stream_lifetime_terminates(monkeypatch):
    user_id = uuid.uuid4()
    pubsub = _FakePubSub(empty_returns_none=True)
    manager = _FakePubSubManager(_ticket(user_id, is_admin=True), pubsub)

    # Force the lifetime check to trip on the first loop iteration.
    monkeypatch.setattr(notifications_module, "STREAM_MAX_SECONDS", 0)
    monkeypatch.setattr(notifications_module.asyncio, "sleep", _noop_sleep)

    response = await notification_stream(ticket="t", pubsub=manager)  # type: ignore[arg-type]
    generator = response.body_iterator

    chunks = [chunk async for chunk in generator]

    assert any("event: connected" in chunk for chunk in chunks)
    # Stream closed cleanly and unsubscribed (forcing the client to reconnect).
    assert pubsub.closed is True
    assert set(pubsub.unsubscribed) == {
        f"notifications:user:{user_id}",
        ADMIN_SUBSCRIPTIONS_CHANNEL,
        ADMIN_EMAILS_CHANNEL,
    }


async def _noop_sleep(*_args, **_kwargs) -> None:
    return None
