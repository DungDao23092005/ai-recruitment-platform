from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.api.v1.endpoints.ai import _get_rag_chat_service
from app.core.exceptions import AIError
from app.domain.enums import MembershipRole, UserRole
from app.main import app
from app.schemas.ai_chat import ChatResponse
from app.services.quota_enforcement_service import (
    QuotaEnforcementService,
    ReservationResult,
)

KNOWN_COMPANY_ID = uuid.uuid4()
KNOWN_USER_ID = uuid.uuid4()


class _FakeUser:
    def __init__(self, role: UserRole = UserRole.RECRUITER, user_id: uuid.UUID | None = None):
        self.id = user_id or KNOWN_USER_ID
        self.role = role
        self.is_active = True
        self.email = "recruiter@example.com"
        self.recruiter_profile = SimpleNamespace(company_id=KNOWN_COMPANY_ID)
        self.awaitable_attrs = SimpleNamespace(
            candidate_profile=AsyncMock(return_value=None)
        )


def _fake_db_session(role: MembershipRole = MembershipRole.RECRUITER, has_membership: bool = True) -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()

    def _execute(stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars().unique().first.return_value = None
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()

        if "from company_memberships" in compiled:
            if has_membership:
                membership = SimpleNamespace(
                    id=uuid.uuid4(),
                    company_id=KNOWN_COMPANY_ID,
                    role=role,
                    company=SimpleNamespace(
                        id=KNOWN_COMPANY_ID,
                        name="TechNova AI",
                        slug="technova-ai",
                    ),
                )
                result.scalar_one_or_none.return_value = membership
                result.scalars().unique().all.return_value = [membership]
            else:
                result.scalar_one_or_none.return_value = None
                result.scalars().unique().all.return_value = []
        return result

    session.execute = AsyncMock(side_effect=_execute)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def mock_rag_chat_service():
    service = MagicMock()
    service.chat = AsyncMock(
        return_value=ChatResponse(
            answer="Dạ, TechNova hiện có 3 vị trí tuyển dụng.",
            confidence=0.92,
            sources=[],
            suggested_followups=["Chi tiết từng vị trí?"],
        )
    )
    return service


@pytest.fixture
def mock_quota_service():
    with patch("app.api.v1.endpoints.ai.QuotaEnforcementService") as mock_class:
        service = MagicMock(spec=QuotaEnforcementService)
        reservation_result = ReservationResult(
            usage_id=uuid.uuid4(),
            remaining=4,
            limit=5,
            used=1,
            bypassed=False,
        )
        service.reserve_ai_quota = AsyncMock(return_value=reservation_result)
        service.finalize_reservation = AsyncMock()
        service.release_reservation = AsyncMock()
        mock_class.return_value = service
        yield service


def _build_client(db_session, user, mock_rag_chat, mock_redis=None):
    app.dependency_overrides[_get_rag_chat_service] = lambda: mock_rag_chat
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: user

    original_redis = getattr(app.state, "redis", None)
    app.state.redis = mock_redis

    client = TestClient(app)
    return client, original_redis


def _restore_client(original_redis):
    app.dependency_overrides.clear()
    app.state.redis = original_redis


def test_recruiter_chat_success_consumes_quota_and_finalizes(
    mock_rag_chat_service, mock_quota_service
):
    mock_redis = AsyncMock()
    # First eval is LUA_CLAIM -> returns ["ACQUIRED"]
    # Second eval is LUA_COMPLETE -> returns 1
    mock_redis.eval.side_effect = [["ACQUIRED"], 1]

    session = _fake_db_session()
    user = _FakeUser()
    client, orig_redis = _build_client(session, user, mock_rag_chat_service, mock_redis)

    try:
        resp = client.post(
            "/api/v1/ai/chat",
            json={"message": "Các vị trí đang mở?", "history": []},
            headers={"Idempotency-Key": "rec_chat_001"},
        )

        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "TechNova" in data["answer"]

        # Verifies Company quota was reserved with company_id and finalized
        mock_quota_service.reserve_ai_quota.assert_awaited_once()
        kwargs = mock_quota_service.reserve_ai_quota.call_args.kwargs
        assert kwargs["company_id"] == KNOWN_COMPANY_ID
        assert kwargs["idempotency_key"] == "rec_chat_001"
        mock_quota_service.finalize_reservation.assert_awaited_once()
        mock_quota_service.release_reservation.assert_not_called()
    finally:
        _restore_client(orig_redis)


def test_recruiter_chat_llm_failure_releases_quota_and_lock(
    mock_rag_chat_service, mock_quota_service
):
    mock_redis = AsyncMock()
    mock_redis.eval.side_effect = [["ACQUIRED"], 1]  # claim then release
    mock_rag_chat_service.chat.side_effect = AIError("Model provider timeout")

    session = _fake_db_session()
    user = _FakeUser()
    client, orig_redis = _build_client(session, user, mock_rag_chat_service, mock_redis)

    try:
        resp = client.post(
            "/api/v1/ai/chat",
            json={"message": "Các vị trí đang mở?", "history": []},
            headers={"Idempotency-Key": "rec_chat_002"},
        )

        assert resp.status_code == status.HTTP_502_BAD_GATEWAY
        # Verifies quota reservation was released safely
        mock_quota_service.release_reservation.assert_awaited_once()
        mock_quota_service.finalize_reservation.assert_not_called()
    finally:
        _restore_client(orig_redis)


def test_recruiter_chat_replay_returns_cached_without_llm_or_quota(
    mock_rag_chat_service, mock_quota_service
):
    mock_redis = AsyncMock()
    cached_payload = json.dumps({
        "answer": "Cached answer from previous call",
        "confidence": 0.95,
        "sources": [],
        "suggested_followups": [],
        "recommended_job_ids": [],
    })
    mock_redis.eval.return_value = ["COMPLETED", cached_payload]

    session = _fake_db_session()
    user = _FakeUser()
    client, orig_redis = _build_client(session, user, mock_rag_chat_service, mock_redis)

    try:
        resp = client.post(
            "/api/v1/ai/chat",
            json={"message": "Các vị trí đang mở?", "history": []},
            headers={"Idempotency-Key": "rec_chat_003"},
        )

        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["answer"] == "Cached answer from previous call"

        # Neither LLM nor quota reservation should be called on replay
        mock_rag_chat_service.chat.assert_not_called()
        mock_quota_service.reserve_ai_quota.assert_not_called()
    finally:
        _restore_client(orig_redis)


def test_recruiter_chat_mismatch_payload_returns_409(
    mock_rag_chat_service, mock_quota_service
):
    mock_redis = AsyncMock()
    mock_redis.eval.return_value = ["MISMATCH"]

    session = _fake_db_session()
    user = _FakeUser()
    client, orig_redis = _build_client(session, user, mock_rag_chat_service, mock_redis)

    try:
        resp = client.post(
            "/api/v1/ai/chat",
            json={"message": "A different question with same key", "history": []},
            headers={"Idempotency-Key": "rec_chat_004"},
        )

        assert resp.status_code == status.HTTP_409_CONFLICT
        assert "Idempotency-Key" in resp.json()["detail"]
        mock_rag_chat_service.chat.assert_not_called()
        mock_quota_service.reserve_ai_quota.assert_not_called()
    finally:
        _restore_client(orig_redis)


def test_recruiter_chat_redis_unavailable_fails_closed_503(
    mock_rag_chat_service, mock_quota_service
):
    session = _fake_db_session()
    user = _FakeUser()
    # redis is None
    client, orig_redis = _build_client(session, user, mock_rag_chat_service, mock_redis=None)

    try:
        resp = client.post(
            "/api/v1/ai/chat",
            json={"message": "Testing redis down", "history": []},
            headers={"Idempotency-Key": "rec_chat_005"},
        )

        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "Redis" in resp.json()["detail"]
        mock_rag_chat_service.chat.assert_not_called()
        mock_quota_service.reserve_ai_quota.assert_not_called()
    finally:
        _restore_client(orig_redis)


def test_recruiter_chat_interviewer_role_returns_403(
    mock_rag_chat_service, mock_quota_service
):
    mock_redis = AsyncMock()
    session = _fake_db_session(role=MembershipRole.INTERVIEWER)
    user = _FakeUser()
    client, orig_redis = _build_client(session, user, mock_rag_chat_service, mock_redis)

    try:
        resp = client.post(
            "/api/v1/ai/chat",
            json={"message": "Testing interviewer forbidden", "history": []},
        )

        assert resp.status_code == status.HTTP_403_FORBIDDEN
    finally:
        _restore_client(orig_redis)


def test_recruiter_chat_no_company_workspace_returns_403(
    mock_rag_chat_service, mock_quota_service
):
    mock_redis = AsyncMock()
    session = _fake_db_session(has_membership=False)
    user = _FakeUser()
    client, orig_redis = _build_client(session, user, mock_rag_chat_service, mock_redis)

    try:
        resp = client.post(
            "/api/v1/ai/chat",
            json={"message": "Testing no workspace", "history": []},
        )

        assert resp.status_code == status.HTTP_403_FORBIDDEN
    finally:
        _restore_client(orig_redis)


def test_recruiter_chat_invalid_idempotency_key_length_returns_400(
    mock_rag_chat_service, mock_quota_service
):
    mock_redis = AsyncMock()
    session = _fake_db_session()
    user = _FakeUser()
    client, orig_redis = _build_client(session, user, mock_rag_chat_service, mock_redis)

    try:
        resp = client.post(
            "/api/v1/ai/chat",
            json={"message": "Testing too long key", "history": []},
            headers={"Idempotency-Key": "x" * 129},
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "Idempotency-Key" in resp.json()["detail"]
    finally:
        _restore_client(orig_redis)
