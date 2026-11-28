from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db, get_optional_workspace
from app.api.v1.endpoints.ai import _get_ai_service, _get_rag_chat_service
from app.core.exceptions import CandidateQuotaExhaustedException
from app.domain.enums import JobStatus, SubscriptionUsageFeatureType, UserRole
from app.main import app
from app.schemas.ai_chat import ChatResponse, ChatSource
from app.schemas.ai_job import ParsedJobSchema
from app.services.quota_enforcement_service import QuotaEnforcementService, ReservationResult


def _make_candidate_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = UserRole.CANDIDATE
    user.is_active = True
    return user


def _make_recruiter_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = UserRole.RECRUITER
    user.is_active = True
    return user


def _mock_db():
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _setup_quota_mock():
    reservation = ReservationResult(
        usage_id=uuid.uuid4(),
        remaining=4,
        limit=5,
        used=1,
        bypassed=False,
    )
    quota_service = MagicMock(spec=QuotaEnforcementService)
    quota_service.reserve_candidate_ai_quota = AsyncMock(return_value=reservation)
    quota_service.finalize_reservation = AsyncMock()
    quota_service.release_reservation = AsyncMock(return_value=True)
    return quota_service, reservation


@pytest.fixture
def api_client():
    """FastAPI TestClient without repeating lifespan Redis/DB probes."""
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_candidate_chat_no_cv_early_guidance_releases_quota(api_client):
    quota_service, reservation = _setup_quota_mock()
    rag_service = MagicMock()
    resp = ChatResponse(
        answer="Bạn chưa có CV nào trong hệ thống. Vui lòng tải lên và xác nhận CV tại trang Tải CV (/candidate/cv-upload).",
        confidence=0.0,
        sources=[],
        suggested_followups=[],
    )
    resp._charge_quota = False
    rag_service.chat = AsyncMock(return_value=resp)

    app.dependency_overrides[get_current_user] = lambda: _make_candidate_user()
    app.dependency_overrides[_get_rag_chat_service] = lambda: rag_service
    app.dependency_overrides[get_db] = lambda: _mock_db()

    with patch("app.api.v1.endpoints.ai.QuotaEnforcementService", return_value=quota_service):
        res = api_client.post(
            "/api/v1/ai/chat",
            json={"message": "cv của tôi phù hợp với công việc nào"},
            headers={"Idempotency-Key": "cand-no-cv-1"},
        )

    assert res.status_code == status.HTTP_200_OK
    assert "/candidate/cv-upload" in res.json()["answer"]
    assert "_charge_quota" not in res.json()
    quota_service.reserve_candidate_ai_quota.assert_awaited_once()
    assert (
        quota_service.reserve_candidate_ai_quota.call_args.kwargs["feature_type"]
        == SubscriptionUsageFeatureType.CANDIDATE_CHAT
    )
    assert (
        quota_service.reserve_candidate_ai_quota.call_args.kwargs["idempotency_key"]
        == "cand-no-cv-1"
    )
    quota_service.release_reservation.assert_awaited_once_with(reservation.usage_id)
    quota_service.finalize_reservation.assert_not_awaited()


@pytest.mark.parametrize(
    "msg",
    [
        "Bạn đã tải lên bản nháp CV nhưng chưa xác nhận CV.",
        "Hiện chưa thể xác minh đủ thông tin chi tiết từ dữ liệu công việc và hồ sơ hiện có.",
    ],
)
def test_candidate_chat_unconfirmed_draft_and_grounding_failure_release_quota(api_client, msg):
    quota_service, reservation = _setup_quota_mock()
    rag_service = MagicMock()
    resp = ChatResponse(
        answer=msg,
        confidence=0.0,
        sources=[],
        suggested_followups=[],
    )
    resp._charge_quota = False
    rag_service.chat = AsyncMock(return_value=resp)

    app.dependency_overrides[get_current_user] = lambda: _make_candidate_user()
    app.dependency_overrides[_get_rag_chat_service] = lambda: rag_service
    app.dependency_overrides[get_db] = lambda: _mock_db()

    with patch("app.api.v1.endpoints.ai.QuotaEnforcementService", return_value=quota_service):
        res = api_client.post(
            "/api/v1/ai/chat",
            json={"message": "gợi ý việc làm phù hợp với cv của tôi"},
        )

    assert res.status_code == status.HTTP_200_OK
    quota_service.release_reservation.assert_awaited_once_with(reservation.usage_id)
    quota_service.finalize_reservation.assert_not_awaited()


