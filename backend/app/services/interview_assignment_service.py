from __future__ import annotations

import inspect
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
)
from app.domain.enums import InterviewStatus, MembershipRole
from app.models import (
    Application,
    CompanyMembership,
    Interview,
    InterviewAssignment,
    User,
)
from app.repositories import (
    ApplicationRepository,
    CompanyMembershipRepository,
    InterviewAssignmentRepository,
    InterviewRepository,
    UserRepository,
)
from app.schemas.interview_assignment import InterviewAssignmentRead
from app.services.notification_service import (
    INTERVIEW_ASSIGNED_TITLE,
    INTERVIEW_ASSIGNED_TYPE,
    INTERVIEW_UNASSIGNED_TITLE,
    INTERVIEW_UNASSIGNED_TYPE,
    NotificationService,
    interview_assignment_notification_id,
)
from app.services.pipeline_email_service import (
    schedule_interviewer_assignment_email,
)


async def _check_existing_notification(
    notification_service: NotificationService,
    notification_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Any:
    repo = getattr(notification_service, "notifications", None)
    if repo is not None and hasattr(repo, "get_by_id_and_user"):
        res = repo.get_by_id_and_user(
            notification_id=notification_id,
            user_id=user_id,
        )
        if inspect.isawaitable(res):
            return await res
    return None
from app.services.workspace_service import WorkspaceContext

_ASSIGNABLE_ROLES = frozenset(
    {
        MembershipRole.ADMIN,
        MembershipRole.RECRUITER,
        MembershipRole.INTERVIEWER,
    }
)
_ASSIGNABLE_INTERVIEW_STATUSES = frozenset(
    {
        InterviewStatus.SCHEDULED,
        InterviewStatus.CANDIDATE_CONFIRMED,
        InterviewStatus.COMPLETED,
    }
)


class InterviewAssignmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.assignments = InterviewAssignmentRepository(session)
        self.interviews = InterviewRepository(session, Interview)
        self.applications = ApplicationRepository(session, Application)
        self.memberships = CompanyMembershipRepository(
            session, CompanyMembership
        )
        self.users = UserRepository(session, User)

    async def assign(
        self,
        context: WorkspaceContext,
        interview_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> InterviewAssignmentRead:
        self._require_assignment_manager(context)
        interview, application = await self._load_interview(context, interview_id)
        if interview.status not in _ASSIGNABLE_INTERVIEW_STATUSES:
            raise ConflictException(
                "Interviews in this status cannot be assigned"
            )

        membership = await self.memberships.get_active(
            user_id, context.company_id
        )
        if membership is None or membership.role not in _ASSIGNABLE_ROLES:
            raise EntityNotFoundException("Workspace member not found")

        assignee = await self.users.get_by_id(user_id)
        if assignee is None or not assignee.is_active:
            raise EntityNotFoundException("Workspace member not found")

        existing = await self.assignments.get_active_for_interview_user(
            interview_id, user_id
        )
        if existing is not None:
            raise ConflictException(
                "This workspace member is already assigned to the interview"
            )

        assignment = InterviewAssignment(
            interview_id=interview_id,
            user_id=user_id,
            assigned_by_id=context.user.id,
        )
        self.session.add(assignment)
        try:
            await self.session.flush()

            # In-App notification for assigned interviewer
            notification_service = NotificationService(self.session)
            notif_id = interview_assignment_notification_id(
                "assigned",
                user_id,
                assignment.id,
            )
            existing_notif = await _check_existing_notification(
                notification_service,
                notif_id,
                user_id,
            )
            job_title = (
                application.job.title
                if application and application.job and application.job.title
                else "N/A"
            )
            if existing_notif is None:
                await notification_service.create_notification(
                    user_id=user_id,
                    title=INTERVIEW_ASSIGNED_TITLE,
                    content=f"Bạn đã được phân công tham gia phỏng vấn cho vị trí {job_title}.",
                    notification_type=INTERVIEW_ASSIGNED_TYPE,
                    entity_type="interview",
                    entity_id=interview.id,
                    notification_id=notif_id,
                )

            # Transactional Email Outbox for assigned interviewer
            if assignee.email:
                await schedule_interviewer_assignment_email(
                    self.session,
                    to_email=assignee.email,
                    job_title=job_title,
                    scheduled_at=interview.scheduled_at,
                    location=interview.location,
                    meeting_url=interview.meeting_url,
                    idempotency_key=f"interview-assignment:{assignment.id}",
                )

            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise ConflictException(
                "This workspace member is already assigned to the interview"
            ) from None
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(assignment)
        return InterviewAssignmentRead.model_validate(assignment)

    async def unassign(
        self,
        context: WorkspaceContext,
        interview_id: uuid.UUID,
        assignment_id: uuid.UUID,
    ) -> None:
        self._require_assignment_manager(context)
        interview, application = await self._load_interview(context, interview_id)
        assignment = await self.assignments.get_active_by_id_for_interview(
            assignment_id, interview_id
        )
        if assignment is None:
            raise EntityNotFoundException("Interview assignment not found")

        assignment.is_deleted = True
        try:
            await self.session.flush()

            # In-App notification only (no email) for unassigned interviewer
            notification_service = NotificationService(self.session)
            notif_id = interview_assignment_notification_id(
                "unassigned",
                assignment.user_id,
                assignment.id,
            )
            existing_notif = await _check_existing_notification(
                notification_service,
                notif_id,
                assignment.user_id,
            )
            job_title = (
                application.job.title
                if application and application.job and application.job.title
                else "N/A"
            )
            if existing_notif is None:
                await notification_service.create_notification(
                    user_id=assignment.user_id,
                    title=INTERVIEW_UNASSIGNED_TITLE,
                    content=f"Bạn đã được rút khỏi buổi phỏng vấn cho vị trí {job_title}.",
                    notification_type=INTERVIEW_UNASSIGNED_TYPE,
                    entity_type="interview",
                    entity_id=interview.id,
                    notification_id=notif_id,
                )

            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def list_for_interview(
        self,
        context: WorkspaceContext,
        interview_id: uuid.UUID,
    ) -> list[InterviewAssignmentRead]:
        self._require_assignment_manager(context)
        await self._load_interview(context, interview_id)
        assignments = await self.assignments.list_active_by_interview(
            interview_id
        )
        return [
            InterviewAssignmentRead.model_validate(assignment)
            for assignment in assignments
        ]

    async def _load_interview(
        self,
        context: WorkspaceContext,
        interview_id: uuid.UUID,
    ) -> tuple[Interview, Application]:
        interview = await self.interviews.get_by_id_with_application(
            interview_id
        )
        if interview is None:
            raise EntityNotFoundException(f"Interview {interview_id} not found")

        application = await self.applications.get_by_id_with_job_company_and_recruiters(
            interview.application_id
        )
        if (
            application is None
            or application.job is None
            or application.job.company is None
            or application.job.company_id != context.company_id
        ):
            raise EntityNotFoundException(f"Interview {interview_id} not found")
        return interview, application

    @staticmethod
    def _require_assignment_manager(context: WorkspaceContext) -> None:
        if context.is_platform_admin:
            return
        if context.role not in {
            MembershipRole.ADMIN,
            MembershipRole.RECRUITER,
        }:
            raise ForbiddenException(
                "Only workspace admins and recruiters can manage assignments"
            )
