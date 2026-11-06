from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
)
from app.domain import hiring
from app.domain.enums import MembershipRole, MembershipStatus
from app.models import Interview, InterviewEvaluation, User
from app.models.interview_evaluation import (
    EVALUATION_STATUS_DRAFT,
    EVALUATION_STATUS_SUBMITTED,
)
from app.repositories import (
    InterviewAssignmentRepository,
    InterviewEvaluationRepository,
    InterviewRepository,
)
from app.schemas.interview_evaluation import (
    InterviewEvaluationCreate,
    InterviewEvaluationRead,
    InterviewEvaluationUpdate,
)
from app.services.application_access import require_recruiter_application
from app.services.application_activity_service import record_activity
from app.services.interview_access import require_workspace_interview
from app.services.workspace_service import WorkspaceContext


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InterviewEvaluationService:
    """Private interview scorecards with an explicit draft/submit workflow.

    A scorecard starts as ``draft``. Only its author may edit or delete it, and
    only while it is still a draft. Submission is an atomic draft -> submitted
    transition; a submitted scorecard is permanently immutable, including for
    company admins and platform administrators.

    Visibility is blind:
    * managers see submitted scorecards plus their own draft;
    * interviewers see only their own scorecard until they submit it, after
      which they can see the other submitted scorecards for that interview.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.evaluations = InterviewEvaluationRepository(session)
        self.interviews = InterviewRepository(session, Interview)
        self.assignments = InterviewAssignmentRepository(session)

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

    async def _load_workspace_interview(
        self,
        context: WorkspaceContext,
        interview_id: uuid.UUID,
    ) -> Interview:
        access = await require_workspace_interview(
            self.session, context, interview_id
        )
        return access.interview

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

    async def _load_workspace_evaluation(
        self,
        context: WorkspaceContext,
        interview_id: uuid.UUID,
        evaluation_id: uuid.UUID,
    ) -> InterviewEvaluation:
        await self._load_workspace_interview(context, interview_id)
        evaluation = await self.evaluations.get_by_id_active(evaluation_id)
        if evaluation is None or evaluation.interview_id != interview_id:
            raise EntityNotFoundException(f"Evaluation {evaluation_id} not found")
        return evaluation

    @staticmethod
    def _authorize_author(
        actor_id: uuid.UUID,
        evaluation: InterviewEvaluation,
    ) -> None:
        if evaluation.evaluator_id != actor_id:
            raise ForbiddenException(
                "Only the author can modify this evaluation"
            )

    @staticmethod
    def _ensure_draft(evaluation: InterviewEvaluation) -> None:
        if evaluation.status == EVALUATION_STATUS_SUBMITTED:
            raise ConflictException(
                "Submitted evaluations are immutable"
            )

    @staticmethod
    def _visible_evaluations(
        rows: list[InterviewEvaluation],
        viewer_id: uuid.UUID,
        *,
        blind: bool,
        active_interview_ids: set[uuid.UUID] | None = None,
    ) -> list[InterviewEvaluation]:
        def _can_view_own_draft(row: InterviewEvaluation) -> bool:
            if row.evaluator_id != viewer_id:
                return False
            if active_interview_ids is None:
                return True
            return row.interview_id in active_interview_ids

        if not blind:
            return [
                row
                for row in rows
                if row.status == EVALUATION_STATUS_SUBMITTED
                or _can_view_own_draft(row)
            ]

        own = next(
            (row for row in rows if row.evaluator_id == viewer_id),
            None,
        )
        if own is None:
            return []
        if own.status != EVALUATION_STATUS_SUBMITTED:
            return [own] if _can_view_own_draft(own) else []
        return [
            row for row in rows if row.status == EVALUATION_STATUS_SUBMITTED
        ]

    async def _active_draft_interview_ids_for_legacy_list(
        self,
        rows: list[InterviewEvaluation],
        viewer_id: uuid.UUID,
    ) -> set[uuid.UUID]:
        own_draft_interview_ids = {
            row.interview_id
            for row in rows
            if row.evaluator_id == viewer_id
            and row.status != EVALUATION_STATUS_SUBMITTED
        }
        active_ids: set[uuid.UUID] = set()
        for interview_id in own_draft_interview_ids:
            if not await self.assignments.has_inactive_without_active_for_interview_user(
                interview_id, viewer_id
            ):
                active_ids.add(interview_id)
        return active_ids

    async def _require_active_workspace_assignment(
        self,
        context: WorkspaceContext,
        interview_id: uuid.UUID,
        message: str,
    ) -> None:
        if context.is_platform_admin:
            return
        if (
            context.membership is not None
            and context.membership.status != MembershipStatus.ACTIVE
        ):
            raise ForbiddenException(
                "Your workspace membership is no longer active"
            )
        assignment = await self.assignments.get_active_for_interview_user(
            interview_id, context.user.id
        )
        if assignment is None:
            raise ForbiddenException(message)

    async def _create_draft(
        self,
        *,
        interview_id: uuid.UUID,
        application_id: uuid.UUID,
        author_id: uuid.UUID,
        data: InterviewEvaluationCreate,
    ) -> InterviewEvaluationRead:
        existing = await self.evaluations.get_by_interview_and_evaluator(
            interview_id, author_id
        )
        if existing is not None:
            raise ConflictException(
                "You have already evaluated this interview. "
                "Update your existing evaluation instead."
            )

        evaluation = InterviewEvaluation(
            interview_id=interview_id,
            application_id=application_id,
            evaluator_id=author_id,
            rating=data.rating,
            strengths=data.strengths,
            weaknesses=data.weaknesses,
            recommendation=data.recommendation,
            notes=data.notes,
            status=EVALUATION_STATUS_DRAFT,
        )
        self.session.add(evaluation)
        try:
            await self.session.flush()
            await record_activity(
                self.session,
                application_id=application_id,
                actor_id=author_id,
                action_type=hiring.EVALUATION_ADDED,
                metadata={
                    "evaluation_id": str(evaluation.id),
                    "interview_id": str(interview_id),
                    "status": EVALUATION_STATUS_DRAFT,
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

    async def _update_draft(
        self,
        *,
        evaluation: InterviewEvaluation,
        actor_id: uuid.UUID,
        data: InterviewEvaluationUpdate,
    ) -> InterviewEvaluationRead:
        self._authorize_author(actor_id, evaluation)
        self._ensure_draft(evaluation)

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

        try:
            await self.session.flush()
            await record_activity(
                self.session,
                application_id=evaluation.application_id,
                actor_id=actor_id,
                action_type=hiring.EVALUATION_UPDATED,
                metadata={
                    "evaluation_id": str(evaluation.id),
                    "status": EVALUATION_STATUS_DRAFT,
                },
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(evaluation)
        return InterviewEvaluationRead.model_validate(evaluation)

    async def _delete_draft(
        self,
        *,
        evaluation: InterviewEvaluation,
        actor_id: uuid.UUID,
    ) -> None:
        self._authorize_author(actor_id, evaluation)
        self._ensure_draft(evaluation)

        evaluation.is_deleted = True
        try:
            await self.session.flush()
            await record_activity(
                self.session,
                application_id=evaluation.application_id,
                actor_id=actor_id,
                action_type=hiring.EVALUATION_DELETED,
                metadata={"evaluation_id": str(evaluation.id)},
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def _submit(
        self,
        *,
        evaluation: InterviewEvaluation,
        actor_id: uuid.UUID,
    ) -> InterviewEvaluationRead:
        self._authorize_author(actor_id, evaluation)
        self._ensure_draft(evaluation)

        submitted_at = _utc_now()
        try:
            transitioned = await self.evaluations.try_submit(
                evaluation.id,
                actor_id,
                submitted_at,
            )
            if not transitioned:
                await self.session.rollback()
                await self.session.refresh(evaluation)
                if evaluation.status == EVALUATION_STATUS_SUBMITTED:
                    raise ConflictException(
                        "This evaluation has already been submitted"
                    )
                raise ConflictException(
                    "The evaluation could not be submitted"
                )

            await record_activity(
                self.session,
                application_id=evaluation.application_id,
                actor_id=actor_id,
                action_type=hiring.EVALUATION_UPDATED,
                metadata={
                    "evaluation_id": str(evaluation.id),
                    "status": EVALUATION_STATUS_SUBMITTED,
                },
            )
            await self.session.commit()
        except ConflictException:
            raise
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(evaluation)
        return InterviewEvaluationRead.model_validate(evaluation)

    async def create_evaluation(
        self,
        current_user: User,
        application_id: uuid.UUID,
        interview_id: uuid.UUID,
        data: InterviewEvaluationCreate,
    ) -> InterviewEvaluationRead:
        interview = await self._load_interview(
            current_user, application_id, interview_id
        )
        return await self._create_draft(
            interview_id=interview.id,
            application_id=application_id,
            author_id=current_user.id,
            data=data,
        )

    async def list_by_interview(
        self,
        current_user: User,
        application_id: uuid.UUID,
        interview_id: uuid.UUID,
    ) -> list[InterviewEvaluationRead]:
        await self._load_interview(current_user, application_id, interview_id)
        rows = await self.evaluations.list_by_interview(interview_id)
        active_interview_ids = (
            await self._active_draft_interview_ids_for_legacy_list(
                rows, current_user.id
            )
        )
        visible = self._visible_evaluations(
            rows,
            current_user.id,
            blind=False,
            active_interview_ids=active_interview_ids,
        )
        return [InterviewEvaluationRead.model_validate(row) for row in visible]

    async def list_by_application(
        self,
        current_user: User,
        application_id: uuid.UUID,
    ) -> list[InterviewEvaluationRead]:
        await require_recruiter_application(
            self.session, current_user, application_id
        )
        rows = await self.evaluations.list_by_application(application_id)
        active_interview_ids = (
            await self._active_draft_interview_ids_for_legacy_list(
                rows, current_user.id
            )
        )
        visible = self._visible_evaluations(
            rows,
            current_user.id,
            blind=False,
            active_interview_ids=active_interview_ids,
        )
        return [InterviewEvaluationRead.model_validate(row) for row in visible]

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
        self._authorize_author(current_user.id, evaluation)
        self._ensure_draft(evaluation)
        if await self.assignments.has_inactive_without_active_for_interview_user(
            evaluation.interview_id, current_user.id
        ):
            raise ForbiddenException(
                "Only assigned evaluators can modify an evaluation"
            )
        return await self._update_draft(
            evaluation=evaluation,
            actor_id=current_user.id,
            data=data,
        )

    async def delete_evaluation(
        self,
        current_user: User,
        application_id: uuid.UUID,
        evaluation_id: uuid.UUID,
    ) -> None:
        evaluation = await self._load_evaluation(
            current_user, application_id, evaluation_id
        )
        self._authorize_author(current_user.id, evaluation)
        self._ensure_draft(evaluation)
        if await self.assignments.has_inactive_without_active_for_interview_user(
            evaluation.interview_id, current_user.id
        ):
            raise ForbiddenException(
                "Only assigned evaluators can delete an evaluation"
            )
        await self._delete_draft(
            evaluation=evaluation,
            actor_id=current_user.id,
        )

    async def submit_evaluation(
        self,
        current_user: User,
        application_id: uuid.UUID,
        evaluation_id: uuid.UUID,
    ) -> InterviewEvaluationRead:
        evaluation = await self._load_evaluation(
            current_user, application_id, evaluation_id
        )
        self._authorize_author(current_user.id, evaluation)
        self._ensure_draft(evaluation)
        if await self.assignments.has_inactive_without_active_for_interview_user(
            evaluation.interview_id, current_user.id
        ):
            raise ForbiddenException(
                "Only assigned evaluators can submit an evaluation"
            )
        return await self._submit(
            evaluation=evaluation,
            actor_id=current_user.id,
        )

    async def create_for_workspace(
        self,
        context: WorkspaceContext,
        interview_id: uuid.UUID,
        data: InterviewEvaluationCreate,
    ) -> InterviewEvaluationRead:
        interview = await self._load_workspace_interview(context, interview_id)
        await self._require_active_workspace_assignment(
            context,
            interview_id,
            "Only assigned evaluators can evaluate this interview",
        )
        return await self._create_draft(
            interview_id=interview.id,
            application_id=interview.application_id,
            author_id=context.user.id,
            data=data,
        )

    async def list_for_workspace(
        self,
        context: WorkspaceContext,
        interview_id: uuid.UUID,
    ) -> list[InterviewEvaluationRead]:
        await self._load_workspace_interview(context, interview_id)
        rows = await self.evaluations.list_by_interview(interview_id)
        blind = (
            not context.is_platform_admin
            and context.role == MembershipRole.INTERVIEWER
        )
        if context.is_platform_admin:
            active_interview_ids = {interview_id}
        else:
            assignment = await self.assignments.get_active_for_interview_user(
                interview_id, context.user.id
            )
            active_interview_ids = (
                {interview_id} if assignment is not None else set()
            )
        visible = self._visible_evaluations(
            rows,
            context.user.id,
            blind=blind,
            active_interview_ids=active_interview_ids,
        )
        return [InterviewEvaluationRead.model_validate(row) for row in visible]

    async def update_for_workspace(
        self,
        context: WorkspaceContext,
        interview_id: uuid.UUID,
        evaluation_id: uuid.UUID,
        data: InterviewEvaluationUpdate,
    ) -> InterviewEvaluationRead:
        evaluation = await self._load_workspace_evaluation(
            context, interview_id, evaluation_id
        )
        self._authorize_author(context.user.id, evaluation)
        self._ensure_draft(evaluation)
        await self._require_active_workspace_assignment(
            context,
            interview_id,
            "Only assigned evaluators can modify an evaluation",
        )
        return await self._update_draft(
            evaluation=evaluation,
            actor_id=context.user.id,
            data=data,
        )

    async def delete_for_workspace(
        self,
        context: WorkspaceContext,
        interview_id: uuid.UUID,
        evaluation_id: uuid.UUID,
    ) -> None:
        evaluation = await self._load_workspace_evaluation(
            context, interview_id, evaluation_id
        )
        self._authorize_author(context.user.id, evaluation)
        self._ensure_draft(evaluation)
        await self._require_active_workspace_assignment(
            context,
            interview_id,
            "Only assigned evaluators can delete an evaluation",
        )
        await self._delete_draft(
            evaluation=evaluation,
            actor_id=context.user.id,
        )

    async def submit_for_workspace(
        self,
        context: WorkspaceContext,
        interview_id: uuid.UUID,
        evaluation_id: uuid.UUID,
    ) -> InterviewEvaluationRead:
        evaluation = await self._load_workspace_evaluation(
            context, interview_id, evaluation_id
        )
        await self._require_active_workspace_assignment(
            context,
            interview_id,
            "Only assigned evaluators can submit an evaluation",
        )
        return await self._submit(
            evaluation=evaluation,
            actor_id=context.user.id,
        )
