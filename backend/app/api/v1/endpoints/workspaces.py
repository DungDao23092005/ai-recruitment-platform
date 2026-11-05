from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_active_user,
    get_current_workspace,
    get_db,
    require_recruiter,
)
from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
    InvalidTransitionException,
    ServiceException,
    ValidationError,
    WorkspaceRequiredException,
    WorkspaceSelectionRequiredException,
)
from app.models import User
from app.schemas.workspace import (
    InvitationAcceptRead,
    InvitationAcceptRequest,
    InvitationCreate,
    InvitationPreviewRead,
    InvitationPreviewRequest,
    InvitationRead,
    MemberRead,
    WorkspaceRead,
)
from app.services.workspace_service import WorkspaceContext, WorkspaceService

router = APIRouter()


def _service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EntityNotFoundException):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )
    if isinstance(
        exc, (ForbiddenException, WorkspaceRequiredException)
    ):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        )
    if isinstance(
        exc,
        (
            ConflictException,
            InvalidTransitionException,
        ),
    ):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )
    if isinstance(
        exc, (ValidationError, WorkspaceSelectionRequiredException)
    ):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
    )


@router.get(
    "/workspaces",
    response_model=list[WorkspaceRead],
)
async def list_workspaces(
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> list[WorkspaceRead]:
    try:
        return await WorkspaceService(db).list_workspaces(current_user)
    except ServiceException as exc:
        raise _service_error(exc) from exc


@router.get(
    "/workspaces/members",
    response_model=list[MemberRead],
)
async def list_workspace_members(
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> list[MemberRead]:
    try:
        return await WorkspaceService(db).list_members(workspace)
    except ServiceException as exc:
        raise _service_error(exc) from exc


@router.delete(
    "/workspaces/members/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_workspace_membership(
    membership_id: uuid.UUID,
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await WorkspaceService(db).revoke_membership(
            workspace, membership_id
        )
    except ServiceException as exc:
        raise _service_error(exc) from exc


@router.get(
    "/workspaces/invitations",
    response_model=list[InvitationRead],
)
async def list_workspace_invitations(
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> list[InvitationRead]:
    try:
        return await WorkspaceService(db).list_invitations(workspace)
    except ServiceException as exc:
        raise _service_error(exc) from exc


@router.post(
    "/workspaces/invitations",
    response_model=InvitationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_workspace_invitation(
    data: InvitationCreate,
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> InvitationRead:
    try:
        return await WorkspaceService(db).create_invitation(
            workspace, data
        )
    except ServiceException as exc:
        raise _service_error(exc) from exc


@router.post(
    "/workspaces/invitations/{invitation_id}/revoke",
    response_model=InvitationRead,
)
async def revoke_workspace_invitation(
    invitation_id: uuid.UUID,
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> InvitationRead:
    try:
        return await WorkspaceService(db).revoke_invitation(
            workspace, invitation_id
        )
    except ServiceException as exc:
        raise _service_error(exc) from exc


@router.post(
    "/invitations/preview",
    response_model=InvitationPreviewRead,
)
async def preview_invitation(
    data: InvitationPreviewRequest,
    db: AsyncSession = Depends(get_db),
) -> InvitationPreviewRead:
    try:
        return await WorkspaceService(db).preview_invitation(data.token)
    except ServiceException as exc:
        raise _service_error(exc) from exc


@router.post(
    "/invitations/accept",
    response_model=InvitationAcceptRead,
)
async def accept_invitation(
    data: InvitationAcceptRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> InvitationAcceptRead:
    try:
        return await WorkspaceService(db).accept_invitation(
            current_user, data.token
        )
    except ServiceException as exc:
        raise _service_error(exc) from exc
