from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.core.exceptions import EntityNotFoundException
from app.domain.enums import AdminAuditAction, UserRole
from app.models import AdminAuditLog, User
from app.schemas.admin import (
    AdminCompanyListResponse,
    AdminCompanyRead,
    AdminJobListParams,
    AdminJobListResponse,
    AdminJobRead,
    AdminStatsResponse,
    AdminUserListResponse,
    AdminUserRead,
)
from app.schemas.admin_audit import (
    AdminAuditLogListParams,
    AdminAuditLogListResponse,
    AdminAuditLogRead,
)
from app.services.admin_service import AdminService

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_admin)],
)


def _get_admin_service(db: AsyncSession = Depends(get_db)) -> AdminService:
    return AdminService(db)


def _to_admin_audit_read(log: AdminAuditLog) -> AdminAuditLogRead:
    return AdminAuditLogRead(
        id=log.id,
        admin_id=log.admin_id,
        admin_email=log.admin.email if log.admin is not None else None,
        target_user_id=log.target_user_id,
        target_user_email=(
            log.target_user.email if log.target_user is not None else None
        ),
        action=log.action,
        reason=log.reason,
        details=log.details,
        created_at=log.created_at,
    )


@router.get("/audit-logs", response_model=AdminAuditLogListResponse)
async def list_admin_audit_logs(
    current_user: User = Depends(require_admin),
    service: AdminService = Depends(_get_admin_service),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    action: AdminAuditAction | None = Query(default=None),
    admin_id: uuid.UUID | None = Query(default=None),
    target_user_id: uuid.UUID | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
) -> AdminAuditLogListResponse:
    try:
        params = AdminAuditLogListParams(
            skip=skip,
            limit=limit,
            action=action,
            admin_id=admin_id,
            target_user_id=target_user_id,
            created_from=created_from,
            created_to=created_to,
            search=search,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="; ".join(error["msg"] for error in exc.errors()),
        ) from exc

    items, total = await service.list_audit_logs(params)
    return AdminAuditLogListResponse(
        items=[_to_admin_audit_read(log) for log in items],
        total=total,
        skip=params.skip,
        limit=params.limit,
    )


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


@router.get("/companies", response_model=AdminCompanyListResponse)
async def list_admin_companies(
    current_user: User = Depends(require_admin),
    service: AdminService = Depends(_get_admin_service),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None, max_length=100),
) -> AdminCompanyListResponse:
    items, total = await service.list_companies(
        skip=skip,
        limit=limit,
        search=search,
    )
    return AdminCompanyListResponse(
        items=[AdminCompanyRead.model_validate(company) for company in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/jobs", response_model=AdminJobListResponse)
async def list_admin_jobs(
    current_user: User = Depends(require_admin),
    service: AdminService = Depends(_get_admin_service),
    params: AdminJobListParams = Depends(),
) -> AdminJobListResponse:
    items, total = await service.list_jobs(params)
    return AdminJobListResponse(
        items=[AdminJobRead.model_validate(job) for job in items],
        total=total,
        skip=params.skip,
        limit=params.limit,
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


from pydantic import BaseModel, ConfigDict, Field


class DeactivateUserRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for locking the account")


@router.patch(
    "/users/{user_id}/deactivate",
    response_model=AdminUserRead,
)
async def deactivate_user(
    user_id: uuid.UUID,
    payload: DeactivateUserRequest,
    current_user: User = Depends(require_admin),
    service: AdminService = Depends(_get_admin_service),
) -> AdminUserRead:
    try:
        user = await service.deactivate_user(user_id, reason=payload.reason, admin_id=current_user.id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return AdminUserRead.model_validate(user)


@router.patch(
    "/users/{user_id}/activate",
    response_model=AdminUserRead,
)
async def activate_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    service: AdminService = Depends(_get_admin_service),
) -> AdminUserRead:
    try:
        user = await service.activate_user(user_id, admin_id=current_user.id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return AdminUserRead.model_validate(user)


@router.delete(
    "/users/{user_id}",
    response_model=AdminUserRead,
)
async def delete_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    service: AdminService = Depends(_get_admin_service),
) -> AdminUserRead:
    try:
        user = await service.delete_user(user_id, admin_id=current_user.id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return AdminUserRead.model_validate(user)