from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_active_user
from app.core.exceptions import ConflictException, EntityNotFoundException, ValidationError
from app.models import User
from app.schemas.recruitment_plan import RecruitmentPlanRead
from app.services.recruitment_plan_service import RecruitmentPlanService

router = APIRouter(prefix="/plans", tags=["Recruitment Plans"])


def _get_plan_service(db: AsyncSession = Depends(get_db)) -> RecruitmentPlanService:
    return RecruitmentPlanService(db)


@router.get(
    "",
    response_model=list[RecruitmentPlanRead],
)
async def list_active_plans(
    current_user: User = Depends(get_current_active_user),
    service: RecruitmentPlanService = Depends(_get_plan_service),
) -> list[RecruitmentPlanRead]:
    """List all active recruitment plans."""
    plans = await service.list_active_plans()
    return [RecruitmentPlanRead.model_validate(p) for p in plans]


@router.get(
    "/{plan_id}",
    response_model=RecruitmentPlanRead,
)
async def get_plan(
    plan_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: RecruitmentPlanService = Depends(_get_plan_service),
) -> RecruitmentPlanRead:
    """Get an active recruitment plan by ID."""
    plan = await service.get_plan(plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found or inactive",
        )
    return RecruitmentPlanRead.model_validate(plan)