from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_optional_workspace
from app.api.v1.endpoints.companies import _get_company_service
from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
)
from app.domain.enums import CompanySize, MembershipRole, MembershipStatus, UserRole
from app.main import app
from app.models import Company, CompanyMembership, EmailOutbox, Notification, RecruiterProfile, User
from app.repositories import CompanyMembershipRepository, CompanyRepository, UserRepository
from app.schemas.company import CompanyRead, CompanyUpdate
from app.services.company_email_service import CompanyEmailService
from app.services.company_service import CompanyService
from app.services.notification_service import NotificationService
from app.services.workspace_service import WorkspaceContext

API_PREFIX = "/api/v1/companies"


def _fake_company(company_id: uuid.UUID | None = None) -> Company:
    now = datetime.now(timezone.utc)
    return Company(
        id=company_id or uuid.uuid4(),
        name="TechCorp AI",
        slug="techcorp-ai",
        tax_code="0109876543",
        size=CompanySize.STARTUP,
        created_at=now,
        updated_at=now,
    )


def _fake_user(role: UserRole, user_id: uuid.UUID | None = None, full_name: str | None = None) -> User:
    uid = user_id or uuid.uuid4()
    profile = RecruiterProfile(full_name=full_name) if full_name else None
    return User(
        id=uid,
        email=f"user-{uid}@example.com",
        role=role,
        is_active=True,
        recruiter_profile=profile,
    )


def _fake_workspace_context(
    user: User,
    company: Company | None = None,
    company_id: uuid.UUID | None = None,
    role: MembershipRole = MembershipRole.ADMIN,
    is_platform_admin: bool = False,
) -> WorkspaceContext:
    target_company = company or _fake_company(company_id=company_id)
    membership = CompanyMembership(
        id=uuid.uuid4(),
        company_id=target_company.id,
        user_id=user.id,
        role=role,
        status=MembershipStatus.ACTIVE,
        company=target_company,
        user=user,
    )
    return WorkspaceContext(
        user=user,
        company=target_company,
        membership=membership,
        is_platform_admin=is_platform_admin,
    )


