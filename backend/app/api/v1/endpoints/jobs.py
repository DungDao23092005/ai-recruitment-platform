from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ensure_not_interviewer,
    get_current_user_optional,
    get_db,
    get_optional_workspace,
    require_recruiter,
)
from app.core.exceptions import (
    AIError,
    EmptyDocumentError,
    EntityNotFoundException,
    ForbiddenException,
    InvalidDocumentError,
    InvalidTransitionException,
    ValidationError,
)
from app.domain.enums import JobStatus, JobType, UserRole, WorkplaceType
from app.models import CompanyMembership, Job, User
from app.repositories import CompanyMembershipRepository
from app.schemas.job import JobCreate, JobRead, JobStatusUpdate, JobUpdate
from app.services.company_service import CompanyService
from app.services.job_service import JobService
from app.services.job_view_telemetry_service import (
    JobViewTelemetryService,
    get_job_view_telemetry_service,
)
from app.services.workspace_service import WorkspaceContext

router = APIRouter()


def to_job_read(job: Job) -> JobRead:
    req_skills: list[str] = []
    pref_skills: list[str] = []
    skills_list: list[str] = []

    if isinstance(job, Job):
        if "required_skills" in job.__dict__ and job.required_skills:
            req_skills = [
                s.name if hasattr(s, "name") else str(s)
                for s in job.required_skills
                if s is not None
            ]
        if "preferred_skills" in job.__dict__ and job.preferred_skills:
            pref_skills = [
                s.name if hasattr(s, "name") else str(s)
                for s in job.preferred_skills
                if s is not None
            ]
        if "skills" in job.__dict__ and job.skills:
            skills_list = [
                s.name if hasattr(s, "name") else str(s)
                for s in job.skills
                if s is not None
            ]

        if not req_skills and not pref_skills and "job_skills" in job.__dict__ and job.job_skills:
            for js in job.job_skills:
                skill_obj = js.skill if ("skill" in js.__dict__ and js.skill) else None
                s_name = skill_obj.name if (skill_obj and hasattr(skill_obj, "name")) else None
                if s_name:
                    if js.is_mandatory:
                        if s_name not in req_skills:
                            req_skills.append(s_name)
                    else:
                        if s_name not in pref_skills:
                            pref_skills.append(s_name)
                    if s_name not in skills_list:
                        skills_list.append(s_name)

        if not skills_list and (req_skills or pref_skills):
            skills_list = list(dict.fromkeys(req_skills + pref_skills))
    else:
        # Fallback for mock or test objects
        req = getattr(job, "required_skills", None)
        if req:
            req_skills = [
                s.name if hasattr(s, "name") else str(s)
                for s in req
                if s is not None
            ]
        pref = getattr(job, "preferred_skills", None)
        if pref:
            pref_skills = [
                s.name if hasattr(s, "name") else str(s)
                for s in pref
                if s is not None
            ]
        sk = getattr(job, "skills", None)
        if sk:
            skills_list = [
                s.name if hasattr(s, "name") else str(s)
                for s in sk
                if s is not None
            ]
        elif req_skills or pref_skills:
            skills_list = list(dict.fromkeys(req_skills + pref_skills))

    company_name = job.company.name if (job.company is not None and hasattr(job.company, "name")) else None
    return JobRead(
        id=job.id,
        company_id=job.company_id,
        company_name=company_name,
        title=job.title,
        description=job.description,
        status=job.status,
        job_type=job.job_type,
        workplace_type=job.workplace_type,
        location=job.location,
        skills=skills_list,
        required_skills=req_skills,
        preferred_skills=pref_skills,
        minimum_years_experience=job.minimum_years_experience,
        education_level=job.education_level,
        published_at=job.published_at,
        expires_at=job.expires_at,
        expiration_duration_days=job.expiration_duration_days,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _get_job_service(db: AsyncSession = Depends(get_db)) -> JobService:
    return JobService(db)


@router.post(
    "",
    response_model=JobRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    data: JobCreate,
    request: Request,
    current_user: User = Depends(require_recruiter),
    workspace: WorkspaceContext | None = Depends(get_optional_workspace),
    service: JobService = Depends(_get_job_service),
) -> JobRead:
    ensure_not_interviewer(workspace)
    is_admin = current_user.role == UserRole.ADMIN

    if data.company_id is not None and (
        workspace is None or request.headers.get("X-Company-ID") is None
    ):
        company = await CompanyService(service.session).get_company_by_id(
            data.company_id
        )
        if company is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Company {data.company_id} not found",
            )
        if (
            not is_admin
            and workspace is not None
            and request.headers.get("X-Company-ID") is None
            and workspace.company_id != data.company_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "You do not have permission to create a job "
                    "for this company"
                ),
            )

    try:
        job = await service.create_job(
            data,
            current_user=current_user,
            workspace=workspace,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ForbiddenException as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
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
    workspace: WorkspaceContext | None = Depends(get_optional_workspace),
    skip: int = 0,
    limit: int = 10,
    service: JobService = Depends(_get_job_service),
) -> list[JobRead]:
    ensure_not_interviewer(workspace)
    if current_user.role == UserRole.ADMIN and workspace is None:
        jobs = await service.list_all_jobs(skip=skip, limit=limit)
    else:
        jobs = await service.list_recruiter_jobs(
            current_user.id,
            skip=skip,
            limit=limit,
            company_id=workspace.company_id if workspace else None,
        )
    return [to_job_read(j) for j in jobs]


