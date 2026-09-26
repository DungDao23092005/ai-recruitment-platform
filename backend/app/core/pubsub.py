from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import redis.asyncio as redis
from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class PubSubManager:
    """Redis Pub/Sub manager for real-time notifications."""

    def __init__(self) -> None:
        self._redis: Redis | None = None
        self._pubsub = None

    async def connect(self) -> None:
        """Initialize Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                password=settings.REDIS_PASSWORD or None,
                decode_responses=True,
            )
            self._pubsub = self._redis.pubsub()

    async def disconnect(self) -> None:
        """Close Redis connection and cleanup."""
        if self._pubsub:
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()

    async def publish(self, channel: str, message: dict) -> int:
        """Publish a message to a channel.

        Returns the number of subscribers that received the message.
        """
        if not self._redis:
            await self.connect()

        message_json = json.dumps(message, default=str)
        try:
            return await self._redis.publish(channel, message_json)
        except Exception as e:
            logger.warning(f"Failed to publish to channel {channel}: {e}")
            return 0

    async def subscribe(self, channel: str) -> AsyncGenerator[dict, None]:
        """Subscribe to a channel and yield messages."""
        if not self._redis:
            await self.connect()

        pubsub = self._redis.pubsub()
        try:
            await pubsub.subscribe(channel)
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        yield json.loads(message["data"])
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to decode message from {channel}: {message['data']}")
                        continue
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    def get_user_channel(self, user_id: str) -> str:
        """Get the channel name for a user."""
        return f"notifications:user:{user_id}"


# Global pubsub manager instance
pubsub_manager = PubSubManager()


async def get_pubsub_manager() -> PubSubManager:
    """Get the pubsub manager instance."""
    return pubsub_manager


@asynccontextmanager
async def pubsub_lifespan() -> AsyncGenerator[PubSubManager, None]:
    """Lifespan context manager for pubsub."""
    await pubsub_manager.connect()
    try:
        yield pubsub_manager
    finally:
        await pubsub_manager.disconnect()
