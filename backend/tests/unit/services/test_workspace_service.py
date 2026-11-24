
import json
import asyncio
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
    InvalidTransitionException,
    ValidationError,
    WorkspaceRequiredException,
    WorkspaceSelectionRequiredException,
)
from app.database.base_class import utc_now
from app.domain.enums import (
    AdminAuditAction,
    InvitationStatus,
    MembershipRole,
    MembershipStatus,
    UserRole,
)
from app.models import (
    AdminAuditLog,
    Company,
    CompanyInvitation,
    CompanyMembership,
    Subscription,
    User,
)
from app.repositories import (
    CompanyInvitationRepository,
    CompanyMembershipRepository,
    CompanyRepository,
    UserRepository,
)
from app.schemas.workspace import InvitationCreate
from app.services.notification_service import NotificationService
from app.services.workspace_service import (
    WorkspaceService,
    hash_invitation_token,
)


def make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    session.begin_nested.return_value.__aenter__ = AsyncMock()
    session.begin_nested.return_value.__aexit__ = AsyncMock(return_value=False)
    return session


def make_company(
    company_id: uuid.UUID | None = None,
    *,
    name: str = "Acme Corp",
) -> Company:
    company = Company(
        id=company_id or uuid.uuid4(),
        name=name,
        slug="acme-corp",
        tax_code="123456789",
    )
    company.created_at = utc_now()
    company.updated_at = utc_now()
    return company


def make_user(
    user_id: uuid.UUID | None = None,
    *,
    email: str = "user@example.com",
    role: UserRole = UserRole.RECRUITER,
    is_active: bool = True,
) -> User:
    user = User(
        id=user_id or uuid.uuid4(),
        email=email,
        password_hash="hashed",
        role=role,
        is_active=is_active,
    )
    user.created_at = utc_now()
    user.updated_at = utc_now()
    return user


