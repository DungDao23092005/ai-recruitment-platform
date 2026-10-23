from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.domain.enums import AdminAuditAction
from app.models import AdminAuditLog, User


def _escape_like(value: str) -> str:
    """Treat user input as literal text inside a LIKE pattern."""
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


class AdminAuditRepository:
    """Read-only query surface for the append-only admin audit ledger.

    Deliberately does not inherit the generic CRUD repository: audit rows are
    staged by the mutation service in its own transaction and must never be
    updated or deleted through a repository method.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_page(
        self,
        *,
        skip: int,
        limit: int,
        action: AdminAuditAction | None = None,
        admin_id: uuid.UUID | None = None,
        target_user_id: uuid.UUID | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        search: str | None = None,
    ) -> tuple[list[AdminAuditLog], int]:
        """Return a deterministic, database-paginated audit page and total.

        Date bounds are inclusive on both ends. ``search`` is matched against
        the reason and the current actor/target email addresses. LIKE wildcards
        in the query are escaped so ``%`` and ``_`` are searched literally.
        """
        filters = []
        if action is not None:
            filters.append(AdminAuditLog.action == action)
        if admin_id is not None:
            filters.append(AdminAuditLog.admin_id == admin_id)
        if target_user_id is not None:
            filters.append(AdminAuditLog.target_user_id == target_user_id)
        if created_from is not None:
            filters.append(AdminAuditLog.created_at >= created_from)
        if created_to is not None:
            filters.append(AdminAuditLog.created_at <= created_to)

        trimmed_search = search.strip() if search else ""
        actor_alias = aliased(User, name="audit_actor")
        target_alias = aliased(User, name="audit_target")

        list_stmt = select(AdminAuditLog)
        count_stmt = select(func.count(AdminAuditLog.id)).select_from(AdminAuditLog)

        if trimmed_search:
            pattern = f"%{_escape_like(trimmed_search)}%"
            search_filter = or_(
                AdminAuditLog.reason.ilike(pattern, escape="\\"),
                actor_alias.email.ilike(pattern, escape="\\"),
                target_alias.email.ilike(pattern, escape="\\"),
            )
            joins = (
                (actor_alias, AdminAuditLog.admin_id == actor_alias.id),
                (target_alias, AdminAuditLog.target_user_id == target_alias.id),
            )
            for alias, condition in joins:
                list_stmt = list_stmt.outerjoin(alias, condition)
                count_stmt = count_stmt.outerjoin(alias, condition)
            filters.append(search_filter)

        list_stmt = (
            list_stmt.options(
                selectinload(AdminAuditLog.admin),
                selectinload(AdminAuditLog.target_user),
            )
            .where(*filters)
            .order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
            .offset(skip)
            .limit(limit)
        )
        count_stmt = count_stmt.where(*filters)

        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = (await self.session.execute(list_stmt)).scalars().all()
        return list(rows), int(total)
