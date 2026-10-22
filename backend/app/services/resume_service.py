from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, EntityNotFoundException
from app.models import CandidateProfile, Resume
from app.repositories import ResumeRepository
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.ai_matching_service import AIMatchingService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResumeConfirmationResult:
    resume: Resume
    indexing_status: Literal["indexed", "failed"]
    message: str


class ResumeService:
    """Candidate-owned CV draft and confirmation lifecycle."""

    def __init__(
        self,
        session: AsyncSession,
        matching_service: AIMatchingService | None = None,
    ) -> None:
        self.session = session
        self.resumes = ResumeRepository(session, Resume)
        self.matching_service = matching_service

    def _matching_service(self) -> AIMatchingService:
        if self.matching_service is None:
            self.matching_service = AIMatchingService()
        return self.matching_service

    async def get_confirmed_resume(self, candidate_id: uuid.UUID) -> Resume | None:
        return await self.resumes.get_primary_by_candidate(candidate_id)

    async def get_draft(self, candidate_id: uuid.UUID) -> Resume | None:
        return await self.resumes.get_latest_draft_by_candidate(candidate_id)

    async def save_draft(
        self,
        candidate_id: uuid.UUID,
        resume_id: uuid.UUID,
        parsed_data: ParsedResumeSchema,
        title: str | None = None,
    ) -> Resume:
        draft = await self.resumes.get_owned_by_id(resume_id, candidate_id)
        if draft is None:
            raise EntityNotFoundException("Resume draft not found")
        if draft.is_confirmed:
            raise ConflictException(
                "Confirmed resumes cannot be edited. Upload a new CV instead."
            )

        updated = await self.resumes.save_draft(
            resume_id=resume_id,
            candidate_id=candidate_id,
            parsed_data=parsed_data.model_dump(mode="json"),
            title=title,
        )
        if updated is None:
            raise EntityNotFoundException("Resume draft not found")

        try:
            await self.session.commit()
            await self.session.refresh(updated)
        except Exception:
            await self.session.rollback()
            raise
        return updated

    async def confirm_resume(
        self,
        candidate_id: uuid.UUID,
        resume_id: uuid.UUID,
    ) -> ResumeConfirmationResult:
        draft = await self.resumes.get_owned_by_id(resume_id, candidate_id)
        if draft is None:
            raise EntityNotFoundException("Resume draft not found")

        parsed_resume = ParsedResumeSchema.model_validate(draft.parsed_data or {})
        parsed_payload = parsed_resume.model_dump(mode="json")

        confirmed = await self.resumes.confirm_draft(
            resume_id=resume_id,
            candidate_id=candidate_id,
            parsed_data=parsed_payload,
            title=draft.title,
        )
        if confirmed is None:
            raise EntityNotFoundException("Resume draft not found")

        profile = await self.session.get(CandidateProfile, candidate_id)
        if profile is not None:
            if parsed_resume.full_name:
                profile.full_name = parsed_resume.full_name
            if parsed_resume.phone:
                profile.phone = parsed_resume.phone
            if parsed_resume.title:
                profile.title = parsed_resume.title

        try:
            await self.session.commit()
            await self.session.refresh(confirmed)
        except Exception:
            await self.session.rollback()
            raise

        try:
            await self._matching_service().index_confirmed_resume(
                candidate_id=candidate_id,
                resume_id=confirmed.id,
                parsed_resume=parsed_resume,
                confirmed_at=confirmed.confirmed_at,
            )
        except Exception:
            logger.exception(
                "Confirmed resume %s but failed to index it in Qdrant", confirmed.id
            )
            return ResumeConfirmationResult(
                resume=confirmed,
                indexing_status="failed",
                message=(
                    "CV đã được xác nhận nhưng chưa thể lập chỉ mục tìm kiếm. "
                    "Vui lòng thử lại."
                ),
            )

        return ResumeConfirmationResult(
            resume=confirmed,
            indexing_status="indexed",
            message="CV đã được xác nhận và sẵn sàng cho tìm kiếm, ghép nối.",
        )