def test_candidate_chat_grounded_recommendation_commits_quota(api_client):
    quota_service, reservation = _setup_quota_mock()
    job_id = uuid.uuid4()
    rag_service = MagicMock()
    resp = ChatResponse(
        answer="Bạn phù hợp với Backend Python Engineer.",
        confidence=0.91,
        sources=[
            ChatSource(
                source_type="job",
                entity_id=job_id,
                title="Backend Python Engineer",
                relevance_score=0.91,
                skills=["Python", "FastAPI"],
            )
        ],
        suggested_followups=["Tại sao tôi phù hợp?"],
        recommended_job_ids=[job_id],
    )
    rag_service.chat = AsyncMock(return_value=resp)

    app.dependency_overrides[get_current_user] = lambda: _make_candidate_user()
    app.dependency_overrides[_get_rag_chat_service] = lambda: rag_service
    app.dependency_overrides[get_db] = lambda: _mock_db()

    with patch("app.api.v1.endpoints.ai.QuotaEnforcementService", return_value=quota_service):
        res = api_client.post(
            "/api/v1/ai/chat",
            json={"message": "cv của tôi hiện tại phù hợp với những công việc gì có trong hệ thống"},
        )

    assert res.status_code == status.HTTP_200_OK
    assert res.json()["recommended_job_ids"] == [str(job_id)]
    quota_service.finalize_reservation.assert_awaited_once_with(
        reservation.usage_id, success=True
    )
    quota_service.release_reservation.assert_not_awaited()


def test_candidate_chat_forwards_session_recommended_job_ids_to_service(api_client):
    quota_service, _ = _setup_quota_mock()
    job_a = uuid.uuid4()
    job_b = uuid.uuid4()
    rag_service = MagicMock()
    rag_service.chat = AsyncMock(
        return_value=ChatResponse(
            answer="Bạn còn thiếu PyTorch cho vị trí AI Engineer.",
            confidence=0.88,
            sources=[],
            suggested_followups=[],
            recommended_job_ids=[job_a, job_b],
        )
    )

    app.dependency_overrides[get_current_user] = lambda: _make_candidate_user()
    app.dependency_overrides[_get_rag_chat_service] = lambda: rag_service
    app.dependency_overrides[get_db] = lambda: _mock_db()

    with patch("app.api.v1.endpoints.ai.QuotaEnforcementService", return_value=quota_service):
        res = api_client.post(
            "/api/v1/ai/chat",
            json={
                "message": "Tôi còn thiếu kỹ năng gì cho các vị trí trên?",
                "history": [{"role": "user", "content": "Follow-up sau 10 tin nhắn"}],
                "recommended_job_ids": [str(job_a), str(job_b)],
            },
        )

    assert res.status_code == status.HTTP_200_OK
    assert rag_service.chat.call_args.kwargs["recommended_job_ids"] == [job_a, job_b]


def test_candidate_chat_accepts_ten_recommended_job_ids_and_deduplicates(api_client):
    quota_service, _ = _setup_quota_mock()
    ten_ids = [uuid.uuid4() for _ in range(10)]
    duplicated_ten = [ten_ids[0], ten_ids[1], ten_ids[0], *ten_ids[2:9]]
    rag_service = MagicMock()
    rag_service.chat = AsyncMock(
        return_value=ChatResponse(
            answer="Đã kiểm tra danh sách vị trí.",
            confidence=0.9,
            sources=[],
            suggested_followups=[],
            recommended_job_ids=ten_ids,
        )
    )

    app.dependency_overrides[get_current_user] = lambda: _make_candidate_user()
    app.dependency_overrides[_get_rag_chat_service] = lambda: rag_service
    app.dependency_overrides[get_db] = lambda: _mock_db()

    with patch("app.api.v1.endpoints.ai.QuotaEnforcementService", return_value=quota_service):
        res_exact = api_client.post(
            "/api/v1/ai/chat",
            json={
                "message": "Chi tiết mức độ phù hợp cho từng vị trí là bao nhiêu?",
                "recommended_job_ids": [str(jid) for jid in ten_ids],
            },
        )
        res_dedup = api_client.post(
            "/api/v1/ai/chat",
            json={
                "message": "Chi tiết mức độ phù hợp cho từng vị trí là bao nhiêu?",
                "recommended_job_ids": [str(jid) for jid in duplicated_ten],
            },
        )

    assert res_exact.status_code == status.HTTP_200_OK
    assert rag_service.chat.call_args_list[0].kwargs["recommended_job_ids"] == ten_ids
    assert res_dedup.status_code == status.HTTP_200_OK
    assert rag_service.chat.call_args_list[1].kwargs["recommended_job_ids"] == [
        ten_ids[0],
        ten_ids[1],
        *ten_ids[2:9],
    ]


