from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
)
from app.domain.enums import ContactRequestStatus, MembershipRole, MembershipStatus
from app.domain.models.base import utc_now
from app.models.candidate import CandidateProfile
from app.models.candidate_contact_request import (
    CandidateContactRequest,
    ContactDisclosureAuditLog,
)
from app.models.company import Company
from app.models.company_membership import CompanyMembership
from app.models.resume import Resume
from app.models.user import User
from app.schemas.ai_search import CandidatePreviewResponse
from app.schemas.contact_request import (
    CandidateContactResponse,
    ContactRequestStatusCheck,
)
from app.services.contact_request_email_service import ContactRequestEmailService
from app.services.notification_service import (
    CONTACT_REQUEST_ACCEPTED_TITLE,
    CONTACT_REQUEST_ACCEPTED_TYPE,
    CONTACT_REQUEST_DECLINED_TITLE,
    CONTACT_REQUEST_DECLINED_TYPE,
    CONTACT_REQUEST_ENTITY_TYPE,
    CONTACT_REQUEST_RECEIVED_TITLE,
    CONTACT_REQUEST_RECEIVED_TYPE,
    CONTACT_REQUEST_REVOKED_TITLE,
    CONTACT_REQUEST_REVOKED_TYPE,
    NotificationService,
)
from app.services.pii_masking import mask_parsed_resume

logger = logging.getLogger(__name__)

EXPIRATION_DAYS = 14
DECLINED_COOLDOWN_DAYS = 30
REVOKED_COOLDOWN_DAYS = 90
ROLLING_WINDOW_DAYS = 180
MAX_REQUESTS_PER_WINDOW = 2

CONTACT_REQUEST_EXPIRED_TYPE = "contact_request_expired"
CONTACT_REQUEST_EXPIRED_TITLE = "Yêu cầu liên hệ đã hết hạn"


