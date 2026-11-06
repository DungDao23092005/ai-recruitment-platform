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
    User,
)
from app.repositories import (
    CompanyInvitationRepository,
    CompanyMembershipRepository,
    CompanyRepository,
    UserRepository,
)
from app.schemas.workspace import InvitationCreate
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
    return session


def make_company(company_id: uuid.UUID | None = None) -> Company:
    company = Company(
        id=company_id or uuid.uuid4(),
        name="Acme Corp",
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
) -> User:
    user = User(
        id=user_id or uuid.uuid4(),
        email=email,
        password_hash="hashed",
        role=role,
        is_active=True,
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
    service.companies = AsyncMock(spec=CompanyRepository)
    service.users = AsyncMock(spec=UserRepository)
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
        service.users.get_by_email.return_value = None
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
        assert "#token=" in email_kwargs["text_body"]
        session.commit.assert_awaited_once()

    def test_existing_active_member_conflicts(self):
        service = make_service(make_session())
        admin = make_user()
        company = make_company()
        context = service_context(
            company, admin, role=MembershipRole.ADMIN
        )
        service.invitations.expire_stale.return_value = 0
        service.users.get_by_email.return_value = make_user(
            email="member@example.com"
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
        service.users.get_by_email.return_value = None
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
            "app.services.workspace_service.asyncio.create_task"
        ) as create_task:
            result = asyncio.run(
                service.revoke_membership(context, target.id)
            )
            coroutine = create_task.call_args.args[0]
            coroutine.close()

        assert result.status == MembershipStatus.REVOKED
        assert target.revoked_by_id == admin.id
        assert target.revoked_at is not None
        session.commit.assert_awaited_once()
        create_task.assert_called_once()

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
            "app.services.workspace_service.asyncio.create_task"
        ) as create_task:
            result = asyncio.run(
                service.revoke_membership(context, target.id)
            )
            coroutine = create_task.call_args.args[0]
            coroutine.close()

        assert result.status == MembershipStatus.REVOKED
        session.commit.assert_awaited_once()
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
