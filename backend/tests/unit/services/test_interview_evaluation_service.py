from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import (
    ConflictException,
    ForbiddenException,
)
from app.domain.enums import MembershipRole, MembershipStatus, UserRole
from app.models import (
    Application,
    Interview,
    InterviewAssignment,
    InterviewEvaluation,
    User,
)
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
    InterviewEvaluationUpdate,
)
from app.services.interview_evaluation_service import InterviewEvaluationService
from app.services.workspace_service import WorkspaceContext


def _make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    async def _mock_refresh(obj):
        now = datetime.now(timezone.utc)
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = now
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = now

    session.refresh = AsyncMock(side_effect=_mock_refresh)
    session.rollback = AsyncMock()
    return session


def _make_user(
    role: UserRole = UserRole.RECRUITER,
    user_id: uuid.UUID | None = None,
) -> User:
    return User(
        id=user_id or uuid.uuid4(),
        email="evaluator@example.com",
        role=role,
        is_active=True,
    )


def _make_interview(
    interview_id: uuid.UUID | None = None,
    application_id: uuid.UUID | None = None,
) -> Interview:
    return Interview(
        id=interview_id or uuid.uuid4(),
        application_id=application_id or uuid.uuid4(),
        interview_type="technical",
        scheduled_at=datetime.now(timezone.utc),
        duration_minutes=45,
        status="scheduled",
    )


def _make_service(session: MagicMock) -> InterviewEvaluationService:
    service = InterviewEvaluationService(session)
    service.interviews = AsyncMock(spec=InterviewRepository)
    service.evaluations = AsyncMock(spec=InterviewEvaluationRepository)
    service.assignments = AsyncMock(spec=InterviewAssignmentRepository)
    return service


