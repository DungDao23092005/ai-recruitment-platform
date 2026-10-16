import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import EntityNotFoundException, ForbiddenException
from app.domain.enums import SubscriptionStatus, SubscriptionUsageFeatureType, SubscriptionUsageStatus, UserRole
from app.domain.models.base import utc_now
from app.models import RecruitmentPlan, Subscription, SubscriptionUsage, User
from app.repositories import SubscriptionRepository
from app.services.quota_enforcement_service import QuotaEnforcementService


def make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock()
    return session


def _make_subscription_result(sub: Subscription | None) -> MagicMock:
    mock = MagicMock()
    mock.scalar_one_or_none.return_value = sub
    return mock


def _make_update_result(rowcount: int) -> MagicMock:
    mock = MagicMock()
    mock.rowcount = rowcount
    return mock


def make_plan(plan_id: uuid.UUID | None = None) -> RecruitmentPlan:
    return RecruitmentPlan(
        id=plan_id or uuid.uuid4(),
        name="Test Plan",
        price=1000000,
        currency="VND",
        duration_days=30,
        max_job_posts=5,
        max_candidate_searches=10,
        max_ai_features=20,
    )


def make_subscription(
    sub_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    plan_id: uuid.UUID | None = None,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    expires_at: datetime | None = None,
    max_job_posts: int = 5,
    max_candidate_searches: int = 10,
    max_ai_features: int = 20,
    job_posts_used: int = 0,
    candidate_searches_used: int = 0,
    ai_features_used: int = 0,
) -> Subscription:
    now = utc_now()
    return Subscription(
        id=sub_id or uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        plan_id=plan_id or uuid.uuid4(),
        status=status,
        started_at=now - timedelta(days=1),
        expires_at=expires_at if expires_at is not None else now + timedelta(days=30),
        max_job_posts=max_job_posts,
        max_candidate_searches=max_candidate_searches,
        max_ai_features=max_ai_features,
        job_posts_used=job_posts_used,
        candidate_searches_used=candidate_searches_used,
        ai_features_used=ai_features_used,
    )


def make_user(user_id: uuid.UUID | None = None, role: UserRole = UserRole.RECRUITER) -> User:
    return User(
        id=user_id or uuid.uuid4(),
        email="test@example.com",
        password_hash="hash",
        role=role,
    )


def make_usage(
    usage_id: uuid.UUID | None = None,
    subscription_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    feature_type: SubscriptionUsageFeatureType = SubscriptionUsageFeatureType.JOB_POST,
    status: SubscriptionUsageStatus = SubscriptionUsageStatus.RESERVED,
    idempotency_key: str | None = None,
) -> SubscriptionUsage:
    return SubscriptionUsage(
        id=usage_id or uuid.uuid4(),
        subscription_id=subscription_id or uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        feature_type=feature_type,
        status=status,
        idempotency_key=idempotency_key,
        amount=1,
    )


def make_service(session: MagicMock) -> QuotaEnforcementService:
    service = QuotaEnforcementService(session)
    service.subscriptions = AsyncMock(spec=SubscriptionRepository)
    return service


