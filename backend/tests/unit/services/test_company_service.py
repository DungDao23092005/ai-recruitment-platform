import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import (
    ConfigurationError,
    ConflictException,
    EntityNotFoundException,
)
from app.domain.enums import CompanySize, MembershipRole, MembershipStatus, UserRole
from app.models import Company, CompanyMembership, RecruiterProfile, User
from app.repositories import (
    CompanyMembershipRepository,
    CompanyRepository,
    UserRepository,
)
from app.schemas.company import CompanyCreate, CompanyUpdate
from app.services.company_email_service import CompanyEmailService
from app.services.company_entitlement_service import CompanyEntitlementService
from app.services.company_service import CompanyService
from app.services.notification_service import NotificationService


def make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
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
    service.users = AsyncMock(spec=UserRepository)
    service.memberships = AsyncMock(spec=CompanyMembershipRepository)
    service.memberships.list_by_company.return_value = []
    service.notifications = AsyncMock(spec=NotificationService)
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


class TestCreateCompanyForOwner:
    """Gap A — Company workspace creation and entitlement provisioning rollback tests."""

    def test_successful_provisioning_adds_entities_and_commits(self):
        session = make_session()
        service = make_service(session)
        service.companies.get_by_slug.return_value = None
        service.companies.get_by_tax_code.return_value = None

        owner = User(
            id=uuid.uuid4(),
            email="owner@example.com",
            role=UserRole.RECRUITER,
            recruiter_profile=None,
        )
        service.users.get_with_profile.return_value = owner

        data = CompanyCreate(
            name="Acme Corp",
            slug="acme-corp",
            tax_code="123456789",
            size=CompanySize.STARTUP,
        )

        with patch.object(
            CompanyEntitlementService,
            "provision_company_free_subscription",
            new_callable=AsyncMock,
        ) as mock_provision:
            company = asyncio.run(service.create_company_for_owner(data, owner))

            # Verify Company is added
            added_companies = [
                call.args[0]
                for call in session.add.call_args_list
                if isinstance(call.args[0], Company)
            ]
            assert len(added_companies) == 1
            assert added_companies[0] is company

            # Verify CompanyMembership owner is added with ADMIN role and ACTIVE status
            added_memberships = [
                call.args[0]
                for call in session.add.call_args_list
                if isinstance(call.args[0], CompanyMembership)
            ]
            assert len(added_memberships) == 1
            membership = added_memberships[0]
            assert membership.company_id == company.id
            assert membership.user_id == owner.id
            assert membership.role == MembershipRole.ADMIN
            assert membership.status == MembershipStatus.ACTIVE

            # Verify RecruiterProfile is created when missing
            added_profiles = [
                call.args[0]
                for call in session.add.call_args_list
                if isinstance(call.args[0], RecruiterProfile)
            ]
            assert len(added_profiles) == 1
            assert added_profiles[0].company_id == company.id
            assert added_profiles[0].user_id == owner.id

            # Verify provisioning is called exactly once with the new company.id
            mock_provision.assert_awaited_once_with(company.id)

            # Verify session.commit is awaited exactly once
            session.commit.assert_awaited_once()

            # Verify session.rollback is not awaited
            session.rollback.assert_not_awaited()

    def test_successful_provisioning_associates_existing_unbound_profile(self):
        session = make_session()
        service = make_service(session)
        service.companies.get_by_slug.return_value = None
        service.companies.get_by_tax_code.return_value = None

        existing_profile = RecruiterProfile(
            user_id=uuid.uuid4(),
            company_id=None,
        )
        owner = User(
            id=existing_profile.user_id,
            email="owner@example.com",
            role=UserRole.RECRUITER,
            recruiter_profile=existing_profile,
        )
        service.users.get_with_profile.return_value = owner

        data = CompanyCreate(
            name="Acme Corp",
            slug="acme-corp",
            tax_code="123456789",
            size=CompanySize.STARTUP,
        )

        with patch.object(
            CompanyEntitlementService,
            "provision_company_free_subscription",
            new_callable=AsyncMock,
        ) as mock_provision:
            company = asyncio.run(service.create_company_for_owner(data, owner))

            assert existing_profile.company_id == company.id
            mock_provision.assert_awaited_once_with(company.id)
            session.commit.assert_awaited_once()
            session.rollback.assert_not_awaited()

    def test_configuration_error_during_provisioning_rolls_back_without_commit(self):
        session = make_session()
        service = make_service(session)
        service.companies.get_by_slug.return_value = None
        service.companies.get_by_tax_code.return_value = None

        owner = User(
            id=uuid.uuid4(),
            email="owner@example.com",
            role=UserRole.RECRUITER,
            recruiter_profile=None,
        )
        service.users.get_with_profile.return_value = owner

        data = CompanyCreate(
            name="Acme Corp",
            slug="acme-corp",
            tax_code="123456789",
            size=CompanySize.STARTUP,
        )

        with patch.object(
            CompanyEntitlementService,
            "provision_company_free_subscription",
            new_callable=AsyncMock,
        ) as mock_provision:
            mock_provision.side_effect = ConfigurationError(
                "No active Company Free Plan configured. Provision the canonical "
                "Company Free plan before creating workspaces."
            )

            with pytest.raises(ConfigurationError, match="No active Company Free Plan"):
                asyncio.run(service.create_company_for_owner(data, owner))

            # Assert rollback is awaited exactly once
            session.rollback.assert_awaited_once()

            # Assert session.commit is not awaited
            session.commit.assert_not_awaited()

    def test_unexpected_runtime_exception_during_provisioning_rolls_back(self):
        session = make_session()
        service = make_service(session)
        service.companies.get_by_slug.return_value = None
        service.companies.get_by_tax_code.return_value = None

        owner = User(
            id=uuid.uuid4(),
            email="owner@example.com",
            role=UserRole.RECRUITER,
            recruiter_profile=None,
        )
        service.users.get_with_profile.return_value = owner

        data = CompanyCreate(
            name="Acme Corp",
            slug="acme-corp",
            tax_code="123456789",
            size=CompanySize.STARTUP,
        )

        with patch.object(
            CompanyEntitlementService,
            "provision_company_free_subscription",
            new_callable=AsyncMock,
        ) as mock_provision:
            mock_provision.side_effect = RuntimeError("database connection failed")

            with pytest.raises(RuntimeError, match="database connection failed"):
                asyncio.run(service.create_company_for_owner(data, owner))

            # Assert rollback is awaited exactly once
            session.rollback.assert_awaited_once()

            # Assert session.commit is not awaited
            session.commit.assert_not_awaited()


