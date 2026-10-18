"""Unit tests for the admin subscription invalidation event payload."""

from __future__ import annotations

import uuid

from app.services.subscription_realtime import (
    ACTION_ACTIVATED,
    ACTION_ORDER_CREATED,
    ACTION_PLAN_CHANGED,
    ACTION_REVOKED,
    ADMIN_SUBSCRIPTION_CHANGED_EVENT,
    VALID_ACTIONS,
    build_admin_subscription_event,
)


def test_payload_is_minimal_and_exposes_no_sensitive_fields():
    user_id = uuid.uuid4()
    subscription_id = uuid.uuid4()

    payload = build_admin_subscription_event(
        user_id=user_id, subscription_id=subscription_id, action=ACTION_ACTIVATED
    )

    assert set(payload.keys()) == {
        "type",
        "user_id",
        "subscription_id",
        "action",
        "timestamp",
    }
    assert payload["type"] == ADMIN_SUBSCRIPTION_CHANGED_EVENT
    assert payload["user_id"] == str(user_id)
    assert payload["subscription_id"] == str(subscription_id)
    assert payload["action"] == ACTION_ACTIVATED
    assert payload["timestamp"]

    serialized = str(payload).lower()
    for forbidden in ("email", "plan_name", "amount", "payment", "reason", "audit"):
        assert forbidden not in serialized


def test_payload_stringifies_identifiers_and_allows_missing_subscription():
    payload = build_admin_subscription_event(
        user_id="11111111-1111-1111-1111-111111111111",
        subscription_id=None,
        action=ACTION_ORDER_CREATED,
    )

    assert payload["user_id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["subscription_id"] is None


def test_action_vocabulary_is_closed():
    assert VALID_ACTIONS == {
        ACTION_ACTIVATED,
        ACTION_PLAN_CHANGED,
        ACTION_REVOKED,
        ACTION_ORDER_CREATED,
    }
