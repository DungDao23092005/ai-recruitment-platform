from __future__ import annotations

import asyncio
import hashlib
import html
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

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
    InvitationPreviewRead,
    InvitationRead,
    MemberRead,
    WorkspaceRead,
    normalize_email,
)
from app.services.email_outbox_service import enqueue_email

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


def build_invitation_url(token: str) -> str:
    return (
        f"{settings.FRONTEND_URL.rstrip('/')}/invitations/accept"
        f"#token={token}"
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

    async def list_members(self, context: WorkspaceContext) -> list[MemberRead]:
        self._require_company_manager(context)
        memberships = await self.memberships.list_by_company(
            context.company_id,
            include_revoked=True,
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
        if existing_user is not None:
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

    async def accept_invitation(
        self,
        user: User,
        token: str,
    ) -> InvitationAcceptRead:
        invitation = await self.invitations.get_by_token_hash_for_update(
            hash_invitation_token(token)
        )
        if invitation is None:
            raise EntityNotFoundException("Invitation not found")

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

        membership = CompanyMembership(
            company_id=invitation.company_id,
            user_id=user.id,
            role=invitation.role,
            status=MembershipStatus.ACTIVE,
            invited_by_id=invitation.invited_by_id,
            joined_at=now,
        )
        self.session.add(membership)
        invitation.status = InvitationStatus.ACCEPTED
        invitation.accepted_at = now
        await self.session.execute(
            update(RecruiterProfile)
            .where(
                RecruiterProfile.user_id == user.id,
                RecruiterProfile.company_id.is_(None),
            )
            .values(company_id=invitation.company_id)
        )
        try:
            await self.session.flush()
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise ConflictException(
                "You are already an active member of this workspace"
            ) from None
        await self.session.refresh(membership)
        return InvitationAcceptRead(
            workspace=WorkspaceContext(
                user=user,
                company=company,
                membership=membership,
            ).to_read(),
            membership_id=membership.id,
        )

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
        invitation.status = InvitationStatus.REVOKED
        invitation.revoked_at = utc_now()
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(invitation)
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
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        asyncio.create_task(
            pubsub_manager.publish(
                channel=pubsub_manager.get_user_channel(str(target.user_id)),
                message={
                    "type": "workspace.revoked",
                    "company_id": str(context.company_id),
                    "membership_id": str(target.id),
                },
            )
        )
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
        invitation_url = build_invitation_url(token)
        safe_company = html.escape(company_name)
        safe_url = html.escape(invitation_url, quote=True)
        role_label = {
            MembershipRole.ADMIN: "Admin",
            MembershipRole.RECRUITER: "Recruiter",
            MembershipRole.INTERVIEWER: "Interviewer",
        }[invitation.role]
        await enqueue_email(
            self.session,
            event_type="company_invitation",
            to_email=invitation.email,
            subject=f"You are invited to join {company_name}",
            html_body=(
                f"<p>{html.escape(inviter_email)} invited you to join "
                f"<strong>{safe_company}</strong> as {role_label}.</p>"
                f'<p><a href="{safe_url}">Accept invitation</a></p>'
                f"<p>This link expires on "
                f"{invitation.expires_at.strftime('%Y-%m-%d %H:%M UTC')}.</p>"
            ),
            text_body=(
                f"{inviter_email} invited you to join {company_name} "
                f"as {role_label}.\n\n"
                f"Accept invitation: {invitation_url}\n\n"
                f"This link expires on "
                f"{invitation.expires_at.strftime('%Y-%m-%d %H:%M UTC')}."
            ),
            idempotency_key=f"company-invitation:{invitation.id}",
        )