class ContactRequestService:
    def __init__(
        self,
        session: AsyncSession,
        email_service: ContactRequestEmailService | None = None,
        notification_service: NotificationService | None = None,
    ) -> None:
        self.session = session
        self.notifications = notification_service or NotificationService(session)
        self.email_service = email_service or ContactRequestEmailService(session)

    async def _is_active_company_member(
        self, company_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[bool, User | None]:
        """Check if a user is currently an active member of the company with an active account."""
        stmt = (
            select(CompanyMembership)
            .options(selectinload(CompanyMembership.user))
            .where(
                CompanyMembership.company_id == company_id,
                CompanyMembership.user_id == user_id,
                CompanyMembership.status == MembershipStatus.ACTIVE,
                CompanyMembership.is_deleted == False,  # noqa: E712
            )
        )
        res = await self.session.execute(stmt)
        membership = res.scalar_one_or_none() if hasattr(res, "scalar_one_or_none") else None
        if (
            membership
            and hasattr(membership, "user")
            and membership.user
            and getattr(membership.user, "is_active", False)
            and not getattr(membership.user, "is_deleted", False)
        ):
            return True, membership.user
        return False, None

    async def _resolve_response_recipients(
        self, company_id: uuid.UUID, requester_user_id: uuid.UUID
    ) -> list[User]:
        """Resolve recipients for candidate response events under D2.

        Normally returns [requester_user] if the requester has active membership in company_id.
        If the initiating recruiter is no longer an active member, falls back to all active
        Workspace Admin members of that company.
        """
        is_active, requester_user = await self._is_active_company_member(
            company_id, requester_user_id
        )
        if is_active and requester_user:
            return [requester_user]

        # Fallback to all currently active Workspace Admin members
        admin_stmt = (
            select(CompanyMembership)
            .options(selectinload(CompanyMembership.user))
            .where(
                CompanyMembership.company_id == company_id,
                CompanyMembership.role == MembershipRole.ADMIN,
                CompanyMembership.status == MembershipStatus.ACTIVE,
                CompanyMembership.is_deleted == False,  # noqa: E712
            )
        )
        admin_res = await self.session.execute(admin_stmt)
        admin_memberships = (
            list(admin_res.scalars().all())
            if hasattr(admin_res, "scalars")
            else []
        )

        return [
            m.user
            for m in admin_memberships
            if hasattr(m, "user")
            and m.user
            and getattr(m.user, "is_active", False)
            and not getattr(m.user, "is_deleted", False)
        ]

    async def _expire_stale_requests(
        self,
        *,
        company_id: uuid.UUID | None = None,
        candidate_id: uuid.UUID | None = None,
        request_id: uuid.UUID | None = None,
    ) -> list[CandidateContactRequest]:
        """Deterministically update expired PENDING requests to EXPIRED status and emit notifications."""
        now = utc_now()
        stmt = (
            select(CandidateContactRequest)
            .options(
                selectinload(CandidateContactRequest.company),
                selectinload(CandidateContactRequest.candidate),
            )
            .where(
                CandidateContactRequest.status == ContactRequestStatus.PENDING,
                CandidateContactRequest.expires_at <= now,
                CandidateContactRequest.is_deleted == False,  # noqa: E712
            )
        )

        if request_id is not None:
            stmt = stmt.where(CandidateContactRequest.id == request_id)
        if company_id is not None:
            stmt = stmt.where(CandidateContactRequest.company_id == company_id)
        if candidate_id is not None:
            stmt = stmt.where(CandidateContactRequest.candidate_id == candidate_id)

        bind = self.session.bind
        dialect_name = bind.dialect.name if bind else ""
        if dialect_name != "sqlite":
            stmt = stmt.with_for_update()

        result = await self.session.execute(stmt)
        stale_requests = list(result.scalars().all()) if hasattr(result, "scalars") else []

        for req in stale_requests:
            req.status = ContactRequestStatus.EXPIRED

            # D1: Emit expiration notification & email to initiating recruiter if active
            is_active, requester_user = await self._is_active_company_member(
                req.company_id, req.requester_user_id
            )
            if is_active and requester_user:
                candidate = req.candidate
                if candidate is None:
                    candidate = await self.session.get(CandidateProfile, req.candidate_id)
                candidate_name = candidate.full_name if candidate and candidate.full_name else "Ứng viên"
                company = req.company
                if company is None:
                    company = await self.session.get(Company, req.company_id)
                company_name = company.name if company else "Doanh nghiệp"

                notif_id = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"contact_request:expired:{req.requester_user_id}:{req.id}",
                )
                await self.notifications.create_notification(
                    user_id=req.requester_user_id,
                    title=CONTACT_REQUEST_EXPIRED_TITLE,
                    content=(
                        f"Yêu cầu liên hệ với ứng viên {candidate_name} đã hết hạn sau 14 ngày. "
                        "Bạn có thể gửi lại yêu cầu khi chính sách thời gian chờ và giới hạn cho phép."
                    ),
                    notification_type=CONTACT_REQUEST_EXPIRED_TYPE,
                    entity_type=CONTACT_REQUEST_ENTITY_TYPE,
                    entity_id=req.id,
                    notification_id=notif_id,
                )
                requester_email = getattr(requester_user, "email", None)
                if requester_email:
                    await self.email_service.send_request_expired_email(
                        to_email=requester_email,
                        candidate_name=candidate_name,
                        company_name=company_name,
                        request_id=req.id,
                    )

        if stale_requests:
            await self.session.flush()

        return stale_requests

    async def check_contact_request_status(
        self,
        company_id: uuid.UUID,
        candidate_id: uuid.UUID,
    ) -> ContactRequestStatusCheck:
        """Check whether a company can send a contact request to a candidate, and current status."""
        await self._expire_stale_requests(
            company_id=company_id, candidate_id=candidate_id
        )

        now = utc_now()
        stmt = (
            select(CandidateContactRequest)
            .where(
                CandidateContactRequest.company_id == company_id,
                CandidateContactRequest.candidate_id == candidate_id,
                CandidateContactRequest.is_deleted == False,  # noqa: E712
            )
            .order_by(CandidateContactRequest.created_at.desc())
        )
        result = await self.session.execute(stmt)
        requests = list(result.scalars().all())

        if not requests:
            return ContactRequestStatusCheck(
                candidate_id=candidate_id,
                status=None,
                can_request=True,
            )

        most_recent = requests[0]
        current_status = most_recent.status
        if current_status == ContactRequestStatus.PENDING and most_recent.expires_at <= now:
            current_status = ContactRequestStatus.EXPIRED

        # Active PENDING
        if current_status == ContactRequestStatus.PENDING:
            return ContactRequestStatusCheck(
                candidate_id=candidate_id,
                status=ContactRequestStatus.PENDING,
                can_request=False,
                request_id=most_recent.id,
                reason="Yêu cầu liên hệ trước đó đang chờ phản hồi từ ứng viên.",
            )

        # Active ACCEPTED
        if current_status == ContactRequestStatus.ACCEPTED:
            return ContactRequestStatusCheck(
                candidate_id=candidate_id,
                status=ContactRequestStatus.ACCEPTED,
                can_request=False,
                request_id=most_recent.id,
                reason="Công ty đã được ứng viên cấp quyền xem thông tin liên hệ.",
            )

        # Check cooldowns from recent terminal records
        applicable_cooldown: datetime | None = None
        cooldown_reason: str | None = None

        for req in requests:
            if req.status == ContactRequestStatus.DECLINED and req.responded_at:
                cd = req.responded_at + timedelta(days=DECLINED_COOLDOWN_DAYS)
                if cd > now and (applicable_cooldown is None or cd > applicable_cooldown):
                    applicable_cooldown = cd
                    cooldown_reason = (
                        f"Ứng viên đã từ chối yêu cầu. Vui lòng thử lại sau 30 ngày kể từ ngày từ chối."
                    )
            elif req.status == ContactRequestStatus.REVOKED and req.revoked_at:
                cd = req.revoked_at + timedelta(days=REVOKED_COOLDOWN_DAYS)
                if cd > now and (applicable_cooldown is None or cd > applicable_cooldown):
                    applicable_cooldown = cd
                    cooldown_reason = (
                        f"Ứng viên đã thu hồi quyền liên hệ. Vui lòng thử lại sau 90 ngày kể từ ngày thu hồi."
                    )

        if applicable_cooldown and applicable_cooldown > now:
            return ContactRequestStatusCheck(
                candidate_id=candidate_id,
                status=current_status,
                can_request=False,
                request_id=most_recent.id,
                cooldown_until=applicable_cooldown,
                reason=cooldown_reason,
            )

        # Check rolling 180-day window limit
        rolling_cutoff = now - timedelta(days=ROLLING_WINDOW_DAYS)
        recent_requests_count = sum(
            1 for req in requests if req.created_at > rolling_cutoff
        )

        if recent_requests_count >= MAX_REQUESTS_PER_WINDOW:
            return ContactRequestStatusCheck(
                candidate_id=candidate_id,
                status=current_status,
                can_request=False,
                request_id=most_recent.id,
                reason=(
                    f"Đã đạt giới hạn tối đa {MAX_REQUESTS_PER_WINDOW} yêu cầu liên hệ trong vòng 180 ngày cho ứng viên này."
                ),
            )

        return ContactRequestStatusCheck(
            candidate_id=candidate_id,
            status=current_status,
            can_request=True,
            request_id=most_recent.id,
        )

    async def create_contact_request(
        self,
        company_id: uuid.UUID,
        candidate_id: uuid.UUID,
        requester_user_id: uuid.UUID,
    ) -> CandidateContactRequest:
        """Create a new contact request under anti-spam policies and atomic locking."""
        # Validate candidate discoverability and active status
        candidate_stmt = (
            select(CandidateProfile)
            .options(selectinload(CandidateProfile.user))
            .where(
                CandidateProfile.id == candidate_id,
                CandidateProfile.is_deleted == False,  # noqa: E712
            )
        )
        cand_res = await self.session.execute(candidate_stmt)
        candidate = cand_res.scalar_one_or_none()

        if candidate is None:
            raise EntityNotFoundException("Hồ sơ ứng viên không tồn tại.")

        if not candidate.is_searchable:
            raise ForbiddenException("Ứng viên chưa bật chế độ cho phép tìm kiếm công khai.")

        if not candidate.user or not candidate.user.is_active or candidate.user.is_deleted:
            raise ForbiddenException("Tài khoản ứng viên không còn hoạt động.")

        # Concurrency control: select existing rows for this company/candidate pair
        now = utc_now()
        stmt = (
            select(CandidateContactRequest)
            .where(
                CandidateContactRequest.company_id == company_id,
                CandidateContactRequest.candidate_id == candidate_id,
                CandidateContactRequest.is_deleted == False,  # noqa: E712
            )
            .order_by(CandidateContactRequest.created_at.desc())
        )
        # Apply row-level lock if supported by the engine (skip for SQLite in unit tests)
        bind = self.session.bind
        dialect_name = bind.dialect.name if bind else ""
        if dialect_name != "sqlite":
            stmt = stmt.with_for_update()

        result = await self.session.execute(stmt)
        requests = list(result.scalars().all())

        # Expire any stale requests on the fly
        stale_updated = False
        for req in requests:
            if req.status == ContactRequestStatus.PENDING and req.expires_at <= now:
                req.status = ContactRequestStatus.EXPIRED
                stale_updated = True
        if stale_updated:
            await self.session.flush()

        # Check for active PENDING or ACCEPTED
        for req in requests:
            if req.status == ContactRequestStatus.PENDING:
                raise ConflictException("Yêu cầu liên hệ trước đó đang chờ phản hồi từ ứng viên.")
            if req.status == ContactRequestStatus.ACCEPTED:
                raise ConflictException("Công ty đã được ứng viên cấp quyền xem thông tin liên hệ.")

        # Check cooldowns from DECLINED or REVOKED records
        for req in requests:
            if req.status == ContactRequestStatus.DECLINED and req.responded_at:
                cooldown = req.responded_at + timedelta(days=DECLINED_COOLDOWN_DAYS)
                if now < cooldown:
                    raise ConflictException(
                        "Ứng viên đã từ chối yêu cầu. Vui lòng thử lại sau 30 ngày kể từ ngày từ chối."
                    )
            elif req.status == ContactRequestStatus.REVOKED and req.revoked_at:
                cooldown = req.revoked_at + timedelta(days=REVOKED_COOLDOWN_DAYS)
                if now < cooldown:
                    raise ConflictException(
                        "Ứng viên đã thu hồi quyền liên hệ. Vui lòng thử lại sau 90 ngày kể từ ngày thu hồi."
                    )

        # Check rolling 180-day window limit
        rolling_cutoff = now - timedelta(days=ROLLING_WINDOW_DAYS)
        recent_count = sum(1 for req in requests if req.created_at > rolling_cutoff)
        if recent_count >= MAX_REQUESTS_PER_WINDOW:
            raise ConflictException(
                f"Đã đạt giới hạn tối đa {MAX_REQUESTS_PER_WINDOW} yêu cầu liên hệ trong vòng 180 ngày cho ứng viên này."
            )

        # Create new request
        expires_at = now + timedelta(days=EXPIRATION_DAYS)
        contact_request = CandidateContactRequest(
            company_id=company_id,
            candidate_id=candidate_id,
            requester_user_id=requester_user_id,
            status=ContactRequestStatus.PENDING,
            expires_at=expires_at,
        )
        self.session.add(contact_request)
        await self.session.flush()

        # Send notification to candidate
        company = await self.session.get(Company, company_id)
        company_name = company.name if company else "Một doanh nghiệp"

        notif_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"contact_request:received:{candidate.user_id}:{contact_request.id}",
        )
        await self.notifications.create_notification(
            user_id=candidate.user_id,
            title=CONTACT_REQUEST_RECEIVED_TITLE,
            content=f"Doanh nghiệp {company_name} muốn kết nối và xem thông tin liên hệ của bạn.",
            notification_type=CONTACT_REQUEST_RECEIVED_TYPE,
            entity_type=CONTACT_REQUEST_ENTITY_TYPE,
            entity_id=contact_request.id,
            notification_id=notif_id,
        )

        if candidate.user and candidate.user.email:
            candidate_name = candidate.full_name or "Ứng viên"
            await self.email_service.send_request_received_email(
                to_email=candidate.user.email,
                candidate_name=candidate_name,
                company_name=company_name,
                request_id=contact_request.id,
            )

        return contact_request

    async def list_for_company(
        self,
        company_id: uuid.UUID,
        status: ContactRequestStatus | None = None,
    ) -> list[CandidateContactRequest]:
        """List contact requests created by a company, with lazy expiration applied."""
        await self._expire_stale_requests(company_id=company_id)

        stmt = (
            select(CandidateContactRequest)
            .options(
                selectinload(CandidateContactRequest.candidate),
                selectinload(CandidateContactRequest.company),
            )
            .where(
                CandidateContactRequest.company_id == company_id,
                CandidateContactRequest.is_deleted == False,  # noqa: E712
            )
            .order_by(CandidateContactRequest.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(CandidateContactRequest.status == status)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_candidate(
        self,
        candidate_id: uuid.UUID,
        status: ContactRequestStatus | None = None,
    ) -> list[CandidateContactRequest]:
        """List incoming contact requests for a candidate, with lazy expiration applied."""
        await self._expire_stale_requests(candidate_id=candidate_id)

        stmt = (
            select(CandidateContactRequest)
            .options(
                selectinload(CandidateContactRequest.company),
                selectinload(CandidateContactRequest.candidate),
            )
            .where(
                CandidateContactRequest.candidate_id == candidate_id,
                CandidateContactRequest.is_deleted == False,  # noqa: E712
            )
            .order_by(CandidateContactRequest.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(CandidateContactRequest.status == status)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_request_with_relations(
        self, request_id: uuid.UUID
    ) -> CandidateContactRequest | None:
        stmt = (
            select(CandidateContactRequest)
            .options(
                selectinload(CandidateContactRequest.company),
                selectinload(CandidateContactRequest.candidate),
            )
            .where(
                CandidateContactRequest.id == request_id,
                CandidateContactRequest.is_deleted == False,  # noqa: E712
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def accept_request(
        self,
        request_id: uuid.UUID,
        candidate_id: uuid.UUID,
    ) -> CandidateContactRequest:
        """Candidate accepts an incoming contact request."""
        await self._expire_stale_requests(request_id=request_id)

        req = await self._get_request_with_relations(request_id)
        if req is None or req.is_deleted or req.candidate_id != candidate_id:
            raise EntityNotFoundException("Yêu cầu liên hệ không tồn tại.")

        now = utc_now()
        if req.status == ContactRequestStatus.PENDING and req.expires_at <= now:
            req.status = ContactRequestStatus.EXPIRED
            await self.session.flush()

        if req.status != ContactRequestStatus.PENDING:
            raise ConflictException("Yêu cầu liên hệ không ở trạng thái chờ phản hồi.")

        req.status = ContactRequestStatus.ACCEPTED
        req.responded_at = now
        await self.session.flush()

        # Notify requester or fallback to active Workspace Admins (D2)
        recipients = await self._resolve_response_recipients(req.company_id, req.requester_user_id)
        candidate = await self.session.get(CandidateProfile, candidate_id)
        candidate_name = getattr(candidate, "full_name", None) or "Ứng viên"
        company = await self.session.get(Company, req.company_id)
        company_name = getattr(company, "name", None) or "Doanh nghiệp"

        for recipient in recipients:
            is_fallback = recipient.id != req.requester_user_id
            notif_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"contact_request:accepted:{recipient.id}:{req.id}",
            )
            await self.notifications.create_notification(
                user_id=recipient.id,
                title=CONTACT_REQUEST_ACCEPTED_TITLE,
                content=f"Ứng viên {candidate_name} đã chấp nhận yêu cầu liên hệ từ công ty bạn.",
                notification_type=CONTACT_REQUEST_ACCEPTED_TYPE,
                entity_type=CONTACT_REQUEST_ENTITY_TYPE,
                entity_id=req.id,
                notification_id=notif_id,
            )
            recipient_email = getattr(recipient, "email", None)
            if recipient_email:
                await self.email_service.send_request_accepted_email(
                    to_email=recipient_email,
                    candidate_name=candidate_name,
                    company_name=company_name,
                    request_id=req.id,
                    recipient_user_id=recipient.id if is_fallback else None,
                )

        # Send security confirmation email to candidate (Q1)
        candidate_user = getattr(candidate, "user", None)
        if candidate_user is None and hasattr(candidate, "user_id") and candidate.user_id:
            candidate_user = await self.session.get(User, candidate.user_id)
        candidate_email = getattr(candidate_user, "email", None) if candidate_user else None
        if candidate_email:
            await self.email_service.send_candidate_authorization_granted_email(
                to_email=candidate_email,
                candidate_name=candidate_name,
                company_name=company_name,
                request_id=req.id,
            )

        return req

    async def decline_request(
        self,
        request_id: uuid.UUID,
        candidate_id: uuid.UUID,
    ) -> CandidateContactRequest:
        """Candidate declines an incoming contact request."""
        await self._expire_stale_requests(request_id=request_id)

        req = await self._get_request_with_relations(request_id)
        if req is None or req.is_deleted or req.candidate_id != candidate_id:
            raise EntityNotFoundException("Yêu cầu liên hệ không tồn tại.")

        now = utc_now()
        if req.status == ContactRequestStatus.PENDING and req.expires_at <= now:
            req.status = ContactRequestStatus.EXPIRED
            await self.session.flush()

        if req.status != ContactRequestStatus.PENDING:
            raise ConflictException("Yêu cầu liên hệ không ở trạng thái chờ phản hồi.")

        req.status = ContactRequestStatus.DECLINED
        req.responded_at = now
        await self.session.flush()

        # Notify requester or fallback to active Workspace Admins (D2)
        recipients = await self._resolve_response_recipients(req.company_id, req.requester_user_id)
        candidate = await self.session.get(CandidateProfile, candidate_id)
        candidate_name = getattr(candidate, "full_name", None) or "Ứng viên"
        company = await self.session.get(Company, req.company_id)
        company_name = getattr(company, "name", None) or "Doanh nghiệp"

        for recipient in recipients:
            is_fallback = recipient.id != req.requester_user_id
            notif_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"contact_request:declined:{recipient.id}:{req.id}",
            )
            await self.notifications.create_notification(
                user_id=recipient.id,
                title=CONTACT_REQUEST_DECLINED_TITLE,
                content=(
                    f"Ứng viên {candidate_name} đã từ chối yêu cầu liên hệ. "
                    "Công ty có thể gửi lại yêu cầu sau 30 ngày thời gian chờ, "
                    "tùy thuộc vào giới hạn yêu cầu và các chính sách hệ thống áp dụng."
                ),
                notification_type=CONTACT_REQUEST_DECLINED_TYPE,
                entity_type=CONTACT_REQUEST_ENTITY_TYPE,
                entity_id=req.id,
                notification_id=notif_id,
            )
            recipient_email = getattr(recipient, "email", None)
            if recipient_email:
                await self.email_service.send_request_declined_email(
                    to_email=recipient_email,
                    candidate_name=candidate_name,
                    company_name=company_name,
                    request_id=req.id,
                    recipient_user_id=recipient.id if is_fallback else None,
                )

        return req

    async def revoke_authorization(
        self,
        request_id: uuid.UUID,
        candidate_id: uuid.UUID,
    ) -> CandidateContactRequest:
        """Candidate revokes previously accepted contact authorization."""
        req = await self._get_request_with_relations(request_id)
        if req is None or req.is_deleted or req.candidate_id != candidate_id:
            raise EntityNotFoundException("Yêu cầu liên hệ không tồn tại.")

        if req.status != ContactRequestStatus.ACCEPTED:
            raise ConflictException("Chỉ có thể thu hồi quyền liên hệ đã được chấp nhận.")

        now = utc_now()
        req.status = ContactRequestStatus.REVOKED
        req.revoked_at = now
        await self.session.flush()
        await self.session.refresh(req)

        # Notify requester or fallback to active Workspace Admins (D2)
        recipients = await self._resolve_response_recipients(req.company_id, req.requester_user_id)
        candidate = await self.session.get(CandidateProfile, candidate_id)
        candidate_name = getattr(candidate, "full_name", None) or "Ứng viên"
        company = await self.session.get(Company, req.company_id)
        company_name = getattr(company, "name", None) or "Doanh nghiệp"

        for recipient in recipients:
            is_fallback = recipient.id != req.requester_user_id
            notif_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"contact_request:revoked:{recipient.id}:{req.id}",
            )
            await self.notifications.create_notification(
                user_id=recipient.id,
                title=CONTACT_REQUEST_REVOKED_TITLE,
                content=(
                    f"Ứng viên {candidate_name} đã thu hồi quyền liên hệ. "
                    "Công ty có thể gửi lại yêu cầu sau 90 ngày thời gian chờ, "
                    "tùy thuộc vào giới hạn yêu cầu và các chính sách hệ thống áp dụng."
                ),
                notification_type=CONTACT_REQUEST_REVOKED_TYPE,
                entity_type=CONTACT_REQUEST_ENTITY_TYPE,
                entity_id=req.id,
                notification_id=notif_id,
            )
            recipient_email = getattr(recipient, "email", None)
            if recipient_email:
                await self.email_service.send_request_revoked_email(
                    to_email=recipient_email,
                    candidate_name=candidate_name,
                    company_name=company_name,
                    request_id=req.id,
                    recipient_user_id=recipient.id if is_fallback else None,
                )

        # Send security confirmation email to candidate (Q1)
        candidate_user = getattr(candidate, "user", None)
        if candidate_user is None and hasattr(candidate, "user_id") and candidate.user_id:
            candidate_user = await self.session.get(User, candidate.user_id)
        candidate_email = getattr(candidate_user, "email", None) if candidate_user else None
        if candidate_email:
            await self.email_service.send_candidate_authorization_revoked_email(
                to_email=candidate_email,
                candidate_name=candidate_name,
                company_name=company_name,
                request_id=req.id,
            )

        return req

    async def disclose_contact_details(
        self,
        company_id: uuid.UUID,
        candidate_id: uuid.UUID,
        disclosed_to_user_id: uuid.UUID,
    ) -> CandidateContactResponse:
        """Dedicated authorized contact disclosure endpoint.

        Verifies:
        1. Recruiter user has active membership in company_id.
        2. Active ACCEPTED contact request exists for (company_id, candidate_id).
        Creates an append-only metadata audit log and returns email and phone.
        """
        # 1. Verify active company membership
        membership_stmt = (
            select(CompanyMembership)
            .where(
                CompanyMembership.company_id == company_id,
                CompanyMembership.user_id == disclosed_to_user_id,
                CompanyMembership.status == MembershipStatus.ACTIVE,
                CompanyMembership.is_deleted == False,  # noqa: E712
            )
        )
        mem_res = await self.session.execute(membership_stmt)
        membership = mem_res.scalar_one_or_none()
        if membership is None:
            raise ForbiddenException("Bạn không có quyền truy cập thông tin liên hệ cho doanh nghiệp này.")

        # 2. Verify active ACCEPTED contact authorization
        req_stmt = (
            select(CandidateContactRequest)
            .where(
                CandidateContactRequest.company_id == company_id,
                CandidateContactRequest.candidate_id == candidate_id,
                CandidateContactRequest.status == ContactRequestStatus.ACCEPTED,
                CandidateContactRequest.is_deleted == False,  # noqa: E712
            )
        )
        req_res = await self.session.execute(req_stmt)
        active_req = req_res.scalar_one_or_none()
        if active_req is None:
            raise ForbiddenException("Doanh nghiệp chưa được cấp quyền xem thông tin liên hệ của ứng viên này.")

        # 3. Fetch candidate user email and profile phone
        cand_stmt = (
            select(CandidateProfile)
            .options(selectinload(CandidateProfile.user))
            .where(CandidateProfile.id == candidate_id)
        )
        cand_res = await self.session.execute(cand_stmt)
        candidate = cand_res.scalar_one_or_none()
        if candidate is None or not candidate.user:
            raise EntityNotFoundException("Hồ sơ ứng viên không tồn tại.")

        # 4. Create append-only metadata audit record (never contains email or phone)
        audit_log = ContactDisclosureAuditLog(
            contact_request_id=active_req.id,
            company_id=company_id,
            candidate_id=candidate_id,
            disclosed_to_user_id=disclosed_to_user_id,
            disclosed_at=utc_now(),
        )
        self.session.add(audit_log)
        await self.session.flush()

        return CandidateContactResponse(
            candidate_id=candidate.id,
            full_name=candidate.full_name,
            email=candidate.user.email,
            phone=candidate.phone,
            disclosed_at=audit_log.disclosed_at,
        )

    async def get_candidate_preview(
        self,
        candidate_id: uuid.UUID,
        company_id: uuid.UUID | None = None,
    ) -> CandidatePreviewResponse:
        """Fetch candidate professional details with PII scrubbed/masked.

        Never returns email or phone, even when contact status is ACCEPTED.
        """
        # Fetch candidate profile and check eligibility
        cand_stmt = (
            select(CandidateProfile)
            .options(selectinload(CandidateProfile.user))
            .where(
                CandidateProfile.id == candidate_id,
                CandidateProfile.is_deleted == False,  # noqa: E712
            )
        )
        cand_res = await self.session.execute(cand_stmt)
        candidate = cand_res.scalar_one_or_none()

        if candidate is None:
            raise EntityNotFoundException("Hồ sơ ứng viên không tồn tại.")

        if not candidate.is_searchable:
            raise ForbiddenException("Ứng viên chưa bật chế độ cho phép tìm kiếm công khai.")

        if not candidate.user or not candidate.user.is_active or candidate.user.is_deleted:
            raise ForbiddenException("Tài khoản ứng viên không còn hoạt động.")

        # Fetch confirmed primary resume
        resume_stmt = (
            select(Resume)
            .where(
                Resume.candidate_id == candidate_id,
                Resume.is_confirmed == True,  # noqa: E712
                Resume.is_primary == True,  # noqa: E712
                Resume.is_deleted == False,  # noqa: E712
            )
        )
        resume_res = await self.session.execute(resume_stmt)
        resume = resume_res.scalar_one_or_none()

        # Mask parsed resume data
        masked_data = mask_parsed_resume(resume.parsed_data) if resume and resume.parsed_data else None

        # Check contact request status for the company
        if company_id is not None:
            status_check = await self.check_contact_request_status(company_id, candidate_id)
        else:
            status_check = ContactRequestStatusCheck(
                status=None,
                request_id=None,
                can_request=True,
                cooldown_until=None,
            )

        # Build response
        skills = masked_data.skills if masked_data else []
        summary = masked_data.summary if masked_data else None
        total_years = masked_data.total_years_experience if masked_data else None

        experiences: list[dict] = []
        if masked_data and masked_data.experiences:
            for exp in masked_data.experiences:
                experiences.append({
                    "company": exp.company,
                    "position": exp.position,
                    "start_date": exp.start_date,
                    "end_date": exp.end_date,
                    "is_current": exp.is_current,
                    "description": exp.description,
                    "skills_used": exp.skills_used,
                })

        education: list[dict] = []
        if masked_data and masked_data.education:
            for edu in masked_data.education:
                education.append({
                    "institution": edu.institution,
                    "degree": edu.degree,
                    "field_of_study": edu.field_of_study,
                    "start_year": edu.start_year,
                    "end_year": edu.end_year,
                })

        return CandidatePreviewResponse(
            id=candidate.id,
            full_name=candidate.full_name,
            title=candidate.title,
            summary=summary,
            total_years_experience=total_years,
            skills=skills,
            experiences=experiences,
            education=education,
            contact_request_status=status_check.status,
            contact_request_id=status_check.request_id,
            can_request_contact=status_check.can_request,
            cooldown_until=status_check.cooldown_until,
        )
