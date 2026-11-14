from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import AdminAuditAction
from app.models import AdminAuditLog


def record_admin_audit(
    session: AsyncSession,
    *,
    admin_id: uuid.UUID | None,
    action: AdminAuditAction,
    target_id: uuid.UUID | None = None,
    target_type: str = "user",
    target_name: str | None = None,
    target_user_id: uuid.UUID | None = None,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Stage an immutable admin audit row in the caller's transaction.

    ``target_user_id`` remains populated for user-management rows so existing
    queries and relationships keep working. ``target_id``/``target_type`` form
    the generic target used by non-user entities such as recruitment plans.
    """
    if admin_id is None:
        return
    session.add(
        AdminAuditLog(
            admin_id=admin_id,
            target_user_id=target_user_id,
            target_id=target_id if target_id is not None else target_user_id,
            target_type=target_type,
            target_name=target_name,
            action=action,
            reason=reason,
            details=details,
        )
    )
