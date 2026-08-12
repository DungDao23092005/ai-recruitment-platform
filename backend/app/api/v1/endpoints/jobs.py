from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_recruiter
from app.core.exceptions import EntityNotFoundException
from app.domain.enums import JobStatus
from app.models import User
from app.schemas.job import JobCreate, JobRead
from app.services.job_service import JobService

router = APIRouter()


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
    try:
        job = await JobService(db).create_job(data)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return JobRead.model_validate(job)


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
    return [JobRead.model_validate(j) for j in jobs]


@router.get(
    "/{id}",
    response_model=JobRead,
)
async def get_job(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JobRead:
    service = JobService(db)
    job = await service.jobs.get_by_id(id)
    if job is None or job.is_deleted or job.status != JobStatus.PUBLISHED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return JobRead.model_validate(job)
