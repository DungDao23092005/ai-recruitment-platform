from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from typing import Any, Optional

from fastapi import HTTPException, status
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.schemas.ai_chat import ChatMessage, ChatResponse

logger = logging.getLogger(__name__)

COMPLETED_TTL_SECONDS = 86400  # 24 hours
IN_PROGRESS_TTL_SECONDS = 120  # Safe lease longer than provider timeout
MAX_CONCURRENT_WAIT_SECONDS = 2.0
POLL_INTERVAL_SECONDS = 0.2

# Atomic Lua Scripts

LUA_CLAIM = """
local record = redis.call("GET", KEYS[1])
if not record then
    local payload = cjson.encode({
        state = "IN_PROGRESS",
        fingerprint = ARGV[1],
        owner_token = ARGV[2]
    })
    redis.call("SET", KEYS[1], payload, "EX", tonumber(ARGV[3]))
    return { "ACQUIRED" }
end

local data = cjson.decode(record)
if data.fingerprint ~= ARGV[1] then
    return { "MISMATCH" }
end

if data.state == "COMPLETED" then
    return { "COMPLETED", cjson.encode(data.response) }
end

if data.state == "IN_PROGRESS" then
    return { "IN_PROGRESS" }
end

return { "UNKNOWN" }
"""

LUA_COMPLETE = """
local record = redis.call("GET", KEYS[1])
if record then
    local data = cjson.decode(record)
    if data.owner_token == ARGV[1] then
        data.state = "COMPLETED"
        data.response = cjson.decode(ARGV[2])
        data.owner_token = nil
        redis.call("SET", KEYS[1], cjson.encode(data), "EX", tonumber(ARGV[3]))
        return 1
    end
end
return 0
"""

LUA_RELEASE = """
local record = redis.call("GET", KEYS[1])
if record then
    local data = cjson.decode(record)
    if data.owner_token == ARGV[1] and data.state == "IN_PROGRESS" then
        redis.call("DEL", KEYS[1])
        return 1
    end
end
return 0
"""


def compute_chat_fingerprint(
    message: str,
    history: list[ChatMessage] | list[dict[str, Any]] | None,
) -> str:
    """Compute a canonical SHA256 hex digest of the chat request payload."""
    normalized_history: list[dict[str, str]] = []
    if history:
        for item in history:
            if isinstance(item, dict):
                normalized_history.append(
                    {
                        "role": str(item.get("role", "")),
                        "content": str(item.get("content", "")),
                    }
                )
            else:
                normalized_history.append(
                    {
                        "role": str(getattr(item, "role", "")),
                        "content": str(getattr(item, "content", "")),
                    }
                )

    payload = {
        "message": message.strip(),
        "history": normalized_history,
    }
    canonical_bytes = json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


class RecruiterChatCoordinator:
    """Coordinates idempotency, atomic locking, and response replay for Recruiter AI Chat.

    Guarantees:
    - Namespaced by user, company/workspace and idempotency key.
    - Stable request fingerprint from message and history.
    - Atomic claim in Redis so only the lock owner executes the LLM.
    - Completed duplicate returns cached ChatResponse without calling LLM or charging quota.
    - Mismatched fingerprint returns HTTP 409.
    - Lock release verifies ownership token so workers never delete another's lock.
    - Fail closed with HTTP 503 if Redis is unavailable.
    """

    def __init__(
        self,
        redis_client: Optional[Redis],
        user_id: uuid.UUID,
        company_id: uuid.UUID,
        idempotency_key: str,
        message: str,
        history: list[ChatMessage] | list[dict[str, Any]] | None,
    ) -> None:
        self.redis = redis_client
        self.user_id = user_id
        self.company_id = company_id
        self.idempotency_key = idempotency_key
        self.fingerprint = compute_chat_fingerprint(message, history)
        self.owner_token = str(uuid.uuid4())
        self.record_key = (
            f"ai_chat:idempotency:{user_id}:{company_id}:{idempotency_key}"
        )
        self.claimed = False

    def _ensure_redis(self) -> Redis:
        if self.redis is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Dịch vụ AI tạm thời không khả dụng do hệ thống lưu trữ phiên (Redis). Vui lòng thử lại sau.",
            )
        return self.redis

    async def claim_or_get_completed(self) -> ChatResponse | None:
        """Attempt to claim the lock or retrieve an existing completed response.

        Returns:
            ChatResponse if already completed and cached.
            None if lock was acquired (caller must proceed with quota reservation and LLM call).

        Raises:
            HTTPException 409: If payload mismatch or concurrent execution in progress.
            HTTPException 503: If Redis is unavailable or fails.
        """
        redis = self._ensure_redis()

        elapsed = 0.0
        while True:
            try:
                res = await redis.eval(
                    LUA_CLAIM,
                    1,
                    self.record_key,
                    self.fingerprint,
                    self.owner_token,
                    IN_PROGRESS_TTL_SECONDS,
                )
            except RedisError as exc:
                logger.error("Redis error claiming chat lock: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Dịch vụ AI tạm thời không khả dụng do lỗi kết nối Redis. Vui lòng thử lại sau.",
                ) from exc

            action = res[0] if isinstance(res, (list, tuple)) else str(res)
            if isinstance(action, bytes):
                action = action.decode("utf-8")

            if action == "ACQUIRED":
                self.claimed = True
                return None

            if action == "MISMATCH":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency-Key đã được sử dụng cho một yêu cầu khác với nội dung hoặc lịch sử trò chuyện khác.",
                )

            if action == "COMPLETED":
                raw_response = res[1] if len(res) > 1 else "{}"
                if isinstance(raw_response, bytes):
                    raw_response = raw_response.decode("utf-8")
                try:
                    data = json.loads(raw_response)
                    return ChatResponse.model_validate(data)
                except Exception as exc:
                    logger.warning("Failed to decode cached ChatResponse: %s", exc)
                    # If cached response corrupted, treat as invalid
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Lỗi phân giải phản hồi đã lưu trong bộ nhớ tạm.",
                    ) from exc

            if action == "IN_PROGRESS":
                if elapsed >= MAX_CONCURRENT_WAIT_SECONDS:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Yêu cầu đang được xử lý bởi một tiến trình khác, vui lòng thử lại sau giây lát.",
                        headers={"Retry-After": "2"},
                    )
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                elapsed += POLL_INTERVAL_SECONDS
                continue

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Trạng thái yêu cầu không xác định, vui lòng thử lại.",
            )

    async def complete(self, response: ChatResponse | dict[str, Any]) -> None:
        """Mark processing as completed and cache the response for replay."""
        if not self.claimed or self.redis is None:
            return

        if isinstance(response, BaseModel):
            payload = response.model_dump(mode="json")
        elif isinstance(response, dict):
            payload = response
        else:
            payload = getattr(response, "__dict__", {})
        response_json = json.dumps(payload, default=str)
        try:
            await self.redis.eval(
                LUA_COMPLETE,
                1,
                self.record_key,
                self.owner_token,
                response_json,
                COMPLETED_TTL_SECONDS,
            )
            self.claimed = False
        except RedisError as exc:
            logger.warning("Failed to complete recruiter chat state in Redis: %s", exc)

    async def release(self) -> None:
        """Release the claimed lock on ordinary failure so retry with the same key is permitted."""
        if not self.claimed or self.redis is None:
            return

        try:
            await self.redis.eval(
                LUA_RELEASE,
                1,
                self.record_key,
                self.owner_token,
            )
            self.claimed = False
        except RedisError as exc:
            logger.warning("Failed to release recruiter chat lock in Redis: %s", exc)
