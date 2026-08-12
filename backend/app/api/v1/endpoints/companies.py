from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_recruiter
from app.core.exceptions import ConflictException
from app.models import User
from app.schemas.company import CompanyCreate, CompanyRead
from app.services.company_service import CompanyService

router = APIRouter()


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
