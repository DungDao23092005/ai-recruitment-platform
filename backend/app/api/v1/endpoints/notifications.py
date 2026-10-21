from __future__ import annotations

import json
import logging
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
from app.domain.enums import UserRole
from app.models import User
from app.schemas.notification import NotificationRead, UnreadCountResponse
from app.services.notification_service import NotificationService
from app.services.account_lock_realtime import ACCOUNT_LOCKED_EVENT
from app.services.email_outbox_realtime import (
    ADMIN_EMAILS_CHANNEL,
    EMAIL_OUTBOX_UPDATED_EVENT,
)
from app.services.subscription_realtime import (
    ADMIN_SUBSCRIPTIONS_CHANNEL,
    ADMIN_SUBSCRIPTION_CHANGED_EVENT,
)
from app.services.pipeline_realtime import (
    CANDIDATE_PIPELINE_UPDATED_EVENT,
    PIPELINE_UPDATED_EVENT,
    company_pipeline_channel,
    is_candidate_pipeline_message,
    is_company_pipeline_message,
    parse_pipeline_payload,
)
from app.services.user_service import UserService
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

TICKET_TTL_SECONDS = 10
# Bound the stream lifetime so long-lived connections periodically re-authenticate
# through a fresh ticket, re-checking the user's role for admin-channel access.
STREAM_MAX_SECONDS = 1800

# Default SSE event for a personal-channel message.
NOTIFICATION_CREATED_EVENT = "notification.created"


def _personal_event_name(raw_data: object) -> str:
    """Classify a personal-channel payload into its SSE event name.

    Account locks and candidate pipeline invalidations are promoted only when
    their trusted payload shape validates. Ordinary notification payloads - and
    anything malformed or unrecognised - keep the default
    ``notification.created`` event so existing consumers are unaffected.
    """
    payload = parse_pipeline_payload(raw_data)
    if payload is not None and payload.get("type") == ACCOUNT_LOCKED_EVENT:
        return ACCOUNT_LOCKED_EVENT
    if is_candidate_pipeline_message(raw_data):
        return CANDIDATE_PIPELINE_UPDATED_EVENT
    return NOTIFICATION_CREATED_EVENT


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
    db: AsyncSession = Depends(get_db),
    pubsub: PubSubManager = Depends(get_pubsub_manager),
) -> dict:
    """Create a short-lived ticket for SSE stream authentication.

    The ticket stores server-derived authorization data so the stream can
    subscribe to the admin and recruiter-company channels without trusting any
    client-supplied flag or company identifier.
    """
    is_admin = current_user.role == UserRole.ADMIN
    company_id = None
    if current_user.role == UserRole.RECRUITER:
        try:
            user = await UserService(db).get_user_with_profile(current_user.id)
            profile = user.recruiter_profile if user is not None else None
            company_id = profile.company_id if profile is not None else None
        except Exception as exc:  # pragma: no cover - defensive boundary
            logger.warning("Failed to resolve recruiter company for SSE: %s", exc)

    ticket = secrets.token_urlsafe(32)
    ticket_key = f"notification:stream_ticket:{ticket}"
    ticket_payload: dict[str, object] = {
        "user_id": str(current_user.id),
        "is_admin": is_admin,
    }
    if company_id is not None:
        ticket_payload["company_id"] = str(company_id)
    payload = json.dumps(ticket_payload)
    await pubsub._redis.setex(ticket_key, TICKET_TTL_SECONDS, payload)
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
    raw_ticket = await pubsub._redis.get(ticket_key)
    if not raw_ticket:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired ticket",
        )

    # Delete ticket immediately (single-use)
    await pubsub._redis.delete(ticket_key)

    try:
        ticket_data = json.loads(raw_ticket)
        user_id = uuid.UUID(str(ticket_data["user_id"]))
        is_admin = bool(ticket_data.get("is_admin", False))
        raw_company_id = ticket_data.get("company_id")
        company_id = (
            uuid.UUID(str(raw_company_id)) if raw_company_id else None
        )
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid ticket",
        )

    user_id_str = str(user_id)
    personal_channel = f"notifications:user:{user_id_str}"
    company_channel = None
    channels = [personal_channel]
    if is_admin:
        channels.append(ADMIN_SUBSCRIPTIONS_CHANNEL)
        channels.append(ADMIN_EMAILS_CHANNEL)
    elif company_id is not None:
        company_channel = company_pipeline_channel(company_id)
        channels.append(company_channel)

    async def event_generator() -> AsyncGenerator[str, None]:
        pubsub_client = pubsub._redis.pubsub()
        try:
            await pubsub_client.subscribe(*channels)

            # Send initial connection confirmation
            connected_data = json.dumps({"type": "connected", "user_id": user_id_str})
            yield f"event: connected\ndata: {connected_data}\n\n"

            started_at = asyncio.get_event_loop().time()
            last_heartbeat = started_at

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
                            channel = message.get("channel")
                            event_name: str | None
                            if channel == ADMIN_SUBSCRIPTIONS_CHANNEL:
                                event_name = ADMIN_SUBSCRIPTION_CHANGED_EVENT
                            elif channel == ADMIN_EMAILS_CHANNEL:
                                event_name = EMAIL_OUTBOX_UPDATED_EVENT
                            elif (
                                company_channel is not None
                                and channel == company_channel
                            ):
                                if is_company_pipeline_message(
                                    data, company_id=company_id
                                ):
                                    event_name = PIPELINE_UPDATED_EVENT
                                else:
                                    event_name = None
                                    logger.warning(
                                        "Ignoring malformed company pipeline event"
                                    )
                            else:
                                event_name = _personal_event_name(data)
                            if event_name is not None:
                                yield f"event: {event_name}\ndata: {data}\n\n"
                        except Exception as e:
                            logger.warning("Failed to process SSE message: %s", e)

                    # Independent heartbeat check - runs every iteration
                    if current_time - last_heartbeat >= 30.0:
                        yield ": keepalive\n\n"
                        last_heartbeat = current_time

                    # Re-check role/stream age: bounded lifetime forces the client
                    # to reconnect with a fresh ticket.
                    if current_time - started_at >= STREAM_MAX_SECONDS:
                        break

                    # Small sleep to prevent tight loop when no message
                    if message is None:
                        await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("SSE stream error: %s", e)
            finally:
                await pubsub_client.unsubscribe(*channels)
                await pubsub_client.close()
        except Exception as e:
            logger.error("SSE stream error: %s", e)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
