from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ValidationError,
)
from app.models import RecruitmentPlan
from app.repositories import RecruitmentPlanRepository
from app.schemas.recruitment_plan import RecruitmentPlanCreate, RecruitmentPlanUpdate


class RecruitmentPlanService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.plans = RecruitmentPlanRepository(session)

    async def create_plan(self, data: RecruitmentPlanCreate) -> RecruitmentPlan:
        plan = RecruitmentPlan(
            name=data.name,
            description=data.description,
            price=data.price,
            currency=data.currency.upper(),
            duration_days=data.duration_days,
            max_job_posts=data.max_job_posts,
            max_candidate_searches=data.max_candidate_searches,
            max_ai_features=data.max_ai_features,
            display_order=data.display_order,
            is_active=True,
        )
        self.session.add(plan)
        try:
            await self.session.commit()
            await self.session.refresh(plan)
        except Exception:
            await self.session.rollback()
            raise
        return plan

    async def get_plan(self, plan_id: uuid.UUID) -> RecruitmentPlan | None:
        return await self.plans.get_active_by_id(plan_id)

    async def get_plan_admin(self, plan_id: uuid.UUID) -> RecruitmentPlan | None:
        return await self.plans.get_active_by_id_admin(plan_id)

    async def list_active_plans(self) -> list[RecruitmentPlan]:
        return await self.plans.list_active()

    async def list_admin(
        self,
        skip: int = 0,
        limit: int = 10,
        search: Optional[str] = None,
    ) -> tuple[list[RecruitmentPlan], int]:
        return await self.plans.list_admin(skip, limit, search)

    async def update_plan(
        self,
        plan_id: uuid.UUID,
        data: RecruitmentPlanUpdate,
    ) -> RecruitmentPlan:
        plan = await self.plans.get_active_by_id_admin(plan_id)
        if plan is None:
            raise EntityNotFoundException(f"Recruitment plan {plan_id} not found")

        if data.name is not None:
            plan.name = data.name
        if data.description is not None:
            plan.description = data.description
        if data.price is not None:
            plan.price = data.price
        if data.currency is not None:
            plan.currency = data.currency.upper()
        if data.duration_days is not None:
            plan.duration_days = data.duration_days
        if data.max_job_posts is not None:
            plan.max_job_posts = data.max_job_posts
        if data.max_candidate_searches is not None:
            plan.max_candidate_searches = data.max_candidate_searches
        if data.max_ai_features is not None:
            plan.max_ai_features = data.max_ai_features
        if data.is_active is not None:
            plan.is_active = data.is_active
        if data.display_order is not None:
            plan.display_order = data.display_order

        try:
            await self.session.commit()
            await self.session.refresh(plan)
        except Exception:
            await self.session.rollback()
            raise
        return plan

    async def set_plan_status(
        self,
        plan_id: uuid.UUID,
        is_active: bool,
    ) -> RecruitmentPlan:
        plan = await self.plans.get_active_by_id_admin(plan_id)
        if plan is None:
            raise EntityNotFoundException(f"Recruitment plan {plan_id} not found")

        plan.is_active = is_active
        try:
            await self.session.commit()
            await self.session.refresh(plan)
        except Exception:
            await self.session.rollback()
            raise
        return plan