from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

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


def make_user(role: UserRole, profile_company_id: uuid.UUID | None) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    profile = MagicMock() if profile_company_id is not None else None
    if profile is not None:
        profile.company_id = profile_company_id
    user.recruiter_profile = profile
    return user


class TestUpdateOwnedCompany:
    def test_recruiter_updates_owned_company(self):
        session = make_session()
        service = CompanyService(session)
        service.companies = AsyncMock(spec=CompanyRepository)
        company = make_company()
        service.companies.get_by_id.return_value = company
        owner = make_user(UserRole.RECRUITER, company.id)
        data = CompanyUpdate(name="Acme International")

        with patch(
            "app.services.company_service.UserService"
        ) as mock_user_service:
            mock_user_service.return_value.get_user_with_profile = AsyncMock(
                return_value=owner
            )
            result = asyncio.run(
                service.update_owned_company(owner, company.id, data)
            )

        assert result is company
        assert company.name == "Acme International"
        service.companies.get_by_id.assert_awaited_once_with(company.id)
        session.commit.assert_awaited_once()

    def test_recruiter_without_profile_forbidden(self):
        session = make_session()
        service = CompanyService(session)
        service.companies = AsyncMock(spec=CompanyRepository)
        owner = make_user(UserRole.RECRUITER, None)
        data = CompanyUpdate(name="Renamed")

        with patch(
            "app.services.company_service.UserService"
        ) as mock_user_service:
            mock_user_service.return_value.get_user_with_profile = AsyncMock(
                return_value=owner
            )
            with pytest.raises(ForbiddenException):
                asyncio.run(
                    service.update_owned_company(
                        owner, uuid.uuid4(), data
                    )
                )

        service.companies.get_by_id.assert_not_awaited()
        session.commit.assert_not_awaited()

    def test_recruiter_foreign_company_forbidden(self):
        session = make_session()
        service = CompanyService(session)
        service.companies = AsyncMock(spec=CompanyRepository)
        foreign_company_id = uuid.uuid4()
        owner = make_user(UserRole.RECRUITER, foreign_company_id)
        data = CompanyUpdate(name="Renamed")

        with patch(
            "app.services.company_service.UserService"
        ) as mock_user_service:
            mock_user_service.return_value.get_user_with_profile = AsyncMock(
                return_value=owner
            )
            with pytest.raises(ForbiddenException):
                asyncio.run(
                    service.update_owned_company(
                        owner, uuid.uuid4(), data
                    )
                )

        service.companies.get_by_id.assert_not_awaited()
        session.commit.assert_not_awaited()

    def test_admin_can_update_any_company(self):
        session = make_session()
        service = CompanyService(session)
        service.companies = AsyncMock(spec=CompanyRepository)
        company = make_company()
        service.companies.get_by_id.return_value = company
        admin = make_user(UserRole.ADMIN, None)
        data = CompanyUpdate(size=CompanySize.ENTERPRISE)

        with patch(
            "app.services.company_service.UserService"
        ) as mock_user_service:
            mock_user_service.return_value.get_user_with_profile = AsyncMock()
            result = asyncio.run(
                service.update_owned_company(admin, company.id, data)
            )

        assert result is company
        assert company.size == CompanySize.ENTERPRISE
        mock_user_service.return_value.get_user_with_profile.assert_not_awaited()
        service.companies.get_by_id.assert_awaited_once_with(company.id)
        session.commit.assert_awaited_once()

    def test_unknown_company_raises_not_found(self):
        session = make_session()
        service = CompanyService(session)
        service.companies = AsyncMock(spec=CompanyRepository)
        company_id = uuid.uuid4()
        owner = make_user(UserRole.RECRUITER, company_id)
        service.companies.get_by_id.return_value = None
        data = CompanyUpdate(name="Renamed")

        with patch(
            "app.services.company_service.UserService"
        ) as mock_user_service:
            mock_user_service.return_value.get_user_with_profile = AsyncMock(
                return_value=owner
            )
            with pytest.raises(EntityNotFoundException):
                asyncio.run(
                    service.update_owned_company(owner, company_id, data)
                )

    def test_slug_conflict_propagates(self):
        session = make_session()
        service = CompanyService(session)
        service.companies = AsyncMock(spec=CompanyRepository)
        company = make_company()
        other = make_company()
        service.companies.get_by_id.return_value = company
        service.companies.get_by_slug.return_value = other
        owner = make_user(UserRole.RECRUITER, company.id)
        data = CompanyUpdate(slug="taken")

        with patch(
            "app.services.company_service.UserService"
        ) as mock_user_service:
            mock_user_service.return_value.get_user_with_profile = AsyncMock(
                return_value=owner
            )
            with pytest.raises(ConflictException):
                asyncio.run(
                    service.update_owned_company(owner, company.id, data)
                )

    def test_tax_code_conflict_propagates(self):
        session = make_session()
        service = CompanyService(session)
        service.companies = AsyncMock(spec=CompanyRepository)
        company = make_company()
        other = make_company()
        service.companies.get_by_id.return_value = company
        service.companies.get_by_tax_code.return_value = other
        owner = make_user(UserRole.RECRUITER, company.id)
        data = CompanyUpdate(tax_code="999")

        with patch(
            "app.services.company_service.UserService"
        ) as mock_user_service:
            mock_user_service.return_value.get_user_with_profile = AsyncMock(
                return_value=owner
            )
            with pytest.raises(ConflictException):
                asyncio.run(
                    service.update_owned_company(owner, company.id, data)
                )
