from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.core.exceptions import (
    EntityNotFoundException,
    InvalidTransitionException,
)
from app.domain.enums import OutboxStatus
from app.models import User
from app.schemas.email_outbox import (
    EmailOutboxListResponse,
    EmailOutboxRead,
    EmailOutboxStatsResponse,
)
from app.services.email_outbox_service import EmailOutboxService

router = APIRouter(
    prefix="/admin/emails",
    tags=["Admin - Emails"],
    dependencies=[Depends(require_admin)],
)


def _get_email_outbox_service(
    db: AsyncSession = Depends(get_db),
) -> EmailOutboxService:
    return EmailOutboxService(db)


@router.get("/stats", response_model=EmailOutboxStatsResponse)
async def get_email_outbox_stats(
    current_user: User = Depends(require_admin),
    service: EmailOutboxService = Depends(_get_email_outbox_service),
) -> EmailOutboxStatsResponse:
    """Aggregate outbox counts for the admin dashboard."""
    return EmailOutboxStatsResponse(**await service.get_stats())


@router.get("", response_model=EmailOutboxListResponse)
async def list_email_outbox(
    current_user: User = Depends(require_admin),
    service: EmailOutboxService = Depends(_get_email_outbox_service),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    status_filter: Optional[OutboxStatus] = Query(default=None, alias="status"),
    event_type: Optional[str] = Query(default=None, max_length=50),
    search: Optional[str] = Query(default=None, max_length=255),
) -> EmailOutboxListResponse:
    """List queued/sent/failed notification emails (bodies are never exposed)."""
    items, total = await service.list_messages(
        skip=skip,
        limit=limit,
        status=status_filter,
        event_type=event_type,
        search=search,
    )
    return EmailOutboxListResponse(
        items=[EmailOutboxRead.model_validate(item) for item in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("/{message_id}/retry", response_model=EmailOutboxRead)
async def retry_email_outbox_message(
    message_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    service: EmailOutboxService = Depends(_get_email_outbox_service),
) -> EmailOutboxRead:
    """Requeue a failed/pending email. Refuses messages being processed."""
    try:
        message = await service.retry_message(message_id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InvalidTransitionException as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return EmailOutboxRead.model_validate(message)
