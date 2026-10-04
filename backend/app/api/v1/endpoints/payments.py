from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_active_user, require_candidate
from app.core.config import settings
from app.core.exceptions import EntityNotFoundException
from app.models import User
from app.schemas.payment import (
    VNPayCreatePaymentRequest,
    VNPayCreatePaymentResponse,
    VNPayIPNParams,
    VNPayReturnParams,
    PaymentStatusResponse,
)
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/payments/vnpay", tags=["VNPAY Payments"])


def _get_payment_service(db: AsyncSession = Depends(get_db)) -> PaymentService:
    return PaymentService(db)


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request, respecting trusted proxies."""
    # Check X-Forwarded-For header (from trusted proxies)
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for and settings.TRUSTED_PROXIES:
        # Only trust if request comes from a trusted proxy
        client_host = request.client.host if request.client else ""
        if client_host in settings.TRUSTED_PROXIES:
            return x_forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header
    x_real_ip = request.headers.get("x-real-ip")
    if x_real_ip and settings.TRUSTED_PROXIES:
        client_host = request.client.host if request.client else ""
        if client_host in settings.TRUSTED_PROXIES:
            return x_real_ip

    # Fallback to direct client IP
    return request.client.host if request.client else "127.0.0.1"


@router.post(
    "/create",
    response_model=VNPayCreatePaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_vnpay_payment(
    data: VNPayCreatePaymentRequest,
    current_user: User = Depends(require_candidate),
    service: PaymentService = Depends(_get_payment_service),
    request: Request = None,
) -> VNPayCreatePaymentResponse:
    """Create a VNPAY payment for a recruitment plan.

    Authenticated candidate only.
    Uses authoritative plan price from backend.
    Creates PENDING subscription and PaymentOrder.
    Returns VNPAY payment URL for redirect.
    """
    client_ip = _get_client_ip(request) if request else "127.0.0.1"

    # Build return URL if not configured
    return_url = settings.VNPAY_RETURN_URL
    if not return_url:
        # Default to frontend payment result page
        base_url = str(request.base_url).rstrip("/") if request else ""
        return_url = f"{base_url}/payment-result"

    try:
        payment_url, internal_order_id, subscription_id = await service.create_vnpay_payment(
            user_id=current_user.id,
            plan_id=data.plan_id,
            client_ip=client_ip,
            return_url=return_url,
        )
    except EntityNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    # Find the payment order to get its ID
    payment_order = await service.payment_orders.get_by_internal_order_id(internal_order_id)

    return VNPayCreatePaymentResponse(
        payment_url=payment_url,
        internal_order_id=internal_order_id,
        payment_order_id=payment_order.id if payment_order else uuid.uuid4(),
        subscription_id=subscription_id,
    )


@router.get(
    "/return",
    response_class=RedirectResponse,
)
async def vnpay_return(
    request: Request,
    service: PaymentService = Depends(_get_payment_service),
) -> RedirectResponse:
    """VNPAY Return URL endpoint (browser redirect).

    This is the user-facing redirect after payment.
    Does NOT independently activate subscription - IPN is authoritative.
    Redirects to frontend payment-result page with status parameters.
    """
    # Parse query parameters
    params = dict(request.query_params)

    # Process return (informational only)
    is_successful, message, internal_order_id = await service.process_vnpay_return(params)

    # Determine frontend redirect URL
    frontend_base = settings.BACKEND_CORS_ORIGINS[0] if settings.BACKEND_CORS_ORIGINS else "http://localhost:5173"
    redirect_url = f"{frontend_base}/payment-result"

    # Add status parameters to redirect URL
    from urllib.parse import urlencode
    redirect_params = {
        "success": "true" if is_successful else "false",
        "message": message,
    }
    if internal_order_id:
        redirect_params["order_id"] = internal_order_id

    # Add VNPAY response params for frontend display
    if "vnp_ResponseCode" in params:
        redirect_params["vnp_ResponseCode"] = params["vnp_ResponseCode"]
    if "vnp_TransactionStatus" in params:
        redirect_params["vnp_TransactionStatus"] = params["vnp_TransactionStatus"]
    if "vnp_TransactionNo" in params:
        redirect_params["vnp_TransactionNo"] = params["vnp_TransactionNo"]

    final_url = f"{redirect_url}?{urlencode(redirect_params)}"
    return RedirectResponse(url=final_url, status_code=status.HTTP_302_FOUND)


@router.get(
    "/ipn",
)
async def vnpay_ipn(
    request: Request,
    service: PaymentService = Depends(_get_payment_service),
) -> dict[str, str]:
    """VNPAY IPN (Instant Payment Notification) endpoint.

    Server-to-server callback from VNPAY.
    Authoritative payment processing path.
    Implements idempotent processing and subscription activation.
    Returns VNPAY IPN response format.
    """
    # Parse query parameters (VNPAY sends GET for IPN)
    params = dict(request.query_params)

    # Get client IP
    client_ip = _get_client_ip(request)

    # Process IPN
    response = await service.process_vnpay_ipn(params, client_ip)

    return response


@router.get(
    "/status/{internal_order_id}",
    response_model=PaymentStatusResponse,
)
async def get_payment_status(
    internal_order_id: str,
    current_user: User = Depends(get_current_active_user),
    service: PaymentService = Depends(_get_payment_service),
) -> PaymentStatusResponse:
    """Get payment status for a payment order.

    Authenticated user can only check their own payments.
    Returns payment order, transaction, and success status.
    """
    result = await service.get_payment_status(current_user.id, internal_order_id)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment order not found",
        )

    payment_order = result["payment_order"]
    transaction = result["transaction"]
    is_successful = result["is_successful"]

    # Build response
    return PaymentStatusResponse(
        payment_order=payment_order,
        transaction=transaction,
        is_successful=is_successful,
        message="Payment successful" if is_successful else "Payment pending or failed",
    )