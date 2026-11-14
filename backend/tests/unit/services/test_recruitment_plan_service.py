import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ValidationError,
)
from app.domain.enums import AdminAuditAction, PlanAudience
from app.models import AdminAuditLog, RecruitmentPlan
from app.repositories import RecruitmentPlanRepository
from app.schemas.recruitment_plan import (
    RecruitmentPlanAdminRead,
    RecruitmentPlanCreate,
    RecruitmentPlanRead,
    RecruitmentPlanUpdate,
)
from app.services.recruitment_plan_service import RecruitmentPlanService


def make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    return session


def make_plan(plan_id: uuid.UUID | None = None) -> RecruitmentPlan:
    return RecruitmentPlan(
        id=plan_id or uuid.uuid4(),
        name="Test Plan",
        price=1000000,
        currency="VND",
        duration_days=30,
        max_job_posts=5,
        plan_audience=PlanAudience.COMPANY,
        is_free=False,
    )


def make_service(session: MagicMock) -> RecruitmentPlanService:
    service = RecruitmentPlanService(session)
    service.plans = AsyncMock(spec=RecruitmentPlanRepository)
    return service


class TestCreatePlan:
    def test_creates_plan(self):
        session = make_session()
        service = make_service(session)
        data = RecruitmentPlanCreate(
            name="Professional",
            description="Professional plan",
            price=2000000,
            currency="VND",
            duration_days=30,
            max_job_posts=10,
        )

        plan = asyncio.run(service.create_plan(data))

        assert isinstance(plan, RecruitmentPlan)
        assert plan.name == "Professional"
        assert plan.price == 2000000
        assert plan.currency == "VND"
        assert plan.duration_days == 30
        assert plan.max_job_posts == 10
        assert plan.is_active is True
        session.add.assert_called_once_with(plan)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(plan)

    def test_schema_validates_price_non_negative(self):
        """Schema validation happens at pydantic level before service is called."""
        with pytest.raises(Exception):  # Pydantic validation error
            RecruitmentPlanCreate(
                name="Invalid",
                price=-1,
                currency="VND",
                duration_days=30,
                max_job_posts=5,
            )

    def test_schema_validates_duration_positive(self):
        with pytest.raises(Exception):  # Pydantic validation error
            RecruitmentPlanCreate(
                name="Invalid",
                price=1000,
                currency="VND",
                duration_days=0,
                max_job_posts=5,
            )

    def test_schema_validates_max_job_posts_non_negative(self):
        with pytest.raises(Exception):  # Pydantic validation error
            RecruitmentPlanCreate(
                name="Invalid",
                price=1000,
                currency="VND",
                duration_days=30,
                max_job_posts=-1,
            )

    def test_validates_currency_uppercase(self):
        session = make_session()
        service = make_service(session)
        data = RecruitmentPlanCreate(
            name="Test",
            price=1000,
            currency="vnd",
            duration_days=30,
            max_job_posts=5,
        )

        plan = asyncio.run(service.create_plan(data))
        assert plan.currency == "VND"

    def test_creates_candidate_free_plan(self):
        session = make_session()
        service = make_service(session)
        data = RecruitmentPlanCreate(
            name="Candidate Free",
            description="Candidate free plan",
            price=0,
            currency="vnd",
            duration_days=30,
            max_job_posts=0,
            max_candidate_searches=0,
            max_ai_features=0,
            plan_audience=PlanAudience.CANDIDATE,
            is_free=True,
        )

        plan = asyncio.run(service.create_plan(data))

        assert plan.plan_audience == PlanAudience.CANDIDATE
        assert plan.is_free is True
        assert plan.currency == "VND"

    def test_defaults_to_company_paid_plan(self):
        session = make_session()
        service = make_service(session)
        data = RecruitmentPlanCreate(
            name="Company Plan",
            price=1000,
            duration_days=30,
            max_job_posts=5,
        )

        plan = asyncio.run(service.create_plan(data))

        assert plan.plan_audience == PlanAudience.COMPANY
        assert plan.is_free is False

    def test_rejects_free_company_plan_at_schema_level(self):
        with pytest.raises(ValueError, match="candidate audience"):
            RecruitmentPlanCreate(
                name="Invalid Free",
                price=0,
                duration_days=30,
                max_job_posts=0,
                plan_audience=PlanAudience.COMPANY,
                is_free=True,
            )


