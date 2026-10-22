from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select, update

from app.database.base_class import utc_now
from app.models import Resume
from app.repositories.base import BaseRepository


class ResumeRepository(BaseRepository[Resume]):
    async def get_primary_by_candidate(
        self, candidate_id: Any
    ) -> Resume | None:
        """Return the candidate's active, explicitly confirmed primary resume."""
        stmt = select(Resume).where(
            Resume.candidate_id == candidate_id,
            Resume.is_primary == True,  # noqa: E712
            Resume.is_confirmed == True,  # noqa: E712
            Resume.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_owned_by_id(
        self,
        resume_id: Any,
        candidate_id: Any,
    ) -> Resume | None:
        """Return a non-deleted resume only when it belongs to the candidate."""
        stmt = select(Resume).where(
            Resume.id == resume_id,
            Resume.candidate_id == candidate_id,
            Resume.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_draft_by_candidate(
        self,
        candidate_id: Any,
    ) -> Resume | None:
        """Return the newest unconfirmed resume, including legacy primaries."""
        stmt = (
            select(Resume)
            .where(
                Resume.candidate_id == candidate_id,
                Resume.is_confirmed == False,  # noqa: E712
                Resume.is_deleted == False,  # noqa: E712
            )
            .order_by(Resume.created_at.desc(), Resume.id.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def upsert_draft(
        self,
        candidate_id: Any,
        title: str | None,
        parsed_data: dict | None,
    ) -> Resume:
        """Create or update the candidate's newest unconfirmed resume draft.

        Confirmed resumes are never modified by parsing or editing. The
        candidate keeps their previous active CV until they explicitly
        confirm the new draft.
        """
        resume = await self.get_latest_draft_by_candidate(candidate_id)
        if resume is None:
            resume = Resume(
                candidate_id=candidate_id,
                title=title,
                is_primary=False,
                is_confirmed=False,
                parsed_data=parsed_data,
            )
            self.session.add(resume)
        else:
            resume.title = title
            resume.parsed_data = parsed_data
            resume.is_primary = False
            resume.is_confirmed = False
            resume.confirmed_at = None
        await self.session.flush()
        await self.session.refresh(resume)
        return resume

    async def save_draft(
        self,
        resume_id: Any,
        candidate_id: Any,
        parsed_data: dict | None,
        title: str | None = None,
    ) -> Resume | None:
        """Update an owned unconfirmed draft. Confirmed rows are immutable."""
        resume = await self.get_owned_by_id(resume_id, candidate_id)
        if resume is None or resume.is_confirmed:
            return None
        resume.parsed_data = parsed_data
        if title is not None:
            resume.title = title
        await self.session.flush()
        await self.session.refresh(resume)
        return resume

    async def confirm_draft(
        self,
        resume_id: Any,
        candidate_id: Any,
        parsed_data: dict | None,
        title: str | None = None,
        confirmed_at: datetime | None = None,
    ) -> Resume | None:
        """Promote an owned draft to the single active confirmed resume.

        Any previously confirmed primary is demoted, and other unconfirmed
        drafts are soft-deleted so stale CV data cannot resurface. Repeated
        confirmation of the same active resume is idempotent.
        """
        resume = await self.get_owned_by_id(resume_id, candidate_id)
        if resume is None:
            return None

        was_confirmed = resume.is_confirmed
        now = confirmed_at or resume.confirmed_at or utc_now()

        demote_stmt = (
            update(Resume)
            .where(
                Resume.candidate_id == candidate_id,
                Resume.id != resume.id,
                Resume.is_primary == True,  # noqa: E712
                Resume.is_deleted == False,  # noqa: E712
            )
            .values(is_primary=False)
        )
        await self.session.execute(demote_stmt)

        resume.parsed_data = parsed_data
        if title is not None:
            resume.title = title
        resume.is_primary = True
        resume.is_confirmed = True
        resume.confirmed_at = now
        await self.session.flush()

        if not was_confirmed:
            stale_drafts_stmt = (
                update(Resume)
                .where(
                    Resume.candidate_id == candidate_id,
                    Resume.id != resume.id,
                    Resume.is_confirmed == False,  # noqa: E712
                    Resume.is_deleted == False,  # noqa: E712
                )
                .values(is_deleted=True)
            )
            await self.session.execute(stale_drafts_stmt)
        await self.session.refresh(resume)
        return resume

    async def upsert_primary(
        self,
        candidate_id: Any,
        title: str | None,
        parsed_data: dict | None,
    ) -> Resume:
        """Legacy-compatible confirmed primary upsert for trusted writes."""
        resume = await self.get_primary_by_candidate(candidate_id)
        if resume is None:
            resume = Resume(
                candidate_id=candidate_id,
                title=title,
                is_primary=True,
                is_confirmed=True,
                confirmed_at=utc_now(),
                parsed_data=parsed_data,
            )
            self.session.add(resume)
        else:
            resume.title = title
            resume.parsed_data = parsed_data
            resume.is_primary = True
            resume.is_confirmed = True
            resume.confirmed_at = utc_now()
        await self.session.flush()
        await self.session.refresh(resume)
        return resume
