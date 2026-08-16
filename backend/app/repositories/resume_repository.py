from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.models import Resume
from app.repositories.base import BaseRepository


class ResumeRepository(BaseRepository[Resume]):
    async def get_primary_by_candidate(
        self, candidate_id: Any
    ) -> Resume | None:
        stmt = select(Resume).where(
            Resume.candidate_id == candidate_id,
            Resume.is_primary == True,  # noqa: E712
            Resume.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_primary(
        self,
        candidate_id: Any,
        title: str | None,
        parsed_data: dict | None,
    ) -> Resume:
        """Create or update the candidate's single primary resume.

        A candidate has at most one primary resume: uploading a new CV
        updates the existing primary row instead of creating duplicates.
        """
        resume = await self.get_primary_by_candidate(candidate_id)
        if resume is None:
            resume = Resume(
                candidate_id=candidate_id,
                title=title,
                is_primary=True,
                parsed_data=parsed_data,
            )
            self.session.add(resume)
        else:
            resume.title = title
            resume.is_primary = True
            resume.parsed_data = parsed_data
        await self.session.flush()
        await self.session.refresh(resume)
        return resume