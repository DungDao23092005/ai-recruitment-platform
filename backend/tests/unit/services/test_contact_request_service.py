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
from app.domain.enums import ContactRequestStatus, MembershipStatus
from app.models import (
    CandidateContactRequest,
    CandidateProfile,
    Company,
    CompanyMembership,
    ContactDisclosureAuditLog,
    Resume,
    User,
)
from app.services.contact_request_service import (
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
    session.execute = AsyncMock()
    session.get = AsyncMock()
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
