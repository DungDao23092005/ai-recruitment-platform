from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ensure_not_interviewer,
    get_current_workspace,
    get_db,
    require_candidate,
    require_recruiter,
)
from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
)
from app.domain.enums import ContactRequestStatus
from app.models.user import User
from app.schemas.contact_request import (
    CandidateContactResponse,
    ContactRequestCreate,
    ContactRequestRead,
    ContactRequestStatusCheck,
)
from app.services.contact_request_service import ContactRequestService
from app.services.user_service import UserService
from app.services.workspace_service import WorkspaceContext

router = APIRouter()


# ----------------------------------------------------------------------
# Recruiter Endpoints
# ----------------------------------------------------------------------


@router.post(
    "/contact-requests",
    response_model=ContactRequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a contact authorization request for a discoverable candidate",
)
async def create_contact_request(
    data: ContactRequestCreate,
    current_user: User = Depends(require_recruiter),
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> ContactRequestRead:
    ensure_not_interviewer(workspace)
    service = ContactRequestService(db)
    try:
        req = await service.create_contact_request(
            company_id=workspace.company_id,
            candidate_id=data.candidate_id,
            requester_user_id=current_user.id,
        )
        await db.commit()

        return ContactRequestRead(
            id=req.id,
            company_id=req.company_id,
            candidate_id=req.candidate_id,
            requester_user_id=req.requester_user_id,
            status=req.status,
            created_at=req.created_at,
            updated_at=req.updated_at,
            expires_at=req.expires_at,
            responded_at=req.responded_at,
            revoked_at=req.revoked_at,
            company_name=workspace.company.name if workspace.company else None,
            candidate_name=None,
            candidate_title=None,
        )
    except ConflictException as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except EntityNotFoundException as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ForbiddenException as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.get(
    "/contact-requests",
    response_model=list[ContactRequestRead],
    summary="List contact requests initiated by the active company",
)
async def list_company_contact_requests(
    status_filter: Optional[ContactRequestStatus] = Query(None, alias="status"),
    current_user: User = Depends(require_recruiter),
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> list[ContactRequestRead]:
    ensure_not_interviewer(workspace)
    service = ContactRequestService(db)
    reqs = await service.list_for_company(
        company_id=workspace.company_id, status=status_filter
    )
    await db.commit()

    return [
        ContactRequestRead(
            id=r.id,
            company_id=r.company_id,
            candidate_id=r.candidate_id,
            requester_user_id=r.requester_user_id,
            status=r.status,
            created_at=r.created_at,
            updated_at=r.updated_at,
            expires_at=r.expires_at,
            responded_at=r.responded_at,
            revoked_at=r.revoked_at,
            company_name=r.company.name if r.company else (workspace.company.name if workspace.company else None),
            candidate_name=r.candidate.full_name if r.candidate else None,
            candidate_title=r.candidate.title if r.candidate else None,
        )
        for r in reqs
    ]


@router.get(
    "/contact-requests/candidates/{candidate_id}/status",
    response_model=ContactRequestStatusCheck,
    summary="Check contact authorization status and re-request eligibility for a candidate",
)
async def check_candidate_contact_status(
    candidate_id: uuid.UUID,
    current_user: User = Depends(require_recruiter),
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> ContactRequestStatusCheck:
    ensure_not_interviewer(workspace)
    service = ContactRequestService(db)
    result = await service.check_contact_request_status(
        company_id=workspace.company_id,
        candidate_id=candidate_id,
    )
    await db.commit()
    return result


@router.get(
    "/contact-requests/candidates/{candidate_id}/contact",
    response_model=CandidateContactResponse,
    summary="Dedicated authorized contact disclosure endpoint",
)
async def get_candidate_contact_details(
    candidate_id: uuid.UUID,
    current_user: User = Depends(require_recruiter),
    workspace: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> CandidateContactResponse:
    ensure_not_interviewer(workspace)
    service = ContactRequestService(db)
    try:
        contact = await service.disclose_contact_details(
            company_id=workspace.company_id,
            candidate_id=candidate_id,
            disclosed_to_user_id=current_user.id,
        )
        await db.commit()
        return contact
    except ForbiddenException as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except EntityNotFoundException as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ----------------------------------------------------------------------
# Candidate Endpoints
# ----------------------------------------------------------------------


@router.get(
    "/candidate/contact-requests",
    response_model=list[ContactRequestRead],
    summary="List incoming contact requests for the authenticated candidate",
)
async def list_candidate_contact_requests(
    status_filter: Optional[ContactRequestStatus] = Query(None, alias="status"),
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> list[ContactRequestRead]:
    user_with_profile = await UserService(db).users.get_with_profile(
        current_user.id
    )
    if not user_with_profile or not user_with_profile.candidate_profile:
        return []

    candidate_id = user_with_profile.candidate_profile.id
    service = ContactRequestService(db)
    reqs = await service.list_for_candidate(
        candidate_id=candidate_id, status=status_filter
    )
    await db.commit()

    return [
        ContactRequestRead(
            id=r.id,
            company_id=r.company_id,
            candidate_id=r.candidate_id,
            requester_user_id=r.requester_user_id,
            status=r.status,
            created_at=r.created_at,
            updated_at=r.updated_at,
            expires_at=r.expires_at,
            responded_at=r.responded_at,
            revoked_at=r.revoked_at,
            company_name=r.company.name if r.company else None,
            candidate_name=r.candidate.full_name if r.candidate else None,
            candidate_title=r.candidate.title if r.candidate else None,
        )
        for r in reqs
    ]


@router.post(
    "/candidate/contact-requests/{request_id}/accept",
    response_model=ContactRequestRead,
    summary="Candidate accepts an incoming contact request",
)
async def accept_candidate_contact_request(
    request_id: uuid.UUID,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> ContactRequestRead:
    user_with_profile = await UserService(db).users.get_with_profile(
        current_user.id
    )
    if not user_with_profile or not user_with_profile.candidate_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Candidate profile required",
        )

    candidate_id = user_with_profile.candidate_profile.id
    service = ContactRequestService(db)
    try:
        req = await service.accept_request(request_id, candidate_id)
        await db.commit()
        return ContactRequestRead(
            id=req.id,
            company_id=req.company_id,
            candidate_id=req.candidate_id,
            requester_user_id=req.requester_user_id,
            status=req.status,
            created_at=req.created_at,
            updated_at=req.updated_at,
            expires_at=req.expires_at,
            responded_at=req.responded_at,
            revoked_at=req.revoked_at,
            company_name=req.company.name if req.company else None,
            candidate_name=req.candidate.full_name if req.candidate else None,
            candidate_title=req.candidate.title if req.candidate else None,
        )
    except EntityNotFoundException as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ConflictException as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/candidate/contact-requests/{request_id}/decline",
    response_model=ContactRequestRead,
    summary="Candidate declines an incoming contact request",
)
async def decline_candidate_contact_request(
    request_id: uuid.UUID,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> ContactRequestRead:
    user_with_profile = await UserService(db).users.get_with_profile(
        current_user.id
    )
    if not user_with_profile or not user_with_profile.candidate_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Candidate profile required",
        )

    candidate_id = user_with_profile.candidate_profile.id
    service = ContactRequestService(db)
    try:
        req = await service.decline_request(request_id, candidate_id)
        await db.commit()
        return ContactRequestRead(
            id=req.id,
            company_id=req.company_id,
            candidate_id=req.candidate_id,
            requester_user_id=req.requester_user_id,
            status=req.status,
            created_at=req.created_at,
            updated_at=req.updated_at,
            expires_at=req.expires_at,
            responded_at=req.responded_at,
            revoked_at=req.revoked_at,
            company_name=req.company.name if req.company else None,
            candidate_name=req.candidate.full_name if req.candidate else None,
            candidate_title=req.candidate.title if req.candidate else None,
        )
    except EntityNotFoundException as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ConflictException as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/candidate/contact-requests/{request_id}/revoke",
    response_model=ContactRequestRead,
    summary="Candidate revokes previously accepted contact authorization",
)
async def revoke_candidate_contact_request(
    request_id: uuid.UUID,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> ContactRequestRead:
    user_with_profile = await UserService(db).users.get_with_profile(
        current_user.id
    )
    if not user_with_profile or not user_with_profile.candidate_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Candidate profile required",
        )

    candidate_id = user_with_profile.candidate_profile.id
    service = ContactRequestService(db)
    try:
        req = await service.revoke_authorization(request_id, candidate_id)
        await db.commit()
        return ContactRequestRead(
            id=req.id,
            company_id=req.company_id,
            candidate_id=req.candidate_id,
            requester_user_id=req.requester_user_id,
            status=req.status,
            created_at=req.created_at,
            updated_at=req.updated_at,
            expires_at=req.expires_at,
            responded_at=req.responded_at,
            revoked_at=req.revoked_at,
            company_name=req.company.name if req.company else None,
            candidate_name=req.candidate.full_name if req.candidate else None,
            candidate_title=req.candidate.title if req.candidate else None,
        )
    except EntityNotFoundException as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ConflictException as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