class TestGetActiveSubscriptionOrRaise:
    def test_returns_active_subscription(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        sub = make_subscription(user_id=user_id)
        service.subscriptions.get_active_by_user_id.return_value = sub

        result = asyncio.run(service.get_active_subscription_or_raise(user_id))

        assert result is sub

    def test_raises_forbidden_when_no_subscription(self):
        session = make_session()
        service = make_service(session)
        service.subscriptions.get_active_by_user_id.return_value = None

        with pytest.raises(ForbiddenException) as exc_info:
            asyncio.run(service.get_active_subscription_or_raise(uuid.uuid4()))

        assert "chưa có gói đăng ký hợp lệ" in str(exc_info.value)

    def test_raises_forbidden_when_no_quota(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        sub = make_subscription(user_id=user_id, max_job_posts=0, max_candidate_searches=0, max_ai_features=0)
        service.subscriptions.get_active_by_user_id.return_value = sub

        with pytest.raises(ForbiddenException) as exc_info:
            asyncio.run(service.get_active_subscription_or_raise(user_id))

        assert "không bao gồm quyền sử dụng" in str(exc_info.value)


class TestCheckJobPostQuota:
    def test_returns_allowed_when_quota_available(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        sub = make_subscription(user_id=user_id, max_job_posts=5, job_posts_used=2)
        service.subscriptions.get_active_by_user_id.return_value = sub

        result = asyncio.run(service.check_job_post_quota(user_id))

        assert result.allowed is True
        assert result.limit == 5
        assert result.used == 2
        assert result.remaining == 3

    def test_returns_not_allowed_when_limit_zero(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        sub = make_subscription(user_id=user_id, max_job_posts=0)
        service.subscriptions.get_active_by_user_id.return_value = sub

        result = asyncio.run(service.check_job_post_quota(user_id))

        assert result.allowed is False
        assert result.limit == 0
        assert "không bao gồm quyền đăng tin" in result.message

    def test_returns_not_allowed_when_exhausted(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        sub = make_subscription(user_id=user_id, max_job_posts=5, job_posts_used=5)
        service.subscriptions.get_active_by_user_id.return_value = sub

        result = asyncio.run(service.check_job_post_quota(user_id))

        assert result.allowed is False
        assert result.remaining == 0
        assert "Đã hết lượt đăng tin" in result.message


class TestConsumeJobPostQuota:
    def test_consumes_quota_successfully(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        sub = make_subscription(user_id=user_id, max_job_posts=5, job_posts_used=2)
        service.subscriptions.get_active_by_user_id.return_value = sub
        session.execute.return_value = _make_update_result(1)
        session.get.return_value = None

        job_id = uuid.uuid4()
        result = asyncio.run(service.consume_job_post_quota(user_id, job_id))

        assert result.allowed is True
        assert result.used == 3
        assert result.remaining == 2
        session.add.assert_called()

    def test_raises_forbidden_when_exhausted(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        sub = make_subscription(user_id=user_id, max_job_posts=5, job_posts_used=5)
        service.subscriptions.get_active_by_user_id.return_value = sub
        session.execute.return_value = _make_update_result(0)

        with pytest.raises(ForbiddenException) as exc_info:
            asyncio.run(service.consume_job_post_quota(user_id, uuid.uuid4()))

        assert "Đã hết lượt đăng tin" in str(exc_info.value)

    def test_admin_bypasses_quota(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()

        result = asyncio.run(service.consume_job_post_quota(user_id, uuid.uuid4(), is_admin=True))

        assert result.allowed is True
        assert result.remaining == -1
        service.subscriptions.get_active_by_user_id.assert_not_called()


class TestConsumeJobPostQuotaReference:
    def test_consume_job_post_quota_sets_reference_id_to_job_id(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        job_id = uuid.uuid4()
        sub = make_subscription(user_id=user_id, max_job_posts=5, job_posts_used=2)
        service.subscriptions.get_active_by_user_id.return_value = sub
        session.execute.return_value = _make_update_result(1)

        captured = {}

        def capture_add(obj):
            if isinstance(obj, SubscriptionUsage):
                captured["usage"] = obj

        session.add.side_effect = capture_add

        result = asyncio.run(service.consume_job_post_quota(user_id, job_id))

        assert result.allowed is True
        assert result.used == 3
        assert captured["usage"].reference_id == job_id


class TestConsumeJobPostQuotaIdempotent:
    def test_charges_once_when_no_existing_usage(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        job_id = uuid.uuid4()
        sub = make_subscription(user_id=user_id, max_job_posts=5, job_posts_used=2)
        service.subscriptions.get_active_by_user_id.return_value = sub
        # Lock (rowcount irrelevant) + insert + increment (rowcount=1).
        session.execute.return_value = _make_update_result(1)

        # No existing completed usage for this job under this subscription.
        service._get_completed_job_post_usage = AsyncMock(return_value=None)

        result = asyncio.run(
            service.consume_job_post_quota_idempotent(user_id, job_id)
        )

        assert result.allowed is True
        assert result.used == 3
        # Three execute calls: range lock + claim insert + counter increment.
        assert session.execute.call_count == 3

    def test_skips_charge_when_already_consumed_under_same_subscription(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        job_id = uuid.uuid4()
        sub_id = uuid.uuid4()
        sub = make_subscription(
            sub_id=sub_id,
            user_id=user_id,
            max_job_posts=5,
            job_posts_used=3,
        )
        service.subscriptions.get_active_by_user_id.return_value = sub

        existing = make_usage(
            usage_id=uuid.uuid4(),
            subscription_id=sub_id,
            user_id=user_id,
            feature_type=SubscriptionUsageFeatureType.JOB_POST,
            status=SubscriptionUsageStatus.COMPLETED,
        )
        existing.reference_id = job_id
        existing.idempotency_key = f"job_post_{job_id}"
        service._get_completed_job_post_usage = AsyncMock(return_value=existing)
        # Only the range-lock SELECT is executed; no insert/increment.
        session.execute.return_value = _make_update_result(0)

        result = asyncio.run(
            service.consume_job_post_quota_idempotent(user_id, job_id)
        )

        # Already charged: no increment, no duplicate ledger
        assert result.allowed is True
        assert result.used == 3
        assert result.remaining == 2
        # Only the lock SELECT was executed.
        assert session.execute.call_count == 1

    def test_charges_under_new_subscription_even_if_job_consumed_before(self):
        """Same job under a different subscription must consume that subscription's quota once."""
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        job_id = uuid.uuid4()
        sub_id = uuid.uuid4()
        sub = make_subscription(
            sub_id=sub_id,
            user_id=user_id,
            max_job_posts=5,
            job_posts_used=0,
        )
        service.subscriptions.get_active_by_user_id.return_value = sub

        # No existing usage under this (new) subscription
        service._get_completed_job_post_usage = AsyncMock(return_value=None)
        # Lock + insert + increment (rowcount=1).
        session.execute.return_value = _make_update_result(1)

        result = asyncio.run(
            service.consume_job_post_quota_idempotent(user_id, job_id)
        )

        assert result.allowed is True
        assert result.used == 1
        assert session.execute.call_count == 3

    def test_concurrent_loser_detects_winner_and_returns_idempotent(self):
        """Concurrent loser blocks on the range lock, then observes the
        winner's committed record and returns idempotent without double charge."""
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        job_id = uuid.uuid4()
        sub_id = uuid.uuid4()
        sub = make_subscription(
            sub_id=sub_id,
            user_id=user_id,
            max_job_posts=5,
            job_posts_used=1,
        )
        service.subscriptions.get_active_by_user_id.return_value = sub

        # Lock SELECT executed; rowcount irrelevant.
        session.execute.return_value = _make_update_result(0)
        service._get_completed_job_post_usage = AsyncMock(return_value=None)

        winner = make_usage(
            usage_id=uuid.uuid4(),
            subscription_id=sub_id,
            user_id=user_id,
            feature_type=SubscriptionUsageFeatureType.JOB_POST,
            status=SubscriptionUsageStatus.COMPLETED,
        )
        winner.reference_id = job_id
        winner.idempotency_key = f"job_post_{job_id}"
        service._get_completed_job_post_usage = AsyncMock(return_value=winner)

        result = asyncio.run(
            service.consume_job_post_quota_idempotent(user_id, job_id)
        )

        # Idempotent: allowed, no second charge (used stays at 1 from winner).
        assert result.allowed is True
        assert result.used == 1
        assert result.limit == 5
        assert result.remaining == 4

    def test_counter_exhausted_raises_forbidden_without_double_charge(self):
        """When the counter is already at max, increment fails (rowcount=0),
        our claimed row is removed, and ForbiddenException is raised."""
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        job_id = uuid.uuid4()
        sub = make_subscription(user_id=user_id, max_job_posts=5, job_posts_used=5)
        service.subscriptions.get_active_by_user_id.return_value = sub

        # Lock + insert succeed; increment returns rowcount=0 (quota exhausted).
        session.execute.return_value = _make_update_result(1)
        service._get_completed_job_post_usage = AsyncMock(return_value=None)

        with pytest.raises(ForbiddenException):
            asyncio.run(service.consume_job_post_quota_idempotent(user_id, job_id))

    def test_admin_bypasses_quota_idempotent(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()

        result = asyncio.run(
            service.consume_job_post_quota_idempotent(
                user_id, uuid.uuid4(), is_admin=True
            )
        )

        assert result.allowed is True
        assert result.remaining == -1
        service.subscriptions.get_active_by_user_id.assert_not_called()
        session.execute.assert_not_called()


class TestReserveSearchQuota:
    def test_reserves_successfully(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        sub = make_subscription(user_id=user_id, max_candidate_searches=10, candidate_searches_used=3)
        service.subscriptions.get_active_by_user_id.return_value = sub
        session.execute.return_value = _make_update_result(1)

        # Mock flush to assign an ID to the usage object
        async def mock_flush():
            # The usage object is the last one added to session
            for call in session.add.call_args_list:
                obj = call.args[0]
                if isinstance(obj, SubscriptionUsage):
                    obj.id = uuid.uuid4()
        session.flush.side_effect = mock_flush

        result = asyncio.run(service.reserve_search_quota(user_id, "idem-key-1"))

        assert result.used == 4
        assert result.remaining == 6
        assert result.usage_id is not None

    def test_idempotency_returns_existing_reservation(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        sub = make_subscription(user_id=user_id, max_candidate_searches=10, candidate_searches_used=3)
        service.subscriptions.get_active_by_user_id.return_value = sub

        existing_usage = make_usage(
            subscription_id=sub.id,
            user_id=user_id,
            feature_type=SubscriptionUsageFeatureType.CANDIDATE_SEARCH,
            status=SubscriptionUsageStatus.RESERVED,
            idempotency_key="idem-key-1",
        )

        # Mock the internal _get_usage_by_idempotency
        service._get_usage_by_idempotency = AsyncMock(return_value=existing_usage)

        result = asyncio.run(service.reserve_search_quota(user_id, "idem-key-1"))

        assert result.usage_id == existing_usage.id
        session.execute.assert_not_called()

    def test_admin_bypasses_quota(self):
        """Admin should bypass quota check and get a bypassed result."""
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()

        result = asyncio.run(service.reserve_search_quota(user_id, "idem-key-1", is_admin=True))

        assert result.bypassed is True
        assert result.usage_id is None
        assert result.remaining == -1
        assert result.limit == -1
        assert result.used == -1
        service.subscriptions.get_active_by_user_id.assert_not_called()
        session.execute.assert_not_called()

    def test_bypassed_finalize_noop(self):
        """Finalizing a bypassed reservation should be a no-op."""
        session = make_session()
        service = make_service(session)

        # Should not raise
        asyncio.run(service.finalize_reservation(None, success=True))
        asyncio.run(service.finalize_reservation(None, success=False))

        session.get.assert_not_called()
        session.execute.assert_not_called()

    def test_bypassed_release_noop(self):
        """Releasing a bypassed reservation should be a no-op."""
        session = make_session()
        service = make_service(session)

        # Should not raise
        asyncio.run(service.release_reservation(None))

        session.get.assert_not_called()
        session.execute.assert_not_called()


class TestReserveAIQuota:
    def test_reserves_successfully(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        sub = make_subscription(user_id=user_id, max_ai_features=20, ai_features_used=5)
        service.subscriptions.get_active_by_user_id.return_value = sub
        session.execute.return_value = _make_update_result(1)

        async def mock_flush():
            for call in session.add.call_args_list:
                obj = call.args[0]
                if isinstance(obj, SubscriptionUsage):
                    obj.id = uuid.uuid4()
        session.flush.side_effect = mock_flush

        result = asyncio.run(service.reserve_ai_quota(user_id, "idem-key-ai-1"))

        assert result.used == 6
        assert result.remaining == 14
        assert result.usage_id is not None

    def test_admin_bypasses_quota(self):
        """Admin should bypass quota check and get a bypassed result."""
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()

        result = asyncio.run(service.reserve_ai_quota(user_id, "idem-key-ai-1", is_admin=True))

        assert result.bypassed is True
        assert result.usage_id is None
        assert result.remaining == -1
        assert result.limit == -1
        assert result.used == -1
        service.subscriptions.get_active_by_user_id.assert_not_called()
        session.execute.assert_not_called()

    def test_bypassed_finalize_noop(self):
        """Finalizing a bypassed reservation should be a no-op."""
        session = make_session()
        service = make_service(session)

        asyncio.run(service.finalize_reservation(None, success=True))
        asyncio.run(service.finalize_reservation(None, success=False))

        session.get.assert_not_called()
        session.execute.assert_not_called()

    def test_bypassed_release_noop(self):
        """Releasing a bypassed reservation should be a no-op."""
        session = make_session()
        service = make_service(session)

        asyncio.run(service.release_reservation(None))

        session.get.assert_not_called()
        session.execute.assert_not_called()


class TestFinalizeReservation:
    def test_finalizes_completed(self):
        session = make_session()
        service = make_service(session)
        usage_id = uuid.uuid4()
        usage = make_usage(status=SubscriptionUsageStatus.RESERVED)
        session.get.return_value = usage

        asyncio.run(service.finalize_reservation(usage_id, success=True))

        assert usage.status == SubscriptionUsageStatus.COMPLETED
        assert usage.finalized_at is not None

    def test_finalizes_failed_and_releases_counter(self):
        session = make_session()
        service = make_service(session)
        usage_id = uuid.uuid4()
        sub_id = uuid.uuid4()
        usage = make_usage(
            subscription_id=sub_id,
            status=SubscriptionUsageStatus.RESERVED,
            feature_type=SubscriptionUsageFeatureType.CANDIDATE_SEARCH,
        )
        session.get.return_value = usage
        session.execute.return_value = _make_update_result(1)

        asyncio.run(service.finalize_reservation(usage_id, success=False))

        assert usage.status == SubscriptionUsageStatus.FAILED
        session.execute.assert_called()

    def test_idempotent_on_already_completed(self):
        session = make_session()
        service = make_service(session)
        usage_id = uuid.uuid4()
        usage = make_usage(status=SubscriptionUsageStatus.COMPLETED)
        session.get.return_value = usage

        asyncio.run(service.finalize_reservation(usage_id, success=True))

        # Should not modify already completed usage
        assert usage.status == SubscriptionUsageStatus.COMPLETED


class TestReleaseReservation:
    def test_releases_reserved(self):
        session = make_session()
        service = make_service(session)
        usage_id = uuid.uuid4()
        sub_id = uuid.uuid4()
        usage = make_usage(
            subscription_id=sub_id,
            status=SubscriptionUsageStatus.RESERVED,
            feature_type=SubscriptionUsageFeatureType.CANDIDATE_SEARCH,
        )
        session.get.return_value = usage
        session.execute.return_value = _make_update_result(1)

        asyncio.run(service.release_reservation(usage_id))

        assert usage.status == SubscriptionUsageStatus.FAILED
        session.execute.assert_called()

    def test_noop_on_already_finalized(self):
        session = make_session()
        service = make_service(session)
        usage_id = uuid.uuid4()
        usage = make_usage(status=SubscriptionUsageStatus.COMPLETED)
        session.get.return_value = usage

        asyncio.run(service.release_reservation(usage_id))

        assert usage.status == SubscriptionUsageStatus.COMPLETED
        session.execute.assert_not_called()


class TestGetUsageSummary:
    def test_returns_summary_for_active_subscription(self):
        session = make_session()
        service = make_service(session)
        user_id = uuid.uuid4()
        sub = make_subscription(
            user_id=user_id,
            max_job_posts=5,
            max_candidate_searches=10,
            max_ai_features=20,
            job_posts_used=2,
            candidate_searches_used=3,
            ai_features_used=5,
        )
        service.subscriptions.get_active_by_user_id.return_value = sub

        result = asyncio.run(service.get_usage_summary(user_id))

        assert result["has_subscription"] is True
        assert result["job_posts"]["limit"] == 5
        assert result["job_posts"]["used"] == 2
        assert result["job_posts"]["remaining"] == 3
        assert result["candidate_searches"]["limit"] == 10
        assert result["candidate_searches"]["used"] == 3
        assert result["candidate_searches"]["remaining"] == 7
        assert result["ai_features"]["limit"] == 20
        assert result["ai_features"]["used"] == 5
        assert result["ai_features"]["remaining"] == 15

    def test_returns_zero_when_no_subscription(self):
        session = make_session()
        service = make_service(session)
        service.subscriptions.get_active_by_user_id.return_value = None

        result = asyncio.run(service.get_usage_summary(uuid.uuid4()))

        assert result["has_subscription"] is False
        assert result["job_posts"]["limit"] == 0
        assert result["candidate_searches"]["limit"] == 0
        assert result["ai_features"]["limit"] == 0


class TestReleaseReservationSafety:
    def test_double_release_does_not_decrement_twice(self):
        """Releasing an already-finalized reservation must not decrement counter again."""
        session = make_session()
        service = make_service(session)
        usage_id = uuid.uuid4()
        sub_id = uuid.uuid4()
        usage = make_usage(
            usage_id=usage_id,
            subscription_id=sub_id,
            status=SubscriptionUsageStatus.RESERVED,
            feature_type=SubscriptionUsageFeatureType.CANDIDATE_SEARCH,
        )
        session.get.return_value = usage
        session.execute.return_value = _make_update_result(1)

        asyncio.run(service.release_reservation(usage_id))
        asyncio.run(service.release_reservation(usage_id))

        assert usage.status == SubscriptionUsageStatus.FAILED
        # _release_counter runs exactly once; counter never goes negative
        assert session.execute.call_count == 1

    def test_finalize_on_failed_is_noop(self):
        """Finalizing an already-failed reservation must not release the counter again."""
        session = make_session()
        service = make_service(session)
        usage_id = uuid.uuid4()
        sub_id = uuid.uuid4()
        usage = make_usage(
            usage_id=usage_id,
            subscription_id=sub_id,
            status=SubscriptionUsageStatus.FAILED,
            feature_type=SubscriptionUsageFeatureType.CANDIDATE_SEARCH,
        )
        session.get.return_value = usage
        session.execute.return_value = _make_update_result(1)

        asyncio.run(service.finalize_reservation(usage_id, success=True))
        asyncio.run(service.finalize_reservation(usage_id, success=False))

        assert usage.status == SubscriptionUsageStatus.FAILED
        session.execute.assert_not_called()

    def test_completed_reservation_is_not_refunded(self):
        """A completed reservation must not be released or refunded."""
        session = make_session()
        service = make_service(session)
        usage_id = uuid.uuid4()
        usage = make_usage(status=SubscriptionUsageStatus.COMPLETED)
        session.get.return_value = usage

        asyncio.run(service.release_reservation(usage_id))

        assert usage.status == SubscriptionUsageStatus.COMPLETED
        session.execute.assert_not_called()


class TestReconcileStaleReservations:
    def _stale_usage(self, usage_id, sub_id, minutes_ago):
        usage = make_usage(
            usage_id=usage_id,
            subscription_id=sub_id,
            status=SubscriptionUsageStatus.RESERVED,
            feature_type=SubscriptionUsageFeatureType.CANDIDATE_SEARCH,
        )
        usage.created_at = utc_now() - timedelta(minutes=minutes_ago)
        return usage

    def test_reconcile_marks_stale_reserved_failed_and_releases_counter(self):
        session = make_session()
        service = make_service(session)
        sub_id = uuid.uuid4()
        usage_id = uuid.uuid4()
        usage = self._stale_usage(usage_id, sub_id, minutes_ago=120)

        calls = {"n": 0}

        async def fake_execute(stmt):
            calls["n"] += 1
            result = MagicMock()
            if calls["n"] == 1:
                result.scalars().all.return_value = [usage]
            else:
                result.rowcount = 1
            return result

        session.execute = AsyncMock(side_effect=fake_execute)

        reconciled = asyncio.run(
            service.reconcile_stale_reservations(max_age_minutes=60, limit=10)
        )

        assert reconciled == 1
        assert usage.status == SubscriptionUsageStatus.FAILED
        assert usage.finalized_at is not None
        # select + one counter release
        assert calls["n"] == 2

    def test_reconcile_ignores_recent_reservation(self):
        session = make_session()
        service = make_service(session)
        sub_id = uuid.uuid4()
        usage = self._stale_usage(uuid.uuid4(), sub_id, minutes_ago=10)

        async def fake_execute(stmt):
            result = MagicMock()
            result.scalars().all.return_value = []
            return result

        session.execute = AsyncMock(side_effect=fake_execute)

        reconciled = asyncio.run(
            service.reconcile_stale_reservations(max_age_minutes=60, limit=10)
        )

        assert reconciled == 0
        assert usage.status == SubscriptionUsageStatus.RESERVED

    def test_reconcile_ignores_completed_and_failed(self):
        session = make_session()
        service = make_service(session)
        sub_id = uuid.uuid4()
        completed = self._stale_usage(uuid.uuid4(), sub_id, minutes_ago=120)
        completed.status = SubscriptionUsageStatus.COMPLETED
        failed = self._stale_usage(uuid.uuid4(), sub_id, minutes_ago=120)
        failed.status = SubscriptionUsageStatus.FAILED

        async def fake_execute(stmt):
            result = MagicMock()
            result.scalars().all.return_value = []
            return result

        session.execute = AsyncMock(side_effect=fake_execute)

        reconciled = asyncio.run(
            service.reconcile_stale_reservations(max_age_minutes=60, limit=10)
        )

        assert reconciled == 0
        assert completed.status == SubscriptionUsageStatus.COMPLETED
        assert failed.status == SubscriptionUsageStatus.FAILED
        session.execute.assert_called_once()

    def test_reconcile_respects_limit(self):
        session = make_session()
        service = make_service(session)
        sub_id = uuid.uuid4()
        usages = [self._stale_usage(uuid.uuid4(), sub_id, minutes_ago=120) for _ in range(5)]

        async def fake_execute(stmt):
            result = MagicMock()
            result.scalars().all.return_value = usages[:2]
            return result

        session.execute = AsyncMock(side_effect=fake_execute)

        reconciled = asyncio.run(
            service.reconcile_stale_reservations(max_age_minutes=60, limit=2)
        )

        assert reconciled == 2
        assert all(u.status == SubscriptionUsageStatus.FAILED for u in usages[:2])