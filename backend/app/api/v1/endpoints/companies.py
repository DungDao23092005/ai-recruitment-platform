from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin, require_recruiter
from app.core.exceptions import (
    AIError,
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
)
from app.domain.enums import UserRole
from app.models import User
from app.schemas.company import CompanyCreate, CompanyRead, CompanyUpdate
from app.services.company_service import CompanyService
from app.services.user_service import UserService

router = APIRouter()


def _get_company_service(db: AsyncSession = Depends(get_db)) -> CompanyService:
    return CompanyService(db)


@router.post(
    "",
    response_model=CompanyRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_company(
    data: CompanyCreate,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> CompanyRead:
    try:
        company = await CompanyService(db).create_company(data)
    except ConflictException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if current_user.role == UserRole.RECRUITER:
        await UserService(db).attach_recruiter_to_company(
            user_id=current_user.id,
            company_id=company.id,
        )

    return CompanyRead.model_validate(company)


@router.get(
    "",
    response_model=list[CompanyRead],
)
async def list_companies(
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> list[CompanyRead]:
    if current_user.role == UserRole.ADMIN:
        companies = await CompanyService(db).list_companies()
        return [CompanyRead.model_validate(c) for c in companies]

    user = await UserService(db).get_user_with_profile(current_user.id)
    profile = user.recruiter_profile if user is not None else None
    if profile is None or profile.company_id is None:
        return []

    company = await CompanyService(db).get_company_by_id(profile.company_id)
    if company is None:
        return []
    return [CompanyRead.model_validate(company)]


@router.patch(
    "/{company_id}",
    response_model=CompanyRead,
)
async def update_company(
    company_id: uuid.UUID,
    data: CompanyUpdate,
    current_user: User = Depends(require_recruiter),
    service: CompanyService = Depends(_get_company_service),
) -> CompanyRead:
    """Update the company owned by the caller (name/slug/tax_code/size).

    Ownership is resolved server-side through the caller's recruiter
    profile; a foreign company yields 403. Admin, allowed by the shared
    ``require_recruiter`` guard and the job-ownership convention, may update
    any company. All validation/uniqueness/commit logic is reused from
    ``CompanyService.update_company`` (via ``update_owned_company``).
    """
    try:
        company = await service.update_owned_company(
            current_user, company_id, data
        )
    except ForbiddenException as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
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
    return CompanyRead.model_validate(company)


@router.get(
    "/{id}",
    response_model=CompanyRead,
)
async def get_company(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CompanyRead:
    company = await CompanyService(db).get_company_by_id(id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {id} not found",
        )
    return CompanyRead.model_validate(company)


@router.delete(
    "/{company_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_company(
    company_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    service: CompanyService = Depends(_get_company_service),
) -> None:
    """Admin-only company lock: soft-delete the company and cascade-delete
    its active jobs (soft delete + Qdrant vector removal). Applications are
    preserved."""
    try:
        await service.delete_company(current_user, company_id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except AIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
