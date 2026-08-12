from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_candidate, require_recruiter
from app.core.exceptions import ConflictException, EntityNotFoundException
from app.models import User
from app.schemas.user import CandidateProfileCreate, RecruiterProfileCreate
from app.services.user_service import UserService

router = APIRouter()


@router.post(
    "/me/candidate-profile",
    status_code=status.HTTP_201_CREATED,
)
async def create_candidate_profile(
    data: CandidateProfileCreate,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        profile = await UserService(db).create_candidate_profile(
            user_id=current_user.id,
            data=data,
        )
    except ConflictException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "full_name": profile.full_name,
        "phone": profile.phone,
        "title": profile.title,
    }


@router.post(
    "/me/recruiter-profile",
    status_code=status.HTTP_201_CREATED,
)
async def create_recruiter_profile(
    data: RecruiterProfileCreate,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        profile = await UserService(db).create_recruiter_profile(
            user_id=current_user.id,
            data=data,
        )
    except ConflictException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "company_id": profile.company_id,
        "full_name": profile.full_name,
        "position": profile.position,
    }
