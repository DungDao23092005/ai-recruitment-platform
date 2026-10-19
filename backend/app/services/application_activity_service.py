from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import hiring
from app.models import ApplicationActivity, User
from app.repositories import ApplicationActivityRepository
from app.schemas.application_activity import (
    ApplicationActivityRead,
    CandidateApplicationActivityRead,
)
from app.services.application_access import (
    require_candidate_application,
    require_recruiter_application,
)

DEFAULT_ACTIVITY_PAGE_SIZE = 50


async def record_activity(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    actor_id: uuid.UUID,
    action_type: str,
    from_status: str | None = None,
    to_status: str | None = None,
    note: str | None = None,
    metadata: Optional[dict[str, Any]] = None,
) -> ApplicationActivity:
    """Append one immutable history row inside the caller's transaction.

    This is the single write path for the audit trail. It never commits, so the
    activity commits (or rolls back) atomically with the state change it
    describes. ``note`` is reserved for a short human-readable label - callers
    must never copy private note bodies or evaluation content into it, and
    ``metadata`` should carry identifiers, not payloads.
    """
    activity = ApplicationActivity(
        application_id=application_id,
        actor_id=actor_id,
        action_type=action_type,
        from_status=from_status,
        to_status=to_status,
        note=note,
        metadata_json=(
            json.dumps(metadata, ensure_ascii=False) if metadata is not None else None
        ),
    )
    return await ApplicationActivityRepository(session).append(activity)


class ApplicationActivityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.activities = ApplicationActivityRepository(session)

    async def list_activities(
        self,
        current_user: User,
        application_id: uuid.UUID,
        skip: int = 0,
        limit: int = DEFAULT_ACTIVITY_PAGE_SIZE,
    ) -> list[ApplicationActivityRead]:
        """Full recruiter/admin history for an application (newest first)."""
        await require_recruiter_application(
            self.session, current_user, application_id
        )
        rows = await self.activities.list_by_application(
            application_id, skip=skip, limit=limit
        )
        return [ApplicationActivityRead.model_validate(row) for row in rows]

    async def list_candidate_timeline(
        self,
        current_user: User,
        application_id: uuid.UUID,
        skip: int = 0,
        limit: int = DEFAULT_ACTIVITY_PAGE_SIZE,
    ) -> list[CandidateApplicationActivityRead]:
        """Candidate-visible timeline for one of the caller's applications.

        The action-type allowlist is applied in the SQL query, so internal rows
        (notes, evaluations) are never even loaded for a candidate request.
        """
        await require_candidate_application(
            self.session, current_user, application_id
        )
        rows = await self.activities.list_by_application(
            application_id,
            skip=skip,
            limit=limit,
            action_types=hiring.CANDIDATE_VISIBLE_ACTIVITY_TYPES,
        )
        return [CandidateApplicationActivityRead.model_validate(row) for row in rows]
