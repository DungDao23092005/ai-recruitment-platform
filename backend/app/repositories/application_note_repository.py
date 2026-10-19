from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApplicationNote
from app.repositories.base import BaseRepository


class ApplicationNoteRepository(BaseRepository[ApplicationNote]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ApplicationNote)

    async def list_by_application(
        self,
        application_id: Any,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ApplicationNote]:
        """Return an application's notes oldest-first, excluding deleted rows."""
        stmt = (
            select(ApplicationNote)
            .where(
                ApplicationNote.application_id == application_id,
                ApplicationNote.is_deleted == False,  # noqa: E712
            )
            .order_by(ApplicationNote.created_at.asc(), ApplicationNote.id.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_application(self, application_id: Any) -> int:
        stmt = select(func.count(ApplicationNote.id)).where(
            ApplicationNote.application_id == application_id,
            ApplicationNote.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def get_by_id_and_application(
        self,
        note_id: Any,
        application_id: Any,
    ) -> ApplicationNote | None:
        """Retrieve a note scoped to its application (no note-ID-only bypass).

        A note can only ever be resolved together with the application path it
        was requested under, so a leaked note id cannot be used to read another
        application's note.
        """
        stmt = select(ApplicationNote).where(
            ApplicationNote.id == note_id,
            ApplicationNote.application_id == application_id,
            ApplicationNote.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