class TestGetPlan:
    def test_returns_active_plan(self):
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        service.plans.get_active_by_id.return_value = plan

        result = asyncio.run(service.get_plan(plan.id))

        assert result is plan
        service.plans.get_active_by_id.assert_awaited_once_with(plan.id)

    def test_returns_none_for_inactive_plan(self):
        session = make_session()
        service = make_service(session)
        service.plans.get_active_by_id.return_value = None

        result = asyncio.run(service.get_plan(uuid.uuid4()))

        assert result is None


class TestListActivePlans:
    def test_returns_active_plans(self):
        session = make_session()
        service = make_service(session)
        plans = [make_plan() for _ in range(3)]
        service.plans.list_active.return_value = plans

        result = asyncio.run(service.list_active_plans())

        assert result == plans
        service.plans.list_active.assert_awaited_once()

    def test_passes_audience_filter(self):
        session = make_session()
        service = make_service(session)
        service.plans.list_active.return_value = []

        asyncio.run(service.list_active_plans(audience=PlanAudience.CANDIDATE))

        service.plans.list_active.assert_awaited_once_with(
            audience=PlanAudience.CANDIDATE
        )


class TestListAdmin:
    def test_returns_paginated(self):
        session = make_session()
        service = make_service(session)
        plans = [make_plan() for _ in range(2)]
        service.plans.list_admin.return_value = (plans, 2)

        result = asyncio.run(service.list_admin(skip=0, limit=10, search=None))

        assert result == (plans, 2)
        service.plans.list_admin.assert_awaited_once_with(0, 10, None, None)


class TestUpdatePlan:
    def test_updates_fields(self):
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        service.plans.get_active_by_id_admin.return_value = plan
        data = RecruitmentPlanUpdate(
            name="Updated",
            price=3000000,
        )

        result = asyncio.run(service.update_plan(plan.id, data))

        assert result is plan
        assert plan.name == "Updated"
        assert plan.price == 3000000
        session.commit.assert_awaited_once()

    def test_raises_not_found(self):
        session = make_session()
        service = make_service(session)
        service.plans.get_active_by_id_admin.return_value = None
        data = RecruitmentPlanUpdate(name="Updated")

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.update_plan(uuid.uuid4(), data))

    def test_uppercases_currency(self):
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        service.plans.get_active_by_id_admin.return_value = plan
        data = RecruitmentPlanUpdate(currency="usd")

        asyncio.run(service.update_plan(plan.id, data))

        assert plan.currency == "USD"

    def test_updates_audience_and_free_flag(self):
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        service.plans.get_active_by_id_admin.return_value = plan
        data = RecruitmentPlanUpdate(
            plan_audience=PlanAudience.CANDIDATE,
            is_free=True,
        )

        result = asyncio.run(service.update_plan(plan.id, data))

        assert result is plan
        assert plan.plan_audience == PlanAudience.CANDIDATE
        assert plan.is_free is True
        session.commit.assert_awaited_once()

    def test_rejects_free_update_for_company_plan(self):
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        service.plans.get_active_by_id_admin.return_value = plan
        data = RecruitmentPlanUpdate(is_free=True)

        with pytest.raises(ValidationError, match="candidate audience"):
            asyncio.run(service.update_plan(plan.id, data))

        assert plan.is_free is False
        session.commit.assert_not_awaited()

    def test_rejects_company_audience_for_free_plan_in_payload(self):
        with pytest.raises(ValueError, match="candidate audience"):
            RecruitmentPlanUpdate(
                plan_audience=PlanAudience.COMPANY,
                is_free=True,
            )

    def test_rollback_on_commit_failure(self):
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        service.plans.get_active_by_id_admin.return_value = plan
        session.commit.side_effect = RuntimeError("db down")
        data = RecruitmentPlanUpdate(name="Updated")

        with pytest.raises(RuntimeError):
            asyncio.run(service.update_plan(plan.id, data))

        session.rollback.assert_awaited_once()