class TestInterviewEvaluationServicePermissions:
    def test_unassigned_recruiter_cannot_create_evaluation(self):
        session = _make_session()
        service = _make_service(session)

        user = _make_user(UserRole.RECRUITER)
        interview = _make_interview()
        app_id = interview.application_id

        service.interviews.get_by_id_with_application.return_value = interview
        service.assignments.get_active_for_interview_user.return_value = None

        with patch(
            "app.services.interview_evaluation_service.require_recruiter_application",
            new_callable=AsyncMock,
        ):
            with pytest.raises(ForbiddenException) as exc_info:
                asyncio.run(
                    service.create_evaluation(
                        current_user=user,
                        application_id=app_id,
                        interview_id=interview.id,
                        data=InterviewEvaluationCreate(rating=4),
                    )
                )

        assert "Only assigned evaluators can evaluate this interview" in str(
            exc_info.value
        )

    def test_assigned_recruiter_can_create_evaluation(self):
        session = _make_session()
        service = _make_service(session)

        user = _make_user(UserRole.RECRUITER)
        interview = _make_interview()
        app_id = interview.application_id

        service.interviews.get_by_id_with_application.return_value = interview
        assignment = InterviewAssignment(
            id=uuid.uuid4(),
            interview_id=interview.id,
            user_id=user.id,
            assigned_by_id=uuid.uuid4(),
        )
        service.assignments.get_active_for_interview_user.return_value = (
            assignment
        )
        service.evaluations.get_by_interview_and_evaluator.return_value = None

        with patch(
            "app.services.interview_evaluation_service.require_recruiter_application",
            new_callable=AsyncMock,
        ), patch(
            "app.services.interview_evaluation_service.record_activity",
            new_callable=AsyncMock,
        ):
            result = asyncio.run(
                service.create_evaluation(
                    current_user=user,
                    application_id=app_id,
                    interview_id=interview.id,
                    data=InterviewEvaluationCreate(rating=5),
                )
            )

        assert result.rating == 5
        assert result.evaluator_id == user.id
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    def test_platform_admin_can_create_evaluation_without_assignment(self):
        session = _make_session()
        service = _make_service(session)

        admin = _make_user(UserRole.ADMIN)
        interview = _make_interview()
        app_id = interview.application_id

        service.interviews.get_by_id_with_application.return_value = interview
        service.evaluations.get_by_interview_and_evaluator.return_value = None

        with patch(
            "app.services.interview_evaluation_service.require_recruiter_application",
            new_callable=AsyncMock,
        ), patch(
            "app.services.interview_evaluation_service.record_activity",
            new_callable=AsyncMock,
        ):
            result = asyncio.run(
                service.create_evaluation(
                    current_user=admin,
                    application_id=app_id,
                    interview_id=interview.id,
                    data=InterviewEvaluationCreate(rating=4),
                )
            )

        assert result.rating == 4
        assert result.evaluator_id == admin.id
        service.assignments.get_active_for_interview_user.assert_not_called()

    def test_unassigned_recruiter_cannot_update_draft(self):
        session = _make_session()
        service = _make_service(session)

        user = _make_user(UserRole.RECRUITER)
        interview = _make_interview()
        evaluation = InterviewEvaluation(
            id=uuid.uuid4(),
            interview_id=interview.id,
            application_id=interview.application_id,
            evaluator_id=user.id,
            rating=3,
            status=EVALUATION_STATUS_DRAFT,
        )

        service.evaluations.get_by_id_and_application.return_value = evaluation
        service.assignments.get_active_for_interview_user.return_value = None

        with patch(
            "app.services.interview_evaluation_service.require_recruiter_application",
            new_callable=AsyncMock,
        ):
            with pytest.raises(ForbiddenException) as exc_info:
                asyncio.run(
                    service.update_evaluation(
                        current_user=user,
                        application_id=interview.application_id,
                        evaluation_id=evaluation.id,
                        data=InterviewEvaluationUpdate(rating=5),
                    )
                )

        assert "Only assigned evaluators can modify an evaluation" in str(
            exc_info.value
        )

    def test_unassigned_recruiter_cannot_delete_draft(self):
        session = _make_session()
        service = _make_service(session)

        user = _make_user(UserRole.RECRUITER)
        interview = _make_interview()
        evaluation = InterviewEvaluation(
            id=uuid.uuid4(),
            interview_id=interview.id,
            application_id=interview.application_id,
            evaluator_id=user.id,
            rating=3,
            status=EVALUATION_STATUS_DRAFT,
        )

        service.evaluations.get_by_id_and_application.return_value = evaluation
        service.assignments.get_active_for_interview_user.return_value = None

        with patch(
            "app.services.interview_evaluation_service.require_recruiter_application",
            new_callable=AsyncMock,
        ):
            with pytest.raises(ForbiddenException) as exc_info:
                asyncio.run(
                    service.delete_evaluation(
                        current_user=user,
                        application_id=interview.application_id,
                        evaluation_id=evaluation.id,
                    )
                )

        assert "Only assigned evaluators can delete an evaluation" in str(
            exc_info.value
        )

    def test_unassigned_recruiter_cannot_submit_draft(self):
        session = _make_session()
        service = _make_service(session)

        user = _make_user(UserRole.RECRUITER)
        interview = _make_interview()
        evaluation = InterviewEvaluation(
            id=uuid.uuid4(),
            interview_id=interview.id,
            application_id=interview.application_id,
            evaluator_id=user.id,
            rating=3,
            status=EVALUATION_STATUS_DRAFT,
        )

        service.evaluations.get_by_id_and_application.return_value = evaluation
        service.assignments.get_active_for_interview_user.return_value = None

        with patch(
            "app.services.interview_evaluation_service.require_recruiter_application",
            new_callable=AsyncMock,
        ):
            with pytest.raises(ForbiddenException) as exc_info:
                asyncio.run(
                    service.submit_evaluation(
                        current_user=user,
                        application_id=interview.application_id,
                        evaluation_id=evaluation.id,
                    )
                )

        assert "Only assigned evaluators can submit an evaluation" in str(
            exc_info.value
        )

    def test_revoked_assignment_prevents_submitting_draft(self):
        session = _make_session()
        service = _make_service(session)

        user = _make_user(UserRole.RECRUITER)
        interview = _make_interview()
        evaluation = InterviewEvaluation(
            id=uuid.uuid4(),
            interview_id=interview.id,
            application_id=interview.application_id,
            evaluator_id=user.id,
            rating=4,
            status=EVALUATION_STATUS_DRAFT,
        )

        service.evaluations.get_by_id_and_application.return_value = evaluation
        # Assignment revoked (returns None from get_active_for_interview_user)
        service.assignments.get_active_for_interview_user.return_value = None

        with patch(
            "app.services.interview_evaluation_service.require_recruiter_application",
            new_callable=AsyncMock,
        ):
            with pytest.raises(ForbiddenException) as exc_info:
                asyncio.run(
                    service.submit_evaluation(
                        current_user=user,
                        application_id=interview.application_id,
                        evaluation_id=evaluation.id,
                    )
                )

        assert "Only assigned evaluators can submit an evaluation" in str(
            exc_info.value
        )

    def test_submitted_evaluation_is_immutable(self):
        session = _make_session()
        service = _make_service(session)

        user = _make_user(UserRole.RECRUITER)
        interview = _make_interview()
        evaluation = InterviewEvaluation(
            id=uuid.uuid4(),
            interview_id=interview.id,
            application_id=interview.application_id,
            evaluator_id=user.id,
            rating=4,
            status=EVALUATION_STATUS_SUBMITTED,
            submitted_at=datetime.now(timezone.utc),
        )

        service.evaluations.get_by_id_and_application.return_value = evaluation
        service.assignments.get_active_for_interview_user.return_value = (
            InterviewAssignment(
                id=uuid.uuid4(),
                interview_id=interview.id,
                user_id=user.id,
                assigned_by_id=uuid.uuid4(),
            )
        )

        with patch(
            "app.services.interview_evaluation_service.require_recruiter_application",
            new_callable=AsyncMock,
        ):
            with pytest.raises(ConflictException) as exc_info:
                asyncio.run(
                    service.update_evaluation(
                        current_user=user,
                        application_id=interview.application_id,
                        evaluation_id=evaluation.id,
                        data=InterviewEvaluationUpdate(rating=5),
                    )
                )

        assert "Submitted evaluations are immutable" in str(exc_info.value)

    def test_company_admin_workspace_requires_active_assignment(self):
        session = _make_session()
        service = _make_service(session)

        user = _make_user(UserRole.RECRUITER)
        interview = _make_interview()
        membership = MagicMock()
        membership.role = MembershipRole.ADMIN
        membership.status = MembershipStatus.ACTIVE

        context = WorkspaceContext(
            user=user,
            company=MagicMock(id=uuid.uuid4(), name="Co", slug="co"),
            membership=membership,
            is_platform_admin=False,
        )

        service.interviews.get_by_id_with_application.return_value = interview
        service.assignments.get_active_for_interview_user.return_value = None

        with patch(
            "app.services.interview_evaluation_service.require_workspace_interview",
            new_callable=AsyncMock,
        ) as mock_req:
            mock_req.return_value = MagicMock(interview=interview)
            with pytest.raises(ForbiddenException) as exc_info:
                asyncio.run(
                    service.create_for_workspace(
                        context=context,
                        interview_id=interview.id,
                        data=InterviewEvaluationCreate(rating=4),
                    )
                )

        assert "Only assigned evaluators can evaluate this interview" in str(
            exc_info.value
        )
