from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_recruiter
from app.core.exceptions import EntityNotFoundException
from app.domain.enums import JobStatus, UserRole
from app.models import Job, User
from app.schemas.job import JobCreate, JobRead
from app.services.company_service import CompanyService
from app.services.job_service import JobService
from app.services.user_service import UserService

router = APIRouter()


def to_job_read(job: Job) -> JobRead:
    read = JobRead.model_validate(job)
    read.company_name = job.company.name if job.company is not None else None
    return read


@router.post(
    "",
    response_model=JobRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    data: JobCreate,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> JobRead:
    company = await CompanyService(db).get_company_by_id(data.company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {data.company_id} not found",
        )

    if current_user.role != UserRole.ADMIN:
        user = await UserService(db).get_user_with_profile(current_user.id)
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
        job = await JobService(db).create_job(data)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return to_job_read(job)


@router.get(
    "",
    response_model=list[JobRead],
)
async def list_jobs(
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
) -> list[JobRead]:
    jobs = await JobService(db).list_jobs(skip=skip, limit=limit)
    return [to_job_read(j) for j in jobs]


@router.get(
    "/mine",
    response_model=list[JobRead],
)
async def list_my_jobs(
    current_user: User = Depends(require_recruiter),
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
) -> list[JobRead]:
    service = JobService(db)
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
    db: AsyncSession = Depends(get_db),
) -> JobRead:
    service = JobService(db)
    try:
        job = await service.get_recruiter_job_by_id(current_user, job_id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return to_job_read(job)


@router.get(
    "/{id}",
    response_model=JobRead,
)
async def get_job(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JobRead:
    service = JobService(db)
    job = await service.jobs.get_job_with_company(id)
    if job is None or job.is_deleted or job.status != JobStatus.PUBLISHED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return to_job_read(job)
