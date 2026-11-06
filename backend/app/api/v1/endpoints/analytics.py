from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ensure_not_interviewer,
    get_db,
    get_optional_workspace,
    require_recruiter,
)
from app.core.exceptions import (
    EntityNotFoundException,
    ValidationError,
)
from app.models import User
from app.schemas.analytics import RecruiterAnalyticsResponse
from app.services.analytics_service import AnalyticsService
from app.services.workspace_service import WorkspaceContext

router = APIRouter()


@router.get(
    "/recruiter-dashboard",
    response_model=RecruiterAnalyticsResponse,
    summary="Recruitment analytics for the authenticated recruiter's company",
)
async def get_recruiter_analytics(
    current_user: User = Depends(require_recruiter),
    workspace: WorkspaceContext | None = Depends(get_optional_workspace),
    db: AsyncSession = Depends(get_db),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    job_id: uuid.UUID | None = Query(default=None),
) -> RecruiterAnalyticsResponse:
    """Return tenant-scoped views, funnel, hires and quota status.

    The company is always resolved from the authenticated recruiter's profile;
    a client-supplied company id is never accepted. ``job_id`` is validated
    against that company and returns 404 when it belongs to another tenant.
    Dates are Vietnam-local calendar dates.
    """
    ensure_not_interviewer(workspace)
    try:
        return await AnalyticsService(db).get_recruiter_dashboard(
            current_user,
            start_date=start_date,
            end_date=end_date,
            job_id=job_id,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