@router.get(
    "/mine/{job_id}",
    response_model=JobRead,
)
async def get_my_job(
    job_id: uuid.UUID,
    current_user: User = Depends(require_recruiter),
    workspace: WorkspaceContext | None = Depends(get_optional_workspace),
    service: JobService = Depends(_get_job_service),
) -> JobRead:
    ensure_not_interviewer(workspace)
    try:
        job = await service.get_recruiter_job_by_id(
            current_user,
            job_id,
            company_id=workspace.company_id if workspace else None,
        )
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
    workspace: WorkspaceContext | None = Depends(get_optional_workspace),
    service: JobService = Depends(_get_job_service),
) -> JobRead:
    ensure_not_interviewer(workspace)
    try:
        job = await service.update_job(
            current_user, job_id, data, workspace=workspace
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ForbiddenException as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
    workspace: WorkspaceContext | None = Depends(get_optional_workspace),
    service: JobService = Depends(_get_job_service),
) -> JobRead:
    ensure_not_interviewer(workspace)
    try:
        job = await service.update_job_status(
            job_id,
            data.status,
            user_id=current_user.id,
            is_admin=current_user.role == UserRole.ADMIN,
            current_user=current_user,
            workspace=workspace,
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
    except ForbiddenException as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
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
    workspace: WorkspaceContext | None = Depends(get_optional_workspace),
    service: JobService = Depends(_get_job_service),
) -> None:
    ensure_not_interviewer(workspace)
    try:
        await service.delete_job(current_user, job_id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
    service: JobService = Depends(_get_job_service),
    telemetry: JobViewTelemetryService = Depends(
        get_job_view_telemetry_service
    ),
) -> JobRead:
    job = await service.jobs.get_job_with_company_and_skills(id)
    if job is None or job.is_deleted or job.status != JobStatus.PUBLISHED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if not await _is_own_company_view(db, current_user, job):
        # Best-effort, never raises: a telemetry outage must not break viewing.
        await telemetry.record_view(request, job)
    return to_job_read(job)


async def _is_own_company_view(
    db: AsyncSession, current_user: User | None, job: Job
) -> bool:
    """True when a recruiter is viewing a job owned by one of their companies."""
    if current_user is None or current_user.role != UserRole.RECRUITER:
        return False
    memberships = await CompanyMembershipRepository(
        db, CompanyMembership
    ).list_active_for_user(current_user.id)
    return any(
        membership.company_id == job.company_id
        for membership in memberships
    )
