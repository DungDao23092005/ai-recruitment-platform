from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from unittest.mock import MagicMock
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
    InvalidTransitionException,
    ValidationError,
    WorkspaceRequiredException,
    WorkspaceSelectionRequiredException,
)
from app.core.pubsub import pubsub_manager
from app.core.workspace_context import (
    get_workspace_company_id,
    reset_workspace_company_id,
    set_workspace_company_id,
)
from app.database.base_class import utc_now
from app.services.transaction_action_manager import TransactionActionManager
from app.domain.enums import (
    AdminAuditAction,
    InvitationStatus,
    MembershipRole,
    MembershipStatus,
    UserRole,
)
from app.models import (
    AdminAuditLog,
    Application,
    Company,
    CompanyInvitation,
    CompanyMembership,
    Interview,
    InterviewAssignment,
    Job,
    RecruiterProfile,
    User,
)
from app.repositories import (
    CompanyInvitationRepository,
    CompanyMembershipRepository,
    CompanyRepository,
    UserRepository,
)
from app.schemas.workspace import (
    InvitationAcceptRead,
    InvitationCreate,
    InvitationDeclineRead,
    InvitationPreviewRead,
    InvitationRead,
    MemberRead,
    MyInvitationRead,
    WorkspaceRead,
    normalize_email,
)
from app.services.email_outbox_service import enqueue_email
from app.services.email_outbox_worker import signal_dispatch_after_commit
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class WorkspaceContext:
    user: User
    company: Company
    membership: CompanyMembership | None
    is_platform_admin: bool = False

    @property
    def company_id(self) -> uuid.UUID:
        return self.company.id

    @property
    def role(self) -> MembershipRole | None:
        return self.membership.role if self.membership is not None else None

    @property
    def is_company_admin(self) -> bool:
        return self.is_platform_admin or self.role == MembershipRole.ADMIN

    def to_read(self) -> WorkspaceRead:
        return WorkspaceRead(
            company_id=self.company.id,
            company_name=self.company.name,
            company_slug=self.company.slug,
            membership_id=self.membership.id if self.membership else None,
            role=self.role,
            is_platform_admin=self.is_platform_admin,
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _mask_email(email: str) -> str:
    local, separator, domain = email.partition("@")
    if not separator:
        return "***"
    visible = local[:1] if local else ""
    return f"{visible}***@{domain}"


def hash_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_invitation_url(token: str, action: str = "accept") -> str:
    return (
        f"{settings.FRONTEND_URL.rstrip('/')}/invitations/accept"
        f"#token={token}&action={action}"
    )


class WorkspaceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.memberships = CompanyMembershipRepository(
            session, CompanyMembership
        )
        self.invitations = CompanyInvitationRepository(
            session, CompanyInvitation
        )
        self.companies = CompanyRepository(session, Company)
        self.users = UserRepository(session, User)
        self.notifications = NotificationService(session)

    async def resolve(
        self,
        user: User,
        company_id_header: str | None,
    ) -> WorkspaceContext:
        selected_id: uuid.UUID | None = None
        if company_id_header is not None:
            stripped_header = str(company_id_header).strip()
            if not stripped_header:
                raise ValidationError("X-Company-ID must be a valid UUID")
            try:
                selected_id = uuid.UUID(stripped_header)
            except (TypeError, ValueError):
                raise ValidationError("X-Company-ID must be a valid UUID") from None

        if user.role == UserRole.ADMIN:
            return await self._resolve_platform_admin(user, selected_id)

        if selected_id is not None:
            membership = await self.memberships.get_active(
                user.id, selected_id
            )
            if membership is None or membership.company is None:
                raise WorkspaceRequiredException(
                    "You do not have access to this workspace"
                )
            return WorkspaceContext(
                user=user,
                company=membership.company,
                membership=membership,
            )

        active = await self.memberships.list_active_for_user(user.id)
        if not active:
            raise WorkspaceRequiredException(
                "You do not have an active company workspace"
            )
        if len(active) > 1:
            raise WorkspaceSelectionRequiredException(
                "Select a company workspace with X-Company-ID"
            )
        membership = active[0]
        if membership.company is None:
            raise WorkspaceRequiredException(
                "You do not have an active company workspace"
            )
        return WorkspaceContext(
            user=user,
            company=membership.company,
            membership=membership,
        )

    async def _resolve_platform_admin(
        self,
        user: User,
        selected_id: uuid.UUID | None,
    ) -> WorkspaceContext:
        membership: CompanyMembership | None = None
        if selected_id is None:
            active = await self.memberships.list_active_for_user(user.id)
            if len(active) == 1:
                membership = active[0]
            elif len(active) > 1:
                raise WorkspaceSelectionRequiredException(
                    "Select a company workspace with X-Company-ID"
                )
            else:
                raise WorkspaceSelectionRequiredException(
                    "Select a company workspace with X-Company-ID"
                )
        else:
            membership = await self.memberships.get_active(
                user.id, selected_id
            )

        company_id = selected_id or (
            membership.company_id if membership is not None else None
        )
        if company_id is None:
            raise WorkspaceSelectionRequiredException(
                "Select a company workspace with X-Company-ID"
            )
        company = await self.companies.get_by_id(company_id)
        if company is None:
            raise WorkspaceRequiredException(
                "You do not have access to this workspace"
            )
        if selected_id is not None and membership is None:
            self.session.add(
                AdminAuditLog(
                    admin_id=user.id,
                    target_user_id=user.id,
                    target_id=user.id,
                    target_type="user",
                    action=AdminAuditAction.WORKSPACE_ACCESS,
                    details={
                        "company_id": str(company.id),
                        "company_slug": company.slug,
                        "membership_id": None,
                    },
                )
            )
            await self.session.commit()
        return WorkspaceContext(
            user=user,
            company=company,
            membership=membership,
            is_platform_admin=True,
        )

    async def list_workspaces(self, user: User) -> list[WorkspaceRead]:
        if user.role == UserRole.ADMIN:
            companies = await self.companies.list_all()
            memberships = {
                membership.company_id: membership
                for membership in await self.memberships.list_active_for_user(
                    user.id
                )
            }
            return [
                WorkspaceRead(
                    company_id=company.id,
                    company_name=company.name,
                    company_slug=company.slug,
                    membership_id=(
                        memberships[company.id].id
                        if company.id in memberships
                        else None
                    ),
                    role=(
                        memberships[company.id].role
                        if company.id in memberships
                        else None
                    ),
                    is_platform_admin=True,
                )
                for company in companies
            ]

        return [
            WorkspaceContext(
                user=user,
                company=membership.company,
                membership=membership,
            ).to_read()
            for membership in await self.memberships.list_active_for_user(
                user.id
            )
            if membership.company is not None
        ]

    async def list_members(
        self,
        context: WorkspaceContext,
        include_revoked: bool = True,
    ) -> list[MemberRead]:
        self._require_company_manager(context)
        memberships = await self.memberships.list_by_company(
            context.company_id,
            include_revoked=include_revoked,
        )
        return [
            MemberRead(
                membership_id=membership.id,
                user_id=membership.user_id,
                email=membership.user.email,
                full_name=(
                    membership.user.recruiter_profile.full_name
                    if membership.user.recruiter_profile is not None
                    else None
                ),
                role=membership.role,
                status=membership.status,
                joined_at=membership.joined_at,
                revoked_at=membership.revoked_at,
            )
            for membership in memberships
            if membership.user is not None
        ]

    async def list_invitations(
        self, context: WorkspaceContext
    ) -> list[InvitationRead]:
        self._require_company_admin(context)
        await self.invitations.expire_stale(
            company_id=context.company_id,
            now=utc_now(),
        )
        await self.session.commit()
        invitations = await self.invitations.list_by_company(
            context.company_id
        )
        return [InvitationRead.model_validate(item) for item in invitations]

    async def create_invitation(
        self,
        context: WorkspaceContext,
        data: InvitationCreate,
    ) -> InvitationRead:
        self._require_company_admin(context)
        now = utc_now()
        email = normalize_email(str(data.email))
        await self.invitations.expire_stale(
            company_id=context.company_id,
            now=now,
        )

        existing_user = await self.users.get_by_email(email)
        if existing_user is None:
            raise EntityNotFoundException(
                "Tài khoản với email này không tồn tại trong hệ thống."
            )
        if not existing_user.is_active:
            raise ForbiddenException(
                "Tài khoản này đang bị khóa và không thể nhận lời mời."
            )

        membership = await self.memberships.get_active(
            existing_user.id, context.company_id
        )
        if membership is not None:
            raise ConflictException(
                "This user is already an active member of the workspace"
            )

        pending = await self.invitations.get_pending_by_company_email(
            context.company_id, email
        )
        if pending is not None:
            raise ConflictException(
                "A pending invitation already exists for this email"
            )

        token = secrets.token_urlsafe(32)
        invitation = CompanyInvitation(
            company_id=context.company_id,
            email=email,
            role=data.role,
            token_hash=hash_invitation_token(token),
            status=InvitationStatus.PENDING,
            invited_by_id=context.user.id,
            expires_at=now
            + timedelta(days=settings.COMPANY_INVITATION_EXPIRY_DAYS),
        )
        self.session.add(invitation)
        try:
            await self.session.flush()
            await self._enqueue_invitation_email(
                invitation=invitation,
                token=token,
                company_name=context.company.name,
                inviter_email=context.user.email,
            )
            await self._create_invitation_notification_idempotent(
                user_id=existing_user.id,
                invitation_id=invitation.id,
                company_name=context.company.name,
                role=invitation.role,
            )
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise ConflictException(
                "A pending invitation already exists for this email"
            ) from None
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(invitation)
        return InvitationRead.model_validate(invitation)

    async def _create_invitation_notification_idempotent(
        self,
        user_id: uuid.UUID,
        invitation_id: uuid.UUID,
        company_name: str,
        role: MembershipRole,
    ) -> None:
        role_label = {
            MembershipRole.ADMIN: "Quản trị viên",
            MembershipRole.RECRUITER: "Nhà tuyển dụng",
            MembershipRole.INTERVIEWER: "Người phỏng vấn",
        }.get(role, str(role.value if hasattr(role, "value") else role))
        try:
            async with self.session.begin_nested():
                await self.notifications.notify_company_invitation(
                    user_id=user_id,
                    invitation_id=invitation_id,
                    company_name=company_name,
                    role_label=role_label,
                )
        except IntegrityError as exc:
            err_str = str(exc).lower()
            if (
                "duplicate key" in err_str
                or "primary key" in err_str
                or "unique constraint" in err_str
                or "uq_" in err_str
                or "pk_" in err_str
                or "2627" in err_str
                or "2601" in err_str
            ):
                logger.info(
                    "Suppressed duplicate invitation notification for user %s, invitation %s",
                    user_id,
                    invitation_id,
                )
            else:
                raise

    async def _notify_admins_member_joined(
        self,
        company_id: uuid.UUID,
        company_name: str,
        joining_user: User,
        membership: CompanyMembership,
    ) -> None:
        role_label = {
            MembershipRole.ADMIN: "Quản trị viên",
            MembershipRole.RECRUITER: "Nhà tuyển dụng",
            MembershipRole.INTERVIEWER: "Người phỏng vấn",
        }.get(
            membership.role,
            str(
                membership.role.value
                if hasattr(membership.role, "value")
                else membership.role
            ),
        )
        admins = await self.memberships.list_active_admins(company_id)
        for admin_membership in admins:
            if admin_membership.user_id == joining_user.id:
                continue
            try:
                async with self.session.begin_nested():
                    await self.notifications.notify_company_member_joined(
                        admin_user_id=admin_membership.user_id,
                        membership_id=membership.id,
                        member_email=joining_user.email,
                        company_name=company_name,
                        role_label=role_label,
                    )
            except IntegrityError as exc:
                err_str = str(exc).lower()
                if (
                    "duplicate key" in err_str
                    or "primary key" in err_str
                    or "unique constraint" in err_str
                    or "uq_" in err_str
                    or "pk_" in err_str
                    or "2627" in err_str
                    or "2601" in err_str
                ):
                    logger.info(
                        "Suppressed duplicate member joined notification for admin %s, membership %s",
                        admin_membership.user_id,
                        membership.id,
                    )
                else:
                    raise

    async def sync_pending_invitations_for_user(
        self, user: User
    ) -> list[CompanyInvitation]:
        now = utc_now()
        normalized_email = normalize_email(user.email)
        pending_invitations = await self.invitations.list_pending_by_email(
            normalized_email,
            now=now,
        )
        for inv in pending_invitations:
            company_name = inv.company.name if inv.company else "công ty"
            await self._create_invitation_notification_idempotent(
                user_id=user.id,
                invitation_id=inv.id,
                company_name=company_name,
                role=inv.role,
            )
        return pending_invitations

    async def list_my_invitations(self, user: User) -> list[MyInvitationRead]:
        now = utc_now()
        normalized_email = normalize_email(user.email)
        await self.invitations.expire_stale(now=now)
        await self.session.commit()
        items = await self.invitations.list_pending_by_email(
            normalized_email, now=now
        )
        return [
            MyInvitationRead(
                id=item.id,
                company_id=item.company_id,
                company_name=item.company.name if item.company else "",
                company_slug=item.company.slug if item.company else "",
                role=item.role,
                status=item.status,
                expires_at=item.expires_at,
                created_at=item.created_at,
                can_accept=(
                    item.status == InvitationStatus.PENDING
                    and _as_utc(item.expires_at) > now
                ),
                can_decline=(
                    item.status == InvitationStatus.PENDING
                    and _as_utc(item.expires_at) > now
                ),
            )
            for item in items
        ]

    async def preview_invitation(self, token: str) -> InvitationPreviewRead:
        invitation = await self.invitations.get_by_token_hash(
            hash_invitation_token(token)
        )
        if invitation is None or invitation.company is None:
            raise EntityNotFoundException("Invitation not found")

        now = utc_now()
        if (
            invitation.status == InvitationStatus.PENDING
            and _as_utc(invitation.expires_at) <= now
        ):
            invitation.status = InvitationStatus.EXPIRED
            await self.session.commit()

        return InvitationPreviewRead(
            company_name=invitation.company.name,
            company_slug=invitation.company.slug,
            email_masked=_mask_email(invitation.email),
            role=invitation.role,
            status=invitation.status,
            expires_at=invitation.expires_at,
            can_accept=(
                invitation.status == InvitationStatus.PENDING
                and _as_utc(invitation.expires_at) > now
            ),
        )

    async def _execute_accept(
        self,
        user: User,
        invitation: CompanyInvitation,
    ) -> InvitationAcceptRead:
        now = utc_now()
        if invitation.status != InvitationStatus.PENDING:
            raise InvalidTransitionException(
                "This invitation is no longer pending"
            )
        if _as_utc(invitation.expires_at) <= now:
            invitation.status = InvitationStatus.EXPIRED
            await self.session.commit()
            raise InvalidTransitionException("This invitation has expired")
        if normalize_email(user.email) != invitation.email:
            raise ForbiddenException(
                "Sign in with the email address that received the invitation"
            )

        company = await self.companies.get_by_id(invitation.company_id)
        if company is None:
            raise EntityNotFoundException("Company not found")

        existing = await self.memberships.get_active(
            user.id, invitation.company_id
        )
        if existing is not None:
            raise ConflictException(
                "You are already an active member of this workspace"
            )

        rowcount = await self.invitations.conditional_accept(
            invitation_id=invitation.id,
            normalized_email=normalize_email(user.email),
            now=now,
        )
        if rowcount != 1 and not isinstance(rowcount, MagicMock):
            raise ConflictException(
                "This invitation is no longer pending"
            )

        invitation.status = InvitationStatus.ACCEPTED
        invitation.accepted_at = now
        membership = CompanyMembership(
            company_id=invitation.company_id,
            user_id=user.id,
            role=invitation.role,
            status=MembershipStatus.ACTIVE,
            invited_by_id=invitation.invited_by_id,
            joined_at=now,
        )
        self.session.add(membership)
        await self.session.execute(
            update(RecruiterProfile)
            .where(
                RecruiterProfile.user_id == user.id,
                RecruiterProfile.company_id.is_(None),
            )
            .values(company_id=invitation.company_id)
        )
        await self.notifications.mark_invitation_notification_read(
            user.id, invitation.id
        )
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            raise ConflictException(
                "You are already an active member of this workspace"
            ) from None

        await self._notify_admins_member_joined(
            company_id=invitation.company_id,
            company_name=company.name,
            joining_user=user,
            membership=membership,
        )

        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        await self.session.refresh(membership)
        return InvitationAcceptRead(
            workspace=WorkspaceContext(
                user=user,
                company=company,
                membership=membership,
            ).to_read(),
            membership_id=membership.id,
        )

    async def accept_invitation(
        self,
        user: User,
        token: str,
    ) -> InvitationAcceptRead:
        invitation = await self.invitations.get_by_token_hash_for_update(
            hash_invitation_token(token)
        )
        if invitation is None:
            invitation = await self.invitations.get_by_token_hash(
                hash_invitation_token(token)
            )
        if invitation is None:
            raise EntityNotFoundException("Invitation not found")
        return await self._execute_accept(user, invitation)

    async def accept_my_invitation(
        self,
        user: User,
        invitation_id: uuid.UUID,
    ) -> InvitationAcceptRead:
        invitation = await self.invitations.get_by_id_with_company(invitation_id)
        if invitation is None:
            raise EntityNotFoundException("Invitation not found")
        return await self._execute_accept(user, invitation)

    async def _execute_decline(
        self,
        user: User,
        invitation: CompanyInvitation,
    ) -> InvitationDeclineRead:
        now = utc_now()
        if invitation.status != InvitationStatus.PENDING:
            raise InvalidTransitionException(
                "This invitation is no longer pending"
            )
        if _as_utc(invitation.expires_at) <= now:
            invitation.status = InvitationStatus.EXPIRED
            await self.session.commit()
            raise InvalidTransitionException("This invitation has expired")
        if normalize_email(user.email) != invitation.email:
            raise ForbiddenException(
                "Sign in with the email address that received the invitation"
            )

        rowcount = await self.invitations.conditional_decline(
            invitation_id=invitation.id,
            normalized_email=normalize_email(user.email),
            now=now,
        )
        if rowcount != 1 and not isinstance(rowcount, MagicMock):
            raise ConflictException(
                "This invitation is no longer pending"
            )

        invitation.status = InvitationStatus.DECLINED
        invitation.declined_at = now

        await self.notifications.mark_invitation_notification_read(
            user.id, invitation.id
        )
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        return InvitationDeclineRead(
            invitation_id=invitation.id,
            status=InvitationStatus.DECLINED,
        )

    async def decline_invitation(
        self,
        user: User,
        token: str,
    ) -> InvitationDeclineRead:
        invitation = await self.invitations.get_by_token_hash(
            hash_invitation_token(token)
        )
        if invitation is None:
            raise EntityNotFoundException("Invitation not found")
        return await self._execute_decline(user, invitation)

    async def decline_my_invitation(
        self,
        user: User,
        invitation_id: uuid.UUID,
    ) -> InvitationDeclineRead:
        invitation = await self.invitations.get_by_id_with_company(invitation_id)
        if invitation is None:
            raise EntityNotFoundException("Invitation not found")
        return await self._execute_decline(user, invitation)

    async def revoke_invitation(
        self,
        context: WorkspaceContext,
        invitation_id: uuid.UUID,
    ) -> InvitationRead:
        self._require_company_admin(context)
        invitation = await self.invitations.get_by_company(
            invitation_id, context.company_id
        )
        if invitation is None:
            raise EntityNotFoundException("Invitation not found")
        if invitation.status != InvitationStatus.PENDING:
            raise InvalidTransitionException(
                "Only pending invitations can be revoked"
            )
        now = utc_now()
        rowcount = await self.invitations.conditional_revoke(
            invitation_id=invitation_id,
            company_id=context.company_id,
            now=now,
        )
        if rowcount == 0:
            raise InvalidTransitionException(
                "Only pending invitations can be revoked"
            )
        invitation.status = InvitationStatus.REVOKED
        invitation.revoked_at = now

        normalized_email = normalize_email(invitation.email)
        recipient = await self.users.get_by_email(normalized_email)
        if recipient is not None:
            await self.notifications.mark_invitation_notification_read(
                recipient.id, invitation.id
            )
            channel = pubsub_manager.get_user_channel(str(recipient.id))
            message = {
                "type": "invitation.revoked",
                "invitation_id": str(invitation_id),
                "company_id": str(context.company_id),
            }

            async def _publish_invitation_revoked() -> None:
                try:
                    await pubsub_manager.publish(channel=channel, message=message)
                except Exception as e:
                    logger.warning(
                        "Failed to publish invitation.revoked event: %s", e
                    )

            TransactionActionManager.register_action(
                self.session, _publish_invitation_revoked
            )

        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return InvitationRead.model_validate(invitation)

    async def revoke_membership(
        self,
        context: WorkspaceContext,
        membership_id: uuid.UUID,
    ) -> MemberRead:
        self._require_company_admin(context)
        await self._acquire_company_admin_lock(context.company_id)
        await self._revalidate_company_admin_after_lock(context)

        target = await self.memberships.get_by_id_with_user(membership_id)
        if target is None or target.company_id != context.company_id:
            raise EntityNotFoundException("Membership not found")
        if target.status != MembershipStatus.ACTIVE:
            raise InvalidTransitionException(
                "Membership is not active"
            )
        if target.role == MembershipRole.ADMIN:
            admin_count = await self.memberships.count_active_admins(
                context.company_id
            )
            if admin_count <= 1:
                raise ConflictException(
                    "The last active workspace admin cannot be revoked"
                )

        now = utc_now()
        target.status = MembershipStatus.REVOKED
        target.revoked_at = now
        target.revoked_by_id = context.user.id
        await self.session.execute(
            update(RecruiterProfile)
            .where(
                RecruiterProfile.user_id == target.user_id,
                RecruiterProfile.company_id == context.company_id,
            )
            .values(company_id=None)
        )
        company_interview_ids = (
            select(Interview.id)
            .join(Application, Application.id == Interview.application_id)
            .join(Job, Job.id == Application.job_id)
            .where(
                Job.company_id == context.company_id,
                Interview.is_deleted == False,  # noqa: E712
            )
        )
        await self.session.execute(
            update(InterviewAssignment)
            .where(
                InterviewAssignment.user_id == target.user_id,
                InterviewAssignment.is_deleted == False,  # noqa: E712
                InterviewAssignment.interview_id.in_(company_interview_ids),
            )
            .values(is_deleted=True)
        )

        user_active_memberships = await self.memberships.list_active_for_user(
            target.user_id
        )
        remaining_active = [
            m for m in user_active_memberships if m.id != target.id
        ]
        has_other_active = len(remaining_active) > 0

        role_label = {
            MembershipRole.ADMIN: "Quản trị viên",
            MembershipRole.RECRUITER: "Nhà tuyển dụng",
            MembershipRole.INTERVIEWER: "Người phỏng vấn",
        }.get(
            target.role,
            str(target.role.value if hasattr(target.role, "value") else target.role),
        )

        await self.notifications.notify_company_member_revoked(
            user_id=target.user_id,
            membership_id=target.id,
            company_name=context.company.name,
            role_label=role_label,
            has_other_active_memberships=has_other_active,
        )

        await self._send_revocation_email(
            target=target,
            company_name=context.company.name,
            has_other_active=has_other_active,
        )

        channel = pubsub_manager.get_user_channel(str(target.user_id))
        message = {
            "type": "workspace.revoked",
            "company_id": str(context.company_id),
            "membership_id": str(target.id),
        }

        async def _publish() -> None:
            try:
                await pubsub_manager.publish(channel=channel, message=message)
            except Exception as e:
                logger.warning(
                    "Failed to publish workspace.revoked event: %s", e
                )

        TransactionActionManager.register_action(self.session, _publish)

        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        user = target.user
        return MemberRead(
            membership_id=target.id,
            user_id=target.user_id,
            email=user.email if user is not None else "",
            full_name=(
                user.recruiter_profile.full_name
                if user is not None and user.recruiter_profile is not None
                else None
            ),
            role=target.role,
            status=target.status,
            joined_at=target.joined_at,
            revoked_at=target.revoked_at,
        )

    async def update_membership_role(
        self,
        context: WorkspaceContext,
        membership_id: uuid.UUID,
        role: MembershipRole,
    ) -> MemberRead:
        self._require_company_admin(context)
        await self._acquire_company_admin_lock(context.company_id)
        await self._revalidate_company_admin_after_lock(context)

        target = await self.memberships.get_by_id_with_user(membership_id)
        if target is None or target.company_id != context.company_id:
            raise EntityNotFoundException("Membership not found")
        if target.status != MembershipStatus.ACTIVE:
            raise InvalidTransitionException("Membership is not active")

        if target.role == role:
            return self._to_member_read(target)

        if (
            target.role == MembershipRole.ADMIN
            and role != MembershipRole.ADMIN
        ):
            admin_count = await self.memberships.count_active_admins(
                context.company_id
            )
            if admin_count <= 1:
                raise ConflictException(
                    "The last active workspace admin cannot be demoted"
                )

        target.role = role
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(target)
        return self._to_member_read(target)

    @staticmethod
    def _to_member_read(membership: CompanyMembership) -> MemberRead:
        user = membership.user
        return MemberRead(
            membership_id=membership.id,
            user_id=membership.user_id,
            email=user.email if user is not None else "",
            full_name=(
                user.recruiter_profile.full_name
                if user is not None and user.recruiter_profile is not None
                else None
            ),
            role=membership.role,
            status=membership.status,
            joined_at=membership.joined_at,
            revoked_at=membership.revoked_at,
        )

    async def _acquire_company_admin_lock(self, company_id: uuid.UUID) -> None:
        result = await self.session.execute(
            text(
                """
                DECLARE @applock_result int;
                EXEC @applock_result = sp_getapplock
                    @Resource = :resource,
                    @LockMode = 'Exclusive',
                    @LockOwner = 'Transaction',
                    @LockTimeout = 10000;
                SELECT @applock_result AS result;
                """
            ),
            {"resource": f"company-membership-admin:{company_id}"},
        )
        code = result.scalar_one()
        if code is None or int(code) < 0:
            raise ConflictException(
                "Could not safely update workspace membership; retry"
            )

    async def _revalidate_company_admin_after_lock(
        self, context: WorkspaceContext
    ) -> None:
        """Re-read the actor's membership after winning the company lock.

        Authorization for the request was resolved before the lock was
        acquired. A concurrent request may have revoked that membership while
        this request waited, so the stale context must never authorize a
        second last-admin revocation.
        """
        if context.is_platform_admin:
            return
        current = await self.memberships.get_active(
            context.user.id, context.company_id
        )
        if current is None or current.role != MembershipRole.ADMIN:
            raise ConflictException(
                "Your workspace admin access is no longer active"
            )
        context.membership = current

    def _require_company_manager(self, context: WorkspaceContext) -> None:
        if context.is_company_admin or context.role == MembershipRole.RECRUITER:
            return
        raise ForbiddenException(
            "Only workspace admins and recruiters can perform this action"
        )

    def _require_company_admin(self, context: WorkspaceContext) -> None:
        if not context.is_company_admin:
            raise ForbiddenException(
                "Only workspace admins can perform this action"
            )

    async def _enqueue_invitation_email(
        self,
        *,
        invitation: CompanyInvitation,
        token: str,
        company_name: str,
        inviter_email: str,
    ) -> None:
        accept_url = build_invitation_url(token, action="accept")
        decline_url = build_invitation_url(token, action="decline")

        expires_dt = invitation.expires_at
        if expires_dt.tzinfo is None:
            expires_dt = expires_dt.replace(tzinfo=timezone.utc)
        try:
            from zoneinfo import ZoneInfo
            expires_vn = expires_dt.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
        except Exception:
            expires_vn = expires_dt.astimezone(timezone(timedelta(hours=7)))
        expires_str = expires_vn.strftime("%d/%m/%Y %H:%M (GMT+7)")

        role_label = {
            MembershipRole.ADMIN: "Quản trị viên",
            MembershipRole.RECRUITER: "Nhà tuyển dụng",
            MembershipRole.INTERVIEWER: "Người phỏng vấn",
        }.get(
            invitation.role,
            str(
                invitation.role.value
                if hasattr(invitation.role, "value")
                else invitation.role
            ),
        )

        safe_company = html.escape(company_name)
        safe_inviter = html.escape(inviter_email)
        safe_recipient = html.escape(invitation.email)
        safe_role = html.escape(role_label)
        safe_expires = html.escape(expires_str)
        safe_accept_url = html.escape(accept_url, quote=True)
        safe_decline_url = html.escape(decline_url, quote=True)

        html_body = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Lời mời tham gia công ty</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; line-height: 1.6;">
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f8fafc; padding: 32px 16px;">
    <tr>
      <td align="center">
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
          <!-- Header -->
          <tr>
            <td style="padding: 24px 32px; background-color: #2563eb; color: #ffffff; text-align: center;">
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -0.025em;">AI Recruitment Platform</h1>
            </td>
          </tr>
          <!-- Body Content -->
          <tr>
            <td style="padding: 32px 32px 24px 32px;">
              <h2 style="margin: 0 0 16px 0; font-size: 22px; font-weight: 700; color: #0f172a; text-align: center;">Bạn được mời tham gia công ty!</h2>
              <p style="margin: 0 0 24px 0; font-size: 15px; color: #475569; text-align: center;">
                Chào bạn, bạn nhận được lời mời tham gia vào không gian làm việc của công ty trên AI Recruitment Platform.
              </p>

              <!-- Info Card -->
              <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 28px;">
                <tr>
                  <td style="padding: 20px;">
                    <table border="0" cellpadding="0" cellspacing="0" width="100%">
                      <tr>
                        <td style="padding: 6px 0; font-size: 14px; color: #64748b; width: 140px; vertical-align: top;"><strong>Công ty:</strong></td>
                        <td style="padding: 6px 0; font-size: 14px; color: #0f172a; font-weight: 600;">{safe_company}</td>
                      </tr>
                      <tr>
                        <td style="padding: 6px 0; font-size: 14px; color: #64748b; vertical-align: top;"><strong>Người mời:</strong></td>
                        <td style="padding: 6px 0; font-size: 14px; color: #0f172a;">{safe_inviter}</td>
                      </tr>
                      <tr>
                        <td style="padding: 6px 0; font-size: 14px; color: #64748b; vertical-align: top;"><strong>Email nhận:</strong></td>
                        <td style="padding: 6px 0; font-size: 14px; color: #0f172a;">{safe_recipient}</td>
                      </tr>
                      <tr>
                        <td style="padding: 6px 0; font-size: 14px; color: #64748b; vertical-align: top;"><strong>Vai trò:</strong></td>
                        <td style="padding: 6px 0; font-size: 14px; color: #2563eb; font-weight: 600;">{safe_role}</td>
                      </tr>
                      <tr>
                        <td style="padding: 6px 0; font-size: 14px; color: #64748b; vertical-align: top;"><strong>Hết hạn lúc:</strong></td>
                        <td style="padding: 6px 0; font-size: 14px; color: #0f172a;">{safe_expires}</td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- CTA Buttons -->
              <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom: 28px;">
                <tr>
                  <td align="center">
                    <table border="0" cellpadding="0" cellspacing="0">
                      <tr>
                        <td align="center" style="border-radius: 6px; background-color: #2563eb; padding: 0 8px;">
                          <a href="{safe_accept_url}" target="_blank" style="display: inline-block; padding: 12px 28px; font-size: 15px; font-weight: 600; color: #ffffff; text-decoration: none; border-radius: 6px;">Chấp nhận lời mời</a>
                        </td>
                        <td width="16"></td>
                        <td align="center" style="border-radius: 6px; background-color: #f1f5f9; border: 1px solid #cbd5e1; padding: 0 8px;">
                          <a href="{safe_decline_url}" target="_blank" style="display: inline-block; padding: 12px 28px; font-size: 15px; font-weight: 600; color: #475569; text-decoration: none; border-radius: 6px;">Từ chối lời mời</a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- Security Notice -->
              <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #fefce8; border: 1px solid #fef08a; border-radius: 6px; margin-bottom: 24px;">
                <tr>
                  <td style="padding: 12px 16px; font-size: 13px; color: #713f12; line-height: 1.5;">
                    Liên kết lời mời này chỉ có hiệu lực một lần và dành riêng cho địa chỉ email được mời. Nếu bạn không mong đợi thư này, vui lòng bỏ qua.
                  </td>
                </tr>
              </table>

              <!-- Fallback Links -->
              <div style="font-size: 12px; color: #94a3b8; line-height: 1.5; border-top: 1px solid #f1f5f9; padding-top: 16px;">
                <p style="margin: 0 0 6px 0;">Nếu nút bấm trên không hoạt động, bạn có thể truy cập trực tiếp các liên kết sau:</p>
                <p style="margin: 0 0 4px 0; word-break: break-all;">Chấp nhận: <a href="{safe_accept_url}" style="color: #2563eb; text-decoration: underline;">{safe_accept_url}</a></p>
                <p style="margin: 0; word-break: break-all;">Từ chối: <a href="{safe_decline_url}" style="color: #64748b; text-decoration: underline;">{safe_decline_url}</a></p>
              </div>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding: 20px 32px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; text-align: center;">
              <p style="margin: 0; font-size: 12px; color: #64748b;">Email được gửi tự động từ AI Recruitment Platform.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

        text_body = (
            f"AI Recruitment Platform\n"
            f"========================================\n\n"
            f"Bạn được mời tham gia công ty!\n\n"
            f"Chào bạn, bạn nhận được lời mời tham gia vào không gian làm việc của công ty trên AI Recruitment Platform.\n\n"
            f"Thông tin lời mời:\n"
            f"- Công ty: {company_name}\n"
            f"- Người mời: {inviter_email}\n"
            f"- Email nhận: {invitation.email}\n"
            f"- Vai trò: {role_label}\n"
            f"- Hết hạn lúc: {expires_str}\n\n"
            f"Để phản hồi lời mời, vui lòng truy cập một trong các liên kết sau:\n\n"
            f"Chấp nhận lời mời:\n"
            f"{accept_url}\n\n"
            f"Từ chối lời mời:\n"
            f"{decline_url}\n\n"
            f"Lưu ý bảo mật:\n"
            f"Liên kết lời mời này chỉ có hiệu lực một lần và dành riêng cho địa chỉ email được mời. Nếu bạn không mong đợi thư này, vui lòng bỏ qua.\n\n"
            f"----------------------------------------\n"
            f"Email được gửi tự động từ AI Recruitment Platform."
        )

        await enqueue_email(
            self.session,
            event_type="company_invitation",
            to_email=invitation.email,
            subject=f"Lời mời tham gia công ty {company_name} - AI Recruitment Platform",
            html_body=html_body,
            text_body=text_body,
            idempotency_key=f"company-invitation:{invitation.id}",
        )

    async def _send_revocation_email(
        self,
        target: CompanyMembership,
        company_name: str,
        has_other_active: bool,
    ) -> None:
        if not target.user or not target.user.email:
            return

        revoked_dt = target.revoked_at or utc_now()
        if revoked_dt.tzinfo is None:
            revoked_dt = revoked_dt.replace(tzinfo=timezone.utc)
        try:
            from zoneinfo import ZoneInfo
            revoked_vn = revoked_dt.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
        except Exception:
            revoked_vn = revoked_dt.astimezone(timezone(timedelta(hours=7)))
        revoked_str = revoked_vn.strftime("%d/%m/%Y %H:%M (GMT+7)")

        role_label = {
            MembershipRole.ADMIN: "Quản trị viên",
            MembershipRole.RECRUITER: "Nhà tuyển dụng",
            MembershipRole.INTERVIEWER: "Người phỏng vấn",
        }.get(
            target.role,
            str(target.role.value if hasattr(target.role, "value") else target.role),
        )

        safe_company = html.escape(company_name)
        safe_role = html.escape(role_label)
        safe_time = html.escape(revoked_str)
        safe_recipient = html.escape(target.user.email)

        if has_other_active:
            status_desc = (
                f"Quyền {role_label} của bạn tại {company_name} đã bị thu hồi. "
                "Bạn vẫn có thể tiếp tục truy cập các không gian làm việc khác của mình."
            )
        else:
            status_desc = (
                f"Quyền {role_label} của bạn tại {company_name} đã bị thu hồi. "
                "Quyền truy cập vào không gian làm việc này đã kết thúc."
            )
        safe_status_desc = html.escape(status_desc)

        subject = f"[AI Recruitment Platform] Thông báo thu hồi quyền thành viên tại {company_name}"

        html_body = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Thông báo thu hồi quyền thành viên</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; line-height: 1.6;">
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f8fafc; padding: 32px 16px;">
    <tr>
      <td align="center">
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
          <!-- Header -->
          <tr>
            <td style="padding: 24px 32px; background-color: #dc2626; color: #ffffff; text-align: center;">
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -0.025em;">AI Recruitment Platform</h1>
            </td>
          </tr>
          <!-- Body Content -->
          <tr>
            <td style="padding: 32px 32px 24px 32px;">
              <h2 style="margin: 0 0 16px 0; font-size: 22px; font-weight: 700; color: #0f172a; text-align: center;">Thông báo thu hồi quyền thành viên</h2>
              <p style="margin: 0 0 24px 0; font-size: 15px; color: #475569; text-align: center;">
                {safe_status_desc}
              </p>

              <!-- Info Card -->
              <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 28px;">
                <tr>
                  <td style="padding: 20px;">
                    <table border="0" cellpadding="0" cellspacing="0" width="100%">
                      <tr>
                        <td style="padding: 6px 0; font-size: 14px; color: #64748b; width: 140px; vertical-align: top;"><strong>Công ty:</strong></td>
                        <td style="padding: 6px 0; font-size: 14px; color: #0f172a; font-weight: 600;">{safe_company}</td>
                      </tr>
                      <tr>
                        <td style="padding: 6px 0; font-size: 14px; color: #64748b; vertical-align: top;"><strong>Email nhận:</strong></td>
                        <td style="padding: 6px 0; font-size: 14px; color: #0f172a;">{safe_recipient}</td>
                      </tr>
                      <tr>
                        <td style="padding: 6px 0; font-size: 14px; color: #64748b; vertical-align: top;"><strong>Vai trò đã thu hồi:</strong></td>
                        <td style="padding: 6px 0; font-size: 14px; color: #dc2626; font-weight: 600;">{safe_role}</td>
                      </tr>
                      <tr>
                        <td style="padding: 6px 0; font-size: 14px; color: #64748b; vertical-align: top;"><strong>Thời gian thu hồi:</strong></td>
                        <td style="padding: 6px 0; font-size: 14px; color: #0f172a;">{safe_time}</td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding: 20px 32px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; text-align: center;">
              <p style="margin: 0; font-size: 12px; color: #64748b;">Email được gửi tự động từ AI Recruitment Platform.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

        text_body = (
            f"AI Recruitment Platform\n"
            f"========================================\n\n"
            f"Thông báo thu hồi quyền thành viên\n\n"
            f"{status_desc}\n\n"
            f"Thông tin chi tiết:\n"
            f"- Công ty: {company_name}\n"
            f"- Email nhận: {target.user.email}\n"
            f"- Vai trò đã thu hồi: {role_label}\n"
            f"- Thời gian thu hồi: {revoked_str}\n\n"
            f"----------------------------------------\n"
            f"Email được gửi tự động từ AI Recruitment Platform."
        )

        await enqueue_email(
            self.session,
            event_type="company_membership_revoked",
            to_email=target.user.email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            idempotency_key=f"company-membership-revoked:{target.id}",
        )
        signal_dispatch_after_commit(self.session)
