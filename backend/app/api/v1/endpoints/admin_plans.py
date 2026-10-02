from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.core.exceptions import ConflictException, EntityNotFoundException, ValidationError
from app.models import User
from app.schemas.recruitment_plan import (
    PlanStatusUpdate,
    RecruitmentPlanAdminRead,
    RecruitmentPlanCreate,
    RecruitmentPlanUpdate,
)
from app.services.recruitment_plan_service import RecruitmentPlanService

router = APIRouter(prefix="/admin/plans", tags=["Admin - Recruitment Plans"], dependencies=[Depends(require_admin)])


def _get_plan_service(db: AsyncSession = Depends(get_db)) -> RecruitmentPlanService:
    return RecruitmentPlanService(db)


@router.get(
    "",
    response_model=list[RecruitmentPlanAdminRead],
)
async def list_admin_plans(
    current_user: User = Depends(require_admin),
    service: RecruitmentPlanService = Depends(_get_plan_service),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    search: Optional[str] = Query(default=None, max_length=100),
) -> list[RecruitmentPlanAdminRead]:
    """List all recruitment plans for admin (including inactive)."""
    plans, total = await service.list_admin(skip, limit, search)
    return [RecruitmentPlanAdminRead.model_validate(p) for p in plans]


@router.post(
    "",
    response_model=RecruitmentPlanAdminRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_plan(
    data: RecruitmentPlanCreate,
    current_user: User = Depends(require_admin),
    service: RecruitmentPlanService = Depends(_get_plan_service),
) -> RecruitmentPlanAdminRead:
    """Create a new recruitment plan (admin only)."""
    try:
        plan = await service.create_plan(data)
    except ConflictException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return RecruitmentPlanAdminRead.model_validate(plan)


@router.get(
    "/{plan_id}",
    response_model=RecruitmentPlanAdminRead,
)
async def get_admin_plan(
    plan_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    service: RecruitmentPlanService = Depends(_get_plan_service),
) -> RecruitmentPlanAdminRead:
    """Get a recruitment plan by ID for admin."""
    plan = await service.get_plan_admin(plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found",
        )
    return RecruitmentPlanAdminRead.model_validate(plan)


@router.patch(
    "/{plan_id}",
    response_model=RecruitmentPlanAdminRead,
)
async def update_plan(
    plan_id: uuid.UUID,
    data: RecruitmentPlanUpdate,
    current_user: User = Depends(require_admin),
    service: RecruitmentPlanService = Depends(_get_plan_service),
) -> RecruitmentPlanAdminRead:
    """Update a recruitment plan (admin only)."""
    try:
        plan = await service.update_plan(plan_id, data)
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
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return RecruitmentPlanAdminRead.model_validate(plan)


@router.patch(
    "/{plan_id}/status",
    response_model=RecruitmentPlanAdminRead,
)
async def update_plan_status(
    plan_id: uuid.UUID,
    data: PlanStatusUpdate,
    current_user: User = Depends(require_admin),
    service: RecruitmentPlanService = Depends(_get_plan_service),
) -> RecruitmentPlanAdminRead:
    """Activate or deactivate a recruitment plan (admin only)."""
    try:
        plan = await service.set_plan_status(plan_id, data.is_active)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return RecruitmentPlanAdminRead.model_validate(plan)