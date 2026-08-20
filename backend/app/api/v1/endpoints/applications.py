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
from app.models import Application, User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationDetailRead,
    ApplicationRead,
    ApplicationStatusUpdate,
    ApplicationWithJobRead,
    CandidateProfileReadMinimal,
)
from app.schemas.resume import ResumeRead
from app.services.application_service import ApplicationService
from app.services.job_service import JobService
from app.services.user_service import UserService

router = APIRouter()


def to_application_with_job_read(
    application: Application,
) -> ApplicationWithJobRead:
    return ApplicationWithJobRead(
        id=application.id,
        job_id=application.job_id,
        job_title=application.job.title,
        company_name=(
            application.job.company.name
            if application.job.company is not None
            else None
        ),
        status=application.status,
        created_at=application.created_at,
        updated_at=application.updated_at,
    )


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
    "/mine",
    response_model=list[ApplicationWithJobRead],
)
async def list_my_applications(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> list[ApplicationWithJobRead]:
    applications = await ApplicationService(db).list_my_applications(
        current_user=current_user,
        skip=skip,
        limit=limit,
    )
    return [
        to_application_with_job_read(application)
        for application in applications
    ]


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


@router.get(
    "/{application_id}",
    response_model=ApplicationDetailRead,
)
async def get_application_detail(
    application_id: uuid.UUID,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetailRead:
    """Return a single application detail for a recruiter/admin.

    Includes the candidate's primary resume (``parsed_data``) so the
    recruiter can view the digital CV. Ownership is enforced server-side:
    admin may access any application; a recruiter only their own company's.
    """
    try:
        application, resume = await ApplicationService(
            db
        ).get_application_detail(
            current_user=current_user,
            application_id=application_id,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    company_name = (
        application.job.company.name
        if application.job is not None and application.job.company is not None
        else None
    )
    return ApplicationDetailRead(
        id=application.id,
        candidate_id=application.candidate_id,
        job_id=application.job_id,
        job_title=application.job.title if application.job is not None else "",
        company_name=company_name,
        status=application.status,
        created_at=application.created_at,
        updated_at=application.updated_at,
        candidate=(
            CandidateProfileReadMinimal.model_validate(application.candidate)
            if application.candidate is not None
            else None
        ),
        resume=ResumeRead.model_validate(resume) if resume is not None else None,
    )


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


@router.patch(
    "/mine/{application_id}/withdraw",
    response_model=ApplicationRead,
)
async def withdraw_application(
    application_id: uuid.UUID,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> ApplicationRead:
    try:
        application = await ApplicationService(db).withdraw_application(
            current_user=current_user,
            application_id=application_id,
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
