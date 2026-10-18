"""Unit tests for the account-locked realtime event payload."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.services.account_lock_realtime import (
    ACCOUNT_LOCKED_EVENT,
    build_account_locked_event,
)


def test_payload_has_expected_shape_and_stringifies_user_id():
    user_id = uuid.uuid4()
    locked_at = datetime(2026, 5, 1, 8, 30, tzinfo=timezone.utc)

    payload = build_account_locked_event(
        user_id=user_id, reason="Vi phạm điều khoản", locked_at=locked_at
    )

    assert set(payload.keys()) == {"type", "user_id", "reason", "locked_at"}
    assert payload["type"] == ACCOUNT_LOCKED_EVENT
    assert payload["user_id"] == str(user_id)
    assert payload["reason"] == "Vi phạm điều khoản"
    assert payload["locked_at"] == locked_at.isoformat()


def test_payload_tolerates_missing_reason_and_timestamp():
    payload = build_account_locked_event(
        user_id="11111111-1111-1111-1111-111111111111"
    )

    assert payload["user_id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["reason"] is None
    assert payload["locked_at"] is None


def test_naive_datetime_is_treated_as_utc():
    naive = datetime(2026, 5, 1, 8, 30)

    payload = build_account_locked_event(user_id=uuid.uuid4(), locked_at=naive)

    assert payload["locked_at"] == naive.replace(tzinfo=timezone.utc).isoformat()


def test_payload_exposes_no_sensitive_fields():
    payload = build_account_locked_event(
        user_id=uuid.uuid4(),
        reason="r",
        locked_at=datetime.now(timezone.utc),
    )

    serialized = str(payload).lower()
    for forbidden in ("email", "password", "token", "admin"):
        assert forbidden not in serialized
