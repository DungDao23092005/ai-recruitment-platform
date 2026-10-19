"""Shared application-scoped authorization helpers.

Every hiring-pipeline sub-resource (notes, evaluations, history, timeline) is
reachable only *through* an application, so each service must apply the exact
same ownership rules as the application endpoints. Centralising them here keeps
those rules consistent and avoids the "note-id-only" / "evaluation-id-only"
bypass that re-deriving ownership per endpoint tends to introduce.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException
from app.models import Application, User
from app.repositories import ApplicationRepository
from app.services.job_service import JobService
from app.services.user_service import UserService


async def require_recruiter_application(
    session: AsyncSession,
    current_user: User,
    application_id: uuid.UUID,
) -> Application:
    """Resolve an application for a recruiter/admin with ownership enforced.

    Admin may access any application; a recruiter only applications on their
    own company's jobs. Missing, soft-deleted or unowned applications all raise
    ``EntityNotFoundException`` (surfaced as non-enumerating 404) so existence
    is never leaked across tenants.
    """
    applications = ApplicationRepository(session, Application)
    application = await applications.get_by_id_with_candidate_job_company_and_recruiters(
        application_id
    )
    if application is None:
        raise EntityNotFoundException(f"Application {application_id} not found")

    try:
        await JobService(session).get_recruiter_job_by_id(
            current_user,
            application.job_id,
        )
    except EntityNotFoundException:
        raise EntityNotFoundException(
            f"Application {application_id} not found"
        ) from None
    return application


async def require_candidate_application(
    session: AsyncSession,
    current_user: User,
    application_id: uuid.UUID,
) -> Application:
    """Resolve an application owned by the candidate, else raise a 404.

    Ownership is resolved from the DB (current_user -> candidate_profile ->
    application.candidate_id). A user without a candidate profile, and any
    missing/foreign application, surface identically so existence is not
    leaked.
    """
    user = await UserService(session).get_user_with_profile(current_user.id)
    if user is None or user.candidate_profile is None:
        raise EntityNotFoundException(f"Application {application_id} not found")

    applications = ApplicationRepository(session, Application)
    application = await applications.get_by_id_with_job_company_and_recruiters(
        application_id
    )
    if application is None or application.candidate_id != user.candidate_profile.id:
        raise EntityNotFoundException(f"Application {application_id} not found")
    return application
