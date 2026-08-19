from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.core.exceptions import EntityNotFoundException
from app.domain.enums import UserRole
from app.models import User
from app.schemas.admin import (
    AdminStatsResponse,
    AdminUserListResponse,
    AdminUserRead,
)
from app.services.admin_service import AdminService

router = APIRouter()


def _get_admin_service(db: AsyncSession = Depends(get_db)) -> AdminService:
    return AdminService(db)


@router.get("/stats", response_model=AdminStatsResponse)
async def get_admin_stats(
    current_user: User = Depends(require_admin),
    service: AdminService = Depends(_get_admin_service),
) -> AdminStatsResponse:
    return await service.get_stats()


@router.get("/users", response_model=AdminUserListResponse)
async def list_admin_users(
    current_user: User = Depends(require_admin),
    service: AdminService = Depends(_get_admin_service),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None, max_length=100),
    role: UserRole | None = Query(default=None),
) -> AdminUserListResponse:
    items, total = await service.list_users(
        skip=skip,
        limit=limit,
        search=search,
        role=role,
    )
    return AdminUserListResponse(
        items=[AdminUserRead.model_validate(user) for user in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/users/{user_id}", response_model=AdminUserRead)
async def get_admin_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    service: AdminService = Depends(_get_admin_service),
) -> AdminUserRead:
    try:
        user = await service.get_user(user_id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return AdminUserRead.model_validate(user)


@router.patch(
    "/users/{user_id}/deactivate",
    response_model=AdminUserRead,
)
async def deactivate_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    service: AdminService = Depends(_get_admin_service),
) -> AdminUserRead:
    try:
        user = await service.deactivate_user(user_id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return AdminUserRead.model_validate(user)