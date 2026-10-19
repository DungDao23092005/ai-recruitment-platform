from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApplicationActivity
from app.repositories.base import BaseRepository


class ApplicationActivityRepository(BaseRepository[ApplicationActivity]):
    """Append-only repository for the application audit trail.

    Only append and read operations are exposed. There is deliberately no
    update or delete path: history is immutable (the model has neither an
    ``updated_at`` nor an ``is_deleted`` column), so it can never be rewritten
    or hidden. The inherited generic ``update``/``soft_delete`` helpers are
    unusable on this model by construction.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ApplicationActivity)

    async def append(self, activity: ApplicationActivity) -> ApplicationActivity:
        """Append one activity row inside the caller's active transaction."""
        return await self.create(activity)

    async def list_by_application(
        self,
        application_id: Any,
        skip: int = 0,
        limit: int = 50,
        action_types: frozenset[str] | None = None,
    ) -> list[ApplicationActivity]:
        """Return an application's history newest-first.

        ``action_types`` is applied at the SQL level, so a candidate-facing
        caller can restrict the projection to its allowlist without ever
        loading (or being able to leak) internal rows.
        """
        stmt = select(ApplicationActivity).where(
            ApplicationActivity.application_id == application_id,
        )
        if action_types is not None:
            stmt = stmt.where(ApplicationActivity.action_type.in_(action_types))
        stmt = (
            stmt.order_by(
                ApplicationActivity.created_at.desc(),
                ApplicationActivity.id.desc(),
            )
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_application(
        self,
        application_id: Any,
        action_types: frozenset[str] | None = None,
    ) -> int:
        stmt = select(func.count(ApplicationActivity.id)).where(
            ApplicationActivity.application_id == application_id,
        )
        if action_types is not None:
            stmt = stmt.where(ApplicationActivity.action_type.in_(action_types))
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)
