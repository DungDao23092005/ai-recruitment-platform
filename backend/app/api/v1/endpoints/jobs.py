from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_recruiter
from app.core.exceptions import (
    AIError,
    EmptyDocumentError,
    EntityNotFoundException,
    InvalidDocumentError,
    InvalidTransitionException,
)
from app.domain.enums import JobStatus, JobType, UserRole, WorkplaceType
from app.models import Job, User
from app.schemas.job import JobCreate, JobRead, JobStatusUpdate, JobUpdate
from app.services.company_service import CompanyService
from app.services.job_service import JobService
from app.services.user_service import UserService

router = APIRouter()


def to_job_read(job: Job) -> JobRead:
    read = JobRead.model_validate(job)
    read.company_name = job.company.name if job.company is not None else None
    return read


def _get_job_service(db: AsyncSession = Depends(get_db)) -> JobService:
    return JobService(db)


@router.post(
    "",
    response_model=JobRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    data: JobCreate,
    current_user: User = Depends(require_recruiter),
    service: JobService = Depends(_get_job_service),
) -> JobRead:
    company = await CompanyService(service.session).get_company_by_id(
        data.company_id
    )
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {data.company_id} not found",
        )

    if current_user.role != UserRole.ADMIN:
        user = await UserService(service.session).get_user_with_profile(
            current_user.id
        )
        profile = user.recruiter_profile if user is not None else None
        owned_company_id = profile.company_id if profile is not None else None
        if owned_company_id is None or owned_company_id != data.company_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "You do not have permission to create a job "
                    "for this company"
                ),
            )

    try:
        job = await service.create_job(data)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return to_job_read(job)


@router.get(
    "",
    response_model=dict,
)
async def list_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    keyword: str | None = Query(None),
    workplace_type: WorkplaceType | None = Query(None),
    job_type: JobType | None = Query(None),
    location: str | None = Query(None),
    service: JobService = Depends(_get_job_service),
) -> dict:
    """Public job board: list published jobs with filters and pagination.

    Returns: { items: JobRead[], total: int }
    """
    jobs, total = await service.list_public_jobs(
        skip=skip,
        limit=limit,
        keyword=keyword,
        workplace_type=workplace_type,
        job_type=job_type,
        location=location,
    )
    return {"items": [to_job_read(j) for j in jobs], "total": total}


@router.get(
    "/mine",
    response_model=list[JobRead],
)
async def list_my_jobs(
    current_user: User = Depends(require_recruiter),
    skip: int = 0,
    limit: int = 10,
    service: JobService = Depends(_get_job_service),
) -> list[JobRead]:
    if current_user.role == UserRole.ADMIN:
        jobs = await service.list_all_jobs(skip=skip, limit=limit)
    else:
        jobs = await service.list_recruiter_jobs(
            current_user.id,
            skip=skip,
            limit=limit,
        )
    return [to_job_read(j) for j in jobs]


@router.get(
    "/mine/{job_id}",
    response_model=JobRead,
)
async def get_my_job(
    job_id: uuid.UUID,
    current_user: User = Depends(require_recruiter),
    service: JobService = Depends(_get_job_service),
) -> JobRead:
    try:
        job = await service.get_recruiter_job_by_id(current_user, job_id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return to_job_read(job)


@router.patch(
    "/mine/{job_id}",
    response_model=JobRead,
)
async def update_my_job(
    job_id: uuid.UUID,
    data: JobUpdate,
    current_user: User = Depends(require_recruiter),
    service: JobService = Depends(_get_job_service),
) -> JobRead:
    try:
        job = await service.update_job(current_user, job_id, data)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (AIError, EmptyDocumentError, InvalidDocumentError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return to_job_read(job)


@router.patch(
    "/mine/{job_id}/status",
    response_model=JobRead,
)
async def update_my_job_status(
    job_id: uuid.UUID,
    data: JobStatusUpdate,
    current_user: User = Depends(require_recruiter),
    service: JobService = Depends(_get_job_service),
) -> JobRead:
    try:
        await service.get_recruiter_job_by_id(current_user, job_id)
        job = await service.update_job_status(job_id, data.status)
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
    return to_job_read(job)


@router.delete(
    "/mine/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_my_job(
    job_id: uuid.UUID,
    current_user: User = Depends(require_recruiter),
    service: JobService = Depends(_get_job_service),
) -> None:
    try:
        await service.delete_job(current_user, job_id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (AIError, EmptyDocumentError, InvalidDocumentError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "/{id}",
    response_model=JobRead,
)
async def get_job(
    id: uuid.UUID,
    service: JobService = Depends(_get_job_service),
) -> JobRead:
    job = await service.jobs.get_job_with_company(id)
    if job is None or job.is_deleted or job.status != JobStatus.PUBLISHED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return to_job_read(job)
