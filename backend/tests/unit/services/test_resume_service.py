from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ConflictException, EntityNotFoundException
from app.models import CandidateProfile, Resume
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.resume_service import ResumeService


def _parsed_resume() -> ParsedResumeSchema:
    return ParsedResumeSchema(
        full_name="Jane Doe",
        phone="+84 900 123 456",
        title="Backend Engineer",
        skills=["Python"],
    )


def _draft(**overrides) -> Resume:
    data = {
        "id": uuid.uuid4(),
        "candidate_id": uuid.uuid4(),
        "title": "cv.pdf",
        "is_primary": False,
        "is_confirmed": False,
        "parsed_data": _parsed_resume().model_dump(mode="json"),
    }
    data.update(overrides)
    return Resume(**data)


def _service(session: MagicMock, matching_service: MagicMock | None = None):
    with patch(
        "app.services.resume_service.ResumeRepository"
    ) as repository_class:
        repository = MagicMock()
        repository.get_owned_by_id = AsyncMock()
        repository.save_draft = AsyncMock()
        repository.confirm_draft = AsyncMock()
        repository.get_primary_by_candidate = AsyncMock()
        repository.get_latest_draft_by_candidate = AsyncMock()
        repository_class.return_value = repository
        service = ResumeService(
            session,
            matching_service=matching_service or MagicMock(),
        )
    return service, repository


@pytest.mark.asyncio
async def test_save_draft_rejects_missing_owned_draft():
    session = MagicMock()
    session.commit = AsyncMock()
    service, repository = _service(session)
    repository.get_owned_by_id.return_value = None

    with pytest.raises(EntityNotFoundException):
        await service.save_draft(
            candidate_id=uuid.uuid4(),
            resume_id=uuid.uuid4(),
            parsed_data=_parsed_resume(),
        )

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_draft_rejects_confirmed_resume():
    session = MagicMock()
    session.commit = AsyncMock()
    service, repository = _service(session)
    repository.get_owned_by_id.return_value = _draft(is_confirmed=True)

    with pytest.raises(ConflictException):
        await service.save_draft(
            candidate_id=uuid.uuid4(),
            resume_id=uuid.uuid4(),
            parsed_data=_parsed_resume(),
        )

    repository.save_draft.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_draft_persists_parsed_data_for_owned_draft():
    session = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    service, repository = _service(session)
    draft = _draft()
    candidate_id = draft.candidate_id
    repository.get_owned_by_id.return_value = draft
    repository.save_draft.return_value = draft

    result = await service.save_draft(
        candidate_id=candidate_id,
        resume_id=draft.id,
        parsed_data=_parsed_resume(),
        title="updated.pdf",
    )

    assert result is draft
    repository.save_draft.assert_awaited_once_with(
        resume_id=draft.id,
        candidate_id=candidate_id,
        parsed_data=_parsed_resume().model_dump(mode="json"),
        title="updated.pdf",
    )
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(draft)


@pytest.mark.asyncio
async def test_confirm_resume_commits_profile_before_indexing():
    session = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    matching_service = MagicMock()
    matching_service.index_confirmed_resume = AsyncMock()
    service, repository = _service(session, matching_service)

    draft = _draft()
    confirmed = _draft(
        id=draft.id,
        candidate_id=draft.candidate_id,
        is_primary=True,
        is_confirmed=True,
        confirmed_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
    )
    profile = CandidateProfile(
        id=draft.candidate_id,
        user_id=uuid.uuid4(),
        full_name="Old Name",
        phone=None,
        title=None,
    )
    session.get = AsyncMock(return_value=profile)
    repository.get_owned_by_id.return_value = draft
    repository.confirm_draft.return_value = confirmed

    order: list[str] = []
    session.commit.side_effect = lambda: order.append("commit")
    matching_service.index_confirmed_resume.side_effect = (
        lambda **kwargs: order.append("index")
    )

    result = await service.confirm_resume(
        candidate_id=draft.candidate_id,
        resume_id=draft.id,
    )

    assert result.resume is confirmed
    assert result.indexing_status == "indexed"
    assert order == ["commit", "index"]
    assert profile.full_name == "Jane Doe"
    assert profile.phone == "+84 900 123 456"
    assert profile.title == "Backend Engineer"
    matching_service.index_confirmed_resume.assert_awaited_once_with(
        candidate_id=draft.candidate_id,
        resume_id=confirmed.id,
        parsed_resume=_parsed_resume(),
        confirmed_at=confirmed.confirmed_at,
    )


@pytest.mark.asyncio
async def test_confirm_resume_keeps_confirmation_when_indexing_fails():
    session = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.rollback = AsyncMock()
    matching_service = MagicMock()
    matching_service.index_confirmed_resume = AsyncMock(
        side_effect=RuntimeError("qdrant unavailable")
    )
    service, repository = _service(session, matching_service)

    draft = _draft()
    confirmed = _draft(
        id=draft.id,
        candidate_id=draft.candidate_id,
        is_primary=True,
        is_confirmed=True,
        confirmed_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
    )
    repository.get_owned_by_id.return_value = draft
    repository.confirm_draft.return_value = confirmed

    result = await service.confirm_resume(
        candidate_id=draft.candidate_id,
        resume_id=draft.id,
    )

    assert result.resume is confirmed
    assert result.indexing_status == "failed"
    assert "thử lại" in result.message.lower()
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirm_resume_rejects_missing_owned_resume():
    session = MagicMock()
    session.commit = AsyncMock()
    matching_service = MagicMock()
    matching_service.index_confirmed_resume = AsyncMock()
    service, repository = _service(session, matching_service)
    repository.get_owned_by_id.return_value = None

    with pytest.raises(EntityNotFoundException):
        await service.confirm_resume(
            candidate_id=uuid.uuid4(),
            resume_id=uuid.uuid4(),
        )

    repository.confirm_draft.assert_not_awaited()
    matching_service.index_confirmed_resume.assert_not_awaited()