class TestCompaniesApiEndpoints:
    @pytest.fixture
    def mock_service(self):
        service = MagicMock(spec=CompanyService)
        service.update_owned_company = AsyncMock()
        return service

    @pytest.fixture
    def client(self, mock_service):
        app.dependency_overrides[_get_company_service] = lambda: mock_service
        with TestClient(app) as c:
            yield c
        app.dependency_overrides.clear()

    def test_anonymous_update_401(self, client):
        resp = client.patch(
            f"{API_PREFIX}/{uuid.uuid4()}",
            json={"name": "New Name"},
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_candidate_update_forbidden_403(self, client):
        app.dependency_overrides[get_current_user] = lambda: _fake_user(UserRole.CANDIDATE)
        resp = client.patch(
            f"{API_PREFIX}/{uuid.uuid4()}",
            json={"name": "New Name"},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_interviewer_workspace_guard_403(self, client):
        company_id = uuid.uuid4()
        user = _fake_user(UserRole.RECRUITER)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_optional_workspace] = lambda: _fake_workspace_context(
            user=user,
            company_id=company_id,
            role=MembershipRole.INTERVIEWER,
        )
        resp = client.patch(
            f"{API_PREFIX}/{company_id}",
            json={"name": "Interviewer Renamed"},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert resp.json()["detail"] == "Not enough permissions"

    def test_recruiter_forbidden_on_foreign_company(self, client, mock_service):
        company_id = uuid.uuid4()
        user = _fake_user(UserRole.RECRUITER)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_optional_workspace] = lambda: _fake_workspace_context(
            user=user,
            company_id=uuid.uuid4(),
            role=MembershipRole.ADMIN,
        )
        mock_service.update_owned_company.side_effect = ForbiddenException(
            f"Not allowed to update company {company_id}"
        )

        resp = client.patch(
            f"{API_PREFIX}/{company_id}",
            json={"name": "Hijacked"},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_company_not_found_404(self, client, mock_service):
        company_id = uuid.uuid4()
        user = _fake_user(UserRole.RECRUITER)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_optional_workspace] = lambda: _fake_workspace_context(
            user=user,
            company_id=company_id,
            role=MembershipRole.ADMIN,
        )
        mock_service.update_owned_company.side_effect = EntityNotFoundException(
            f"Company {company_id} not found"
        )

        resp = client.patch(
            f"{API_PREFIX}/{company_id}",
            json={"name": "Missing Co"},
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_duplicate_slug_conflict_400(self, client, mock_service):
        company_id = uuid.uuid4()
        user = _fake_user(UserRole.RECRUITER)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_optional_workspace] = lambda: _fake_workspace_context(
            user=user,
            company_id=company_id,
            role=MembershipRole.ADMIN,
        )
        mock_service.update_owned_company.side_effect = ConflictException(
            "Đường dẫn (slug) 'taken-slug' đã được sử dụng."
        )

        resp = client.patch(
            f"{API_PREFIX}/{company_id}",
            json={"slug": "taken-slug"},
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "slug" in resp.json()["detail"]

    def test_authorized_update_success_200(self, client, mock_service):
        company_id = uuid.uuid4()
        user = _fake_user(UserRole.RECRUITER)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_optional_workspace] = lambda: _fake_workspace_context(
            user=user,
            company_id=company_id,
            role=MembershipRole.ADMIN,
        )
        updated_company = _fake_company(company_id=company_id)
        updated_company.name = "TechCorp Global"
        mock_service.update_owned_company.return_value = updated_company

        resp = client.patch(
            f"{API_PREFIX}/{company_id}",
            json={"name": "TechCorp Global"},
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["name"] == "TechCorp Global"
        assert data["id"] == str(company_id)
        mock_service.update_owned_company.assert_awaited_once()


class TestCompaniesServiceEndToEndIntegration:
    """End-to-end integration tests verifying notifications, email outbox, and attribution."""

    @staticmethod
    def _setup_service():
        session = MagicMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.rollback = AsyncMock()

        service = CompanyService(session)
        service.companies = AsyncMock(spec=CompanyRepository)
        service.users = AsyncMock(spec=UserRepository)
        service.memberships = AsyncMock(spec=CompanyMembershipRepository)
        service.notifications = NotificationService(session)
        service.notifications.notifications = MagicMock()
        service.notifications.create_notification = AsyncMock()
        return service, session

    def test_update_creates_notifications_and_enqueues_emails(self):
        service, session = self._setup_service()
        company = _fake_company()
        service.companies.get_by_id.return_value = company

        updater_id = uuid.uuid4()
        updater = _fake_user(UserRole.RECRUITER, user_id=updater_id, full_name="Lê Hoàng Nam")

        admin_id = uuid.uuid4()
        admin_user = _fake_user(UserRole.RECRUITER, user_id=admin_id, full_name="Vũ Mai Chi")

        interviewer_id = uuid.uuid4()
        interviewer_user = _fake_user(UserRole.RECRUITER, user_id=interviewer_id, full_name="Đặng Tuấn Anh")

        memberships = [
            CompanyMembership(
                id=uuid.uuid4(),
                company_id=company.id,
                user_id=updater_id,
                role=MembershipRole.ADMIN,
                status=MembershipStatus.ACTIVE,
                user=updater,
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
                user_id=interviewer_id,
                role=MembershipRole.INTERVIEWER,
                status=MembershipStatus.ACTIVE,
                user=interviewer_user,
            ),
        ]
        service.memberships.list_by_company.return_value = memberships

        payload = CompanyUpdate(name="TechCorp Super AI", size=CompanySize.GROWTH)

        with patch(
            "app.services.company_service.CompanyEmailService.schedule_company_profile_updated_email",
            new_callable=AsyncMock,
        ) as mock_email:
            res = asyncio.run(
                service.update_company(company.id, payload, updated_by=updater)
            )

            assert res.name == "TechCorp Super AI"
            assert res.size == CompanySize.GROWTH
            session.commit.assert_awaited_once()

            # PO-1 & PO-2: Updater excluded; Admin and Interviewer notified
            created_calls = service.notifications.create_notification.call_args_list
            notified_ids = [c.kwargs["user_id"] for c in created_calls]
            assert updater_id not in notified_ids
            assert set(notified_ids) == {admin_id, interviewer_id}

            # PO-4: Updater attribution matches full name of updater member
            for c in created_calls:
                assert c.kwargs["title"] == "Thông tin công ty đã được cập nhật"
                assert "Lê Hoàng Nam" in c.kwargs["content"]
                assert c.kwargs["notification_type"] == "company_profile_updated"
                assert c.kwargs["entity_type"] == "company"
                assert c.kwargs["entity_id"] == company.id

            # Email outbox scheduling verified for eligible members
            emailed_ids = [c.kwargs["recipient_user_id"] for c in mock_email.call_args_list]
            assert updater_id not in emailed_ids
            assert set(emailed_ids) == {admin_id, interviewer_id}
            for c in mock_email.call_args_list:
                assert c.kwargs["updater_name"] == "Lê Hoàng Nam"
                assert "tên công ty" in c.kwargs["changed_fields_summary"]
                assert "quy mô" in c.kwargs["changed_fields_summary"]

    def test_platform_admin_attribution_in_notifications_and_emails(self):
        service, session = self._setup_service()
        company = _fake_company()
        service.companies.get_by_id.return_value = company

        platform_admin = _fake_user(UserRole.ADMIN, full_name="Super Admin")

        member_id = uuid.uuid4()
        member_user = _fake_user(UserRole.RECRUITER, user_id=member_id, full_name="Trần Văn Minh")

        memberships = [
            CompanyMembership(
                id=uuid.uuid4(),
                company_id=company.id,
                user_id=member_id,
                role=MembershipRole.ADMIN,
                status=MembershipStatus.ACTIVE,
                user=member_user,
            ),
        ]
        service.memberships.list_by_company.return_value = memberships

        payload = CompanyUpdate(tax_code="0987654321")
        service.companies.get_by_tax_code.return_value = None

        with patch(
            "app.services.company_service.CompanyEmailService.schedule_company_profile_updated_email",
            new_callable=AsyncMock,
        ) as mock_email:
            asyncio.run(
                service.update_company(company.id, payload, updated_by=platform_admin)
            )

            # PO-4: "Quản trị viên hệ thống" used instead of Super Admin personal name
            created_calls = service.notifications.create_notification.call_args_list
            assert len(created_calls) == 1
            call_content = created_calls[0].kwargs["content"]
            assert "Quản trị viên hệ thống" in call_content
            assert "Super Admin" not in call_content

            mock_email.assert_awaited_once()
            assert mock_email.call_args.kwargs["updater_name"] == "Quản trị viên hệ thống"

    def test_no_op_suppresses_notifications_and_emails(self):
        service, session = self._setup_service()
        company = _fake_company()
        service.companies.get_by_id.return_value = company

        # Exact same values
        payload = CompanyUpdate(
            name=company.name,
            slug=company.slug,
            tax_code=company.tax_code,
            size=company.size,
        )

        with patch(
            "app.services.company_service.CompanyEmailService.schedule_company_profile_updated_email",
            new_callable=AsyncMock,
        ) as mock_email:
            res = asyncio.run(
                service.update_company(company.id, payload)
            )

            assert res is company
            session.commit.assert_awaited_once()
            service.memberships.list_by_company.assert_not_awaited()
            service.notifications.create_notification.assert_not_awaited()
            mock_email.assert_not_awaited()

    def test_tenant_isolation_never_queries_or_notifies_other_company(self):
        service, session = self._setup_service()
        company_a = _fake_company()
        service.companies.get_by_id.return_value = company_a

        payload = CompanyUpdate(name="Company A New Name")
        asyncio.run(service.update_company(company_a.id, payload))

        # Confirm list_by_company was called strictly for company_a.id
        service.memberships.list_by_company.assert_awaited_once_with(
            company_a.id, include_revoked=False
        )
