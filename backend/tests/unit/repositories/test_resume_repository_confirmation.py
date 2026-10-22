from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.models import Resume
from app.repositories.resume_repository import ResumeRepository


def _resume(**overrides) -> Resume:
    data = {
        "id": uuid.uuid4(),
        "candidate_id": uuid.uuid4(),
        "title": "cv.pdf",
        "is_primary": False,
        "is_confirmed": False,
        "parsed_data": {"full_name": "Jane Doe", "skills": ["Python"]},
    }
    data.update(overrides)
    return Resume(**data)


def _session_for(resume: Resume) -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = resume
    session.execute = AsyncMock(return_value=result)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def test_confirm_draft_promotes_and_soft_deletes_other_drafts():
    resume = _resume()
    session = _session_for(resume)
    repository = ResumeRepository(session, Resume)

    confirmed = asyncio.run(
        repository.confirm_draft(
            resume_id=resume.id,
            candidate_id=resume.candidate_id,
            parsed_data={"full_name": "Jane Doe", "skills": ["Python"]},
            confirmed_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
        )
    )

    assert confirmed is resume
    assert resume.is_primary is True
    assert resume.is_confirmed is True
    assert resume.confirmed_at == datetime(2026, 1, 15, tzinfo=timezone.utc)
    assert session.execute.await_count == 3
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(resume)


def test_confirm_draft_is_idempotent_and_preserves_newer_draft():
    confirmed_at = datetime(2026, 1, 10, tzinfo=timezone.utc)
    resume = _resume(
        is_primary=True,
        is_confirmed=True,
        confirmed_at=confirmed_at,
    )
    session = _session_for(resume)
    repository = ResumeRepository(session, Resume)

    confirmed = asyncio.run(
        repository.confirm_draft(
            resume_id=resume.id,
            candidate_id=resume.candidate_id,
            parsed_data={"full_name": "Jane Doe", "skills": ["Python"]},
        )
    )

    assert confirmed is resume
    assert resume.confirmed_at == confirmed_at
    assert resume.is_primary is True
    assert resume.is_confirmed is True
    assert session.execute.await_count == 2
    session.flush.assert_awaited_once()
