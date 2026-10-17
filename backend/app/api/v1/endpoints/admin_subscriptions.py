from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.core.exceptions import ConflictException, EntityNotFoundException, InvalidTransitionException
from app.domain.enums import SubscriptionStatus
from app.models import User
from app.schemas.subscription import (
    AdminSubscriptionChangePlan,
    AdminSubscriptionDetail,
    AdminSubscriptionList,
    AdminSubscriptionRevoke,
    SubscriptionAdminProvision,
    SubscriptionAdminRead,
)
from app.services.admin_subscription_service import AdminSubscriptionService

router = APIRouter(
    prefix="/admin/subscriptions",
    tags=["Admin - Subscriptions"],
    dependencies=[Depends(require_admin)],
)


def _get_admin_subscription_service(
    db: AsyncSession = Depends(get_db),
) -> AdminSubscriptionService:
    return AdminSubscriptionService(db)


@router.get(
    "",
    response_model=AdminSubscriptionList,
)
async def list_admin_subscriptions(
    current_user: User = Depends(require_admin),
    service: AdminSubscriptionService = Depends(_get_admin_subscription_service),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    user_id: Optional[uuid.UUID] = Query(default=None),
    plan_id: Optional[uuid.UUID] = Query(default=None),
    status_filter: Optional[SubscriptionStatus] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=255),
) -> AdminSubscriptionList:
    """List subscriptions for admin with optional filters and email search."""
    items, total = await service.list_subscriptions(
        skip=skip,
        limit=limit,
        search=search,
        status_filter=status_filter,
        plan_id=plan_id,
    )
    return AdminSubscriptionList(items=items, total=total, skip=skip, limit=limit)


@router.get(
    "/{subscription_id}",
    response_model=AdminSubscriptionDetail,
)
async def get_admin_subscription(
    subscription_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    service: AdminSubscriptionService = Depends(_get_admin_subscription_service),
) -> AdminSubscriptionDetail:
    """Get a subscription with the user's history and its audit trail."""
    try:
        return await service.get_detail(subscription_id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "",
    response_model=SubscriptionAdminRead,
    status_code=status.HTTP_201_CREATED,
)
async def admin_provision_subscription(
    data: SubscriptionAdminProvision,
    current_user: User = Depends(require_admin),
    service: AdminSubscriptionService = Depends(_get_admin_subscription_service),
) -> SubscriptionAdminRead:
    """Admin-only provisioning of an active subscription for a user.

    This is for manual testing and support purposes only. Fails closed while the
    user has an unresolved VNPAY payment.
    """
    try:
        subscription = await service.provision(
            admin_id=current_user.id,
            user_id=data.user_id,
            plan_id=data.plan_id,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ConflictException as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except InvalidTransitionException as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return SubscriptionAdminRead.model_validate(subscription)


@router.post(
    "/{subscription_id}/change-plan",
    response_model=SubscriptionAdminRead,
)
async def admin_change_subscription_plan(
    subscription_id: uuid.UUID,
    data: AdminSubscriptionChangePlan,
    current_user: User = Depends(require_admin),
    service: AdminSubscriptionService = Depends(_get_admin_subscription_service),
) -> SubscriptionAdminRead:
    """Change the plan of an active subscription in place."""
    try:
        subscription = await service.change_plan(
            admin_id=current_user.id,
            subscription_id=subscription_id,
            target_plan_id=data.target_plan_id,
            reason=data.reason,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ConflictException as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except InvalidTransitionException as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return SubscriptionAdminRead.model_validate(subscription)


@router.post(
    "/{subscription_id}/revoke",
    response_model=SubscriptionAdminRead,
)
async def admin_revoke_subscription(
    subscription_id: uuid.UUID,
    data: AdminSubscriptionRevoke,
    current_user: User = Depends(require_admin),
    service: AdminSubscriptionService = Depends(_get_admin_subscription_service),
) -> SubscriptionAdminRead:
    """Revoke a subscription immediately, recording an audited reason."""
    try:
        subscription = await service.revoke(
            admin_id=current_user.id,
            subscription_id=subscription_id,
            reason=data.reason,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ConflictException as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except InvalidTransitionException as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return SubscriptionAdminRead.model_validate(subscription)
