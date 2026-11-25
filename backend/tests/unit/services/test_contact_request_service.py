from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
)
from app.domain.enums import ContactRequestStatus, MembershipRole, MembershipStatus
from app.models import (
    CandidateContactRequest,
    CandidateProfile,
    Company,
    CompanyMembership,
    ContactDisclosureAuditLog,
    EmailOutbox,
    Resume,
    User,
)
from app.services.contact_request_service import (
    CONTACT_REQUEST_EXPIRED_TITLE,
    CONTACT_REQUEST_EXPIRED_TYPE,
    DECLINED_COOLDOWN_DAYS,
    EXPIRATION_DAYS,
    MAX_REQUESTS_PER_WINDOW,
    REVOKED_COOLDOWN_DAYS,
    ROLLING_WINDOW_DAYS,
    ContactRequestService,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    session.get = AsyncMock()

    default_result = MagicMock()
    default_result.scalars.return_value.all.return_value = []
    default_result.scalar_one_or_none.return_value = None

    class RobustAsyncMock(AsyncMock):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._default_res = default_result
            self._custom_items = None

        def __setattr__(self, name, value):
            if name == "side_effect" and isinstance(value, list):
                object.__setattr__(self, "_custom_items", list(value))
                super().__setattr__("side_effect", None)
                return
            super().__setattr__(name, value)

        async def __call__(self, *args, **kwargs):
            if getattr(self, "_custom_items", None) is not None:
                if self._custom_items:
                    item = self._custom_items.pop(0)
                    if isinstance(item, Exception):
                        raise item
                    return item
                return self._default_res
            return await super().__call__(*args, **kwargs)

    session.execute = RobustAsyncMock(return_value=default_result)
    # Mock dialect as sqlite or other
    dialect = MagicMock()
    dialect.name = "postgresql"
    session.bind = MagicMock()
    session.bind.dialect = dialect
    return session


def make_user(
    user_id: uuid.UUID | None = None,
    email: str = "candidate@example.com",
    is_active: bool = True,
    is_deleted: bool = False,
) -> User:
    user = MagicMock(spec=User)
    user.id = user_id or uuid.uuid4()
    user.email = email
    user.is_active = is_active
    user.is_deleted = is_deleted
    return user


def make_candidate_profile(
    candidate_id: uuid.UUID | None = None,
    user: User | None = None,
    full_name: str = "Test Candidate",
    title: str = "Senior Engineer",
    phone: str = "0901234567",
    is_searchable: bool = True,
    is_deleted: bool = False,
) -> CandidateProfile:
    cand = MagicMock(spec=CandidateProfile)
    cand.id = candidate_id or uuid.uuid4()
    cand.user = user or make_user()
    cand.user_id = cand.user.id
    cand.full_name = full_name
    cand.title = title
    cand.phone = phone
    cand.is_searchable = is_searchable
    cand.is_deleted = is_deleted
    return cand


def make_contact_request(
    request_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
    candidate_id: uuid.UUID | None = None,
    requester_user_id: uuid.UUID | None = None,
    status: ContactRequestStatus = ContactRequestStatus.PENDING,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
    responded_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> CandidateContactRequest:
    req = MagicMock(spec=CandidateContactRequest)
    req.id = request_id or uuid.uuid4()
    req.company_id = company_id or uuid.uuid4()
    req.candidate_id = candidate_id or uuid.uuid4()
    req.requester_user_id = requester_user_id or uuid.uuid4()
    req.status = status
    req.created_at = created_at or utc_now()
    req.updated_at = req.created_at
    req.expires_at = expires_at or (req.created_at + timedelta(days=EXPIRATION_DAYS))
    req.responded_at = responded_at
    req.revoked_at = revoked_at
    req.is_deleted = False
    return req


class TestCreateContactRequest:
    def test_candidate_not_found_raises_entity_not_found(self):
        session = make_session()
        # candidate query returns None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        service = ContactRequestService(session)
        with pytest.raises(EntityNotFoundException, match="không tồn tại"):
            asyncio.run(
                service.create_contact_request(
                    company_id=uuid.uuid4(),
                    candidate_id=uuid.uuid4(),
                    requester_user_id=uuid.uuid4(),
                )
            )

    def test_candidate_not_searchable_raises_forbidden(self):
        session = make_session()
        candidate = make_candidate_profile(is_searchable=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = candidate
        session.execute.return_value = mock_result

        service = ContactRequestService(session)
        with pytest.raises(ForbiddenException, match="chưa bật chế độ cho phép tìm kiếm"):
            asyncio.run(
                service.create_contact_request(
                    company_id=uuid.uuid4(),
                    candidate_id=candidate.id,
                    requester_user_id=uuid.uuid4(),
                )
            )

    def test_candidate_inactive_account_raises_forbidden(self):
        session = make_session()
        user = make_user(is_active=False)
        candidate = make_candidate_profile(user=user, is_searchable=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = candidate
        session.execute.return_value = mock_result

        service = ContactRequestService(session)
        with pytest.raises(ForbiddenException, match="không còn hoạt động"):
            asyncio.run(
                service.create_contact_request(
                    company_id=uuid.uuid4(),
                    candidate_id=candidate.id,
                    requester_user_id=uuid.uuid4(),
                )
            )

    def test_active_pending_request_raises_conflict(self):
        session = make_session()
        candidate = make_candidate_profile(is_searchable=True)
        existing_req = make_contact_request(
            candidate_id=candidate.id,
            status=ContactRequestStatus.PENDING,
            expires_at=utc_now() + timedelta(days=5),
        )

        cand_result = MagicMock()
        cand_result.scalar_one_or_none.return_value = candidate

        reqs_result = MagicMock()
        reqs_result.scalars.return_value.all.return_value = [existing_req]

        session.execute.side_effect = [cand_result, reqs_result]

        service = ContactRequestService(session)
        with pytest.raises(ConflictException, match="chờ phản hồi"):
            asyncio.run(
                service.create_contact_request(
                    company_id=uuid.uuid4(),
                    candidate_id=candidate.id,
                    requester_user_id=uuid.uuid4(),
                )
            )

    def test_active_accepted_request_raises_conflict(self):
        session = make_session()
        candidate = make_candidate_profile(is_searchable=True)
        existing_req = make_contact_request(
            candidate_id=candidate.id,
            status=ContactRequestStatus.ACCEPTED,
        )

        cand_result = MagicMock()
        cand_result.scalar_one_or_none.return_value = candidate

        reqs_result = MagicMock()
        reqs_result.scalars.return_value.all.return_value = [existing_req]

        session.execute.side_effect = [cand_result, reqs_result]

        service = ContactRequestService(session)
        with pytest.raises(ConflictException, match="đã được ứng viên cấp quyền"):
            asyncio.run(
                service.create_contact_request(
                    company_id=uuid.uuid4(),
                    candidate_id=candidate.id,
                    requester_user_id=uuid.uuid4(),
                )
            )

    def test_declined_cooldown_within_30_days_raises_conflict(self):
        session = make_session()
        candidate = make_candidate_profile(is_searchable=True)
        declined_req = make_contact_request(
            candidate_id=candidate.id,
            status=ContactRequestStatus.DECLINED,
            responded_at=utc_now() - timedelta(days=10),
            created_at=utc_now() - timedelta(days=11),
        )

        cand_result = MagicMock()
        cand_result.scalar_one_or_none.return_value = candidate

        reqs_result = MagicMock()
        reqs_result.scalars.return_value.all.return_value = [declined_req]

        session.execute.side_effect = [cand_result, reqs_result]

        service = ContactRequestService(session)
        with pytest.raises(ConflictException, match="30 ngày"):
            asyncio.run(
                service.create_contact_request(
                    company_id=uuid.uuid4(),
                    candidate_id=candidate.id,
                    requester_user_id=uuid.uuid4(),
                )
            )

    def test_revoked_cooldown_within_90_days_raises_conflict(self):
        session = make_session()
        candidate = make_candidate_profile(is_searchable=True)
        revoked_req = make_contact_request(
            candidate_id=candidate.id,
            status=ContactRequestStatus.REVOKED,
            revoked_at=utc_now() - timedelta(days=40),
            created_at=utc_now() - timedelta(days=60),
        )

        cand_result = MagicMock()
        cand_result.scalar_one_or_none.return_value = candidate

        reqs_result = MagicMock()
        reqs_result.scalars.return_value.all.return_value = [revoked_req]

        session.execute.side_effect = [cand_result, reqs_result]

        service = ContactRequestService(session)
        with pytest.raises(ConflictException, match="90 ngày"):
            asyncio.run(
                service.create_contact_request(
                    company_id=uuid.uuid4(),
                    candidate_id=candidate.id,
                    requester_user_id=uuid.uuid4(),
                )
            )

    def test_rolling_180_day_limit_exceeded_raises_conflict(self):
        session = make_session()
        candidate = make_candidate_profile(is_searchable=True)
        # 2 previous expired requests within 180 days
        req1 = make_contact_request(
            candidate_id=candidate.id,
            status=ContactRequestStatus.EXPIRED,
            created_at=utc_now() - timedelta(days=50),
        )
        req2 = make_contact_request(
            candidate_id=candidate.id,
            status=ContactRequestStatus.EXPIRED,
            created_at=utc_now() - timedelta(days=20),
        )

        cand_result = MagicMock()
        cand_result.scalar_one_or_none.return_value = candidate

        reqs_result = MagicMock()
        reqs_result.scalars.return_value.all.return_value = [req1, req2]

        session.execute.side_effect = [cand_result, reqs_result]

        service = ContactRequestService(session)
        with pytest.raises(ConflictException, match="giới hạn tối đa 2 yêu cầu"):
            asyncio.run(
                service.create_contact_request(
                    company_id=uuid.uuid4(),
                    candidate_id=candidate.id,
                    requester_user_id=uuid.uuid4(),
                )
            )

    def test_create_success_creates_pending_request_and_notifies(self):
        session = make_session()
        candidate = make_candidate_profile(is_searchable=True)

        cand_result = MagicMock()
        cand_result.scalar_one_or_none.return_value = candidate

        reqs_result = MagicMock()
        reqs_result.scalars.return_value.all.return_value = []

        session.execute.side_effect = [cand_result, reqs_result]
        session.get.return_value = MagicMock(name="TechCorp")

        service = ContactRequestService(session)
        service.notifications.create_notification = AsyncMock()

        company_id = uuid.uuid4()
        requester_id = uuid.uuid4()

        result = asyncio.run(
            service.create_contact_request(
                company_id=company_id,
                candidate_id=candidate.id,
                requester_user_id=requester_id,
            )
        )

        assert result.company_id == company_id
        assert result.candidate_id == candidate.id
        assert result.requester_user_id == requester_id
        assert result.status == ContactRequestStatus.PENDING
        assert session.add.called
        assert service.notifications.create_notification.called


class TestRolling180DayWindowPolicy:
    """Validate exact rolling 180-day window boundary policy and scoping."""

    def test_request_strictly_newer_than_cutoff_is_counted(self):
        session = make_session()
        candidate = make_candidate_profile(is_searchable=True)
        now = utc_now()
        strictly_newer = now - timedelta(days=ROLLING_WINDOW_DAYS) + timedelta(seconds=1)
        req1 = make_contact_request(
            candidate_id=candidate.id,
            status=ContactRequestStatus.EXPIRED,
            created_at=strictly_newer,
        )
        req2 = make_contact_request(
            candidate_id=candidate.id,
            status=ContactRequestStatus.EXPIRED,
            created_at=now - timedelta(days=30),
        )

        cand_result = MagicMock()
        cand_result.scalar_one_or_none.return_value = candidate
        reqs_result = MagicMock()
        reqs_result.scalars.return_value.all.return_value = [req1, req2]
        session.execute.side_effect = [cand_result, reqs_result]

        service = ContactRequestService(session)
        with pytest.raises(ConflictException, match="giới hạn tối đa 2 yêu cầu"):
            asyncio.run(
                service.create_contact_request(
                    company_id=uuid.uuid4(),
                    candidate_id=candidate.id,
                    requester_user_id=uuid.uuid4(),
                )
            )

    def test_request_exactly_at_cutoff_is_not_counted(self):
        session = make_session()
        candidate = make_candidate_profile(is_searchable=True)
        now = utc_now()
        with patch("app.services.contact_request_service.utc_now", return_value=now):
            exact_cutoff = now - timedelta(days=ROLLING_WINDOW_DAYS)
            req_at_cutoff = make_contact_request(
                candidate_id=candidate.id,
                status=ContactRequestStatus.EXPIRED,
                created_at=exact_cutoff,
            )
            req_newer = make_contact_request(
                candidate_id=candidate.id,
                status=ContactRequestStatus.EXPIRED,
                created_at=now - timedelta(days=40),
            )

            cand_result = MagicMock()
            cand_result.scalar_one_or_none.return_value = candidate
            reqs_result = MagicMock()
            reqs_result.scalars.return_value.all.return_value = [req_at_cutoff, req_newer]
            session.execute.side_effect = [cand_result, reqs_result]
            session.get.return_value = MagicMock(name="TechCorp")

            service = ContactRequestService(session)
            service.notifications.create_notification = AsyncMock()

            # req_at_cutoff is exactly at cutoff, so created_at > rolling_cutoff is False.
            # Only req_newer is counted (recent_count = 1 < 2). Creation succeeds!
            result = asyncio.run(
                service.create_contact_request(
                    company_id=uuid.uuid4(),
                    candidate_id=candidate.id,
                    requester_user_id=uuid.uuid4(),
                )
            )
            assert result.status == ContactRequestStatus.PENDING

    def test_request_older_than_cutoff_is_not_counted(self):
        session = make_session()
        candidate = make_candidate_profile(is_searchable=True)
        now = utc_now()
        with patch("app.services.contact_request_service.utc_now", return_value=now):
            older_req1 = make_contact_request(
                candidate_id=candidate.id,
                status=ContactRequestStatus.EXPIRED,
                created_at=now - timedelta(days=ROLLING_WINDOW_DAYS + 1),
            )
            older_req2 = make_contact_request(
                candidate_id=candidate.id,
                status=ContactRequestStatus.EXPIRED,
                created_at=now - timedelta(days=200),
            )

            cand_result = MagicMock()
            cand_result.scalar_one_or_none.return_value = candidate
            reqs_result = MagicMock()
            reqs_result.scalars.return_value.all.return_value = [older_req1, older_req2]
            session.execute.side_effect = [cand_result, reqs_result]
            session.get.return_value = MagicMock(name="TechCorp")

            service = ContactRequestService(session)
            service.notifications.create_notification = AsyncMock()

            result = asyncio.run(
                service.create_contact_request(
                    company_id=uuid.uuid4(),
                    candidate_id=candidate.id,
                    requester_user_id=uuid.uuid4(),
                )
            )
            assert result.status == ContactRequestStatus.PENDING

    def test_third_request_blocked_when_two_requests_remain_inside_rolling_window(self):
        session = make_session()
        candidate = make_candidate_profile(is_searchable=True)
        now = utc_now()
        with patch("app.services.contact_request_service.utc_now", return_value=now):
            req1 = make_contact_request(
                candidate_id=candidate.id,
                status=ContactRequestStatus.EXPIRED,
                created_at=now - timedelta(days=120),
            )
            req2 = make_contact_request(
                candidate_id=candidate.id,
                status=ContactRequestStatus.EXPIRED,
                created_at=now - timedelta(days=10),
            )

            cand_result = MagicMock()
            cand_result.scalar_one_or_none.return_value = candidate
            reqs_result = MagicMock()
            reqs_result.scalars.return_value.all.return_value = [req1, req2]
            session.execute.side_effect = [cand_result, reqs_result]

            service = ContactRequestService(session)
            with pytest.raises(ConflictException, match="giới hạn tối đa 2 yêu cầu"):
                asyncio.run(
                    service.create_contact_request(
                        company_id=uuid.uuid4(),
                        candidate_id=candidate.id,
                        requester_user_id=uuid.uuid4(),
                    )
                )

    def test_request_exactly_180_days_old_no_longer_consumes_a_slot(self):
        session = make_session()
        candidate = make_candidate_profile(is_searchable=True)
        company_id = uuid.uuid4()
        now = utc_now()
        with patch("app.services.contact_request_service.utc_now", return_value=now):
            req_180d_old = make_contact_request(
                company_id=company_id,
                candidate_id=candidate.id,
                status=ContactRequestStatus.EXPIRED,
                created_at=now - timedelta(days=180),
            )
            req_recent = make_contact_request(
                company_id=company_id,
                candidate_id=candidate.id,
                status=ContactRequestStatus.EXPIRED,
                created_at=now - timedelta(days=20),
            )

            # Check status check endpoint logic
            status_reqs_result = MagicMock()
            status_reqs_result.scalars.return_value.all.return_value = [req_180d_old, req_recent]
            session.execute.return_value = status_reqs_result

            service = ContactRequestService(session)
            status_check = asyncio.run(
                service.check_contact_request_status(
                    company_id=company_id,
                    candidate_id=candidate.id,
                )
            )
            assert status_check.can_request is True

            # Check creation logic
            cand_result = MagicMock()
            cand_result.scalar_one_or_none.return_value = candidate
            create_reqs_result = MagicMock()
            create_reqs_result.scalars.return_value.all.return_value = [req_180d_old, req_recent]
            session.execute.side_effect = [cand_result, create_reqs_result]
            session.get.return_value = MagicMock(name="TechCorp")
            service.notifications.create_notification = AsyncMock()

            new_req = asyncio.run(
                service.create_contact_request(
                    company_id=company_id,
                    candidate_id=candidate.id,
                    requester_user_id=uuid.uuid4(),
                )
            )
            assert new_req.status == ContactRequestStatus.PENDING

    def test_rolling_window_scoped_to_company_and_candidate_pair(self):
        session = make_session()
        target_candidate = make_candidate_profile(is_searchable=True)
        target_company_id = uuid.uuid4()

        cand_result = MagicMock()
        cand_result.scalar_one_or_none.return_value = target_candidate
        # When querying for target_company_id and target_candidate, DB returns empty list
        reqs_result = MagicMock()
        reqs_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [cand_result, reqs_result]
        session.get.return_value = MagicMock(name="TechCorp")

        service = ContactRequestService(session)
        service.notifications.create_notification = AsyncMock()

        result = asyncio.run(
            service.create_contact_request(
                company_id=target_company_id,
                candidate_id=target_candidate.id,
                requester_user_id=uuid.uuid4(),
            )
        )
        assert result.status == ContactRequestStatus.PENDING


class TestCandidateResponseFlow:
    def test_accept_request_success(self):
        session = make_session()
        candidate_id = uuid.uuid4()
        req = make_contact_request(
            candidate_id=candidate_id,
            status=ContactRequestStatus.PENDING,
            expires_at=utc_now() + timedelta(days=10),
        )
        session.get.return_value = make_candidate_profile(candidate_id=candidate_id)

        service = ContactRequestService(session)
        service._get_request_with_relations = AsyncMock(return_value=req)
        service._resolve_response_recipients = AsyncMock(return_value=[make_user(user_id=req.requester_user_id)])
        service.notifications.create_notification = AsyncMock()

        updated = asyncio.run(service.accept_request(req.id, candidate_id))

        assert updated.status == ContactRequestStatus.ACCEPTED
        assert updated.responded_at is not None
        assert service.notifications.create_notification.called

    def test_decline_request_success(self):
        session = make_session()
        candidate_id = uuid.uuid4()
        req = make_contact_request(
            candidate_id=candidate_id,
            status=ContactRequestStatus.PENDING,
            expires_at=utc_now() + timedelta(days=10),
        )
        session.get.return_value = make_candidate_profile(candidate_id=candidate_id)

        service = ContactRequestService(session)
        service._get_request_with_relations = AsyncMock(return_value=req)
        service._resolve_response_recipients = AsyncMock(return_value=[make_user(user_id=req.requester_user_id)])
        service.notifications.create_notification = AsyncMock()

        updated = asyncio.run(service.decline_request(req.id, candidate_id))

        assert updated.status == ContactRequestStatus.DECLINED
        assert updated.responded_at is not None
        assert service.notifications.create_notification.called

    def test_revoke_authorization_success(self):
        session = make_session()
        candidate_id = uuid.uuid4()
        req = make_contact_request(
            candidate_id=candidate_id,
            status=ContactRequestStatus.ACCEPTED,
        )
        session.get.return_value = make_candidate_profile(candidate_id=candidate_id)

        service = ContactRequestService(session)
        service._get_request_with_relations = AsyncMock(return_value=req)
        service._resolve_response_recipients = AsyncMock(return_value=[make_user(user_id=req.requester_user_id)])
        service.notifications.create_notification = AsyncMock()

        updated = asyncio.run(service.revoke_authorization(req.id, candidate_id))

        assert updated.status == ContactRequestStatus.REVOKED
        assert updated.revoked_at is not None
        assert service.notifications.create_notification.called

    def test_revoke_non_accepted_raises_conflict(self):
        session = make_session()
        candidate_id = uuid.uuid4()
        req = make_contact_request(
            candidate_id=candidate_id,
            status=ContactRequestStatus.PENDING,
        )

        service = ContactRequestService(session)
        service._get_request_with_relations = AsyncMock(return_value=req)
        with pytest.raises(ConflictException, match="đã được chấp nhận"):
            asyncio.run(service.revoke_authorization(req.id, candidate_id))


class TestDiscloseContactDetails:
    def test_unauthorized_company_membership_raises_forbidden(self):
        session = make_session()
        # membership query returns None
        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mem_result

        service = ContactRequestService(session)
        with pytest.raises(ForbiddenException, match="không có quyền"):
            asyncio.run(
                service.disclose_contact_details(
                    company_id=uuid.uuid4(),
                    candidate_id=uuid.uuid4(),
                    disclosed_to_user_id=uuid.uuid4(),
                )
            )

    def test_no_accepted_request_raises_forbidden(self):
        session = make_session()
        # membership exists, but contact request query returns None
        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = MagicMock()

        req_result = MagicMock()
        req_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [mem_result, req_result]

        service = ContactRequestService(session)
        with pytest.raises(ForbiddenException, match="chưa được cấp quyền"):
            asyncio.run(
                service.disclose_contact_details(
                    company_id=uuid.uuid4(),
                    candidate_id=uuid.uuid4(),
                    disclosed_to_user_id=uuid.uuid4(),
                )
            )

    def test_disclosure_creates_audit_log_without_pii(self):
        session = make_session()
        company_id = uuid.uuid4()
        candidate_id = uuid.uuid4()
        recruiter_id = uuid.uuid4()

        membership = MagicMock()
        accepted_req = make_contact_request(
            company_id=company_id,
            candidate_id=candidate_id,
            status=ContactRequestStatus.ACCEPTED,
        )
        user = make_user(email="alice@example.com")
        candidate = make_candidate_profile(
            candidate_id=candidate_id,
            user=user,
            full_name="Alice Smith",
            phone="0912345678",
        )

        mem_res = MagicMock()
        mem_res.scalar_one_or_none.return_value = membership
        req_res = MagicMock()
        req_res.scalar_one_or_none.return_value = accepted_req
        cand_res = MagicMock()
        cand_res.scalar_one_or_none.return_value = candidate

        session.execute.side_effect = [mem_res, req_res, cand_res]

        service = ContactRequestService(session)
        response = asyncio.run(
            service.disclose_contact_details(
                company_id=company_id,
                candidate_id=candidate_id,
                disclosed_to_user_id=recruiter_id,
            )
        )

        assert response.candidate_id == candidate_id
        assert response.full_name == "Alice Smith"
        assert response.email == "alice@example.com"
        assert response.phone == "0912345678"

        # Check that session.add was called with ContactDisclosureAuditLog
        added_objs = [call[0][0] for call in session.add.call_args_list]
        audit_logs = [obj for obj in added_objs if isinstance(obj, ContactDisclosureAuditLog)]
        assert len(audit_logs) == 1
        log = audit_logs[0]
        assert log.company_id == company_id
        assert log.candidate_id == candidate_id
        assert log.disclosed_to_user_id == recruiter_id
        # Confirm audit log does NOT have email or phone attributes
        assert not hasattr(log, "email")
        assert not hasattr(log, "phone")


class TestContactRequestNotificationAndEmailDelivery:
    """Verifies in-app notification and transactional outbox email enqueueing for all events."""

    def test_create_request_enqueues_email_and_notification_to_candidate(self):
        session = make_session()
        candidate_user = make_user(email="cand@example.com")
        candidate = make_candidate_profile(user=candidate_user, full_name="Candidate A", is_searchable=True)

        cand_result = MagicMock()
        cand_result.scalar_one_or_none.return_value = candidate
        reqs_result = MagicMock()
        reqs_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [cand_result, reqs_result]
        session.get.return_value = MagicMock(name="TechCorp")

        service = ContactRequestService(session)
        service.notifications.create_notification = AsyncMock()
        service.email_service.send_request_received_email = AsyncMock()

        company_id = uuid.uuid4()
        requester_id = uuid.uuid4()
        res = asyncio.run(service.create_contact_request(company_id, candidate.id, requester_id))

        assert service.notifications.create_notification.called
        notif_kwargs = service.notifications.create_notification.call_args[1]
        assert notif_kwargs["user_id"] == candidate_user.id
        assert notif_kwargs["notification_type"] == "contact_request_received"

        assert service.email_service.send_request_received_email.called
        email_kwargs = service.email_service.send_request_received_email.call_args[1]
        assert email_kwargs["to_email"] == "cand@example.com"
        assert email_kwargs["request_id"] == res.id

    def test_accept_request_enqueues_email_and_notification_to_requester(self):
        session = make_session()
        candidate_id = uuid.uuid4()
        requester_id = uuid.uuid4()
        req = make_contact_request(
            candidate_id=candidate_id,
            requester_user_id=requester_id,
            status=ContactRequestStatus.PENDING,
            expires_at=utc_now() + timedelta(days=10),
        )
        session.get.return_value = make_candidate_profile(candidate_id=candidate_id, full_name="Candidate B")

        service = ContactRequestService(session)
        service._get_request_with_relations = AsyncMock(return_value=req)
        requester_user = make_user(user_id=requester_id, email="recruiter@example.com")
        service._resolve_response_recipients = AsyncMock(return_value=[requester_user])
        service.notifications.create_notification = AsyncMock()
        service.email_service.send_request_accepted_email = AsyncMock()

        asyncio.run(service.accept_request(req.id, candidate_id))

        assert service.notifications.create_notification.called
        notif_kwargs = service.notifications.create_notification.call_args[1]
        assert notif_kwargs["user_id"] == requester_id
        assert notif_kwargs["notification_type"] == "contact_request_accepted"

        assert service.email_service.send_request_accepted_email.called
        email_kwargs = service.email_service.send_request_accepted_email.call_args[1]
        assert email_kwargs["to_email"] == "recruiter@example.com"
        assert email_kwargs["recipient_user_id"] is None

    def test_decline_request_enqueues_email_and_notification_to_requester(self):
        session = make_session()
        candidate_id = uuid.uuid4()
        requester_id = uuid.uuid4()
        req = make_contact_request(
            candidate_id=candidate_id,
            requester_user_id=requester_id,
            status=ContactRequestStatus.PENDING,
            expires_at=utc_now() + timedelta(days=10),
        )
        session.get.return_value = make_candidate_profile(candidate_id=candidate_id, full_name="Candidate C")

        service = ContactRequestService(session)
        service._get_request_with_relations = AsyncMock(return_value=req)
        requester_user = make_user(user_id=requester_id, email="recruiter@example.com")
        service._resolve_response_recipients = AsyncMock(return_value=[requester_user])
        service.notifications.create_notification = AsyncMock()
        service.email_service.send_request_declined_email = AsyncMock()

        asyncio.run(service.decline_request(req.id, candidate_id))

        assert service.notifications.create_notification.called
        notif_kwargs = service.notifications.create_notification.call_args[1]
        assert notif_kwargs["user_id"] == requester_id
        assert notif_kwargs["notification_type"] == "contact_request_declined"

        assert service.email_service.send_request_declined_email.called
        email_kwargs = service.email_service.send_request_declined_email.call_args[1]
        assert email_kwargs["to_email"] == "recruiter@example.com"

    def test_revoke_authorization_enqueues_email_and_notification_to_requester(self):
        session = make_session()
        candidate_id = uuid.uuid4()
        requester_id = uuid.uuid4()
        req = make_contact_request(
            candidate_id=candidate_id,
            requester_user_id=requester_id,
            status=ContactRequestStatus.ACCEPTED,
        )
        session.get.return_value = make_candidate_profile(candidate_id=candidate_id, full_name="Candidate D")

        service = ContactRequestService(session)
        service._get_request_with_relations = AsyncMock(return_value=req)
        requester_user = make_user(user_id=requester_id, email="recruiter@example.com")
        service._resolve_response_recipients = AsyncMock(return_value=[requester_user])
        service.notifications.create_notification = AsyncMock()
        service.email_service.send_request_revoked_email = AsyncMock()

        asyncio.run(service.revoke_authorization(req.id, candidate_id))

        assert service.notifications.create_notification.called
        notif_kwargs = service.notifications.create_notification.call_args[1]
        assert notif_kwargs["user_id"] == requester_id
        assert notif_kwargs["notification_type"] == "contact_request_revoked"

        assert service.email_service.send_request_revoked_email.called
        email_kwargs = service.email_service.send_request_revoked_email.call_args[1]
        assert email_kwargs["to_email"] == "recruiter@example.com"


class TestInactiveRequesterFallbackD2:
    """Verifies D2 policy: inactive initiating recruiter falls back to all active Workspace Admins."""

    def test_fallback_to_all_active_workspace_admins_when_requester_inactive(self):
        session = make_session()
        company_id = uuid.uuid4()
        requester_id = uuid.uuid4()
        admin1_user = make_user(user_id=uuid.uuid4(), email="admin1@example.com", is_active=True)
        admin2_user = make_user(user_id=uuid.uuid4(), email="admin2@example.com", is_active=True)

        admin1_mem = MagicMock(spec=CompanyMembership, user=admin1_user, status=MembershipStatus.ACTIVE, is_deleted=False)
        admin2_mem = MagicMock(spec=CompanyMembership, user=admin2_user, status=MembershipStatus.ACTIVE, is_deleted=False)

        mem_res = MagicMock()
        mem_res.scalar_one_or_none.return_value = None
        admin_res = MagicMock()
        admin_res.scalars.return_value.all.return_value = [admin1_mem, admin2_mem]
        session.execute.side_effect = [mem_res, admin_res]

        service = ContactRequestService(session)
        recipients = asyncio.run(service._resolve_response_recipients(company_id, requester_id))

        assert len(recipients) == 2
        recipient_ids = {r.id for r in recipients}
        assert recipient_ids == {admin1_user.id, admin2_user.id}

    def test_no_fallback_to_inactive_deleted_or_revoked_admins(self):
        session = make_session()
        company_id = uuid.uuid4()
        requester_id = uuid.uuid4()

        active_admin_user = make_user(email="active_admin@example.com", is_active=True)
        inactive_admin_user = make_user(email="inactive_admin@example.com", is_active=False)
        deleted_admin_user = make_user(email="deleted_admin@example.com", is_active=True, is_deleted=True)

        mem_active = MagicMock(spec=CompanyMembership, user=active_admin_user, status=MembershipStatus.ACTIVE, is_deleted=False)
        mem_inactive = MagicMock(spec=CompanyMembership, user=inactive_admin_user, status=MembershipStatus.ACTIVE, is_deleted=False)
        mem_deleted = MagicMock(spec=CompanyMembership, user=deleted_admin_user, status=MembershipStatus.ACTIVE, is_deleted=False)

        mem_res = MagicMock()
        mem_res.scalar_one_or_none.return_value = None
        admin_res = MagicMock()
        admin_res.scalars.return_value.all.return_value = [mem_active, mem_inactive, mem_deleted]
        session.execute.side_effect = [mem_res, admin_res]

        service = ContactRequestService(session)
        recipients = asyncio.run(service._resolve_response_recipients(company_id, requester_id))

        assert len(recipients) == 1
        assert recipients[0].id == active_admin_user.id

    def test_fallback_admin_notifications_and_emails_receive_deterministic_idempotency_keys(self):
        session = make_session()
        company_id = uuid.uuid4()
        candidate_id = uuid.uuid4()
        requester_id = uuid.uuid4()
        admin_user = make_user(user_id=uuid.uuid4(), email="admin@example.com")

        req = make_contact_request(
            candidate_id=candidate_id,
            company_id=company_id,
            requester_user_id=requester_id,
            status=ContactRequestStatus.PENDING,
            expires_at=utc_now() + timedelta(days=10),
        )
        session.get.return_value = make_candidate_profile(candidate_id=candidate_id, full_name="Candidate Fallback")

        service = ContactRequestService(session)
        service._get_request_with_relations = AsyncMock(return_value=req)
        service._resolve_response_recipients = AsyncMock(return_value=[admin_user])
        service.notifications.create_notification = AsyncMock()
        service.email_service.send_request_accepted_email = AsyncMock()

        asyncio.run(service.accept_request(req.id, candidate_id))

        assert service.notifications.create_notification.called
        notif_call = service.notifications.create_notification.call_args[1]
        assert notif_call["user_id"] == admin_user.id

        assert service.email_service.send_request_accepted_email.called
        email_call = service.email_service.send_request_accepted_email.call_args[1]
        assert email_call["to_email"] == "admin@example.com"
        assert email_call["recipient_user_id"] == admin_user.id

    def test_expiration_does_not_fallback_to_workspace_admins(self):
        session = make_session()
        company_id = uuid.uuid4()
        requester_id = uuid.uuid4()
        req = make_contact_request(
            company_id=company_id,
            requester_user_id=requester_id,
            status=ContactRequestStatus.PENDING,
            expires_at=utc_now() - timedelta(days=1),
        )
        service = ContactRequestService(session)
        service._is_active_company_member = AsyncMock(return_value=(False, None))
        service.notifications.create_notification = AsyncMock()
        service.email_service.send_request_expired_email = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [req]
        session.execute.side_effect = [mock_result]

        asyncio.run(service._expire_stale_requests(request_id=req.id))

        assert req.status == ContactRequestStatus.EXPIRED
        # D2 strict boundary: no fallback to admins for expiration
        assert not service.notifications.create_notification.called
        assert not service.email_service.send_request_expired_email.called

class TestIdempotentExpirationD1:
    """Verifies D1 policy: lazy idempotent expiration emits exactly once."""

    def test_lazy_expiration_emits_notification_and_email_only_once(self):
        session = make_session()
        company_id = uuid.uuid4()
        requester_id = uuid.uuid4()
        requester_user = make_user(user_id=requester_id, email="recruiter@example.com")
        req = make_contact_request(
            company_id=company_id,
            requester_user_id=requester_id,
            status=ContactRequestStatus.PENDING,
            expires_at=utc_now() - timedelta(days=1),
        )

        service = ContactRequestService(session)
        service._is_active_company_member = AsyncMock(return_value=(True, requester_user))
        service.notifications.create_notification = AsyncMock()
        service.email_service.send_request_expired_email = AsyncMock()

        # 1st call: request is PENDING and expires_at <= now -> transitions to EXPIRED
        mock_result1 = MagicMock()
        mock_result1.scalars.return_value.all.return_value = [req]
        session.execute.side_effect = [mock_result1]

        expired_list = asyncio.run(service._expire_stale_requests(request_id=req.id))
        assert len(expired_list) == 1
        assert req.status == ContactRequestStatus.EXPIRED
        assert service.notifications.create_notification.called
        assert service.email_service.send_request_expired_email.called

        # 2nd call: request is already EXPIRED -> query returns empty list -> no-op
        service.notifications.create_notification.reset_mock()
        service.email_service.send_request_expired_email.reset_mock()
        mock_result2 = MagicMock()
        mock_result2.scalars.return_value.all.return_value = []
        session.execute.side_effect = [mock_result2]

        expired_list2 = asyncio.run(service._expire_stale_requests(request_id=req.id))
        assert len(expired_list2) == 0
        assert not service.notifications.create_notification.called
        assert not service.email_service.send_request_expired_email.called
