from __future__ import annotations

import hmac
from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import settings
from scripts.reconcile_qdrant_jobs import run_reconcile

router = APIRouter()


async def verify_maintenance_token(
    x_maintenance_token: str | None = Header(None, alias="X-Maintenance-Token"),
) -> None:
    """Verify the maintenance token.

    Requires X-Maintenance-Token header and validates against
    configured MAINTENANCE_TOKEN using constant-time comparison.

    Raises:
        HTTPException: 401 if token missing, empty, or mismatch.
    """
    configured_token = settings.MAINTENANCE_TOKEN

    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Maintenance endpoint not configured",
        )

    if not x_maintenance_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing maintenance token",
        )

    if not hmac.compare_digest(x_maintenance_token, configured_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid maintenance token",
        )


@router.post(
    "/reconcile-qdrant-jobs",
    status_code=status.HTTP_200_OK,
    summary="Reconcile Qdrant job vectors with Azure SQL",
    description=(
        "Reconciles Qdrant job vectors with Azure SQL Server. "
        "Identifies and optionally deletes stale job vectors. "
        "Requires X-Maintenance-Token header for authorization."
    ),
)
async def reconcile_qdrant_jobs(
    dry_run: bool = True,
    _auth: None = Depends(verify_maintenance_token),
) -> dict:
    """Reconcile Qdrant job vectors with Azure SQL Server.

    Args:
        dry_run: If True, only identify stale vectors without deleting (default: True).

    Returns:
        Dictionary with reconciliation counters.
    """
    try:
        result = await run_reconcile(dry_run=dry_run)
    except Exception as e:
        # Log the error but don't expose details
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Reconciliation failed",
        ) from None
    return result