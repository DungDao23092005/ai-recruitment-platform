from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_candidate, require_recruiter
from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    InvalidTransitionException,
)
from app.models import User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationRead,
    ApplicationStatusUpdate,
)
from app.services.application_service import ApplicationService
from app.services.job_service import JobService
from app.services.user_service import UserService

router = APIRouter()


@router.post(
    "",
    response_model=ApplicationRead,
    status_code=status.HTTP_201_CREATED,
)
async def apply_job(
    data: ApplicationCreate,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> ApplicationRead:
    user_with_profile = await UserService(db).users.get_with_profile(
        current_user.id
    )
    if (
        user_with_profile is None
        or user_with_profile.candidate_profile is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Candidate profile required",
        )

    candidate_id = user_with_profile.candidate_profile.id

    try:
        application = await ApplicationService(db).apply_job(
            candidate_id=candidate_id,
            job_id=data.job_id,
        )
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

    return ApplicationRead.model_validate(application)


@router.get(
    "",
    response_model=list[ApplicationRead],
)
async def list_applications(
    job_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> list[ApplicationRead]:
    if job_id is None:
        return []
    try:
        await JobService(db).get_recruiter_job_by_id(current_user, job_id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    applications = await ApplicationService(db).list_applications_by_job(
        job_id
    )
    return [
        ApplicationRead.model_validate(a)
        for a in applications[skip : skip + limit]
    ]


@router.patch(
    "/{id}/status",
    response_model=ApplicationRead,
)
async def update_application_status(
    id: uuid.UUID,
    data: ApplicationStatusUpdate,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> ApplicationRead:
    try:
        application = await ApplicationService(db).update_application_status(
            current_user=current_user,
            application_id=id,
            new_status=data.status,
        )
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

    return ApplicationRead.model_validate(application)