class TestSetPlanStatus:
    def test_activates_plan(self):
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        plan.is_active = False
        service.plans.get_active_by_id_admin.return_value = plan

        result = asyncio.run(service.set_plan_status(plan.id, True))

        assert result is plan
        assert plan.is_active is True

    def test_deactivates_plan(self):
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        plan.is_active = True
        service.plans.get_active_by_id_admin.return_value = plan

        result = asyncio.run(service.set_plan_status(plan.id, False))

        assert result is plan
        assert plan.is_active is False


class TestPlanStatusAudit:
    def _added_audit(self, session: MagicMock) -> AdminAuditLog:
        session.add.assert_called_once()
        audit = session.add.call_args.args[0]
        assert isinstance(audit, AdminAuditLog)
        return audit

    def test_lock_records_plan_lock_audit(self):
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        plan.is_active = True
        service.plans.get_active_by_id_admin.return_value = plan
        admin_id = uuid.uuid4()

        asyncio.run(service.set_plan_status(plan.id, False, admin_id=admin_id))

        audit = self._added_audit(session)
        assert audit.admin_id == admin_id
        assert audit.action == AdminAuditAction.PLAN_LOCK
        assert audit.target_id == plan.id
        assert audit.target_user_id is None
        assert audit.target_type == "plan"
        assert audit.target_name == plan.name
        assert audit.details == {
            "is_active": False,
            "plan_audience": "company",
            "is_free": False,
        }

    def test_unlock_records_plan_unlock_audit(self):
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        plan.is_active = False
        service.plans.get_active_by_id_admin.return_value = plan

        asyncio.run(
            service.set_plan_status(plan.id, True, admin_id=uuid.uuid4())
        )

        audit = self._added_audit(session)
        assert audit.action == AdminAuditAction.PLAN_UNLOCK
        assert audit.target_id == plan.id
        assert audit.target_type == "plan"

    def test_unchanged_status_records_no_audit(self):
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        plan.is_active = True
        service.plans.get_active_by_id_admin.return_value = plan

        asyncio.run(
            service.set_plan_status(plan.id, True, admin_id=uuid.uuid4())
        )

        session.add.assert_not_called()

    def test_missing_admin_id_records_no_audit(self):
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        plan.is_active = True
        service.plans.get_active_by_id_admin.return_value = plan

        asyncio.run(service.set_plan_status(plan.id, False))

        session.add.assert_not_called()

    def test_update_plan_status_change_records_audit(self):
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        plan.is_active = True
        service.plans.get_active_by_id_admin.return_value = plan
        admin_id = uuid.uuid4()

        asyncio.run(
            service.update_plan(
                plan.id,
                RecruitmentPlanUpdate(is_active=False),
                admin_id=admin_id,
            )
        )

        audit = self._added_audit(session)
        assert audit.admin_id == admin_id
        assert audit.action == AdminAuditAction.PLAN_LOCK
        assert audit.target_id == plan.id

    def test_update_plan_without_status_change_records_no_audit(self):
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        plan.is_active = True
        service.plans.get_active_by_id_admin.return_value = plan

        asyncio.run(
            service.update_plan(
                plan.id,
                RecruitmentPlanUpdate(name="Renamed"),
                admin_id=uuid.uuid4(),
            )
        )

        session.add.assert_not_called()