def test_candidate_chat_rejects_more_than_ten_recommended_job_ids(api_client):
    quota_service, _ = _setup_quota_mock()
    rag_service = MagicMock()
    rag_service.chat = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: _make_candidate_user()
    app.dependency_overrides[_get_rag_chat_service] = lambda: rag_service
    app.dependency_overrides[get_db] = lambda: _mock_db()

    eleven_ids = [str(uuid.uuid4()) for _ in range(11)]
    with patch("app.api.v1.endpoints.ai.QuotaEnforcementService", return_value=quota_service):
        res = api_client.post(
            "/api/v1/ai/chat",
            json={
                "message": "Tôi còn thiếu kỹ năng gì cho các vị trí trên?",
                "recommended_job_ids": eleven_ids,
            },
        )

    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    rag_service.chat.assert_not_awaited()
    quota_service.reserve_candidate_ai_quota.assert_not_awaited()


def test_candidate_chat_exhausted_quota_returns_403_and_skips_chat(api_client):
    quota_service, _ = _setup_quota_mock()
    quota_service.reserve_candidate_ai_quota = AsyncMock(
        side_effect=CandidateQuotaExhaustedException(
            "Bạn đã hết lượt sử dụng AI Chat.",
            subscription_id=uuid.uuid4(),
            is_free=True,
            period_key="2026-11",
        )
    )
    rag_service = MagicMock()
    rag_service.chat = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: _make_candidate_user()
    app.dependency_overrides[_get_rag_chat_service] = lambda: rag_service
    app.dependency_overrides[get_db] = lambda: _mock_db()

    with (
        patch("app.api.v1.endpoints.ai.QuotaEnforcementService", return_value=quota_service),
        patch("app.api.v1.endpoints.ai.NotificationService") as notif_cls,
    ):
        notif_cls.return_value.notify_candidate_free_quota_exhausted = AsyncMock()
        res = api_client.post(
            "/api/v1/ai/chat",
            json={"message": "tôi phù hợp với những vị trí nào"},
        )

    assert res.status_code == status.HTTP_403_FORBIDDEN
    rag_service.chat.assert_not_awaited()


def test_candidate_chat_cancelled_error_releases_reservation(api_client):
    quota_service, reservation = _setup_quota_mock()
    rag_service = MagicMock()
    rag_service.chat = AsyncMock(side_effect=asyncio.CancelledError())

    app.dependency_overrides[get_current_user] = lambda: _make_candidate_user()
    app.dependency_overrides[_get_rag_chat_service] = lambda: rag_service
    app.dependency_overrides[get_db] = lambda: _mock_db()

    with patch("app.api.v1.endpoints.ai.QuotaEnforcementService", return_value=quota_service):
        try:
            api_client.post(
                "/api/v1/ai/chat",
                json={"message": "cv của tôi phù hợp với công việc nào"},
            )
        except BaseException:
            pass

    quota_service.release_reservation.assert_awaited_once_with(reservation.usage_id)
    quota_service.finalize_reservation.assert_not_awaited()


def test_parse_jd_forwards_draft_status_when_job_not_in_db(api_client):
    quota_service = MagicMock(spec=QuotaEnforcementService)
    reservation = ReservationResult(
        usage_id=uuid.uuid4(),
        remaining=9,
        limit=10,
        used=1,
        bypassed=False,
    )
    quota_service.reserve_ai_quota = AsyncMock(return_value=reservation)
    quota_service.finalize_reservation = AsyncMock()

    matching_svc = MagicMock()
    matching_svc.process_and_index_job = AsyncMock(
        return_value=ParsedJobSchema(title="Python Dev", required_skills=["Python"])
    )

    app.dependency_overrides[get_current_user] = lambda: _make_recruiter_user()
    app.dependency_overrides[get_optional_workspace] = lambda: None
    app.dependency_overrides[_get_ai_service] = lambda: matching_svc
    app.dependency_overrides[get_db] = lambda: _mock_db()

    with (
        patch("app.api.v1.endpoints.ai.resolve_recruiter_ai_quota_company", AsyncMock(return_value=uuid.uuid4())),
        patch("app.api.v1.endpoints.ai.QuotaEnforcementService", return_value=quota_service),
    ):
        res = api_client.post(
            "/api/v1/ai/parse-jd",
            json={"job_title": "Python Dev", "job_description": "Need Python developer"},
        )

    assert res.status_code == status.HTTP_200_OK
    matching_svc.process_and_index_job.assert_awaited_once()
    assert (
        matching_svc.process_and_index_job.call_args.kwargs["status"]
        == JobStatus.DRAFT.value
    )
