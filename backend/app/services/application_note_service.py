from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException, ForbiddenException
from app.domain import hiring
from app.domain.enums import UserRole
from app.models import ApplicationNote, User
from app.repositories import ApplicationNoteRepository
from app.schemas.application_note import ApplicationNoteCreate, ApplicationNoteRead
from app.services.application_access import require_recruiter_application
from app.services.application_activity_service import record_activity

DEFAULT_NOTE_PAGE_SIZE = 50


class ApplicationNoteService:
    """Internal (recruiter-only) notes on an application.

    Notes are always scoped to an application. Any recruiter who can access the
    application may read the notes; only the author (or an admin) may edit or
    delete one. Every mutation appends an immutable history row that records the
    event *without* copying the note body.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.notes = ApplicationNoteRepository(session)

    async def _load_note(
        self,
        current_user: User,
        application_id: uuid.UUID,
        note_id: uuid.UUID,
    ) -> ApplicationNote:
        # Ownership of the *application* is enforced first so a note id from
        # another company is indistinguishable from a missing application.
        await require_recruiter_application(
            self.session, current_user, application_id
        )
        note = await self.notes.get_by_id_and_application(note_id, application_id)
        if note is None:
            raise EntityNotFoundException(f"Note {note_id} not found")
        return note

    @staticmethod
    def _authorize_mutation(current_user: User, note: ApplicationNote) -> None:
        if current_user.role == UserRole.ADMIN:
            return
        if note.author_id != current_user.id:
            raise ForbiddenException(
                "Only the note author or an admin can modify this note"
            )

    async def create_note(
        self,
        current_user: User,
        application_id: uuid.UUID,
        data: ApplicationNoteCreate,
    ) -> ApplicationNoteRead:
        await require_recruiter_application(
            self.session, current_user, application_id
        )
        note = ApplicationNote(
            application_id=application_id,
            author_id=current_user.id,
            content=data.content,
        )
        self.session.add(note)
        await self.session.flush()
        await record_activity(
            self.session,
            application_id=application_id,
            actor_id=current_user.id,
            action_type=hiring.NOTE_ADDED,
            metadata={"note_id": str(note.id)},
        )
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(note)
        return ApplicationNoteRead.model_validate(note)

    async def list_notes(
        self,
        current_user: User,
        application_id: uuid.UUID,
        skip: int = 0,
        limit: int = DEFAULT_NOTE_PAGE_SIZE,
    ) -> list[ApplicationNoteRead]:
        await require_recruiter_application(
            self.session, current_user, application_id
        )
        notes = await self.notes.list_by_application(
            application_id, skip=skip, limit=limit
        )
        return [ApplicationNoteRead.model_validate(note) for note in notes]

    async def update_note(
        self,
        current_user: User,
        application_id: uuid.UUID,
        note_id: uuid.UUID,
        content: str,
    ) -> ApplicationNoteRead:
        note = await self._load_note(current_user, application_id, note_id)
        self._authorize_mutation(current_user, note)

        note.content = content
        await self.session.flush()
        await record_activity(
            self.session,
            application_id=application_id,
            actor_id=current_user.id,
            action_type=hiring.NOTE_UPDATED,
            metadata={"note_id": str(note.id)},
        )
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(note)
        return ApplicationNoteRead.model_validate(note)

    async def delete_note(
        self,
        current_user: User,
        application_id: uuid.UUID,
        note_id: uuid.UUID,
    ) -> None:
        note = await self._load_note(current_user, application_id, note_id)
        self._authorize_mutation(current_user, note)

        note.is_deleted = True
        await self.session.flush()
        await record_activity(
            self.session,
            application_id=application_id,
            actor_id=current_user.id,
            action_type=hiring.NOTE_DELETED,
            metadata={"note_id": str(note.id)},
        )
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