def make_membership(
    *,
    company: Company,
    user: User,
    role: MembershipRole = MembershipRole.RECRUITER,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> CompanyMembership:
    membership = CompanyMembership(
        id=uuid.uuid4(),
        company_id=company.id,
        user_id=user.id,
        role=role,
        status=status,
        joined_at=utc_now(),
    )
    membership.company = company
    membership.user = user
    membership.created_at = utc_now()
    membership.updated_at = utc_now()
    return membership


def make_invitation(
    *,
    company: Company,
    email: str = "invitee@example.com",
    token: str = "invitation-token-value-1234567890",
    status: InvitationStatus = InvitationStatus.PENDING,
    expires_at=None,
    role: MembershipRole = MembershipRole.RECRUITER,
) -> CompanyInvitation:
    invitation = CompanyInvitation(
        id=uuid.uuid4(),
        company_id=company.id,
        email=email,
        role=role,
        token_hash=hash_invitation_token(token),
        status=status,
        invited_by_id=uuid.uuid4(),
        expires_at=expires_at or (utc_now() + timedelta(days=7)),
    )
    invitation.company = company
    invitation.created_at = utc_now()
    invitation.updated_at = utc_now()
    return invitation


def make_service(session) -> WorkspaceService:
    service = WorkspaceService(session)
    service.memberships = AsyncMock(spec=CompanyMembershipRepository)
    service.invitations = AsyncMock(spec=CompanyInvitationRepository)
    service.invitations.conditional_accept.return_value = 1
    service.invitations.conditional_decline.return_value = 1
    service.invitations.conditional_revoke.return_value = 1
    service.invitations.get_pending_by_company_email.return_value = None
    service.memberships.get_active.return_value = None
    service.memberships.list_active_admins.return_value = []
    service.companies = AsyncMock(spec=CompanyRepository)
    service.users = AsyncMock(spec=UserRepository)
    service.notifications = AsyncMock(spec=NotificationService)
    return service


class TestResolveWorkspace:
    def test_invalid_header_uuid_raises_validation_error(self):
        service = make_service(make_session())

        with pytest.raises(ValidationError):
            asyncio.run(service.resolve(make_user(), "not-a-uuid"))

    def test_no_active_memberships_raises_workspace_required(self):
        service = make_service(make_session())
        service.memberships.list_active_for_user.return_value = []

        with pytest.raises(WorkspaceRequiredException):
            asyncio.run(service.resolve(make_user(), None))

    def test_single_membership_is_auto_selected(self):
        service = make_service(make_session())
        company = make_company()
        user = make_user()
        membership = make_membership(company=company, user=user)
        service.memberships.list_active_for_user.return_value = [membership]

        context = asyncio.run(service.resolve(user, None))

        assert context.company is company
        assert context.membership is membership
        assert context.role == MembershipRole.RECRUITER
        assert context.to_read().company_id == company.id

    def test_multiple_memberships_without_header_requires_selection(self):
        service = make_service(make_session())
        user = make_user()
        service.memberships.list_active_for_user.return_value = [
            make_membership(company=make_company(), user=user),
            make_membership(company=make_company(), user=user),
        ]

        with pytest.raises(WorkspaceSelectionRequiredException):
            asyncio.run(service.resolve(user, None))

    def test_explicit_header_selects_matching_active_membership(self):
        service = make_service(make_session())
        user = make_user()
        company = make_company()
        membership = make_membership(company=company, user=user)
        service.memberships.get_active.return_value = membership

        context = asyncio.run(service.resolve(user, str(company.id)))

        service.memberships.get_active.assert_awaited_once_with(
            user.id, company.id
        )
        assert context.company_id == company.id

    def test_explicit_header_without_membership_is_rejected(self):
        service = make_service(make_session())
        service.memberships.get_active.return_value = None

        with pytest.raises(WorkspaceRequiredException):
            asyncio.run(service.resolve(make_user(), str(uuid.uuid4())))

    def test_platform_admin_can_select_company_without_membership(self):
        service = make_service(make_session())
        admin = make_user(role=UserRole.ADMIN)
        company = make_company()
        service.memberships.get_active.return_value = None
        service.companies.get_by_id.return_value = company

        context = asyncio.run(service.resolve(admin, str(company.id)))

        assert context.is_platform_admin is True
        assert context.membership is None
        assert context.company_id == company.id
        assert context.is_company_admin is True

    def test_platform_admin_without_header_needs_selection(self):
        service = make_service(make_session())
        service.memberships.list_active_for_user.return_value = []

        with pytest.raises(WorkspaceSelectionRequiredException):
            asyncio.run(service.resolve(make_user(role=UserRole.ADMIN), None))

    def test_platform_admin_bypass_is_audited(self):
        session = make_session()
        service = make_service(session)
        admin = make_user(role=UserRole.ADMIN)
        company = make_company()
        service.memberships.get_active.return_value = None
        service.companies.get_by_id.return_value = company

        asyncio.run(service.resolve(admin, str(company.id)))

        session.add.assert_called_once()
        audit = session.add.call_args.args[0]
        assert isinstance(audit, AdminAuditLog)
        assert audit.admin_id == admin.id
        assert audit.target_user_id == admin.id
        assert audit.target_id == admin.id
        assert audit.target_type == "user"
        assert audit.action == AdminAuditAction.WORKSPACE_ACCESS
        assert audit.details == {
            "company_id": str(company.id),
            "company_slug": company.slug,
            "membership_id": None,
        }
        session.commit.assert_awaited_once()

    def test_platform_admin_with_membership_is_not_audited_as_bypass(self):
        session = make_session()
        service = make_service(session)
        admin = make_user(role=UserRole.ADMIN)
        company = make_company()
        membership = make_membership(company=company, user=admin)
        service.memberships.get_active.return_value = membership

        asyncio.run(service.resolve(admin, str(company.id)))

        session.add.assert_not_called()
        session.commit.assert_not_awaited()


class TestListWorkspaces:
    def test_recruiter_sees_only_active_memberships(self):
        service = make_service(make_session())
        user = make_user()
        first = make_membership(company=make_company(), user=user)
        second = make_membership(company=make_company(), user=user)
        service.memberships.list_active_for_user.return_value = [
            first,
            second,
        ]

        result = asyncio.run(service.list_workspaces(user))

        assert {item.company_id for item in result} == {
            first.company_id,
            second.company_id,
        }
        assert all(item.is_platform_admin is False for item in result)

    def test_platform_admin_sees_all_companies(self):
        service = make_service(make_session())
        admin = make_user(role=UserRole.ADMIN)
        companies = [make_company(), make_company()]
        membership = make_membership(company=companies[0], user=admin)
        service.companies.list_all.return_value = companies
        service.memberships.list_active_for_user.return_value = [membership]

        result = asyncio.run(service.list_workspaces(admin))

        assert [item.company_id for item in result] == [
            companies[0].id,
            companies[1].id,
        ]
        assert result[0].role == MembershipRole.RECRUITER
        assert result[1].role is None
        assert all(item.is_platform_admin for item in result)


class TestListMembers:
    def test_interviewer_cannot_list_members(self):
        service = make_service(make_session())
        user = make_user()
        company = make_company()
        context = service_context(
            company, user, role=MembershipRole.INTERVIEWER
        )

        with pytest.raises(ForbiddenException):
            asyncio.run(service.list_members(context))

    def test_recruiter_lists_members_read_only(self):
        service = make_service(make_session())
        user = make_user()
        member = make_user(email="member@example.com")
        company = make_company()
        context = service_context(
            company, user, role=MembershipRole.RECRUITER
        )
        membership = make_membership(company=company, user=member)
        service.memberships.list_by_company.return_value = [membership]

        result = asyncio.run(service.list_members(context))

        assert result[0].user_id == member.id

    def test_admin_lists_members_with_profiles(self):
        service = make_service(make_session())
        admin = make_user(role=UserRole.RECRUITER)
        member = make_user(email="member@example.com")
        company = make_company()
        context = service_context(
            company, admin, role=MembershipRole.ADMIN
        )
        membership = make_membership(company=company, user=member)
        service.memberships.list_by_company.return_value = [membership]

        result = asyncio.run(service.list_members(context))

        assert result[0].user_id == member.id
        assert result[0].email == "member@example.com"

    def test_list_members_respects_include_revoked(self):
        service = make_service(make_session())
        admin = make_user(role=UserRole.RECRUITER)
        company = make_company()
        context = service_context(company, admin, role=MembershipRole.ADMIN)
        service.memberships.list_by_company.return_value = []

        asyncio.run(service.list_members(context, include_revoked=False))
        service.memberships.list_by_company.assert_awaited_once_with(
            context.company_id,
            include_revoked=False,
        )


class TestCreateInvitation:
    def test_creates_pending_invitation_and_enqueues_email(self):
        session = make_session()
        service = make_service(session)
        admin = make_user(role=UserRole.RECRUITER)
        company = make_company()
        context = service_context(
            company, admin, role=MembershipRole.ADMIN
        )
        service.invitations.expire_stale.return_value = 0
        service.users.get_by_email.return_value = make_user(
            email="invitee@example.com", is_active=True
        )
        service.memberships.get_active.return_value = None
        service.invitations.get_pending_by_company_email.return_value = None

        captured = {}

        def assign_defaults():
            invitation = session.add.call_args.args[0]
            invitation.id = uuid.uuid4()
            invitation.created_at = utc_now()
            invitation.updated_at = utc_now()
            captured["invitation"] = invitation

        session.flush.side_effect = assign_defaults

        with patch(
            "app.services.workspace_service.enqueue_email",
            new=AsyncMock(),
        ) as enqueue:
            result = asyncio.run(
                service.create_invitation(
                    context,
                    InvitationCreate(email="  Invitee@Example.COM "),
                )
            )

        invitation = captured["invitation"]
        assert invitation.email == "invitee@example.com"
        assert invitation.status == InvitationStatus.PENDING
        assert invitation.token_hash != "invitee@example.com"
        assert len(invitation.token_hash) == 64
        assert result.email == "invitee@example.com"
        enqueue.assert_awaited_once()
        email_kwargs = enqueue.await_args.kwargs
        assert email_kwargs["event_type"] == "company_invitation"
        assert email_kwargs["to_email"] == "invitee@example.com"
        assert "Lời mời tham gia công ty" in email_kwargs["subject"]
        assert "Chấp nhận lời mời" in email_kwargs["html_body"]
        assert "Từ chối lời mời" in email_kwargs["html_body"]
        assert "(GMT+7)" in email_kwargs["html_body"]
        assert "#token=" in email_kwargs["text_body"]
        assert "(GMT+7)" in email_kwargs["text_body"]
        session.commit.assert_awaited_once()

    def test_unknown_account_raises_entity_not_found(self):
        session = make_session()
        service = make_service(session)
        admin = make_user()
        company = make_company()
        context = service_context(
            company, admin, role=MembershipRole.ADMIN
        )
        service.invitations.expire_stale.return_value = 0
        service.users.get_by_email.return_value = None

        with patch("app.services.workspace_service.enqueue_email", new=AsyncMock()) as mock_enqueue:
            with pytest.raises(EntityNotFoundException) as exc_info:
                asyncio.run(
                    service.create_invitation(
                        context,
                        InvitationCreate(email="unknown@example.com"),
                    )
                )
            assert "Tài khoản với email này không tồn tại trong hệ thống." in str(exc_info.value)
            session.add.assert_not_called()
            mock_enqueue.assert_not_called()
            service.notifications.notify_company_invitation.assert_not_called()

    def test_inactive_account_raises_forbidden(self):
        session = make_session()
        service = make_service(session)
        admin = make_user()
        company = make_company()
        context = service_context(
            company, admin, role=MembershipRole.ADMIN
        )
        service.invitations.expire_stale.return_value = 0
        service.users.get_by_email.return_value = make_user(
            email="locked@example.com", is_active=False
        )

        with patch("app.services.workspace_service.enqueue_email", new=AsyncMock()) as mock_enqueue:
            with pytest.raises(ForbiddenException) as exc_info:
                asyncio.run(
                    service.create_invitation(
                        context,
                        InvitationCreate(email="locked@example.com"),
                    )
                )
            assert "Tài khoản này đang bị khóa và không thể nhận lời mời." in str(exc_info.value)
            session.add.assert_not_called()
            mock_enqueue.assert_not_called()
            service.notifications.notify_company_invitation.assert_not_called()

    def test_soft_deleted_account_raises_entity_not_found(self):
        session = make_session()
        service = make_service(session)
        admin = make_user()
        company = make_company()
        context = service_context(
            company, admin, role=MembershipRole.ADMIN
        )
        service.invitations.expire_stale.return_value = 0
        # UserRepository.get_by_email returns None for is_deleted=True
        service.users.get_by_email.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(
                service.create_invitation(
                    context,
                    InvitationCreate(email="deleted@example.com"),
                )
            )
        session.add.assert_not_called()

    def test_existing_active_member_conflicts(self):
        service = make_service(make_session())
        admin = make_user()
        company = make_company()
        context = service_context(
            company, admin, role=MembershipRole.ADMIN
        )
        service.invitations.expire_stale.return_value = 0
        service.users.get_by_email.return_value = make_user(
            email="member@example.com", is_active=True
        )
        service.memberships.get_active.return_value = MagicMock()

        with pytest.raises(ConflictException):
            asyncio.run(
                service.create_invitation(
                    context,
                    InvitationCreate(email="member@example.com"),
                )
            )

    def test_duplicate_pending_invitation_conflicts(self):
        service = make_service(make_session())
        admin = make_user()
        company = make_company()
        context = service_context(
            company, admin, role=MembershipRole.ADMIN
        )
        service.invitations.expire_stale.return_value = 0
        service.users.get_by_email.return_value = make_user(
            email="invitee@example.com", is_active=True
        )
        service.memberships.get_active.return_value = None
        service.invitations.get_pending_by_company_email.return_value = (
            MagicMock()
        )

        with pytest.raises(ConflictException):
            asyncio.run(
                service.create_invitation(
                    context,
                    InvitationCreate(email="invitee@example.com"),
                )
            )

    def test_non_admin_cannot_invite(self):
        service = make_service(make_session())
        context = service_context(make_company(), make_user())

        with pytest.raises(ForbiddenException):
            asyncio.run(
                service.create_invitation(
                    context,
                    InvitationCreate(email="invitee@example.com"),
                )
            )

    def test_invitation_email_vietnamese_content_and_gmt7_formatting(self):
        session = make_session()
        service = make_service(session)
        admin = make_user(email="admin@company.com", role=UserRole.RECRUITER)
        company = make_company(name="Cong Ty Cong Nghe")
        context = service_context(company, admin, role=MembershipRole.ADMIN)

        service.invitations.expire_stale.return_value = 0
        service.users.get_by_email.return_value = make_user(
            email="developer@example.com", is_active=True
        )
        service.memberships.get_active.return_value = None
        service.invitations.get_pending_by_company_email.return_value = None

        def assign_defaults():
            invitation = session.add.call_args.args[0]
            invitation.id = uuid.uuid4()
            invitation.created_at = utc_now()
            invitation.updated_at = utc_now()

        session.flush.side_effect = assign_defaults

        with patch("app.services.workspace_service.enqueue_email", new=AsyncMock()) as mock_enqueue:
            asyncio.run(
                service.create_invitation(
                    context,
                    InvitationCreate(email="developer@example.com", role=MembershipRole.INTERVIEWER),
                )
            )
            mock_enqueue.assert_awaited_once()
            kwargs = mock_enqueue.await_args.kwargs
            assert kwargs["subject"] == "Lời mời tham gia công ty Cong Ty Cong Nghe - AI Recruitment Platform"
            assert "Người phỏng vấn" in kwargs["html_body"]
            assert "Người phỏng vấn" in kwargs["text_body"]
            assert "Cong Ty Cong Nghe" in kwargs["html_body"]
            assert "admin@company.com" in kwargs["html_body"]
            assert "developer@example.com" in kwargs["html_body"]
            assert "(GMT+7)" in kwargs["html_body"]
            assert "Chấp nhận lời mời" in kwargs["html_body"]
            assert "Từ chối lời mời" in kwargs["html_body"]
            assert "action=accept" in kwargs["html_body"]
            assert "action=decline" in kwargs["html_body"]
            assert "Liên kết lời mời này chỉ có hiệu lực một lần" in kwargs["html_body"]
            assert "Email được gửi tự động từ AI Recruitment Platform." in kwargs["html_body"]

    def test_invitation_email_html_escaping(self):
        session = make_session()
        service = make_service(session)
        admin = make_user(email="<script>alert(1)</script>@company.com", role=UserRole.RECRUITER)
        company = make_company(name="<Evil & Sons Ltd>")
        context = service_context(company, admin, role=MembershipRole.ADMIN)

        service.invitations.expire_stale.return_value = 0
        service.users.get_by_email.return_value = make_user(
            email="innocent@example.com", is_active=True
        )
        service.memberships.get_active.return_value = None
        service.invitations.get_pending_by_company_email.return_value = None

        def assign_defaults():
            invitation = session.add.call_args.args[0]
            invitation.id = uuid.uuid4()
            invitation.created_at = utc_now()
            invitation.updated_at = utc_now()

        session.flush.side_effect = assign_defaults

        with patch("app.services.workspace_service.enqueue_email", new=AsyncMock()) as mock_enqueue:
            asyncio.run(
                service.create_invitation(
                    context,
                    InvitationCreate(email="innocent@example.com", role=MembershipRole.ADMIN),
                )
            )
            mock_enqueue.assert_awaited_once()
            kwargs = mock_enqueue.await_args.kwargs
            assert "<Evil & Sons Ltd>" not in kwargs["html_body"]
            assert "&lt;Evil &amp; Sons Ltd&gt;" in kwargs["html_body"]
            assert "<script>alert(1)</script>" not in kwargs["html_body"]
            assert "&lt;script&gt;alert(1)&lt;/script&gt;" in kwargs["html_body"]
            assert "Quản trị viên" in kwargs["html_body"]


class TestPreviewInvitation:
    def test_unknown_token_raises_not_found(self):
        service = make_service(make_session())
        service.invitations.get_by_token_hash.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.preview_invitation("missing-token-value-123456"))

    def test_pending_invitation_preview_masks_email(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        token = "invitation-token-value-1234567890"
        invitation = make_invitation(
            company=company,
            email="invitee@example.com",
            token=token,
        )
        service.invitations.get_by_token_hash.return_value = invitation

        result = asyncio.run(service.preview_invitation(token))

        assert result.company_name == "Acme Corp"
        assert result.email_masked == "i***@example.com"
        assert result.can_accept is True
        session.commit.assert_not_awaited()

    def test_expired_pending_invitation_is_marked_expired(self):
        session = make_session()
        service = make_service(session)
        invitation = make_invitation(
            company=make_company(),
            expires_at=utc_now() - timedelta(minutes=1),
        )
        service.invitations.get_by_token_hash.return_value = invitation

        result = asyncio.run(
            service.preview_invitation(
                "invitation-token-value-1234567890"
            )
        )

        assert result.can_accept is False
        assert invitation.status == InvitationStatus.EXPIRED
        session.commit.assert_awaited_once()


class TestAcceptInvitation:
    def test_accept_creates_membership_and_updates_legacy_profile(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        user = make_user(email="Invitee@Example.com")
        token = "invitation-token-value-1234567890"
        invitation = make_invitation(
            company=company,
            email="invitee@example.com",
            token=token,
            role=MembershipRole.ADMIN,
        )
        service.invitations.get_by_token_hash_for_update.return_value = (
            invitation
        )
        service.companies.get_by_id.return_value = company
        service.memberships.get_active.return_value = None

        def assign_defaults():
            membership = session.add.call_args.args[0]
            membership.id = uuid.uuid4()
            membership.created_at = utc_now()
            membership.updated_at = utc_now()

        session.flush.side_effect = assign_defaults

        result = asyncio.run(service.accept_invitation(user, token))

        assert result.workspace.company_id == company.id
        assert result.workspace.role == MembershipRole.ADMIN
        assert invitation.status == InvitationStatus.ACCEPTED
        assert invitation.accepted_at is not None
        session.commit.assert_awaited_once()
        assert session.execute.await_count == 1

    def test_accept_invitation_does_not_provision_or_modify_subscriptions(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        user = make_user(email="invitee@example.com")
        token = "invitation-token-value-1234567890"
        invitation = make_invitation(
            company=company,
            email="invitee@example.com",
            token=token,
            role=MembershipRole.RECRUITER,
        )
        service.invitations.get_by_token_hash_for_update.return_value = invitation
        service.companies.get_by_id.return_value = company
        service.memberships.get_active.return_value = None

        def assign_defaults():
            membership = session.add.call_args.args[0]
            membership.id = uuid.uuid4()
            membership.created_at = utc_now()
            membership.updated_at = utc_now()

        session.flush.side_effect = assign_defaults

        with patch(
            "app.services.company_entitlement_service.CompanyEntitlementService.provision_company_free_subscription",
            new_callable=AsyncMock,
        ) as mock_provision:
            result = asyncio.run(service.accept_invitation(user, token))

            # 1. Invitation is accepted
            assert invitation.status == InvitationStatus.ACCEPTED
            assert invitation.accepted_at is not None

            # 2. Invitee CompanyMembership is created for the invitation's company
            assert result.workspace.company_id == company.id
            added_memberships = [
                call.args[0]
                for call in session.add.call_args_list
                if isinstance(call.args[0], CompanyMembership)
            ]
            assert len(added_memberships) == 1
            membership = added_memberships[0]
            assert membership.company_id == company.id
            assert membership.user_id == user.id

            # 3. Invitee role and membership status are preserved
            assert membership.role == MembershipRole.RECRUITER
            assert membership.status == MembershipStatus.ACTIVE
            assert result.workspace.role == MembershipRole.RECRUITER

            # 4. RecruiterProfile is associated with the invited company where applicable
            assert session.execute.await_count == 1

            # 5. No Subscription ORM instance is added to the session
            added_objects = [call.args[0] for call in session.add.call_args_list]
            assert not any(isinstance(obj, Subscription) for obj in added_objects)
            assert all(isinstance(obj, CompanyMembership) for obj in added_objects)

            # 6. No new company entitlement provisioning operation is invoked
            mock_provision.assert_not_called()

            # 7. Session committed once, no rollback
            session.commit.assert_awaited_once()
            session.rollback.assert_not_awaited()

    def test_wrong_email_is_forbidden(self):
        service = make_service(make_session())
        invitation = make_invitation(
            company=make_company(),
            email="invitee@example.com",
        )
        service.invitations.get_by_token_hash_for_update.return_value = (
            invitation
        )

        with pytest.raises(ForbiddenException):
            asyncio.run(
                service.accept_invitation(
                    make_user(email="other@example.com"),
                    "invitation-token-value-1234567890",
                )
            )

    def test_non_pending_invitation_is_invalid_transition(self):
        service = make_service(make_session())
        invitation = make_invitation(
            company=make_company(),
            status=InvitationStatus.REVOKED,
        )
        service.invitations.get_by_token_hash_for_update.return_value = (
            invitation
        )

        with pytest.raises(InvalidTransitionException):
            asyncio.run(
                service.accept_invitation(
                    make_user(email="invitee@example.com"),
                    "invitation-token-value-1234567890",
                )
            )

    def test_expired_invitation_is_marked_expired(self):
        session = make_session()
        service = make_service(session)
        invitation = make_invitation(
            company=make_company(),
            expires_at=utc_now() - timedelta(minutes=1),
        )
        service.invitations.get_by_token_hash_for_update.return_value = (
            invitation
        )

        with pytest.raises(InvalidTransitionException):
            asyncio.run(
                service.accept_invitation(
                    make_user(email="invitee@example.com"),
                    "invitation-token-value-1234567890",
                )
            )

        assert invitation.status == InvitationStatus.EXPIRED
        session.commit.assert_awaited_once()

    def test_existing_member_conflicts(self):
        service = make_service(make_session())
        company = make_company()
        invitation = make_invitation(
            company=company,
            email="invitee@example.com",
        )
        service.invitations.get_by_token_hash_for_update.return_value = (
            invitation
        )
        service.companies.get_by_id.return_value = company
        service.memberships.get_active.return_value = MagicMock()

        with pytest.raises(ConflictException):
            asyncio.run(
                service.accept_invitation(
                    make_user(email="invitee@example.com"),
                    "invitation-token-value-1234567890",
                )
            )


class TestRevokeInvitation:
    def test_non_admin_cannot_revoke(self):
        service = make_service(make_session())
        context = service_context(make_company(), make_user())

        with pytest.raises(ForbiddenException):
            asyncio.run(service.revoke_invitation(context, uuid.uuid4()))

    def test_revokes_pending_invitation(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        context = service_context(
            company, make_user(), role=MembershipRole.ADMIN
        )
        invitation = make_invitation(company=company)
        service.invitations.get_by_company.return_value = invitation

        result = asyncio.run(
            service.revoke_invitation(context, invitation.id)
        )

        assert result.status == InvitationStatus.REVOKED
        assert invitation.revoked_at is not None
        session.commit.assert_awaited_once()

    def test_cross_company_invitation_is_not_found(self):
        service = make_service(make_session())
        context = service_context(
            make_company(), make_user(), role=MembershipRole.ADMIN
        )
        service.invitations.get_by_company.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.revoke_invitation(context, uuid.uuid4()))


class TestRevokeMembership:
    def test_last_admin_cannot_be_revoked(self):
        session = make_session()
        lock_result = MagicMock()
        lock_result.scalar_one.return_value = 0
        session.execute.return_value = lock_result
        service = make_service(session)
        company = make_company()
        admin = make_user()
        context = service_context(
            company, admin, role=MembershipRole.ADMIN
        )
        target = make_membership(
            company=company,
            user=admin,
            role=MembershipRole.ADMIN,
        )
        service.memberships.get_active.return_value = context.membership
        service.memberships.get_by_id_with_user.return_value = target
        service.memberships.count_active_admins.return_value = 1

        with pytest.raises(ConflictException):
            asyncio.run(
                service.revoke_membership(context, target.id)
            )

        session.commit.assert_not_awaited()

    def test_cross_company_membership_is_not_found(self):
        session = make_session()
        lock_result = MagicMock()
        lock_result.scalar_one.return_value = 0
        session.execute.return_value = lock_result
        service = make_service(session)
        context = service_context(
            make_company(), make_user(), role=MembershipRole.ADMIN
        )
        target = make_membership(
            company=make_company(), user=make_user()
        )
        service.memberships.get_active.return_value = context.membership
        service.memberships.get_by_id_with_user.return_value = target

        with pytest.raises(EntityNotFoundException):
            asyncio.run(
                service.revoke_membership(context, target.id)
            )

    def test_admin_may_revoke_self_when_another_admin_exists(self):
        session = make_session()
        lock_result = MagicMock()
        lock_result.scalar_one.return_value = 0
        session.execute.return_value = lock_result
        service = make_service(session)
        company = make_company()
        admin = make_user()
        context = service_context(
            company, admin, role=MembershipRole.ADMIN
        )
        target = make_membership(
            company=company,
            user=admin,
            role=MembershipRole.ADMIN,
        )
        service.memberships.get_active.return_value = context.membership
        service.memberships.get_by_id_with_user.return_value = target
        service.memberships.count_active_admins.return_value = 2

        with patch(
            "app.services.workspace_service.TransactionActionManager"
        ) as tam_mock:
            result = asyncio.run(
                service.revoke_membership(context, target.id)
            )

        assert result.status == MembershipStatus.REVOKED
        assert target.revoked_by_id == admin.id
        assert target.revoked_at is not None
        session.commit.assert_awaited_once()
        tam_mock.register_action.assert_called_once()

    def test_revoke_membership_soft_deletes_active_interview_assignments(self):
        session = make_session()
        lock_result = MagicMock()
        lock_result.scalar_one.return_value = 0
        session.execute.return_value = lock_result
        service = make_service(session)
        company = make_company()
        admin = make_user()
        member_user = make_user()
        context = service_context(
            company, admin, role=MembershipRole.ADMIN
        )
        target = make_membership(
            company=company,
            user=member_user,
            role=MembershipRole.INTERVIEWER,
        )
        service.memberships.get_active.return_value = context.membership
        service.memberships.get_by_id_with_user.return_value = target

        with patch(
            "app.services.workspace_service.TransactionActionManager"
        ) as tam_mock:
            result = asyncio.run(
                service.revoke_membership(context, target.id)
            )

        assert result.status == MembershipStatus.REVOKED
        session.commit.assert_awaited_once()
        tam_mock.register_action.assert_called_once()
        # session.execute is called: lock (1), RecruiterProfile update (2), InterviewAssignment update (3)
        assert session.execute.await_count >= 3

    def test_stale_admin_context_is_rejected_after_lock(self):
        session = make_session()
        lock_result = MagicMock()
        lock_result.scalar_one.return_value = 0
        session.execute.return_value = lock_result
        service = make_service(session)
        context = service_context(
            make_company(), make_user(), role=MembershipRole.ADMIN
        )
        service.memberships.get_active.return_value = None

        with pytest.raises(ConflictException, match="no longer active"):
            asyncio.run(
                service.revoke_membership(context, uuid.uuid4())
            )

        service.memberships.get_by_id_with_user.assert_not_awaited()
        session.commit.assert_not_awaited()

    def test_lock_failure_fails_closed(self):
        session = make_session()
        lock_result = MagicMock()
        lock_result.scalar_one.return_value = -1
        session.execute.return_value = lock_result
        service = make_service(session)
        context = service_context(
            make_company(), make_user(), role=MembershipRole.ADMIN
        )

        with pytest.raises(ConflictException):
            asyncio.run(
                service.revoke_membership(context, uuid.uuid4())
            )

    def test_revoke_membership_creates_notification_and_enqueues_email(self):
        session = make_session()
        lock_result = MagicMock()
        lock_result.scalar_one.return_value = 0
        session.execute.return_value = lock_result
        service = make_service(session)
        company = make_company(name="Acme Corp")
        admin = make_user(email="admin@acme.com")
        member_user = make_user(email="worker@acme.com")
        context = service_context(company, admin, role=MembershipRole.ADMIN)
        target = make_membership(
            company=company,
            user=member_user,
            role=MembershipRole.RECRUITER,
        )
        other_membership = make_membership(
            company=make_company(name="Other Co"),
            user=member_user,
            role=MembershipRole.RECRUITER,
        )
        service.memberships.get_active.return_value = context.membership
        service.memberships.get_by_id_with_user.return_value = target
        service.memberships.list_active_for_user.return_value = [
            target,
            other_membership,
        ]

        with patch("app.services.workspace_service.enqueue_email", new_callable=AsyncMock) as mock_enqueue, \
             patch("app.services.workspace_service.signal_dispatch_after_commit") as mock_signal, \
             patch("app.services.workspace_service.TransactionActionManager"):
            result = asyncio.run(service.revoke_membership(context, target.id))

        assert result.status == MembershipStatus.REVOKED
        service.notifications.notify_company_member_revoked.assert_awaited_once_with(
            user_id=target.user_id,
            membership_id=target.id,
            company_name="Acme Corp",
            role_label="Nhà tuyển dụng",
            has_other_active_memberships=True,
        )
        mock_enqueue.assert_awaited_once()
        email_kwargs = mock_enqueue.await_args.kwargs
        assert email_kwargs["event_type"] == "company_membership_revoked"
        assert email_kwargs["to_email"] == "worker@acme.com"
        assert email_kwargs["idempotency_key"] == f"company-membership-revoked:{target.id}"
        assert "[AI Recruitment Platform] Thông báo thu hồi quyền thành viên tại Acme Corp" in email_kwargs["subject"]
        assert "Nhà tuyển dụng" in email_kwargs["text_body"]
        assert "các không gian làm việc khác" in email_kwargs["text_body"]
        mock_signal.assert_called_once_with(session)
        session.commit.assert_awaited_once()

    def test_revoke_membership_without_remaining_memberships_informs_access_ended(self):
        session = make_session()
        lock_result = MagicMock()
        lock_result.scalar_one.return_value = 0
        session.execute.return_value = lock_result
        service = make_service(session)
        company = make_company(name="Acme Corp")
        admin = make_user(email="admin@acme.com")
        member_user = make_user(email="worker@acme.com")
        context = service_context(company, admin, role=MembershipRole.ADMIN)
        target = make_membership(
            company=company,
            user=member_user,
            role=MembershipRole.INTERVIEWER,
        )
        service.memberships.get_active.return_value = context.membership
        service.memberships.get_by_id_with_user.return_value = target
        service.memberships.list_active_for_user.return_value = [target]

        with patch("app.services.workspace_service.enqueue_email", new_callable=AsyncMock) as mock_enqueue, \
             patch("app.services.workspace_service.signal_dispatch_after_commit"), \
             patch("app.services.workspace_service.TransactionActionManager"):
            result = asyncio.run(service.revoke_membership(context, target.id))

        assert result.status == MembershipStatus.REVOKED
        service.notifications.notify_company_member_revoked.assert_awaited_once_with(
            user_id=target.user_id,
            membership_id=target.id,
            company_name="Acme Corp",
            role_label="Người phỏng vấn",
            has_other_active_memberships=False,
        )
        email_kwargs = mock_enqueue.await_args.kwargs
        assert "không gian làm việc này đã kết thúc" in email_kwargs["text_body"]
        assert "bị khóa" not in email_kwargs["text_body"]

    def test_revoke_membership_non_active_raises_invalid_transition(self):
        session = make_session()
        lock_result = MagicMock()
        lock_result.scalar_one.return_value = 0
        session.execute.return_value = lock_result
        service = make_service(session)
        company = make_company()
        admin = make_user()
        context = service_context(company, admin, role=MembershipRole.ADMIN)
        target = make_membership(
            company=company,
            user=make_user(),
            status=MembershipStatus.REVOKED,
        )
        service.memberships.get_active.return_value = context.membership
        service.memberships.get_by_id_with_user.return_value = target

        with pytest.raises(InvalidTransitionException, match="not active"):
            asyncio.run(service.revoke_membership(context, target.id))

        session.commit.assert_not_awaited()
        service.notifications.notify_company_member_revoked.assert_not_awaited()


class TestUpdateMembershipRole:
    def test_non_admin_cannot_change_role(self):
        session = make_session()
        service = make_service(session)
        context = service_context(
            make_company(), make_user(), role=MembershipRole.RECRUITER
        )

        with pytest.raises(ForbiddenException):
            asyncio.run(
                service.update_membership_role(
                    context, uuid.uuid4(), MembershipRole.INTERVIEWER
                )
            )

        session.execute.assert_not_awaited()
        session.commit.assert_not_awaited()

    def test_last_admin_cannot_be_demoted(self):
        session = make_session()
        lock_result = MagicMock()
        lock_result.scalar_one.return_value = 0
        session.execute.return_value = lock_result
        service = make_service(session)
        company = make_company()
        admin = make_user()
        context = service_context(
            company, admin, role=MembershipRole.ADMIN
        )
        target = make_membership(
            company=company,
            user=admin,
            role=MembershipRole.ADMIN,
        )
        service.memberships.get_active.return_value = context.membership
        service.memberships.get_by_id_with_user.return_value = target
        service.memberships.count_active_admins.return_value = 1

        with pytest.raises(ConflictException, match="last active"):
            asyncio.run(
                service.update_membership_role(
                    context, target.id, MembershipRole.RECRUITER
                )
            )

        assert target.role == MembershipRole.ADMIN
        session.commit.assert_not_awaited()

    def test_admin_can_demote_admin_when_another_remains(self):
        session = make_session()
        lock_result = MagicMock()
        lock_result.scalar_one.return_value = 0
        session.execute.return_value = lock_result
        service = make_service(session)
        company = make_company()
        admin = make_user()
        target_user = make_user(email="target@example.com")
        context = service_context(
            company, admin, role=MembershipRole.ADMIN
        )
        target = make_membership(
            company=company,
            user=target_user,
            role=MembershipRole.ADMIN,
        )
        service.memberships.get_active.return_value = context.membership
        service.memberships.get_by_id_with_user.return_value = target
        service.memberships.count_active_admins.return_value = 2

        result = asyncio.run(
            service.update_membership_role(
                context, target.id, MembershipRole.INTERVIEWER
            )
        )

        assert result.role == MembershipRole.INTERVIEWER
        assert target.role == MembershipRole.INTERVIEWER
        session.commit.assert_awaited_once()

    def test_cross_company_membership_is_not_found(self):
        session = make_session()
        lock_result = MagicMock()
        lock_result.scalar_one.return_value = 0
        session.execute.return_value = lock_result
        service = make_service(session)
        context = service_context(
            make_company(), make_user(), role=MembershipRole.ADMIN
        )
        target = make_membership(
            company=make_company(), user=make_user()
        )
        service.memberships.get_active.return_value = context.membership
        service.memberships.get_by_id_with_user.return_value = target

        with pytest.raises(EntityNotFoundException):
            asyncio.run(
                service.update_membership_role(
                    context, target.id, MembershipRole.INTERVIEWER
                )
            )

        session.commit.assert_not_awaited()

    def test_stale_admin_context_is_rejected_after_lock(self):
        session = make_session()
        lock_result = MagicMock()
        lock_result.scalar_one.return_value = 0
        session.execute.return_value = lock_result
        service = make_service(session)
        context = service_context(
            make_company(), make_user(), role=MembershipRole.ADMIN
        )
        service.memberships.get_active.return_value = None

        with pytest.raises(ConflictException, match="no longer active"):
            asyncio.run(
                service.update_membership_role(
                    context, uuid.uuid4(), MembershipRole.INTERVIEWER
                )
            )

        service.memberships.get_by_id_with_user.assert_not_awaited()
        session.commit.assert_not_awaited()


def service_context(
    company: Company,
    user: User,
    *,
    role: MembershipRole = MembershipRole.RECRUITER,
):
    from app.services.workspace_service import WorkspaceContext

    membership = make_membership(company=company, user=user, role=role)
    return WorkspaceContext(
        user=user,
        company=company,
        membership=membership,
    )


class TestListMyInvitations:
    def test_list_my_invitations_returns_pending_for_user(self):
        service = make_service(make_session())
        company = make_company()
        user = make_user(email="Candidate@Example.com")
        invitation = make_invitation(
            company=company,
            email="candidate@example.com",
            role=MembershipRole.RECRUITER,
        )
        service.invitations.list_pending_by_email.return_value = [invitation]

        result = asyncio.run(service.list_my_invitations(user))

        service.invitations.list_pending_by_email.assert_awaited_once()
        assert service.invitations.list_pending_by_email.await_args.args[0] == "candidate@example.com"
        assert len(result) == 1
        assert result[0].id == invitation.id
        assert result[0].company_name == company.name
        assert result[0].role == MembershipRole.RECRUITER
        assert result[0].status == InvitationStatus.PENDING


class TestAcceptMyInvitation:
    def test_accept_my_invitation_success(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        user = make_user(email="invitee@example.com")
        invitation = make_invitation(
            company=company,
            email="invitee@example.com",
            role=MembershipRole.INTERVIEWER,
        )
        service.invitations.get_by_id_with_company.return_value = invitation
        service.companies.get_by_id.return_value = company
        service.memberships.get_active.return_value = None

        def assign_defaults():
            if session.add.call_args:
                membership = session.add.call_args.args[0]
                membership.id = uuid.uuid4()
                membership.created_at = utc_now()
                membership.updated_at = utc_now()

        session.flush.side_effect = assign_defaults

        result = asyncio.run(
            service.accept_my_invitation(user, invitation.id)
        )

        assert result.workspace.company_id == company.id
        assert result.workspace.role == MembershipRole.INTERVIEWER
        assert invitation.status == InvitationStatus.ACCEPTED
        assert invitation.accepted_at is not None
        session.commit.assert_awaited_once()
        service.notifications.mark_invitation_notification_read.assert_awaited_once_with(
            user.id, invitation.id
        )

    def test_accept_my_invitation_not_found_raises_entity_not_found(self):
        service = make_service(make_session())
        user = make_user(email="invitee@example.com")
        service.invitations.get_by_id_with_company.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.accept_my_invitation(user, uuid.uuid4()))

    def test_accept_my_invitation_wrong_email_raises_forbidden(self):
        service = make_service(make_session())
        company = make_company()
        user = make_user(email="other@example.com")
        invitation = make_invitation(
            company=company,
            email="invitee@example.com",
        )
        service.invitations.get_by_id_with_company.return_value = invitation

        with pytest.raises(ForbiddenException):
            asyncio.run(service.accept_my_invitation(user, invitation.id))

    def test_accept_my_invitation_concurrency_conflict_raises_conflict(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        user = make_user(email="invitee@example.com")
        invitation = make_invitation(
            company=company,
            email="invitee@example.com",
        )
        service.invitations.get_by_id_with_company.return_value = invitation
        service.companies.get_by_id.return_value = company
        service.memberships.get_active.return_value = None
        service.invitations.conditional_accept.return_value = 0

        with pytest.raises(ConflictException, match="no longer pending"):
            asyncio.run(service.accept_my_invitation(user, invitation.id))


class TestDeclineInvitation:
    def test_decline_by_token_success(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        user = make_user(email="Invitee@Example.com")
        token = "token-secret-12345"
        invitation = make_invitation(
            company=company,
            email="invitee@example.com",
            token=token,
        )
        service.invitations.get_by_token_hash.return_value = invitation

        result = asyncio.run(service.decline_invitation(user, token))

        assert result.invitation_id == invitation.id
        assert result.status == InvitationStatus.DECLINED
        assert invitation.status == InvitationStatus.DECLINED
        assert invitation.declined_at is not None
        session.commit.assert_awaited_once()
        service.notifications.mark_invitation_notification_read.assert_awaited_once_with(
            user.id, invitation.id
        )

    def test_decline_my_invitation_success(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        user = make_user(email="invitee@example.com")
        invitation = make_invitation(
            company=company,
            email="invitee@example.com",
        )
        service.invitations.get_by_id_with_company.return_value = invitation

        result = asyncio.run(
            service.decline_my_invitation(user, invitation.id)
        )

        assert result.invitation_id == invitation.id
        assert result.status == InvitationStatus.DECLINED
        assert invitation.status == InvitationStatus.DECLINED
        assert invitation.declined_at is not None
        session.commit.assert_awaited_once()

    def test_decline_wrong_email_raises_forbidden(self):
        service = make_service(make_session())
        company = make_company()
        user = make_user(email="different@example.com")
        invitation = make_invitation(
            company=company,
            email="invitee@example.com",
        )
        service.invitations.get_by_id_with_company.return_value = invitation

        with pytest.raises(ForbiddenException):
            asyncio.run(service.decline_my_invitation(user, invitation.id))

    def test_decline_already_declined_raises_invalid_transition(self):
        service = make_service(make_session())
        company = make_company()
        user = make_user(email="invitee@example.com")
        invitation = make_invitation(
            company=company,
            email="invitee@example.com",
            status=InvitationStatus.DECLINED,
        )
        service.invitations.get_by_id_with_company.return_value = invitation

        with pytest.raises(InvalidTransitionException):
            asyncio.run(service.decline_my_invitation(user, invitation.id))

    def test_decline_concurrency_conflict_raises_conflict(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        user = make_user(email="invitee@example.com")
        invitation = make_invitation(
            company=company,
            email="invitee@example.com",
        )
        service.invitations.get_by_id_with_company.return_value = invitation
        service.invitations.conditional_decline.return_value = 0

        with pytest.raises(ConflictException, match="no longer pending"):
            asyncio.run(service.decline_my_invitation(user, invitation.id))


class TestRevokeInvitationConcurrency:
    def test_revoke_concurrency_conflict_raises_invalid_transition(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        user = make_user()
        context = service_context(company, user, role=MembershipRole.ADMIN)
        invitation = make_invitation(company=company)
        service.invitations.get_by_company.return_value = invitation
        service.invitations.conditional_revoke.return_value = 0

        with pytest.raises(InvalidTransitionException):
            asyncio.run(service.revoke_invitation(context, invitation.id))


class TestInvitationEmailAndNotificationCreation:
    def test_email_outbox_contains_accept_and_decline_links(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        user = make_user()
        context = service_context(company, user, role=MembershipRole.ADMIN)

        service.invitations.list_by_company.return_value = []
        service.users.get_by_email.return_value = make_user(
            email="newuser@example.com", is_active=True
        )
        service.memberships.get_active.return_value = None

        def assign_defaults():
            if session.add.call_args:
                invitation = session.add.call_args.args[0]
                invitation.id = uuid.uuid4()
                invitation.created_at = utc_now()
                invitation.updated_at = utc_now()

        session.flush.side_effect = assign_defaults

        with patch("app.services.workspace_service.secrets.token_urlsafe", return_value="mock-token-xyz"), \
             patch("app.services.workspace_service.enqueue_email", new=AsyncMock()) as mock_enqueue:
            asyncio.run(
                service.create_invitation(
                    context,
                    InvitationCreate(
                        email="newuser@example.com",
                        role=MembershipRole.RECRUITER,
                    ),
                )
            )

            mock_enqueue.assert_awaited_once()
            kwargs = mock_enqueue.await_args.kwargs
            assert "action=accept" in kwargs["html_body"]
            assert "action=decline" in kwargs["html_body"]
            assert "Chấp nhận lời mời" in kwargs["html_body"]
            assert "Từ chối lời mời" in kwargs["html_body"]
            assert "action=accept" in kwargs["text_body"]
            assert "action=decline" in kwargs["text_body"]

    def test_create_invitation_creates_in_app_notification_for_existing_user(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        inviter = make_user()
        context = service_context(company, inviter, role=MembershipRole.ADMIN)
        registered_recipient = make_user(email="registered@example.com")

        service.invitations.list_by_company.return_value = []
        service.users.get_by_email.return_value = registered_recipient

        def assign_defaults():
            if session.add.call_args:
                invitation = session.add.call_args.args[0]
                invitation.id = uuid.uuid4()
                invitation.created_at = utc_now()
                invitation.updated_at = utc_now()

        session.flush.side_effect = assign_defaults

        # Mock begin_nested on session
        session.begin_nested.return_value.__aenter__ = AsyncMock()
        session.begin_nested.return_value.__aexit__ = AsyncMock()

        with patch("app.services.workspace_service.enqueue_email", new=AsyncMock()):
            asyncio.run(
                service.create_invitation(
                    context,
                    InvitationCreate(
                        email="registered@example.com",
                        role=MembershipRole.RECRUITER,
                    ),
                )
            )

        service.notifications.notify_company_invitation.assert_awaited_once()


class TestMemberJoinedNotifications:
    def test_active_administrators_receive_notifications(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        invitee = make_user(email="invitee@example.com")
        admin_1 = make_user(email="admin1@example.com")
        admin_2 = make_user(email="admin2@example.com")

        admin_membership_1 = make_membership(
            company=company, user=admin_1, role=MembershipRole.ADMIN
        )
        admin_membership_2 = make_membership(
            company=company, user=admin_2, role=MembershipRole.ADMIN
        )

        token = "token-secret-12345"
        invitation = make_invitation(
            company=company,
            email="invitee@example.com",
            token=token,
            role=MembershipRole.RECRUITER,
        )

        service.invitations.get_by_token_hash_for_update.return_value = (
            invitation
        )
        service.companies.get_by_id.return_value = company
        service.memberships.list_active_admins.return_value = [
            admin_membership_1,
            admin_membership_2,
        ]

        def assign_defaults():
            if session.add.call_args:
                membership = session.add.call_args.args[0]
                membership.id = uuid.uuid4()
                membership.created_at = utc_now()
                membership.updated_at = utc_now()

        session.flush.side_effect = assign_defaults

        result = asyncio.run(service.accept_invitation(invitee, token))
        assert result.workspace.company_id == company.id

        service.memberships.list_active_admins.assert_awaited_once_with(
            company.id
        )
        assert service.notifications.notify_company_member_joined.await_count == 2
        calls = (
            service.notifications.notify_company_member_joined.await_args_list
        )

        assert calls[0].kwargs["admin_user_id"] == admin_1.id
        assert calls[0].kwargs["member_email"] == "invitee@example.com"
        assert calls[0].kwargs["company_name"] == company.name
        assert calls[0].kwargs["role_label"] == "Nhà tuyển dụng"

        assert calls[1].kwargs["admin_user_id"] == admin_2.id
        assert calls[1].kwargs["member_email"] == "invitee@example.com"
        assert calls[1].kwargs["company_name"] == company.name
        assert calls[1].kwargs["role_label"] == "Nhà tuyển dụng"

    def test_joining_user_does_not_receive_self_notification(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        invitee = make_user(email="joining-admin@example.com")
        other_admin = make_user(email="other-admin@example.com")

        joining_membership = make_membership(
            company=company, user=invitee, role=MembershipRole.ADMIN
        )
        other_membership = make_membership(
            company=company, user=other_admin, role=MembershipRole.ADMIN
        )

        token = "token-admin-12345"
        invitation = make_invitation(
            company=company,
            email="joining-admin@example.com",
            token=token,
            role=MembershipRole.ADMIN,
        )

        service.invitations.get_by_token_hash_for_update.return_value = (
            invitation
        )
        service.companies.get_by_id.return_value = company
        service.memberships.list_active_admins.return_value = [
            joining_membership,
            other_membership,
        ]

        def assign_defaults():
            if session.add.call_args:
                membership = session.add.call_args.args[0]
                membership.id = uuid.uuid4()
                membership.created_at = utc_now()
                membership.updated_at = utc_now()

        session.flush.side_effect = assign_defaults

        result = asyncio.run(service.accept_invitation(invitee, token))
        assert result.workspace.role == MembershipRole.ADMIN

        # Only other_admin receives notification, joining user is excluded
        assert service.notifications.notify_company_member_joined.await_count == 1
        call_kwargs = (
            service.notifications.notify_company_member_joined.await_args.kwargs
        )
        assert call_kwargs["admin_user_id"] == other_admin.id
        assert call_kwargs["member_email"] == "joining-admin@example.com"

    def test_recruiters_and_interviewers_do_not_receive_admin_notifications(
        self,
    ):
        session = make_session()
        service = make_service(session)
        company = make_company()
        invitee = make_user(email="invitee@example.com")

        token = "token-recruiter-123"
        invitation = make_invitation(
            company=company,
            email="invitee@example.com",
            token=token,
            role=MembershipRole.INTERVIEWER,
        )

        service.invitations.get_by_token_hash_for_update.return_value = (
            invitation
        )
        service.companies.get_by_id.return_value = company
        service.memberships.list_active_admins.return_value = []

        def assign_defaults():
            if session.add.call_args:
                membership = session.add.call_args.args[0]
                membership.id = uuid.uuid4()
                membership.created_at = utc_now()
                membership.updated_at = utc_now()

        session.flush.side_effect = assign_defaults

        asyncio.run(service.accept_invitation(invitee, token))

        service.memberships.list_active_admins.assert_awaited_once_with(
            company.id
        )
        service.notifications.notify_company_member_joined.assert_not_awaited()

    def test_administrators_of_other_companies_receive_no_notification(self):
        session = make_session()
        service = make_service(session)
        company_a = make_company()
        company_b = make_company()
        invitee = make_user(email="invitee@example.com")
        admin_b = make_user(email="admin-b@example.com")

        make_membership(
            company=company_b, user=admin_b, role=MembershipRole.ADMIN
        )

        token = "token-a"
        invitation = make_invitation(
            company=company_a,
            email="invitee@example.com",
            token=token,
            role=MembershipRole.RECRUITER,
        )

        service.invitations.get_by_token_hash_for_update.return_value = (
            invitation
        )
        service.companies.get_by_id.return_value = company_a
        service.memberships.list_active_admins.return_value = []

        def assign_defaults():
            if session.add.call_args:
                membership = session.add.call_args.args[0]
                membership.id = uuid.uuid4()
                membership.created_at = utc_now()
                membership.updated_at = utc_now()

        session.flush.side_effect = assign_defaults

        asyncio.run(service.accept_invitation(invitee, token))

        service.memberships.list_active_admins.assert_awaited_once_with(
            company_a.id
        )
        service.notifications.notify_company_member_joined.assert_not_awaited()

    def test_duplicate_notification_id_handled_safely(self):
        from sqlalchemy.exc import IntegrityError

        session = make_session()
        service = make_service(session)
        company = make_company()
        invitee = make_user(email="invitee@example.com")
        admin = make_user(email="admin@example.com")
        admin_membership = make_membership(
            company=company, user=admin, role=MembershipRole.ADMIN
        )

        token = "token-dup"
        invitation = make_invitation(
            company=company,
            email="invitee@example.com",
            token=token,
            role=MembershipRole.RECRUITER,
        )

        service.invitations.get_by_token_hash_for_update.return_value = (
            invitation
        )
        service.companies.get_by_id.return_value = company
        service.memberships.list_active_admins.return_value = [
            admin_membership
        ]

        def assign_defaults():
            if session.add.call_args:
                membership = session.add.call_args.args[0]
                membership.id = uuid.uuid4()
                membership.created_at = utc_now()
                membership.updated_at = utc_now()

        session.flush.side_effect = assign_defaults

        service.notifications.notify_company_member_joined.side_effect = (
            IntegrityError(
                "statement",
                {},
                Exception(
                    "Violation of PRIMARY KEY constraint 'PK_notifications'. Duplicate key value."
                ),
            )
        )

        result = asyncio.run(service.accept_invitation(invitee, token))
        assert result.workspace.company_id == company.id
        session.commit.assert_awaited_once()

    def test_unrelated_integrity_errors_still_propagate(self):
        from sqlalchemy.exc import IntegrityError

        session = make_session()
        service = make_service(session)
        company = make_company()
        invitee = make_user(email="invitee@example.com")
        admin = make_user(email="admin@example.com")
        admin_membership = make_membership(
            company=company, user=admin, role=MembershipRole.ADMIN
        )

        token = "token-unrelated"
        invitation = make_invitation(
            company=company,
            email="invitee@example.com",
            token=token,
            role=MembershipRole.RECRUITER,
        )

        service.invitations.get_by_token_hash_for_update.return_value = (
            invitation
        )
        service.companies.get_by_id.return_value = company
        service.memberships.list_active_admins.return_value = [
            admin_membership
        ]

        def assign_defaults():
            if session.add.call_args:
                membership = session.add.call_args.args[0]
                membership.id = uuid.uuid4()
                membership.created_at = utc_now()
                membership.updated_at = utc_now()

        session.flush.side_effect = assign_defaults

        service.notifications.notify_company_member_joined.side_effect = (
            IntegrityError(
                "statement",
                {},
                Exception(
                    "FOREIGN KEY constraint 'FK_notifications_user' violation."
                ),
            )
        )

        with pytest.raises(IntegrityError):
            asyncio.run(service.accept_invitation(invitee, token))


class TestRevokeMembershipRealtime:
    def test_member_revocation_registers_post_commit_publication_action(self):
        session = make_session()
        lock_result = MagicMock()
        lock_result.scalar_one.return_value = 0
        session.execute.return_value = lock_result

        service = make_service(session)
        company = make_company()
        admin = make_user(email="admin@example.com")
        member = make_user(email="member@example.com")
        context = service_context(company, admin, role=MembershipRole.ADMIN)
        target_membership = make_membership(company=company, user=member, role=MembershipRole.RECRUITER)

        service.memberships.get_active.return_value = context.membership
        service.memberships.get_by_id_with_user.return_value = target_membership

        with patch("app.services.workspace_service.TransactionActionManager") as tam_mock, \
             patch("app.services.workspace_service.pubsub_manager") as ps_mock:
            ps_mock.publish = AsyncMock()
            ps_mock.get_user_channel.return_value = f"notifications:user:{member.id}"
            result = asyncio.run(service.revoke_membership(context, target_membership.id))

            assert result.status == MembershipStatus.REVOKED
            tam_mock.register_action.assert_called_once()
            args, _ = tam_mock.register_action.call_args
            assert args[0] is session
            callback = args[1]
            assert callable(callback)

            # Execute registered callback to assert publication
            asyncio.run(callback())
            ps_mock.publish.assert_awaited_once_with(
                channel=f"notifications:user:{member.id}",
                message={
                    "type": "workspace.revoked",
                    "company_id": str(company.id),
                    "membership_id": str(target_membership.id),
                },
            )

    def test_member_revocation_action_does_not_publish_on_rollback(self):
        session = make_session()
        lock_result = MagicMock()
        lock_result.scalar_one.return_value = 0
        session.execute.return_value = lock_result
        session.commit.side_effect = Exception("DB Commit Failed")

        service = make_service(session)
        company = make_company()
        admin = make_user(email="admin@example.com")
        member = make_user(email="member@example.com")
        context = service_context(company, admin, role=MembershipRole.ADMIN)
        target_membership = make_membership(company=company, user=member, role=MembershipRole.RECRUITER)

        service.memberships.get_active.return_value = context.membership
        service.memberships.get_by_id_with_user.return_value = target_membership

        with patch("app.services.workspace_service.TransactionActionManager"), \
             patch("app.services.workspace_service.pubsub_manager") as ps_mock:
            ps_mock.publish = AsyncMock()
            with pytest.raises(Exception, match="DB Commit Failed"):
                asyncio.run(service.revoke_membership(context, target_membership.id))

            session.rollback.assert_awaited_once()
            ps_mock.publish.assert_not_called()

    def test_member_revocation_targets_only_revoked_user_personal_channel(self):
        session = make_session()
        lock_result = MagicMock()
        lock_result.scalar_one.return_value = 0
        session.execute.return_value = lock_result

        service = make_service(session)
        company = make_company()
        admin = make_user(email="admin@example.com")
        member = make_user(email="member@example.com")
        context = service_context(company, admin, role=MembershipRole.ADMIN)
        target_membership = make_membership(company=company, user=member, role=MembershipRole.RECRUITER)

        service.memberships.get_active.return_value = context.membership
        service.memberships.get_by_id_with_user.return_value = target_membership

        with patch("app.services.workspace_service.TransactionActionManager") as tam_mock, \
             patch("app.services.workspace_service.pubsub_manager") as ps_mock:
            ps_mock.publish = AsyncMock()
            ps_mock.get_user_channel.side_effect = lambda uid: f"notifications:user:{uid}"
            asyncio.run(service.revoke_membership(context, target_membership.id))

            args, _ = tam_mock.register_action.call_args
            asyncio.run(args[1]())
            ps_mock.publish.assert_awaited_once()
            call_channel = ps_mock.publish.call_args.kwargs["channel"]
            assert call_channel == f"notifications:user:{member.id}"
            assert call_channel != f"notifications:user:{admin.id}"


class TestRevokeInvitationRealtime:
    def test_invitation_revocation_marks_registered_recipient_notification_read(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        admin = make_user(email="admin@example.com")
        recipient = make_user(email="invitee@example.com")
        context = service_context(company, admin, role=MembershipRole.ADMIN)
        invitation = make_invitation(company=company, email="invitee@example.com")

        service.invitations.get_by_company.return_value = invitation
        service.invitations.conditional_revoke.return_value = 1
        service.users.get_by_email.return_value = recipient

        result = asyncio.run(service.revoke_invitation(context, invitation.id))

        assert result.status == InvitationStatus.REVOKED
        service.notifications.mark_invitation_notification_read.assert_awaited_once_with(
            recipient.id, invitation.id
        )

    def test_invitation_revocation_registers_post_commit_event_for_recipient(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        admin = make_user(email="admin@example.com")
        recipient = make_user(email="invitee@example.com")
        context = service_context(company, admin, role=MembershipRole.ADMIN)
        invitation = make_invitation(company=company, email="invitee@example.com")

        service.invitations.get_by_company.return_value = invitation
        service.invitations.conditional_revoke.return_value = 1
        service.users.get_by_email.return_value = recipient

        with patch("app.services.workspace_service.TransactionActionManager") as tam_mock, \
             patch("app.services.workspace_service.pubsub_manager") as ps_mock:
            ps_mock.publish = AsyncMock()
            ps_mock.get_user_channel.return_value = f"notifications:user:{recipient.id}"
            asyncio.run(service.revoke_invitation(context, invitation.id))

            tam_mock.register_action.assert_called_once()
            args, _ = tam_mock.register_action.call_args
            assert args[0] is session
            asyncio.run(args[1]())
            ps_mock.publish.assert_awaited_once_with(
                channel=f"notifications:user:{recipient.id}",
                message={
                    "type": "invitation.revoked",
                    "invitation_id": str(invitation.id),
                    "company_id": str(company.id),
                },
            )

    def test_unregistered_recipient_revocation_succeeds_without_personal_event(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        admin = make_user(email="admin@example.com")
        context = service_context(company, admin, role=MembershipRole.ADMIN)
        invitation = make_invitation(company=company, email="unregistered@example.com")

        service.invitations.get_by_company.return_value = invitation
        service.invitations.conditional_revoke.return_value = 1
        service.users.get_by_email.return_value = None

        with patch("app.services.workspace_service.TransactionActionManager") as tam_mock, \
             patch("app.services.workspace_service.pubsub_manager") as ps_mock:
            ps_mock.publish = AsyncMock()
            result = asyncio.run(service.revoke_invitation(context, invitation.id))

            assert result.status == InvitationStatus.REVOKED
            service.notifications.mark_invitation_notification_read.assert_not_called()
            tam_mock.register_action.assert_not_called()
            ps_mock.publish.assert_not_called()

    def test_failed_conditional_revocation_does_not_publish_event(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        admin = make_user(email="admin@example.com")
        context = service_context(company, admin, role=MembershipRole.ADMIN)
        invitation = make_invitation(company=company, email="invitee@example.com")

        service.invitations.get_by_company.return_value = invitation
        service.invitations.conditional_revoke.return_value = 0

        with patch("app.services.workspace_service.TransactionActionManager") as tam_mock:
            with pytest.raises(InvalidTransitionException):
                asyncio.run(service.revoke_invitation(context, invitation.id))

            tam_mock.register_action.assert_not_called()

    def test_duplicate_or_unrelated_integrity_errors_preserve_correct_behavior(self):
        session = make_session()
        session.commit.side_effect = Exception("Integrity Error on Commit")
        service = make_service(session)
        company = make_company()
        admin = make_user(email="admin@example.com")
        recipient = make_user(email="invitee@example.com")
        context = service_context(company, admin, role=MembershipRole.ADMIN)
        invitation = make_invitation(company=company, email="invitee@example.com")

        service.invitations.get_by_company.return_value = invitation
        service.invitations.conditional_revoke.return_value = 1
        service.users.get_by_email.return_value = recipient

        with patch("app.services.workspace_service.TransactionActionManager"), \
             patch("app.services.workspace_service.pubsub_manager") as ps_mock:
            ps_mock.publish = AsyncMock()
            with pytest.raises(Exception, match="Integrity Error on Commit"):
                asyncio.run(service.revoke_invitation(context, invitation.id))

            session.rollback.assert_awaited_once()
            ps_mock.publish.assert_not_called()


class TestSSEClassificationAndStreamDispatch:
    def test_personal_event_name_classifies_invitation_revoked(self):
        from app.api.v1.endpoints.notifications import (
            _personal_event_name,
            INVITATION_REVOKED_EVENT,
            ACCOUNT_LOCKED_EVENT,
            NOTIFICATION_CREATED_EVENT,
        )
        assert _personal_event_name({"type": INVITATION_REVOKED_EVENT}) == INVITATION_REVOKED_EVENT
        assert _personal_event_name({"type": ACCOUNT_LOCKED_EVENT}) == ACCOUNT_LOCKED_EVENT
        assert _personal_event_name({"type": "regular_notification"}) == NOTIFICATION_CREATED_EVENT
        assert _personal_event_name("invalid json") == NOTIFICATION_CREATED_EVENT

    def test_workspace_revoked_delivered_when_company_matches_workspace(self):
        from app.api.v1.endpoints.notifications import (
            WORKSPACE_REVOKED_EVENT,
            notification_stream,
        )
        user_id = uuid.uuid4()
        company_id = uuid.uuid4()
        matching_revocation = {
            "type": WORKSPACE_REVOKED_EVENT,
            "company_id": str(company_id),
            "membership_id": str(uuid.uuid4()),
        }
        personal_channel = f"notifications:user:{user_id}"

        class FakePubSub:
            def __init__(self, msgs):
                self._msgs = list(msgs)
                self.unsubscribed = []
                self.closed = False
            async def subscribe(self, *c):
                pass
            async def get_message(self, *a, **kw):
                if self._msgs:
                    return self._msgs.pop(0)
                return None
            async def unsubscribe(self, *c):
                self.unsubscribed.extend(c)
            async def close(self):
                self.closed = True

        msg = {
            "type": "message",
            "channel": personal_channel,
            "data": json.dumps(matching_revocation),
        }
        pubsub = FakePubSub([msg])
        manager = MagicMock()
        manager._redis.get = AsyncMock(return_value=json.dumps({
            "user_id": str(user_id),
            "is_admin": False,
            "company_id": str(company_id),
        }))
        manager._redis.delete = AsyncMock()
        manager._redis.pubsub = MagicMock(return_value=pubsub)
        manager.get_user_channel.return_value = personal_channel

        response = asyncio.run(notification_stream(ticket="valid-ticket", pubsub=manager))
        generator = response.body_iterator

        async def _collect():
            chunks = []
            async for chunk in generator:
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(_collect())
        joined = "".join(chunks)
        assert f"event: {WORKSPACE_REVOKED_EVENT}" in joined
        assert matching_revocation["membership_id"] in joined

    def test_workspace_revoked_delivered_when_company_differs_without_terminating_stream(self):
        from app.api.v1.endpoints.notifications import (
            WORKSPACE_REVOKED_EVENT,
            notification_stream,
        )
        user_id = uuid.uuid4()
        active_company_id = uuid.uuid4()
        other_company_id = uuid.uuid4()
        other_revocation = {
            "type": WORKSPACE_REVOKED_EVENT,
            "company_id": str(other_company_id),
            "membership_id": str(uuid.uuid4()),
        }
        personal_channel = f"notifications:user:{user_id}"

        class FakePubSub:
            def __init__(self, msgs):
                self._msgs = list(msgs)
                self.unsubscribed = []
                self.closed = False
            async def subscribe(self, *c):
                pass
            async def get_message(self, *a, **kw):
                if self._msgs:
                    return self._msgs.pop(0)
                return None
            async def unsubscribe(self, *c):
                self.unsubscribed.extend(c)
            async def close(self):
                self.closed = True

        msg = {
            "type": "message",
            "channel": personal_channel,
            "data": json.dumps(other_revocation),
        }
        pubsub = FakePubSub([msg])
        manager = MagicMock()
        manager._redis.get = AsyncMock(return_value=json.dumps({
            "user_id": str(user_id),
            "is_admin": False,
            "company_id": str(active_company_id),
        }))
        manager._redis.delete = AsyncMock()
        manager._redis.pubsub = MagicMock(return_value=pubsub)
        manager.get_user_channel.return_value = personal_channel

        with patch("app.api.v1.endpoints.notifications.STREAM_MAX_SECONDS", 0.001):
            response = asyncio.run(notification_stream(ticket="valid-ticket", pubsub=manager))
            generator = response.body_iterator

            async def _collect():
                chunks = []
                async for chunk in generator:
                    chunks.append(chunk)
                return chunks

            chunks = asyncio.run(_collect())
            joined = "".join(chunks)
            assert f"event: {WORKSPACE_REVOKED_EVENT}" in joined
            assert other_revocation["membership_id"] in joined

    def test_invitation_revoked_delivered_as_personal_event_without_terminating_stream(self):
        from app.api.v1.endpoints.notifications import (
            INVITATION_REVOKED_EVENT,
            notification_stream,
        )
        user_id = uuid.uuid4()
        inv_revocation = {
            "type": INVITATION_REVOKED_EVENT,
            "invitation_id": str(uuid.uuid4()),
            "company_id": str(uuid.uuid4()),
        }
        personal_channel = f"notifications:user:{user_id}"

        class FakePubSub:
            def __init__(self, msgs):
                self._msgs = list(msgs)
                self.unsubscribed = []
                self.closed = False
            async def subscribe(self, *c):
                pass
            async def get_message(self, *a, **kw):
                if self._msgs:
                    return self._msgs.pop(0)
                return None
            async def unsubscribe(self, *c):
                self.unsubscribed.extend(c)
            async def close(self):
                self.closed = True

        msg = {
            "type": "message",
            "channel": personal_channel,
            "data": json.dumps(inv_revocation),
        }
        pubsub = FakePubSub([msg])
        manager = MagicMock()
        manager._redis.get = AsyncMock(return_value=json.dumps({
            "user_id": str(user_id),
            "is_admin": False,
            "company_id": None,
        }))
        manager._redis.delete = AsyncMock()
        manager._redis.pubsub = MagicMock(return_value=pubsub)
        manager.get_user_channel.return_value = personal_channel

        with patch("app.api.v1.endpoints.notifications.STREAM_MAX_SECONDS", 0.001):
            response = asyncio.run(notification_stream(ticket="valid-ticket", pubsub=manager))
            generator = response.body_iterator

            async def _collect():
                chunks = []
                async for chunk in generator:
                    chunks.append(chunk)
                return chunks

            chunks = asyncio.run(_collect())
            joined = "".join(chunks)
            assert f"event: {INVITATION_REVOKED_EVENT}" in joined
            assert inv_revocation["invitation_id"] in joined


class TestFrontendUrlConfigValidation:
    def test_valid_http_and_https_url(self):
        from app.core.config import Settings
        s1 = Settings(FRONTEND_URL="http://example.com", ENVIRONMENT="development")
        assert s1.FRONTEND_URL == "http://example.com"
        s2 = Settings(FRONTEND_URL="https://app.example.com", ENVIRONMENT="development")
        assert s2.FRONTEND_URL == "https://app.example.com"

    def test_trailing_slash_normalized(self):
        from app.core.config import Settings
        s = Settings(FRONTEND_URL="https://app.example.com/", ENVIRONMENT="development")
        assert s.FRONTEND_URL == "https://app.example.com"

    def test_invalid_scheme_or_format_rejected(self):
        from app.core.config import Settings
        with pytest.raises(ValueError):
            Settings(FRONTEND_URL="ftp://invalid.com", ENVIRONMENT="development")
        with pytest.raises(ValueError):
            Settings(FRONTEND_URL="not-a-url", ENVIRONMENT="development")

    def test_development_localhost_accepted(self):
        from app.core.config import Settings
        s1 = Settings(FRONTEND_URL="http://localhost:5173", ENVIRONMENT="development")
        assert s1.FRONTEND_URL == "http://localhost:5173"
        s2 = Settings(FRONTEND_URL="http://127.0.0.1:3000", ENVIRONMENT="development")
        assert s2.FRONTEND_URL == "http://127.0.0.1:3000"

    def test_production_localhost_rejected(self):
        from app.core.config import Settings
        with pytest.raises(ValueError) as exc:
            Settings(
                FRONTEND_URL="http://localhost:5173",
                ENVIRONMENT="production",
                BACKEND_CORS_ORIGINS=["https://recruitment.company.com"],
                SECRET_KEY="production-secret-key-that-is-long-enough",
            )
        assert "cannot be localhost or a loopback address in production" in str(exc.value)

    def test_production_loopback_ip_rejected(self):
        from app.core.config import Settings
        with pytest.raises(ValueError) as exc:
            Settings(
                FRONTEND_URL="http://127.0.0.1:3000",
                ENVIRONMENT="production",
                BACKEND_CORS_ORIGINS=["https://recruitment.company.com"],
                SECRET_KEY="production-secret-key-that-is-long-enough",
            )
        assert "cannot be localhost or a loopback address in production" in str(exc.value)

        with pytest.raises(ValueError) as exc:
            Settings(
                FRONTEND_URL="http://[::1]:3000",
                ENVIRONMENT="production",
                BACKEND_CORS_ORIGINS=["https://recruitment.company.com"],
                SECRET_KEY="production-secret-key-that-is-long-enough",
            )
        assert "cannot be localhost or a loopback address in production" in str(exc.value)

        with pytest.raises(ValueError) as exc:
            Settings(
                FRONTEND_URL="http://0.0.0.0:8000",
                ENVIRONMENT="production",
                BACKEND_CORS_ORIGINS=["https://recruitment.company.com"],
                SECRET_KEY="production-secret-key-that-is-long-enough",
            )
        assert "cannot be localhost or a loopback address in production" in str(exc.value)

    def test_production_public_url_accepted(self):
        from app.core.config import Settings
        s = Settings(
            FRONTEND_URL="https://recruitment.company.com/",
            ENVIRONMENT="production",
            BACKEND_CORS_ORIGINS=["https://recruitment.company.com"],
            SECRET_KEY="production-secret-key-that-is-long-enough",
        )
        assert s.FRONTEND_URL == "https://recruitment.company.com"
