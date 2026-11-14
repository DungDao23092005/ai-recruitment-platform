from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
    InvalidTransitionException,
    ValidationError,
    WorkspaceSelectionRequiredException,
)
from app.domain.enums import (
    MembershipRole,
    SubscriptionUsageFeatureType,
    SubscriptionUsageStatus,
    UserRole,
)
from app.models import User
from app.schemas.payment import PaymentOrderRead
from app.schemas.subscription import (
    CandidateEntitlementSummary,
    CandidateUsageHistoryResponse,
    CompanyUsageHistoryResponse,
    SubscriptionRead,
    SubscriptionSummary,
)
from app.services.candidate_entitlement_service import (
    CandidateEntitlementService,
)
from app.services.subscription_service import SubscriptionService
from app.services.workspace_service import WorkspaceContext, WorkspaceService

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


def _get_subscription_service(
    db: AsyncSession = Depends(get_db),
) -> SubscriptionService:
    return SubscriptionService(db)


async def _resolve_company_billing_workspace(
    *,
    db: AsyncSession,
    current_user: User,
    x_company_id: str | None,
    request: Request | None = None,
    require_header: bool = False,
) -> WorkspaceContext:
    if current_user.role != UserRole.RECRUITER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recruiter access required",
        )

    resolved_header: str | None = (
        x_company_id if isinstance(x_company_id, str) else None
    )
    if resolved_header is None and request is not None:
        raw_hdr = request.headers.get("x-company-id")
        if isinstance(raw_hdr, str):
            resolved_header = raw_hdr

    if require_header and resolved_header is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Company-ID header is required",
        )

    try:
        workspace = await WorkspaceService(db).resolve(
            current_user, resolved_header
        )
    except (ValidationError, WorkspaceSelectionRequiredException) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ForbiddenException as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    if workspace.membership is None or workspace.role not in {
        MembershipRole.ADMIN,
        MembershipRole.RECRUITER,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recruiter or Admin workspace membership required",
        )
    return workspace


@router.get(
    "/me",
    response_model=SubscriptionRead,
)
async def get_my_subscription(
    current_user: User = Depends(get_current_active_user),
    service: SubscriptionService = Depends(_get_subscription_service),
) -> SubscriptionRead:
    """Get the current user's active subscription."""
    subscription = await service.get_current_active_subscription(
        current_user.id
    )
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found",
        )
    return SubscriptionRead.model_validate(subscription)


@router.get(
    "/me/history",
    response_model=list[SubscriptionSummary],
)
async def get_my_subscription_history(
    current_user: User = Depends(get_current_active_user),
    service: SubscriptionService = Depends(_get_subscription_service),
) -> list[SubscriptionSummary]:
    """Get the current user's subscription history."""
    subscriptions = await service.list_user_subscriptions(current_user.id)
    return [SubscriptionSummary.model_validate(s) for s in subscriptions]


@router.get(
    "/company",
    response_model=SubscriptionRead,
)
async def get_company_subscription(
    request: Request = None,
    x_company_id: str | None = Header(default=None, alias="X-Company-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    service: SubscriptionService = Depends(_get_subscription_service),
) -> SubscriptionRead:
    """Get the selected company's effective active recruiting subscription."""
    session = db if isinstance(db, AsyncSession) else service.session
    workspace = await _resolve_company_billing_workspace(
        db=session,
        current_user=current_user,
        x_company_id=x_company_id,
        request=request,
    )
    subscription = await service.get_current_active_company_subscription(
        workspace.company_id
    )
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active company subscription found",
        )
    return SubscriptionRead.model_validate(subscription)


@router.get(
    "/company/history",
    response_model=list[PaymentOrderRead],
)
async def get_company_subscription_history(
    request: Request = None,
    x_company_id: str | None = Header(default=None, alias="X-Company-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    service: SubscriptionService = Depends(_get_subscription_service),
) -> list[PaymentOrderRead]:
    """Get payment order history for the selected company workspace."""
    session = db if isinstance(db, AsyncSession) else service.session
    workspace = await _resolve_company_billing_workspace(
        db=session,
        current_user=current_user,
        x_company_id=x_company_id,
        request=request,
    )
    filter_user_id: uuid.UUID | None = (
        None
        if workspace.role == MembershipRole.ADMIN
        else current_user.id
    )
    orders = await service.list_company_payment_orders(
        company_id=workspace.company_id,
        user_id=filter_user_id,
    )
    return [PaymentOrderRead.model_validate(order) for order in orders]


@router.get(
    "/company/usages",
    response_model=CompanyUsageHistoryResponse,
)
async def list_company_usages(
    request: Request = None,
    x_company_id: str | None = Header(default=None, alias="X-Company-ID"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    feature_type: SubscriptionUsageFeatureType | None = Query(default=None),
    user_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    service: SubscriptionService = Depends(_get_subscription_service),
) -> CompanyUsageHistoryResponse:
    """List Company-scoped usage history for the selected workspace."""
    session = db if isinstance(db, AsyncSession) else service.session
    workspace = await _resolve_company_billing_workspace(
        db=session,
        current_user=current_user,
        x_company_id=x_company_id,
        request=request,
        require_header=True,
    )
    try:
        return await service.list_company_usages(
            company_id=workspace.company_id,
            page=page,
            page_size=page_size,
            start_date=start_date,
            end_date=end_date,
            feature_type=feature_type,
            user_id=user_id,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


def _require_candidate(current_user: User) -> None:
    if current_user.role != UserRole.CANDIDATE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Candidate access required",
        )


@router.get(
    "/candidate/me",
    response_model=CandidateEntitlementSummary,
)
async def get_candidate_entitlement(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    service: SubscriptionService = Depends(_get_subscription_service),
) -> CandidateEntitlementSummary:
    """Get the candidate's effective personal AI entitlement.

    Paid always takes precedence over Free. Free preservation is read-only on
    this path; the only permitted write is idempotent lazy provisioning when a
    candidate has neither an active Paid nor an active Free row.
    """
    _require_candidate(current_user)
    session = db if isinstance(db, AsyncSession) else service.session
    summary = await CandidateEntitlementService(
        session
    ).get_candidate_entitlement_summary(current_user.id)
    await session.commit()
    return summary


@router.get(
    "/candidate/usages",
    response_model=CandidateUsageHistoryResponse,
)
async def list_candidate_usages(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    feature_type: SubscriptionUsageFeatureType | None = Query(default=None),
    usage_status: SubscriptionUsageStatus | None = Query(
        default=None, alias="status"
    ),
    current_user: User = Depends(get_current_active_user),
    service: SubscriptionService = Depends(_get_subscription_service),
) -> CandidateUsageHistoryResponse:
    """List the candidate's own personal AI usage history."""
    _require_candidate(current_user)
    try:
        return await service.list_candidate_usages(
            user_id=current_user.id,
            page=page,
            page_size=page_size,
            start_date=start_date,
            end_date=end_date,
            feature_type=feature_type,
            status=usage_status,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get(
    "/{subscription_id}",
    response_model=SubscriptionRead,
)
async def get_subscription(
    subscription_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: SubscriptionService = Depends(_get_subscription_service),
) -> SubscriptionRead:
    """Get a specific subscription by ID (must belong to current user)."""
    try:
        subscription = await service.get_subscription_by_id(
            subscription_id, current_user.id
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return SubscriptionRead.model_validate(subscription)
