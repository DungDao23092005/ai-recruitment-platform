from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ValidationError,
)
from app.domain.enums import AdminAuditAction, PlanAudience
from app.models import RecruitmentPlan
from app.repositories import RecruitmentPlanRepository
from app.schemas.recruitment_plan import RecruitmentPlanCreate, RecruitmentPlanUpdate
from app.services.admin_audit_service import record_admin_audit


def _validate_free_plan_audience(
    plan_audience: PlanAudience,
    is_free: bool,
) -> None:
    """Enforce the database constraint ``is_free = 0 OR audience = candidate``."""
    if is_free and plan_audience != PlanAudience.CANDIDATE:
        raise ValidationError("A free plan must target the candidate audience")


class RecruitmentPlanService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.plans = RecruitmentPlanRepository(session)

    def _record_status_audit(
        self,
        plan: RecruitmentPlan,
        *,
        admin_id: uuid.UUID | None,
    ) -> None:
        audience = getattr(plan.plan_audience, "value", plan.plan_audience)
        record_admin_audit(
            self.session,
            admin_id=admin_id,
            action=(
                AdminAuditAction.PLAN_UNLOCK
                if plan.is_active
                else AdminAuditAction.PLAN_LOCK
            ),
            target_id=plan.id,
            target_type="plan",
            target_name=plan.name,
            details={
                "is_active": plan.is_active,
                "plan_audience": audience,
                "is_free": plan.is_free,
            },
        )

    async def create_plan(self, data: RecruitmentPlanCreate) -> RecruitmentPlan:
        _validate_free_plan_audience(data.plan_audience, data.is_free)
        plan = RecruitmentPlan(
            name=data.name,
            description=data.description,
            price=data.price,
            currency=data.currency.upper(),
            duration_days=data.duration_days,
            max_job_posts=data.max_job_posts,
            max_candidate_searches=data.max_candidate_searches,
            max_ai_features=data.max_ai_features,
            plan_audience=data.plan_audience,
            is_free=data.is_free,
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

    async def list_active_plans(
        self,
        audience: Optional[PlanAudience] = None,
    ) -> list[RecruitmentPlan]:
        return await self.plans.list_active(audience=audience)

    async def list_admin(
        self,
        skip: int = 0,
        limit: int = 10,
        search: Optional[str] = None,
        audience: Optional[PlanAudience] = None,
    ) -> tuple[list[RecruitmentPlan], int]:
        return await self.plans.list_admin(skip, limit, search, audience)

    async def update_plan(
        self,
        plan_id: uuid.UUID,
        data: RecruitmentPlanUpdate,
        admin_id: uuid.UUID | None = None,
    ) -> RecruitmentPlan:
        plan = await self.plans.get_active_by_id_admin(
            plan_id, for_update=True
        )
        if plan is None:
            raise EntityNotFoundException(f"Recruitment plan {plan_id} not found")

        was_active = plan.is_active
        effective_audience = (
            data.plan_audience
            if data.plan_audience is not None
            else plan.plan_audience
        )
        effective_is_free = data.is_free if data.is_free is not None else plan.is_free
        _validate_free_plan_audience(effective_audience, effective_is_free)

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
        if data.plan_audience is not None:
            plan.plan_audience = data.plan_audience
        if data.is_free is not None:
            plan.is_free = data.is_free
        if data.is_active is not None:
            plan.is_active = data.is_active
        if data.display_order is not None:
            plan.display_order = data.display_order

        if plan.is_active != was_active:
            self._record_status_audit(plan, admin_id=admin_id)

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
        admin_id: uuid.UUID | None = None,
    ) -> RecruitmentPlan:
        plan = await self.plans.get_active_by_id_admin(
            plan_id, for_update=True
        )
        if plan is None:
            raise EntityNotFoundException(f"Recruitment plan {plan_id} not found")

        changed = plan.is_active != is_active
        plan.is_active = is_active
        if changed:
            self._record_status_audit(plan, admin_id=admin_id)
        try:
            await self.session.commit()
            await self.session.refresh(plan)
        except Exception:
            await self.session.rollback()
            raise
        return plan

    async def delete_plan(self, plan_id: uuid.UUID) -> None:
        """Delete a plan if it has no subscriptions or payment orders.

        Raises:
            EntityNotFoundException: If the plan does not exist.
            ConflictException: If the plan has subscriptions or payment orders,
                or if a concurrent reference was created.
        """
        plan = await self.plans.get_by_id(plan_id)
        if plan is None:
            raise EntityNotFoundException(f"Recruitment plan {plan_id} not found")

        # Check for subscriptions
        subscription_count = await self.plans.count_subscriptions(plan.id)
        if subscription_count > 0:
            raise ConflictException(
                "Không thể xóa gói này vì đã có người đăng ký. Hãy khóa gói thay vì xóa."
            )

        # Check for payment orders
        payment_order_count = await self.plans.count_payment_orders(plan.id)
        if payment_order_count > 0:
            raise ConflictException(
                "Không thể xóa gói này vì đã có lịch sử thanh toán. Hãy khóa gói thay vì xóa."
            )

        # Check for audit-log references (previous or new plan of an admin
        # subscription mutation). The audit trail is append-only, so a
        # referenced plan must never be hard-deleted.
        audit_log_count = await self.plans.count_audit_logs(plan.id)
        if audit_log_count > 0:
            raise ConflictException(
                "Không thể xóa gói này vì đã có lịch sử thay đổi gói. Hãy khóa gói thay vì xóa."
            )

        # Hard delete the plan - repository commits internally,
        # so wrap the call to catch potential IntegrityError from FK constraints.
        try:
            await self.plans.delete(plan.id)
        except IntegrityError:
            await self.session.rollback()
            raise ConflictException(
                "Không thể xóa gói tuyển dụng do có dữ liệu liên quan vừa phát sinh."
            )
