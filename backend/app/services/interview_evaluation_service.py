from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
)
from app.domain import hiring
from app.domain.enums import UserRole
from app.models import Interview, InterviewEvaluation, User
from app.repositories import InterviewEvaluationRepository, InterviewRepository
from app.schemas.interview_evaluation import (
    InterviewEvaluationCreate,
    InterviewEvaluationRead,
    InterviewEvaluationUpdate,
)
from app.services.application_access import require_recruiter_application
from app.services.application_activity_service import record_activity


class InterviewEvaluationService:
    """Private interview scorecards.

    Each interviewer may submit **one** scorecard per interview; a later
    submission is an authorized update (PATCH), never a second row. The rule is
    enforced both in the service and by a filtered unique database index, so a
    concurrent duplicate insert is rejected rather than silently accepted.
    Evaluations are visible to the hiring company's recruiters and admins, but
    never to candidates.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.evaluations = InterviewEvaluationRepository(session)
        self.interviews = InterviewRepository(session, Interview)

    async def _load_interview(
        self,
        current_user: User,
        application_id: uuid.UUID,
        interview_id: uuid.UUID,
    ) -> Interview:
        await require_recruiter_application(
            self.session, current_user, application_id
        )
        interview = await self.interviews.get_by_id_with_application(interview_id)
        if interview is None or interview.application_id != application_id:
            raise EntityNotFoundException(f"Interview {interview_id} not found")
        return interview

    async def _load_evaluation(
        self,
        current_user: User,
        application_id: uuid.UUID,
        evaluation_id: uuid.UUID,
    ) -> InterviewEvaluation:
        await require_recruiter_application(
            self.session, current_user, application_id
        )
        evaluation = await self.evaluations.get_by_id_and_application(
            evaluation_id, application_id
        )
        if evaluation is None:
            raise EntityNotFoundException(f"Evaluation {evaluation_id} not found")
        return evaluation

    @staticmethod
    def _authorize_mutation(
        current_user: User, evaluation: InterviewEvaluation
    ) -> None:
        if current_user.role == UserRole.ADMIN:
            return
        if evaluation.evaluator_id != current_user.id:
            raise ForbiddenException(
                "Only the evaluator or an admin can modify this evaluation"
            )

    async def create_evaluation(
        self,
        current_user: User,
        application_id: uuid.UUID,
        interview_id: uuid.UUID,
        data: InterviewEvaluationCreate,
    ) -> InterviewEvaluationRead:
        await self._load_interview(current_user, application_id, interview_id)

        existing = await self.evaluations.get_by_interview_and_evaluator(
            interview_id, current_user.id
        )
        if existing is not None:
            raise ConflictException(
                "You have already evaluated this interview. "
                "Update your existing evaluation instead."
            )

        evaluation = InterviewEvaluation(
            interview_id=interview_id,
            application_id=application_id,
            evaluator_id=current_user.id,
            rating=data.rating,
            strengths=data.strengths,
            weaknesses=data.weaknesses,
            recommendation=data.recommendation,
            notes=data.notes,
        )
        self.session.add(evaluation)
        try:
            await self.session.flush()
            await record_activity(
                self.session,
                application_id=application_id,
                actor_id=current_user.id,
                action_type=hiring.EVALUATION_ADDED,
                metadata={
                    "evaluation_id": str(evaluation.id),
                    "interview_id": str(interview_id),
                },
            )
            await self.session.commit()
        except IntegrityError:
            # Lost a race against a concurrent insert of the same scorecard.
            await self.session.rollback()
            raise ConflictException(
                "You have already evaluated this interview. "
                "Update your existing evaluation instead."
            ) from None
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(evaluation)
        return InterviewEvaluationRead.model_validate(evaluation)

    async def list_by_interview(
        self,
        current_user: User,
        application_id: uuid.UUID,
        interview_id: uuid.UUID,
    ) -> list[InterviewEvaluationRead]:
        await self._load_interview(current_user, application_id, interview_id)
        rows = await self.evaluations.list_by_interview(interview_id)
        return [InterviewEvaluationRead.model_validate(row) for row in rows]

    async def list_by_application(
        self,
        current_user: User,
        application_id: uuid.UUID,
    ) -> list[InterviewEvaluationRead]:
        await require_recruiter_application(
            self.session, current_user, application_id
        )
        rows = await self.evaluations.list_by_application(application_id)
        return [InterviewEvaluationRead.model_validate(row) for row in rows]

    async def update_evaluation(
        self,
        current_user: User,
        application_id: uuid.UUID,
        evaluation_id: uuid.UUID,
        data: InterviewEvaluationUpdate,
    ) -> InterviewEvaluationRead:
        evaluation = await self._load_evaluation(
            current_user, application_id, evaluation_id
        )
        self._authorize_mutation(current_user, evaluation)

        if data.rating is not None:
            evaluation.rating = data.rating
        if data.strengths is not None:
            evaluation.strengths = data.strengths
        if data.weaknesses is not None:
            evaluation.weaknesses = data.weaknesses
        if data.recommendation is not None:
            evaluation.recommendation = data.recommendation
        if data.notes is not None:
            evaluation.notes = data.notes

        await self.session.flush()
        await record_activity(
            self.session,
            application_id=application_id,
            actor_id=current_user.id,
            action_type=hiring.EVALUATION_UPDATED,
            metadata={"evaluation_id": str(evaluation.id)},
        )
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(evaluation)
        return InterviewEvaluationRead.model_validate(evaluation)

    async def delete_evaluation(
        self,
        current_user: User,
        application_id: uuid.UUID,
        evaluation_id: uuid.UUID,
    ) -> None:
        evaluation = await self._load_evaluation(
            current_user, application_id, evaluation_id
        )
        self._authorize_mutation(current_user, evaluation)

        evaluation.is_deleted = True
        await self.session.flush()
        await record_activity(
            self.session,
            application_id=application_id,
            actor_id=current_user.id,
            action_type=hiring.EVALUATION_DELETED,
            metadata={"evaluation_id": str(evaluation.id)},
        )
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
