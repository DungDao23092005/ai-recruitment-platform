from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_workspace, get_db
from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
    InvalidTransitionException,
    ServiceException,
)
from app.schemas.interview import (
    AssignedInterviewRead,
    InterviewerApplicationRead,
    InterviewerInterviewRead,
)
from app.schemas.interview_assignment import (
    InterviewAssignmentCreate,
    InterviewAssignmentRead,
)
from app.schemas.interview_evaluation import (
    InterviewEvaluationCreate,
    InterviewEvaluationRead,
    InterviewEvaluationUpdate,
)
from app.services.interview_assignment_service import InterviewAssignmentService
from app.services.interview_evaluation_service import InterviewEvaluationService
from app.services.interview_service import InterviewService
from app.services.workspace_service import WorkspaceContext, WorkspaceService

router = APIRouter()


def _service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EntityNotFoundException):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )
    if isinstance(exc, ForbiddenException):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        )
    if isinstance(exc, (ConflictException, InvalidTransitionException)):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
    )


@router.get(
    "/mine",
    response_model=list[AssignedInterviewRead],
)
async def list_my_interviews(
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> list[AssignedInterviewRead]:
    return await InterviewService(db).list_assigned_for_user(workspace)


@router.get(
    "/{interview_id}",
    response_model=InterviewerInterviewRead,
)
async def get_interview_for_workspace_member(
    interview_id: uuid.UUID,
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> InterviewerInterviewRead:
    try:
        return await InterviewService(db).get_interview_for_workspace_member(
            workspace, interview_id
        )
    except ServiceException as exc:
        raise _service_error(exc) from exc


@router.get(
    "/{interview_id}/application",
    response_model=InterviewerApplicationRead,
)
async def get_interview_application(
    interview_id: uuid.UUID,
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> InterviewerApplicationRead:
    try:
        return await InterviewService(
            db
        ).get_application_for_workspace_member(workspace, interview_id)
    except ServiceException as exc:
        raise _service_error(exc) from exc


@router.get(
    "/{interview_id}/evaluations",
    response_model=list[InterviewEvaluationRead],
)
async def list_interview_evaluations_for_workspace(
    interview_id: uuid.UUID,
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> list[InterviewEvaluationRead]:
    try:
        return await InterviewEvaluationService(db).list_for_workspace(
            workspace, interview_id
        )
    except ServiceException as exc:
        raise _service_error(exc) from exc


@router.post(
    "/{interview_id}/evaluations",
    response_model=InterviewEvaluationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_interview_evaluation_for_workspace(
    interview_id: uuid.UUID,
    data: InterviewEvaluationCreate,
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> InterviewEvaluationRead:
    try:
        return await InterviewEvaluationService(db).create_for_workspace(
            workspace, interview_id, data
        )
    except ServiceException as exc:
        raise _service_error(exc) from exc


@router.patch(
    "/{interview_id}/evaluations/{evaluation_id}",
    response_model=InterviewEvaluationRead,
)
async def update_interview_evaluation_for_workspace(
    interview_id: uuid.UUID,
    evaluation_id: uuid.UUID,
    data: InterviewEvaluationUpdate,
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> InterviewEvaluationRead:
    try:
        return await InterviewEvaluationService(db).update_for_workspace(
            workspace, interview_id, evaluation_id, data
        )
    except ServiceException as exc:
        raise _service_error(exc) from exc


@router.delete(
    "/{interview_id}/evaluations/{evaluation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_interview_evaluation_for_workspace(
    interview_id: uuid.UUID,
    evaluation_id: uuid.UUID,
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await InterviewEvaluationService(db).delete_for_workspace(
            workspace, interview_id, evaluation_id
        )
    except ServiceException as exc:
        raise _service_error(exc) from exc


@router.post(
    "/{interview_id}/evaluations/{evaluation_id}/submit",
    response_model=InterviewEvaluationRead,
)
async def submit_interview_evaluation_for_workspace(
    interview_id: uuid.UUID,
    evaluation_id: uuid.UUID,
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> InterviewEvaluationRead:
    try:
        return await InterviewEvaluationService(db).submit_for_workspace(
            workspace, interview_id, evaluation_id
        )
    except ServiceException as exc:
        raise _service_error(exc) from exc


@router.get(
    "/{interview_id}/assignments",
    response_model=list[InterviewAssignmentRead],
)
async def list_interview_assignments(
    interview_id: uuid.UUID,
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> list[InterviewAssignmentRead]:
    try:
        return await InterviewAssignmentService(db).list_for_interview(
            workspace, interview_id
        )
    except ServiceException as exc:
        raise _service_error(exc) from exc


@router.post(
    "/{interview_id}/assignments",
    response_model=InterviewAssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def assign_interview(
    interview_id: uuid.UUID,
    data: InterviewAssignmentCreate,
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> InterviewAssignmentRead:
    try:
        return await InterviewAssignmentService(db).assign(
            workspace, interview_id, data.user_id
        )
    except ServiceException as exc:
        raise _service_error(exc) from exc


@router.delete(
    "/{interview_id}/assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unassign_interview(
    interview_id: uuid.UUID,
    assignment_id: uuid.UUID,
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await InterviewAssignmentService(db).unassign(
            workspace, interview_id, assignment_id
        )
    except ServiceException as exc:
        raise _service_error(exc) from exc
