from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException
from app.domain.enums import MembershipRole
from app.models import Application, Interview, InterviewAssignment
from app.repositories import (
    ApplicationRepository,
    InterviewAssignmentRepository,
    InterviewRepository,
)
from app.services.workspace_service import WorkspaceContext


@dataclass(slots=True)
class InterviewAccess:
    interview: Interview
    application: Application


async def require_workspace_interview(
    session: AsyncSession,
    context: WorkspaceContext,
    interview_id: uuid.UUID,
) -> InterviewAccess:
    """Resolve an interview only when the caller's workspace permits access.

    Company admins/recruiters may access any interview in their company. An
    interviewer may access only interviews explicitly assigned to them. Missing,
    foreign-company and unassigned interviews all surface as non-enumerating
    404s.
    """
    interviews = InterviewRepository(session, Interview)
    applications = ApplicationRepository(session, Application)

    interview = await interviews.get_by_id_with_application(interview_id)
    if interview is None:
        raise EntityNotFoundException(f"Interview {interview_id} not found")

    application = await applications.get_by_id_with_candidate_job_company_and_recruiters(
        interview.application_id
    )
    if (
        application is None
        or application.job is None
        or application.job.company is None
        or application.job.company_id != context.company_id
    ):
        raise EntityNotFoundException(f"Interview {interview_id} not found")

    if context.is_platform_admin or context.role in {
        MembershipRole.ADMIN,
        MembershipRole.RECRUITER,
    }:
        return InterviewAccess(interview=interview, application=application)

    if context.role == MembershipRole.INTERVIEWER:
        assignments = InterviewAssignmentRepository(session)
        assignment = await assignments.get_active_for_interview_user(
            interview_id, context.user.id
        )
        if assignment is not None:
            return InterviewAccess(
                interview=interview, application=application
            )

    raise EntityNotFoundException(f"Interview {interview_id} not found")
