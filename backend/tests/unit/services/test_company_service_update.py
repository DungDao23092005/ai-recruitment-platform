from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
)
from app.domain.enums import CompanySize, UserRole
from app.models import Company
from app.repositories import CompanyRepository
from app.schemas.company import CompanyUpdate
from app.services.company_service import CompanyService


def make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    return session


def make_company(company_id: uuid.UUID | None = None) -> Company:
    return Company(
        id=company_id or uuid.uuid4(),
        name="Acme Corp",
        slug="acme-corp",
        tax_code="123456789",
        size=CompanySize.STARTUP,
    )


def make_user(role: UserRole) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    return user


def make_service(session) -> CompanyService:
    service = CompanyService(session)
    service.companies = AsyncMock(spec=CompanyRepository)
    return service


class TestUpdateOwnedCompany:
    def test_recruiter_updates_owned_company(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        service.companies.get_by_id.return_value = company
        recruiter = make_user(UserRole.RECRUITER)
        data = CompanyUpdate(name="Acme International")

        result = asyncio.run(
            service.update_owned_company(
                recruiter,
                company.id,
                data,
                workspace_company_id=company.id,
            )
        )

        assert result is company
        assert company.name == "Acme International"
        service.companies.get_by_id.assert_awaited_with(company.id)
        assert service.companies.get_by_id.await_count == 2
        session.commit.assert_awaited_once()

    def test_recruiter_without_workspace_forbidden(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        service.companies.get_by_id.return_value = company
        recruiter = make_user(UserRole.RECRUITER)

        with pytest.raises(ForbiddenException):
            asyncio.run(
                service.update_owned_company(
                    recruiter,
                    company.id,
                    CompanyUpdate(name="Renamed"),
                    workspace_company_id=None,
                )
            )

        service.companies.get_by_id.assert_awaited_once_with(company.id)
        session.commit.assert_not_awaited()

    def test_recruiter_foreign_company_forbidden(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        service.companies.get_by_id.return_value = company
        foreign_company_id = uuid.uuid4()
        recruiter = make_user(UserRole.RECRUITER)

        with pytest.raises(ForbiddenException):
            asyncio.run(
                service.update_owned_company(
                    recruiter,
                    company.id,
                    CompanyUpdate(name="Renamed"),
                    workspace_company_id=foreign_company_id,
                )
            )

        service.companies.get_by_id.assert_awaited_once_with(company.id)
        session.commit.assert_not_awaited()

    def test_admin_can_update_any_company(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        service.companies.get_by_id.return_value = company
        admin = make_user(UserRole.ADMIN)
        data = CompanyUpdate(size=CompanySize.ENTERPRISE)

        result = asyncio.run(
            service.update_owned_company(admin, company.id, data)
        )

        assert result is company
        assert company.size == CompanySize.ENTERPRISE
        service.companies.get_by_id.assert_awaited_once_with(company.id)
        session.commit.assert_awaited_once()

    def test_unknown_company_raises_not_found(self):
        session = make_session()
        service = make_service(session)
        company_id = uuid.uuid4()
        recruiter = make_user(UserRole.RECRUITER)
        service.companies.get_by_id.return_value = None
        data = CompanyUpdate(name="Renamed")

        with pytest.raises(EntityNotFoundException):
            asyncio.run(
                service.update_owned_company(
                    recruiter,
                    company_id,
                    data,
                    workspace_company_id=company_id,
                )
            )

    def test_slug_conflict_propagates(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        other = make_company()
        service.companies.get_by_id.return_value = company
        service.companies.get_by_slug.return_value = other
        recruiter = make_user(UserRole.RECRUITER)
        data = CompanyUpdate(slug="taken")

        with pytest.raises(ConflictException):
            asyncio.run(
                service.update_owned_company(
                    recruiter,
                    company.id,
                    data,
                    workspace_company_id=company.id,
                )
            )

    def test_tax_code_conflict_propagates(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        other = make_company()
        service.companies.get_by_id.return_value = company
        service.companies.get_by_tax_code.return_value = other
        recruiter = make_user(UserRole.RECRUITER)
        data = CompanyUpdate(tax_code="999")

        with pytest.raises(ConflictException):
            asyncio.run(
                service.update_owned_company(
                    recruiter,
                    company.id,
                    data,
                    workspace_company_id=company.id,
                )
            )
