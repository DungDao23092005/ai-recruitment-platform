import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ValidationError,
)
from app.models import RecruitmentPlan
from app.repositories import RecruitmentPlanRepository
from app.schemas.recruitment_plan import RecruitmentPlanCreate, RecruitmentPlanUpdate
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


class TestListAdmin:
    def test_returns_paginated(self):
        session = make_session()
        service = make_service(session)
        plans = [make_plan() for _ in range(2)]
        service.plans.list_admin.return_value = (plans, 2)

        result = asyncio.run(service.list_admin(skip=0, limit=10, search=None))

        assert result == (plans, 2)
        service.plans.list_admin.assert_awaited_once_with(0, 10, None)


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