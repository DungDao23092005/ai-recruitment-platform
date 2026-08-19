from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import AIError, EntityNotFoundException
from app.domain.enums import UserRole
from app.services.company_service import CompanyService


def _fake_company(company_id: uuid.UUID | None = None) -> MagicMock:
    company = MagicMock()
    company.id = company_id or uuid.uuid4()
    company.is_deleted = False
    return company


def _fake_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = UserRole.ADMIN
    return user


def _make_job_service(jobs, delete_side_effect=None):
    job_service = MagicMock()
    job_service.jobs = MagicMock()
    job_service.jobs.list_jobs_by_company = AsyncMock(return_value=jobs)
    job_service.delete_job = AsyncMock(side_effect=delete_side_effect)
    return job_service


def _make_service(company):
    session = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    service = CompanyService(session)
    service.companies = MagicMock()
    service.companies.get_by_id = AsyncMock(return_value=company)
    service.companies.soft_delete = AsyncMock()
    return service, session


class TestDeleteCompany:
    def test_deletes_all_active_jobs_then_soft_deletes_company(self):
        company = _fake_company()
        jobs = [MagicMock(id=uuid.uuid4()), MagicMock(id=uuid.uuid4())]
        job_service = _make_job_service(jobs)
        service, session = _make_service(company)

        result = asyncio.run(
            service.delete_company(_fake_user(), company.id, job_service)
        )

        assert job_service.delete_job.await_count == 2
        first_call = job_service.delete_job.await_args_list[0]
        assert first_call.args[1] == jobs[0].id
        service.companies.soft_delete.assert_awaited_once_with(company)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(company)
        assert result is company

    def test_unknown_company_raises_not_found(self):
        company_id = uuid.uuid4()
        job_service = _make_job_service([])
        session = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.rollback = AsyncMock()
        service = CompanyService(session)
        service.companies = MagicMock()
        service.companies.get_by_id = AsyncMock(return_value=None)
        service.companies.soft_delete = AsyncMock()

        with pytest.raises(EntityNotFoundException):
            asyncio.run(
                service.delete_company(_fake_user(), company_id, job_service)
            )

        job_service.delete_job.assert_not_awaited()
        service.companies.soft_delete.assert_not_awaited()
        session.commit.assert_not_awaited()

    def test_qdrant_failure_aborts_cascade_before_company_lock(self):
        company = _fake_company()
        jobs = [MagicMock(id=uuid.uuid4()), MagicMock(id=uuid.uuid4())]

        async def boom(user, job_id):
            raise AIError("Failed to delete vector from collection 'jobs'")

        job_service = _make_job_service(jobs, delete_side_effect=boom)
        service, session = _make_service(company)

        with pytest.raises(AIError):
            asyncio.run(
                service.delete_company(_fake_user(), company.id, job_service)
            )

        service.companies.soft_delete.assert_not_awaited()
        session.commit.assert_not_awaited()

    def test_already_locked_company_raises_not_found(self):
        company = _fake_company()
        company.is_deleted = True
        service, _ = _make_service(company)
        service.companies.get_by_id = AsyncMock(return_value=None)
        job_service = _make_job_service([])

        with pytest.raises(EntityNotFoundException):
            asyncio.run(
                service.delete_company(_fake_user(), company.id, job_service)
            )

        job_service.delete_job.assert_not_awaited()