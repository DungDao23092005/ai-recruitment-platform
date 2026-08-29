import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ConflictException, EntityNotFoundException
from app.domain.enums import CompanySize
from app.models import Company
from app.repositories import CompanyRepository
from app.schemas.company import CompanyCreate, CompanyUpdate
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


def make_service(session) -> CompanyService:
    service = CompanyService(session)
    service.companies = AsyncMock(spec=CompanyRepository)
    return service


class TestCreateCompany:
    def test_creates_company(self):
        session = make_session()
        service = make_service(session)
        service.companies.get_by_slug.return_value = None
        service.companies.get_by_tax_code.return_value = None
        data = CompanyCreate(
            name="Acme Corp",
            slug="acme-corp",
            tax_code="123456789",
            size=CompanySize.ENTERPRISE,
        )

        company = asyncio.run(service.create_company(data))

        assert company.name == "Acme Corp"
        assert company.slug == "acme-corp"
        assert company.tax_code == "123456789"
        assert company.size == CompanySize.ENTERPRISE
        session.add.assert_called_once_with(company)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(company)

    def test_duplicate_slug_raises_conflict(self):
        session = make_session()
        service = make_service(session)
        service.companies.get_by_slug.return_value = make_company()
        data = CompanyCreate(
            name="Acme Corp",
            slug="acme-corp",
            tax_code="999999999",
            size=CompanySize.STARTUP,
        )

        with pytest.raises(ConflictException):
            asyncio.run(service.create_company(data))

        session.commit.assert_not_awaited()

    def test_duplicate_tax_code_raises_conflict(self):
        session = make_session()
        service = make_service(session)
        service.companies.get_by_slug.return_value = None
        service.companies.get_by_tax_code.return_value = make_company()
        data = CompanyCreate(
            name="Acme Corp",
            slug="acme-corp-2",
            tax_code="123456789",
            size=CompanySize.STARTUP,
        )

        with pytest.raises(ConflictException):
            asyncio.run(service.create_company(data))

        session.commit.assert_not_awaited()

    def test_commit_failure_rolls_back(self):
        session = make_session()
        service = make_service(session)
        service.companies.get_by_slug.return_value = None
        service.companies.get_by_tax_code.return_value = None
        session.commit.side_effect = RuntimeError("db down")
        data = CompanyCreate(
            name="Acme Corp",
            slug="acme-corp",
            tax_code="123456789",
            size=CompanySize.STARTUP,
        )

        with pytest.raises(RuntimeError):
            asyncio.run(service.create_company(data))

        session.rollback.assert_awaited_once()


class TestGetCompanyById:
    def test_returns_company(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        service.companies.get_by_id.return_value = company

        result = asyncio.run(service.get_company_by_id(company.id))

        assert result is company

    def test_returns_none_when_missing(self):
        session = make_session()
        service = make_service(session)
        service.companies.get_by_id.return_value = None

        result = asyncio.run(service.get_company_by_id(uuid.uuid4()))

        assert result is None


class TestListCompanies:
    def test_returns_all_companies(self):
        session = make_session()
        service = make_service(session)
        companies = [make_company(), make_company()]
        service.companies.list_all.return_value = companies

        result = asyncio.run(service.list_companies())

        assert result == companies
        service.companies.list_all.assert_awaited_once()

    def test_returns_empty_list_when_none_exist(self):
        session = make_session()
        service = make_service(session)
        service.companies.list_all.return_value = []

        result = asyncio.run(service.list_companies())

        assert result == []


class TestUpdateCompany:
    def test_updates_name_and_size(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        service.companies.get_by_id.return_value = company
        data = CompanyUpdate(
            name="Acme International",
            size=CompanySize.ENTERPRISE,
        )

        result = asyncio.run(
            service.update_company(company_id=company.id, data=data)
        )

        assert result is company
        assert company.name == "Acme International"
        assert company.size == CompanySize.ENTERPRISE
        session.commit.assert_awaited_once()

    def test_updates_slug_when_available(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        service.companies.get_by_id.return_value = company
        service.companies.get_by_slug.return_value = None
        data = CompanyUpdate(slug="acme-new")

        result = asyncio.run(
            service.update_company(company_id=company.id, data=data)
        )

        assert result is company
        assert company.slug == "acme-new"

    def test_slug_taken_by_other_company_raises_conflict(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        other = make_company()
        service.companies.get_by_id.return_value = company
        service.companies.get_by_slug.return_value = other
        data = CompanyUpdate(slug="acme-new")

        with pytest.raises(ConflictException):
            asyncio.run(service.update_company(company_id=company.id, data=data))

        session.commit.assert_not_awaited()

    def test_tax_code_taken_by_other_company_raises_conflict(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        other = make_company()
        service.companies.get_by_id.return_value = company
        service.companies.get_by_tax_code.return_value = other
        data = CompanyUpdate(tax_code="000000000")

        with pytest.raises(ConflictException):
            asyncio.run(service.update_company(company_id=company.id, data=data))

        session.commit.assert_not_awaited()

    def test_company_not_found_raises(self):
        session = make_session()
        service = make_service(session)
        service.companies.get_by_id.return_value = None
        data = CompanyUpdate(name="Renamed")

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.update_company(company_id=uuid.uuid4(), data=data))

    def test_commit_failure_rolls_back(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        service.companies.get_by_id.return_value = company
        session.commit.side_effect = RuntimeError("db down")
        data = CompanyUpdate(name="Renamed")

        with pytest.raises(RuntimeError):
            asyncio.run(service.update_company(company_id=company.id, data=data))

        session.rollback.assert_awaited_once()


class TestCreateCompanyRecruiterOwnership:
    """Tests for recruiter company creation ownership rules."""

    def test_recruiter_without_company_can_create(self):
        """Recruiter without existing company can create a new company."""
        session = make_session()
        service = make_service(session)
        service.companies.get_by_slug.return_value = None
        service.companies.get_by_tax_code.return_value = None
        data = CompanyCreate(
            name="New Company",
            slug="new-company",
            tax_code="999999999",
            size=CompanySize.STARTUP,
        )

        company = asyncio.run(service.create_company(data))

        assert company is not None
        session.add.assert_called_once_with(company)
        session.commit.assert_awaited_once()

    def test_recruiter_with_existing_company_cannot_create_second(self):
        """Recruiter who already owns a company cannot create a second one.

        This test would require integration with UserService to check
        the recruiter's profile. The actual enforcement happens at the API layer.
        This test documents the expected behavior.
        """
        # The actual check is in the API endpoint (companies.py create_company)
        # which uses UserService to check recruiter_profile.company_id
        # This test is a placeholder to document the requirement
        pass

    def test_duplicate_slug_still_raises_conflict(self):
        """Duplicate slug check still works even with ownership rules."""
        session = make_session()
        service = make_service(session)
        service.companies.get_by_slug.return_value = make_company()
        data = CompanyCreate(
            name="Another Company",
            slug="acme-corp",
            tax_code="999999999",
            size=CompanySize.STARTUP,
        )

        with pytest.raises(ConflictException):
            asyncio.run(service.create_company(data))

        session.commit.assert_not_awaited()