class TestDeletePlan:
    def test_deletes_unreferenced_plan(self):
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        service.plans.get_by_id.return_value = plan
        service.plans.count_subscriptions.return_value = 0
        service.plans.count_payment_orders.return_value = 0
        service.plans.count_audit_logs.return_value = 0
        service.plans.delete.return_value = True

        asyncio.run(service.delete_plan(plan.id))

        service.plans.get_by_id.assert_awaited_once_with(plan.id)
        service.plans.count_subscriptions.assert_awaited_once_with(plan.id)
        service.plans.count_payment_orders.assert_awaited_once_with(plan.id)
        service.plans.count_audit_logs.assert_awaited_once_with(plan.id)
        service.plans.delete.assert_awaited_once_with(plan.id)

    def test_raises_not_found_when_plan_missing(self):
        session = make_session()
        service = make_service(session)
        service.plans.get_by_id.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.delete_plan(uuid.uuid4()))

    def test_raises_conflict_when_subscriptions_exist(self):
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        service.plans.get_by_id.return_value = plan
        service.plans.count_subscriptions.return_value = 5

        with pytest.raises(ConflictException) as exc_info:
            asyncio.run(service.delete_plan(plan.id))

        assert "đã có người đăng ký" in str(exc_info.value)
        service.plans.delete.assert_not_awaited()

    def test_raises_conflict_when_payment_orders_exist(self):
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        service.plans.get_by_id.return_value = plan
        service.plans.count_subscriptions.return_value = 0
        service.plans.count_payment_orders.return_value = 3

        with pytest.raises(ConflictException) as exc_info:
            asyncio.run(service.delete_plan(plan.id))

        assert "lịch sử thanh toán" in str(exc_info.value)
        service.plans.delete.assert_not_awaited()

    def test_raises_conflict_when_audit_logs_exist(self):
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        service.plans.get_by_id.return_value = plan
        service.plans.count_subscriptions.return_value = 0
        service.plans.count_payment_orders.return_value = 0
        service.plans.count_audit_logs.return_value = 1

        with pytest.raises(ConflictException) as exc_info:
            asyncio.run(service.delete_plan(plan.id))

        assert "lịch sử thay đổi gói" in str(exc_info.value)
        service.plans.delete.assert_not_awaited()

    def test_raises_conflict_on_integrity_error_from_repository(self):
        """IntegrityError from repository.delete() is caught and mapped to ConflictException."""
        import sqlalchemy.exc
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        service.plans.get_by_id.return_value = plan
        service.plans.count_subscriptions.return_value = 0
        service.plans.count_payment_orders.return_value = 0
        service.plans.count_audit_logs.return_value = 0
        # Repository delete raises IntegrityError (simulating concurrent FK violation)
        service.plans.delete.side_effect = sqlalchemy.exc.IntegrityError("FK violation", "", None)

        with pytest.raises(ConflictException) as exc_info:
            asyncio.run(service.delete_plan(plan.id))

        assert "dữ liệu liên quan vừa phát sinh" in str(exc_info.value)
        session.rollback.assert_awaited_once()

    def test_other_exceptions_not_caught_as_conflict(self):
        """Unrelated exceptions from repository.delete() propagate as-is."""
        session = make_session()
        service = make_service(session)
        plan = make_plan()
        service.plans.get_by_id.return_value = plan
        service.plans.count_subscriptions.return_value = 0
        service.plans.count_payment_orders.return_value = 0
        service.plans.count_audit_logs.return_value = 0
        service.plans.delete.side_effect = RuntimeError("unexpected db error")

        with pytest.raises(RuntimeError, match="unexpected db error"):
            asyncio.run(service.delete_plan(plan.id))

        # rollback is still called by repository, but service doesn't catch it
        # (repository already rolled back internally)


class TestRecruitmentPlanReadSchemas:
    def test_read_schemas_include_audience_and_free_flag(self):
        plan = make_plan()
        plan.description = None
        plan.max_candidate_searches = None
        plan.max_ai_features = None
        plan.is_active = True
        plan.display_order = 0
        plan.is_deleted = False
        plan.created_at = datetime.now(timezone.utc)
        plan.updated_at = datetime.now(timezone.utc)

        public = RecruitmentPlanRead.model_validate(plan)
        admin = RecruitmentPlanAdminRead.model_validate(plan)

        assert public.plan_audience == PlanAudience.COMPANY
        assert public.is_free is False
        assert admin.plan_audience == PlanAudience.COMPANY
        assert admin.is_free is False
