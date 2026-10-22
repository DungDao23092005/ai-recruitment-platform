from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_candidate, require_recruiter
from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
)
from app.models import Application, Job, Resume, User
from app.repositories import ApplicationRepository, JobRepository, ResumeRepository
from app.schemas.metrics import RecruiterMetricsResponse
from app.schemas.resume import (
    ResumeConfirmationRead,
    ResumeDraftUpdate,
    ResumeRead,
)
from app.schemas.user import (
    CandidateProfileCreate,
    CandidateProfileRead,
    CandidateProfileUpdate,
    RecruiterProfileCreate,
    RecruiterProfileRead,
    RecruiterProfileUpdate,
)
from app.services.resume_service import ResumeService
from app.services.user_service import UserService

router = APIRouter()


def _get_resume_service(
    db: AsyncSession = Depends(get_db),
) -> ResumeService:
    return ResumeService(db)


async def _require_candidate_profile_id(
    current_user: User,
    db: AsyncSession,
) -> uuid.UUID:
    user = await UserService(db).get_user_with_profile(current_user.id)
    if user is None or user.candidate_profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate profile not found",
        )
    return user.candidate_profile.id


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
    """Return the authenticated candidate's active confirmed primary resume.

    Identity always comes from the authenticated user's candidate profile;
    the endpoint never accepts a candidate/resume id from the client.
    """
    candidate_id = await _require_candidate_profile_id(current_user, db)
    resume = await ResumeRepository(db, Resume).get_primary_by_candidate(
        candidate_id
    )
    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Confirmed resume not found",
        )
    return ResumeRead.model_validate(resume)


@router.get(
    "/me/resume/draft",
    response_model=ResumeRead,
)
async def get_my_resume_draft(
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    service: ResumeService = Depends(_get_resume_service),
) -> ResumeRead:
    """Return the newest unconfirmed resume draft for review."""
    candidate_id = await _require_candidate_profile_id(current_user, db)
    draft = await service.get_draft(candidate_id)
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume draft not found",
        )
    return ResumeRead.model_validate(draft)


@router.put(
    "/me/resume/{resume_id}",
    response_model=ResumeRead,
)
async def update_my_resume_draft(
    resume_id: uuid.UUID,
    data: ResumeDraftUpdate,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    service: ResumeService = Depends(_get_resume_service),
) -> ResumeRead:
    """Persist candidate edits to an owned, unconfirmed resume draft."""
    candidate_id = await _require_candidate_profile_id(current_user, db)
    try:
        draft = await service.save_draft(
            candidate_id=candidate_id,
            resume_id=resume_id,
            parsed_data=data.parsed_data,
            title=data.title,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ConflictException as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return ResumeRead.model_validate(draft)


@router.post(
    "/me/resume/{resume_id}/confirm",
    response_model=ResumeConfirmationRead,
)
async def confirm_my_resume(
    resume_id: uuid.UUID,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    service: ResumeService = Depends(_get_resume_service),
) -> ResumeConfirmationRead:
    """Explicitly confirm an owned resume draft as the active searchable CV."""
    candidate_id = await _require_candidate_profile_id(current_user, db)
    try:
        result = await service.confirm_resume(
            candidate_id=candidate_id,
            resume_id=resume_id,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return ResumeConfirmationRead(
        resume=ResumeRead.model_validate(result.resume),
        indexing_status=result.indexing_status,
        message=result.message,
    )


@router.get(
    "/me/recruiter-metrics",
    response_model=RecruiterMetricsResponse,
)
async def get_recruiter_metrics(
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> RecruiterMetricsResponse:
    """Return aggregated recruiter metrics for the authenticated recruiter's company.

    Returns zero metrics if the recruiter has no associated company.
    """
    user = await UserService(db).get_user_with_profile(current_user.id)
    if user is None or user.recruiter_profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recruiter profile not found",
        )

    company_id = user.recruiter_profile.company_id
    if company_id is None:
        return RecruiterMetricsResponse(
            total_jobs=0,
            total_applications=0,
            jobs_by_status=[],
            applications_by_status=[],
        )

    job_counts = await JobRepository(db, Job).get_job_counts_by_status(company_id)
    application_counts = (
        await ApplicationRepository(db, Application).get_application_counts_by_status(
            company_id
        )
    )

    total_jobs = sum(item["count"] for item in job_counts)
    total_applications = sum(item["count"] for item in application_counts)

    return RecruiterMetricsResponse(
        total_jobs=total_jobs,
        total_applications=total_applications,
        jobs_by_status=[
            {"status": item["status"], "count": item["count"]}
            for item in job_counts
        ],
        applications_by_status=[
            {"status": item["status"], "count": item["count"]}
            for item in application_counts
        ],
    )