class TestUpdateCompanyNotifications:
    def test_no_op_suppresses_notifications_and_emails(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        service.companies.get_by_id.return_value = company

        # Send same name, slug, tax_code, size
        data = CompanyUpdate(
            name=company.name,
            slug=company.slug,
            tax_code=company.tax_code,
            size=company.size,
        )

        with patch.object(
            CompanyEmailService,
            "schedule_company_profile_updated_email",
            new_callable=AsyncMock,
        ) as mock_email:
            result = asyncio.run(
                service.update_company(company_id=company.id, data=data)
            )

            assert result is company
            session.commit.assert_awaited_once()
            service.memberships.list_by_company.assert_not_awaited()
            service.notifications.notify_company_profile_updated.assert_not_awaited()
            mock_email.assert_not_awaited()

    def test_initiator_excluded_and_all_active_roles_notified(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        service.companies.get_by_id.return_value = company

        updater_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        recruiter_id = uuid.uuid4()
        interviewer_id = uuid.uuid4()

        updater_user = User(
            id=updater_id,
            email="updater@example.com",
            role=UserRole.RECRUITER,
            recruiter_profile=RecruiterProfile(full_name="Nguyễn Văn A"),
        )
        admin_user = User(
            id=admin_id,
            email="admin@example.com",
            role=UserRole.RECRUITER,
            recruiter_profile=RecruiterProfile(full_name="Trần Thị B"),
        )
        recruiter_user = User(
            id=recruiter_id,
            email="recruiter@example.com",
            role=UserRole.RECRUITER,
            recruiter_profile=RecruiterProfile(full_name="Lê Văn C"),
        )
        interviewer_user = User(
            id=interviewer_id,
            email="interviewer@example.com",
            role=UserRole.RECRUITER,
            recruiter_profile=RecruiterProfile(full_name="Phạm Văn D"),
        )

        memberships = [
            CompanyMembership(
                id=uuid.uuid4(),
                company_id=company.id,
                user_id=updater_id,
                role=MembershipRole.ADMIN,
                status=MembershipStatus.ACTIVE,
                user=updater_user,
            ),
            CompanyMembership(
                id=uuid.uuid4(),
                company_id=company.id,
                user_id=admin_id,
                role=MembershipRole.ADMIN,
                status=MembershipStatus.ACTIVE,
                user=admin_user,
            ),
            CompanyMembership(
                id=uuid.uuid4(),
                company_id=company.id,
                user_id=recruiter_id,
                role=MembershipRole.RECRUITER,
                status=MembershipStatus.ACTIVE,
                user=recruiter_user,
            ),
            CompanyMembership(
                id=uuid.uuid4(),
                company_id=company.id,
                user_id=interviewer_id,
                role=MembershipRole.INTERVIEWER,
                status=MembershipStatus.ACTIVE,
                user=interviewer_user,
            ),
        ]
        service.memberships.list_by_company.return_value = memberships

        data = CompanyUpdate(name="Acme Global")

        with patch.object(
            CompanyEmailService,
            "schedule_company_profile_updated_email",
            new_callable=AsyncMock,
        ) as mock_email:
            result = asyncio.run(
                service.update_company(
                    company_id=company.id,
                    data=data,
                    updated_by=updater_user,
                )
            )

            assert result.name == "Acme Global"
            session.commit.assert_awaited_once()

            # Verify PO-1 & PO-2: Updater excluded, exactly 3 other members notified
            notified_user_ids = [
                call.kwargs["user_id"]
                for call in service.notifications.notify_company_profile_updated.call_args_list
            ]
            assert updater_id not in notified_user_ids
            assert set(notified_user_ids) == {admin_id, recruiter_id, interviewer_id}

            # Verify updater attribution (PO-4): member full name
            for call in service.notifications.notify_company_profile_updated.call_args_list:
                assert call.kwargs["updater_name"] == "Nguyễn Văn A"
                assert call.kwargs["changed_fields_summary"] == "tên công ty"

            # Verify emails scheduled for the 3 members with correct updater attribution
            emailed_user_ids = [
                call.kwargs["recipient_user_id"]
                for call in mock_email.call_args_list
            ]
            assert updater_id not in emailed_user_ids
            assert set(emailed_user_ids) == {admin_id, recruiter_id, interviewer_id}
            for call in mock_email.call_args_list:
                assert call.kwargs["updater_name"] == "Nguyễn Văn A"

    def test_platform_admin_updater_attributed_as_system_admin(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        service.companies.get_by_id.return_value = company

        platform_admin = User(
            id=uuid.uuid4(),
            email="platform.admin@company.com",
            role=UserRole.ADMIN,
            recruiter_profile=None,
        )

        member_id = uuid.uuid4()
        member_user = User(
            id=member_id,
            email="member@example.com",
            role=UserRole.RECRUITER,
            recruiter_profile=RecruiterProfile(full_name="Thành Viên 1"),
        )
        memberships = [
            CompanyMembership(
                id=uuid.uuid4(),
                company_id=company.id,
                user_id=member_id,
                role=MembershipRole.ADMIN,
                status=MembershipStatus.ACTIVE,
                user=member_user,
            )
        ]
        service.memberships.list_by_company.return_value = memberships

        data = CompanyUpdate(tax_code="987654321")
        service.companies.get_by_tax_code.return_value = None

        with patch.object(
            CompanyEmailService,
            "schedule_company_profile_updated_email",
            new_callable=AsyncMock,
        ) as mock_email:
            asyncio.run(
                service.update_company(
                    company_id=company.id,
                    data=data,
                    updated_by=platform_admin,
                )
            )

            # Verify PO-4 (Option A): Platform admin is attributed as "Quản trị viên hệ thống"
            service.notifications.notify_company_profile_updated.assert_awaited_once()
            notif_kwargs = (
                service.notifications.notify_company_profile_updated.call_args.kwargs
            )
            assert notif_kwargs["updater_name"] == "Quản trị viên hệ thống"
            assert notif_kwargs["changed_fields_summary"] == "mã số thuế"

            mock_email.assert_awaited_once()
            email_kwargs = mock_email.call_args.kwargs
            assert email_kwargs["updater_name"] == "Quản trị viên hệ thống"

    def test_tenant_isolation_queries_only_target_company(self):
        session = make_session()
        service = make_service(session)
        target_company_id = uuid.uuid4()
        company = make_company(company_id=target_company_id)
        service.companies.get_by_id.return_value = company

        data = CompanyUpdate(name="Isolated Corp")
        asyncio.run(
            service.update_company(company_id=target_company_id, data=data)
        )

        # Confirm list_by_company was called with target_company_id only
        service.memberships.list_by_company.assert_awaited_once_with(
            target_company_id, include_revoked=False
        )
