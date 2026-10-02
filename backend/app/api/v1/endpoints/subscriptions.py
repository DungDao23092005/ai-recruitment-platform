from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_active_user
from app.core.exceptions import ConflictException, EntityNotFoundException, InvalidTransitionException
from app.models import User
from app.schemas.subscription import SubscriptionRead, SubscriptionSummary
from app.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


def _get_subscription_service(db: AsyncSession = Depends(get_db)) -> SubscriptionService:
    return SubscriptionService(db)


@router.get(
    "/me",
    response_model=SubscriptionRead,
)
async def get_my_subscription(
    current_user: User = Depends(get_current_active_user),
    service: SubscriptionService = Depends(_get_subscription_service),
) -> SubscriptionRead:
    """Get the current user's active subscription."""
    subscription = await service.get_current_active_subscription(current_user.id)
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found",
        )
    return SubscriptionRead.model_validate(subscription)


@router.get(
    "/me/history",
    response_model=list[SubscriptionSummary],
)
async def get_my_subscription_history(
    current_user: User = Depends(get_current_active_user),
    service: SubscriptionService = Depends(_get_subscription_service),
) -> list[SubscriptionSummary]:
    """Get the current user's subscription history."""
    subscriptions = await service.list_user_subscriptions(current_user.id)
    return [SubscriptionSummary.model_validate(s) for s in subscriptions]


@router.get(
    "/{subscription_id}",
    response_model=SubscriptionRead,
)
async def get_subscription(
    subscription_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: SubscriptionService = Depends(_get_subscription_service),
) -> SubscriptionRead:
    """Get a specific subscription by ID (must belong to current user)."""
    try:
        subscription = await service.get_subscription_by_id(subscription_id, current_user.id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return SubscriptionRead.model_validate(subscription)