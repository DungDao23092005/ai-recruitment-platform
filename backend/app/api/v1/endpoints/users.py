from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_candidate, require_recruiter
from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
)
from app.models import Resume, User
from app.repositories import ResumeRepository
from app.schemas.resume import ResumeRead
from app.schemas.user import (
    CandidateProfileCreate,
    CandidateProfileRead,
    CandidateProfileUpdate,
    RecruiterProfileCreate,
    RecruiterProfileRead,
    RecruiterProfileUpdate,
)
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


@router.get(
    "/me/candidate-profile",
    response_model=CandidateProfileRead,
)
async def get_candidate_profile(
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> CandidateProfileRead:
    try:
        profile = await UserService(db).get_candidate_profile(current_user.id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate profile not found",
        )
    return CandidateProfileRead.model_validate(profile)


@router.put(
    "/me/candidate-profile",
    response_model=CandidateProfileRead,
)
async def upsert_candidate_profile(
    data: CandidateProfileUpdate,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> CandidateProfileRead:
    try:
        profile = await UserService(db).upsert_candidate_profile(
            user_id=current_user.id,
            data=data,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return CandidateProfileRead.model_validate(profile)


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


@router.get(
    "/me/recruiter-profile",
    response_model=RecruiterProfileRead,
)
async def get_recruiter_profile(
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> RecruiterProfileRead:
    try:
        profile = await UserService(db).get_recruiter_profile(current_user.id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recruiter profile not found",
        )
    return RecruiterProfileRead.model_validate(profile)


@router.put(
    "/me/recruiter-profile",
    response_model=RecruiterProfileRead,
)
async def upsert_recruiter_profile(
    data: RecruiterProfileUpdate,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> RecruiterProfileRead:
    try:
        profile = await UserService(db).upsert_recruiter_profile(
            user_id=current_user.id,
            data=data,
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

    return RecruiterProfileRead.model_validate(profile)


@router.get(
    "/me/resume",
    response_model=ResumeRead,
)
async def get_my_resume(
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> ResumeRead:
    """Return the authenticated candidate's primary resume.

    Identity always comes from the authenticated user's candidate profile;
    the endpoint never accepts a candidate/resume id from the client.
    """
    user = await UserService(db).get_user_with_profile(current_user.id)
    if user is None or user.candidate_profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate profile not found",
        )

    resume = await ResumeRepository(db, Resume).get_primary_by_candidate(
        user.candidate_profile.id
    )
    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found",
        )
    return ResumeRead.model_validate(resume)
