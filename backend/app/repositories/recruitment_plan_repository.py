from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RecruitmentPlan
from app.repositories.base import BaseRepository


class RecruitmentPlanRepository(BaseRepository[RecruitmentPlan]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RecruitmentPlan)

    async def get_active_by_id(self, plan_id: Any) -> RecruitmentPlan | None:
        stmt = select(RecruitmentPlan).where(
            RecruitmentPlan.id == plan_id,
            RecruitmentPlan.is_deleted == False,  # noqa: E712
            RecruitmentPlan.is_active == True,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_id_admin(self, plan_id: Any) -> RecruitmentPlan | None:
        stmt = select(RecruitmentPlan).where(
            RecruitmentPlan.id == plan_id,
            RecruitmentPlan.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active(self) -> list[RecruitmentPlan]:
        stmt = (
            select(RecruitmentPlan)
            .where(
                RecruitmentPlan.is_deleted == False,  # noqa: E712
                RecruitmentPlan.is_active == True,  # noqa: E712
            )
            .order_by(RecruitmentPlan.display_order, RecruitmentPlan.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_admin(
        self,
        skip: int,
        limit: int,
        search: Optional[str] = None,
    ) -> tuple[list[RecruitmentPlan], int]:
        filters = [
            RecruitmentPlan.is_deleted == False,  # noqa: E712
        ]
        if search:
            from sqlalchemy import or_
            term = f"%{search.strip()}%"
            filters.append(
                or_(
                    RecruitmentPlan.name.ilike(term),
                    RecruitmentPlan.description.ilike(term),
                )
            )

        count_stmt = select(func.count()).select_from(RecruitmentPlan)
        list_stmt = select(RecruitmentPlan).order_by(
            RecruitmentPlan.display_order,
            RecruitmentPlan.id,
        )

        if filters:
            count_stmt = count_stmt.where(*filters)
            list_stmt = list_stmt.where(*filters)

        total = (await self.session.execute(count_stmt)).scalar_one()
        list_stmt = list_stmt.offset(skip).limit(limit)
        rows = (await self.session.execute(list_stmt)).scalars().all()
        return list(rows), total