from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.core.exceptions import ConflictException, EntityNotFoundException, InvalidTransitionException
from app.domain.enums import SubscriptionStatus
from app.models import User
from app.schemas.subscription import SubscriptionAdminProvision, SubscriptionAdminRead
from app.services.subscription_service import SubscriptionService

router = APIRouter(
    prefix="/admin/subscriptions",
    tags=["Admin - Subscriptions"],
    dependencies=[Depends(require_admin)],
)


def _get_subscription_service(db: AsyncSession = Depends(get_db)) -> SubscriptionService:
    return SubscriptionService(db)


@router.get(
    "",
    response_model=list[SubscriptionAdminRead],
)
async def list_admin_subscriptions(
    current_user: User = Depends(require_admin),
    service: SubscriptionService = Depends(_get_subscription_service),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    user_id: Optional[uuid.UUID] = Query(default=None),
    status_filter: Optional[SubscriptionStatus] = Query(default=None),
) -> list[SubscriptionAdminRead]:
    """List subscriptions for admin with optional filters."""
    subscriptions, total = await service.subscriptions.list_admin(
        skip=skip,
        limit=limit,
        user_id=user_id,
        status_filter=status_filter,
    )
    return [SubscriptionAdminRead.model_validate(s) for s in subscriptions]


@router.get(
    "/{subscription_id}",
    response_model=SubscriptionAdminRead,
)
async def get_admin_subscription(
    subscription_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    service: SubscriptionService = Depends(_get_subscription_service),
) -> SubscriptionAdminRead:
    """Get a subscription by ID for admin."""
    sub = await service.subscriptions.get_by_id_including_deleted(subscription_id)
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription {subscription_id} not found",
        )
    return SubscriptionAdminRead.model_validate(sub)


@router.post(
    "",
    response_model=SubscriptionAdminRead,
    status_code=status.HTTP_201_CREATED,
)
async def admin_provision_subscription(
    data: SubscriptionAdminProvision,
    current_user: User = Depends(require_admin),
    service: SubscriptionService = Depends(_get_subscription_service),
) -> SubscriptionAdminRead:
    """Admin-only provisioning of an active subscription for a user.
    This is for manual testing and support purposes only.
    """
    try:
        # Create pending subscription
        subscription = await service.create_pending_subscription(data.user_id, data.plan_id)
        # Activate it immediately
        subscription = await service.activate_subscription(subscription.id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ConflictException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except InvalidTransitionException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return SubscriptionAdminRead.model_validate(subscription)


@router.post(
    "/{subscription_id}/cancel",
    response_model=SubscriptionAdminRead,
)
async def admin_cancel_subscription(
    subscription_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    service: SubscriptionService = Depends(_get_subscription_service),
) -> SubscriptionAdminRead:
    """Admin-only subscription cancellation."""
    try:
        subscription = await service.cancel_subscription(subscription_id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InvalidTransitionException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return SubscriptionAdminRead.model_validate(subscription)