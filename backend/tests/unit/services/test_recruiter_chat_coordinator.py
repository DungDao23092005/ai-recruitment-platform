from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from redis.exceptions import RedisError

from app.schemas.ai_chat import ChatMessage, ChatResponse
from app.services.recruiter_chat_coordinator import (
    RecruiterChatCoordinator,
    compute_chat_fingerprint,
)


def _messages():
    return [
        ChatMessage(role="user", content="Hello AI"),
        ChatMessage(role="assistant", content="Hello Recruiter"),
    ]


@pytest.mark.asyncio
async def test_fingerprint_deterministic_and_sensitive_to_message_and_history():
    msg = "Find candidates"
    hist1 = [ChatMessage(role="user", content="Hi")]
    hist2 = [ChatMessage(role="user", content="Hi2")]

    fp1 = compute_chat_fingerprint(msg, hist1)
    fp1_again = compute_chat_fingerprint(msg, hist1)
    assert fp1 == fp1_again

    fp_different_msg = compute_chat_fingerprint("Find candidates 2", hist1)
    assert fp1 != fp_different_msg

    fp_different_hist = compute_chat_fingerprint(msg, hist2)
    assert fp1 != fp_different_hist


@pytest.mark.asyncio
async def test_claim_lock_acquired_when_no_existing_record():
    mock_redis = AsyncMock()
    mock_redis.eval.return_value = ["ACQUIRED"]

    coord = RecruiterChatCoordinator(
        redis_client=mock_redis,
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        idempotency_key="chat_123",
        message="Test message",
        history=_messages(),
    )

    cached = await coord.claim_or_get_completed()
    assert cached is None
    assert coord.claimed is True
    mock_redis.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_completed_duplicate_returns_cached_response_without_re_executing():
    mock_redis = AsyncMock()
    cached_payload = json.dumps({
        "answer": "This is a cached answer",
        "confidence": 0.95,
        "sources": [],
        "suggested_followups": ["Question 1?"],
    })
    mock_redis.eval.return_value = ["COMPLETED", cached_payload]

    coord = RecruiterChatCoordinator(
        redis_client=mock_redis,
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        idempotency_key="chat_123",
        message="Test message",
        history=_messages(),
    )

    cached = await coord.claim_or_get_completed()
    assert cached is not None
    assert cached.answer == "This is a cached answer"
    assert cached.suggested_followups == ["Question 1?"]
    assert coord.claimed is False


@pytest.mark.asyncio
async def test_same_key_different_payload_returns_409():
    mock_redis = AsyncMock()
    mock_redis.eval.return_value = ["MISMATCH"]

    coord = RecruiterChatCoordinator(
        redis_client=mock_redis,
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        idempotency_key="chat_123",
        message="New message with same key",
        history=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        await coord.claim_or_get_completed()

    assert exc_info.value.status_code == 409
    assert "Idempotency-Key đã được sử dụng" in exc_info.value.detail


@pytest.mark.asyncio
async def test_redis_unavailable_fails_closed():
    coord = RecruiterChatCoordinator(
        redis_client=None,
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        idempotency_key="chat_123",
        message="Test message",
        history=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        await coord.claim_or_get_completed()

    assert exc_info.value.status_code == 503
    assert "Redis" in exc_info.value.detail


@pytest.mark.asyncio
async def test_redis_error_fails_closed():
    mock_redis = AsyncMock()
    mock_redis.eval.side_effect = RedisError("Connection refused")

    coord = RecruiterChatCoordinator(
        redis_client=mock_redis,
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        idempotency_key="chat_123",
        message="Test message",
        history=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        await coord.claim_or_get_completed()

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_release_clears_in_progress_state_on_ordinary_failure():
    mock_redis = AsyncMock()
    coord = RecruiterChatCoordinator(
        redis_client=mock_redis,
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        idempotency_key="chat_123",
        message="Test message",
        history=[],
    )
    coord.claimed = True

    await coord.release()

    assert coord.claimed is False
    mock_redis.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_is_isolated_by_user_and_company():
    user1 = uuid.uuid4()
    user2 = uuid.uuid4()
    company1 = uuid.uuid4()
    company2 = uuid.uuid4()
    key = "chat_abc"

    c1 = RecruiterChatCoordinator(
        None, user1, company1, key, "hello", []
    )
    c2 = RecruiterChatCoordinator(
        None, user2, company1, key, "hello", []
    )
    c3 = RecruiterChatCoordinator(
        None, user1, company2, key, "hello", []
    )

    assert c1.record_key != c2.record_key
    assert c1.record_key != c3.record_key
    assert c2.record_key != c3.record_key
