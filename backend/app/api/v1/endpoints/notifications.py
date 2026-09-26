from __future__ import annotations

import uuid
import secrets
import asyncio
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_active_user
from app.core.exceptions import EntityNotFoundException
from app.core.pubsub import get_pubsub_manager, PubSubManager
from app.models import User
from app.schemas.notification import NotificationRead, UnreadCountResponse
from app.services.notification_service import NotificationService
from app.core.security import decode_access_token
from app.core.config import settings

router = APIRouter()


@router.get(
    "",
    response_model=list[NotificationRead],
)
async def list_notifications(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationRead]:
    service = NotificationService(db)
    return await service.list_notifications(
        user_id=current_user.id, skip=skip, limit=limit
    )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
)
async def get_unread_count(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> UnreadCountResponse:
    service = NotificationService(db)
    count = await service.get_unread_count(user_id=current_user.id)
    return UnreadCountResponse(unread_count=count)


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationRead,
)
async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationRead:
    service = NotificationService(db)
    try:
        result = await service.mark_as_read(
            current_user=current_user, notification_id=notification_id
        )
        await db.commit()
        return result
    except EntityNotFoundException as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.patch(
    "/read-all",
    response_model=dict,
)
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = NotificationService(db)
    count = await service.mark_all_as_read(user_id=current_user.id)
    await db.commit()
    return {"marked_read": count}


@router.post(
    "/stream-ticket",
    response_model=dict,
)
async def create_stream_ticket(
    current_user: User = Depends(get_current_active_user),
    pubsub: PubSubManager = Depends(get_pubsub_manager),
) -> dict:
    """Create a short-lived ticket for SSE stream authentication."""
    ticket = secrets.token_urlsafe(32)
    # Store ticket with user_id in Redis with 10 second TTL
    # Using a simple key-value store with TTL
    ticket_key = f"notification:stream_ticket:{ticket}"
    await pubsub._redis.setex(
        f"notification:stream_ticket:{ticket}",
        10,  # 10 seconds TTL
        str(current_user.id),
    )
    return {"ticket": ticket}


@router.get(
    "/stream",
    response_class=StreamingResponse,
)
async def notification_stream(
    ticket: str = Query(...),
    pubsub: PubSubManager = Depends(get_pubsub_manager),
) -> StreamingResponse:
    """SSE endpoint for real-time notifications with heartbeat."""
    # Validate and consume ticket
    ticket_key = f"notification:stream_ticket:{ticket}"
    user_id_str = await pubsub._redis.get(ticket_key)
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired ticket",
        )

    # Delete ticket immediately (single-use)
    await pubsub._redis.delete(f"notification:stream_ticket:{ticket}")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid ticket",
        )

    channel = f"notifications:user:{user_id_str}"

    async def event_generator() -> AsyncGenerator[str, None]:
        pubsub_client = pubsub._redis.pubsub()
        try:
            await pubsub_client.subscribe(channel)

            # Send initial connection confirmation
            import json
            connected_data = json.dumps({"type": "connected", "user_id": str(user_id_str)})
            yield f"event: connected\ndata: {connected_data}\n\n"

            last_heartbeat = asyncio.get_event_loop().time()

            try:
                while True:
                    # Get message with timeout for heartbeat polling
                    message = await pubsub_client.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    )

                    current_time = asyncio.get_event_loop().time()

                    # Process message if received
                    if message is not None and message["type"] == "message":
                        try:
                            data = message["data"]
                            yield f"event: notification.created\ndata: {data}\n\n"
                        except Exception as e:
                            import logging
                            logging.getLogger(__name__).warning(f"Failed to process SSE message: {e}")

                    # Independent heartbeat check - runs every iteration
                    if current_time - last_heartbeat >= 30.0:
                        yield ": keepalive\n\n"
                        last_heartbeat = current_time

                    # Small sleep to prevent tight loop when no message
                    if message is None:
                        await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"SSE stream error: {e}")
            finally:
                await pubsub_client.unsubscribe(channel)
                await pubsub_client.close()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"SSE stream error: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
