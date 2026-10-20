from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.embedding_service import (
    EmbeddingService,
    SentenceTransformerEmbeddingProvider,
)
from app.ai.interfaces.base_provider import BaseVectorRepository
from app.ai.vector_db.qdrant_client import QdrantVectorRepository
from app.api.deps import get_db, require_candidate, require_recruiter
from app.core.exceptions import (
    AIError,
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
    InvalidTransitionException,
)
from app.models import Application, User
from app.schemas.ai_explanation import ApplicationMatchExplanationResponse
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.application import (
    ApplicationCreate,
    ApplicationDetailRead,
    ApplicationRead,
    ApplicationStatusUpdate,
    ApplicationWithJobRead,
    CandidateProfileReadMinimal,
)
from app.schemas.application_activity import (
    ApplicationActivityRead,
    CandidateApplicationActivityRead,
)
from app.schemas.application_note import (
    ApplicationNoteCreate,
    ApplicationNoteRead,
    ApplicationNoteUpdate,
)
from app.schemas.interview import (
    CandidateInterviewRead,
    InterviewActionRequest,
    InterviewCreate,
    InterviewRead,
    InterviewUpdate,
)
from app.schemas.interview_evaluation import (
    InterviewEvaluationCreate,
    InterviewEvaluationRead,
    InterviewEvaluationUpdate,
)
from app.schemas.resume import ResumeRead
from app.services.ai_matching_service import AIMatchingService
from app.services.application_activity_service import ApplicationActivityService
from app.services.application_note_service import ApplicationNoteService
from app.services.application_service import ApplicationService
from app.services.explainable_ai_service import ExplainableAIService
from app.services.interview_evaluation_service import InterviewEvaluationService
from app.services.interview_service import InterviewService
from app.services.job_service import JobService
from app.services.match_explanation_service import MatchExplanationService
from app.services.user_service import UserService

router = APIRouter()


def _get_ai_matching_service(
    vector_repository: BaseVectorRepository = Depends(
        lambda: QdrantVectorRepository()
    ),
) -> AIMatchingService:
    return AIMatchingService(
        vector_repository=vector_repository,
        embedding_service=EmbeddingService(
            SentenceTransformerEmbeddingProvider()
        ),
    )


def _get_match_explanation_service() -> MatchExplanationService:
    """Build the explanation service, reusing the existing AI explanation hook.

    The deterministic, evidence-verified part of the explanation never depends
    on the LLM; the narrative layer is best-effort and degrades gracefully.
    """
    return MatchExplanationService(narrative_service=ExplainableAIService())


def to_application_with_job_read(
    application: Application,
) -> ApplicationWithJobRead:
    return ApplicationWithJobRead(
        id=application.id,
        job_id=application.job_id,
        job_title=application.job.title,
        company_name=(
            application.job.company.name
            if application.job.company is not None
            else None
        ),
        status=application.status,
        created_at=application.created_at,
        updated_at=application.updated_at,
        interviews=[
            CandidateInterviewRead.model_validate(i)
            for i in application.interviews
            if not i.is_deleted
        ],
    )


@router.post(
    "",
    response_model=ApplicationRead,
    status_code=status.HTTP_201_CREATED,
)
async def apply_job(
    data: ApplicationCreate,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> ApplicationRead:
    user_with_profile = await UserService(db).users.get_with_profile(
        current_user.id
    )
    if (
        user_with_profile is None
        or user_with_profile.candidate_profile is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Candidate profile required",
        )

    candidate_id = user_with_profile.candidate_profile.id

    try:
        application = await ApplicationService(db).apply_job(
            candidate_id=candidate_id,
            job_id=data.job_id,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ConflictException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return ApplicationRead.model_validate(application)


@router.get(
    "/mine",
    response_model=list[ApplicationWithJobRead],
)
async def list_my_applications(
    job_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> list[ApplicationWithJobRead]:
    applications = await ApplicationService(db).list_my_applications(
        current_user=current_user,
        skip=skip,
        limit=limit,
        job_id=job_id,
    )
    return [
        to_application_with_job_read(application)
        for application in applications
    ]


@router.get(
    "",
    response_model=list[ApplicationRead],
)
async def list_applications(
    job_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> list[ApplicationRead]:
    if job_id is None:
        return []
    try:
        await JobService(db).get_recruiter_job_by_id(current_user, job_id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    applications = await ApplicationService(db).list_applications_by_job(
        job_id
    )
    return [
        ApplicationRead.model_validate(a)
        for a in applications[skip : skip + limit]
    ]


@router.get(
    "/{application_id}",
    response_model=ApplicationDetailRead,
)
async def get_application_detail(
    application_id: uuid.UUID,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetailRead:
    """Return a single application detail for a recruiter/admin.

    Includes the candidate's primary resume (``parsed_data``) so the
    recruiter can view the digital CV. Ownership is enforced server-side:
    admin may access any application; a recruiter only their own company's.
    """
    try:
        application, resume = await ApplicationService(
            db
        ).get_application_detail(
            current_user=current_user,
            application_id=application_id,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    company_name = (
        application.job.company.name
        if application.job is not None and application.job.company is not None
        else None
    )
    parsed_job = (
        ParsedJobSchema(
            title=application.job.title,
            summary=application.job.description,
            required_skills=[
                skill.name for skill in application.job.skills
            ],
        )
        if application.job is not None
        else None
    )
    interviews = [
        InterviewRead.model_validate(i)
        for i in application.interviews
        if not i.is_deleted
    ]
    return ApplicationDetailRead(
        id=application.id,
        candidate_id=application.candidate_id,
        job_id=application.job_id,
        job_title=application.job.title if application.job is not None else "",
        company_name=company_name,
        status=application.status,
        created_at=application.created_at,
        updated_at=application.updated_at,
        candidate=(
            CandidateProfileReadMinimal.model_validate(application.candidate)
            if application.candidate is not None
            else None
        ),
        resume=ResumeRead.model_validate(resume) if resume is not None else None,
        parsed_job=parsed_job,
        interviews=interviews,
    )


@router.get(
    "/{application_id}/match",
    response_model=MatchResultSchema,
)
async def get_application_match(
    application_id: uuid.UUID,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
    service: AIMatchingService = Depends(_get_ai_matching_service),
) -> MatchResultSchema:
    """Return the deterministic AI match score for an application.

    Recruiter/admin only. The candidate resume and job are resolved
    server-side from the application (client-supplied IDs are never trusted)
    and ownership is enforced exactly like the application detail endpoint.
    """
    try:
        return await ApplicationService(db).get_application_match(
            current_user=current_user,
            application_id=application_id,
            matching_service=service,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except AIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI Match unavailable. Please try again later.",
        ) from exc


@router.get(
    "/{application_id}/match-explanation",
    response_model=ApplicationMatchExplanationResponse,
)
async def get_application_match_explanation(
    application_id: uuid.UUID,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
    matching_service: AIMatchingService = Depends(_get_ai_matching_service),
    explanation_service: MatchExplanationService = Depends(
        _get_match_explanation_service
    ),
) -> ApplicationMatchExplanationResponse:
    """Return an evidence-grounded explanation of an application's match.

    Recruiter/admin only. The candidate resume and job are resolved
    server-side from the application (client-supplied data is never trusted)
    and ownership is enforced exactly like the match/detail endpoints. The
    overall score is copied from the existing matching engine, never
    recalculated. Missing/foreign applications surface as 404 without leaking
    existence.
    """
    try:
        return await ApplicationService(db).get_application_match_explanation(
            current_user=current_user,
            application_id=application_id,
            matching_service=matching_service,
            explanation_service=explanation_service,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except AIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI Match unavailable. Please try again later.",
        ) from exc


@router.patch(
    "/{id}/status",
    response_model=ApplicationRead,
)
async def update_application_status(
    id: uuid.UUID,
    data: ApplicationStatusUpdate,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> ApplicationRead:
    try:
        application = await ApplicationService(db).update_application_status(
            current_user=current_user,
            application_id=id,
            new_status=data.status,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InvalidTransitionException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ConflictException as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return ApplicationRead.model_validate(application)


@router.patch(
    "/mine/{application_id}/withdraw",
    response_model=ApplicationRead,
)
async def withdraw_application(
    application_id: uuid.UUID,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> ApplicationRead:
    try:
        application = await ApplicationService(db).withdraw_application(
            current_user=current_user,
            application_id=application_id,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InvalidTransitionException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ConflictException as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return ApplicationRead.model_validate(application)


@router.post(
    "/{application_id}/interviews",
    response_model=InterviewRead,
    status_code=status.HTTP_201_CREATED,
)
async def schedule_interview(
    application_id: uuid.UUID,
    data: InterviewCreate,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> InterviewRead:
    """Schedule a new interview for an application.

    Recruiter/admin only. Ownership enforced via job ownership.
    Transitions application to INTERVIEWING if not already.
    """
    try:
        return await InterviewService(db).schedule_interview(
            current_user=current_user,
            application_id=application_id,
            data=data,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InvalidTransitionException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/{application_id}/interviews",
    response_model=list[InterviewRead],
)
async def list_interviews(
    application_id: uuid.UUID,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> list[InterviewRead]:
    """List all interviews for an application.

    Recruiter/admin only. Ownership enforced.
    """
    try:
        return await InterviewService(db).list_interviews(
            current_user=current_user,
            application_id=application_id,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/interviews/{interview_id}",
    response_model=InterviewRead,
)
async def get_interview(
    interview_id: uuid.UUID,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> InterviewRead:
    """Get a single interview by ID.

    Recruiter/admin only. Ownership enforced.
    """
    try:
        return await InterviewService(db).get_interview(
            current_user=current_user,
            interview_id=interview_id,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.patch(
    "/interviews/{interview_id}",
    response_model=InterviewRead,
)
async def update_interview(
    interview_id: uuid.UUID,
    data: InterviewUpdate,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> InterviewRead:
    """Update an interview (reschedule, change type, etc.).

    Recruiter/admin only. Ownership enforced.
    """
    try:
        return await InterviewService(db).update_interview(
            current_user=current_user,
            interview_id=interview_id,
            data=data,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InvalidTransitionException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.delete(
    "/interviews/{interview_id}",
    response_model=InterviewRead,
)
async def cancel_interview(
    interview_id: uuid.UUID,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> InterviewRead:
    """Cancel an interview.

    Recruiter/admin only. Ownership enforced.
    Sets status to CANCELLED and soft-deletes.
    """
    try:
        return await InterviewService(db).cancel_interview(
            current_user=current_user,
            interview_id=interview_id,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{application_id}/interviews/{interview_id}/action",
    response_model=CandidateInterviewRead,
)
async def candidate_action_interview(
    application_id: uuid.UUID,
    interview_id: uuid.UUID,
    data: InterviewActionRequest,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> CandidateInterviewRead:
    """Candidate confirms or declines a scheduled interview.

    Candidate only. Ownership enforced via application -> candidate.
    Interview must be in SCHEDULED status.
    """
    try:
        return await InterviewService(db).candidate_action_interview(
            current_user=current_user,
            application_id=application_id,
            interview_id=interview_id,
            action=data.action,
            candidate_notes=data.candidate_notes,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InvalidTransitionException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# --------------------------------------------------------------------------
# Notes (recruiter-only internal notes on an application)
# --------------------------------------------------------------------------

_PAGE_MAX = 100
_SKIP_QUERY = Query(0, ge=0)
_LIMIT_QUERY = Query(50, ge=1, le=_PAGE_MAX)


@router.post(
    "/{application_id}/notes",
    response_model=ApplicationNoteRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_application_note(
    application_id: uuid.UUID,
    data: ApplicationNoteCreate,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> ApplicationNoteRead:
    """Create an internal note on an application. Recruiter/admin only."""
    try:
        return await ApplicationNoteService(db).create_note(
            current_user=current_user,
            application_id=application_id,
            data=data,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/{application_id}/notes",
    response_model=list[ApplicationNoteRead],
)
async def list_application_notes(
    application_id: uuid.UUID,
    skip: int = _SKIP_QUERY,
    limit: int = _LIMIT_QUERY,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> list[ApplicationNoteRead]:
    """List an application's internal notes. Recruiter/admin only."""
    try:
        return await ApplicationNoteService(db).list_notes(
            current_user=current_user,
            application_id=application_id,
            skip=skip,
            limit=limit,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{application_id}/notes/{note_id}",
    response_model=ApplicationNoteRead,
)
async def update_application_note(
    application_id: uuid.UUID,
    note_id: uuid.UUID,
    data: ApplicationNoteUpdate,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> ApplicationNoteRead:
    """Edit an internal note. Only the author or an admin may do this."""
    try:
        return await ApplicationNoteService(db).update_note(
            current_user=current_user,
            application_id=application_id,
            note_id=note_id,
            content=data.content,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ForbiddenException as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.delete(
    "/{application_id}/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_application_note(
    application_id: uuid.UUID,
    note_id: uuid.UUID,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete an internal note. Only the author or an admin may do this."""
    try:
        await ApplicationNoteService(db).delete_note(
            current_user=current_user,
            application_id=application_id,
            note_id=note_id,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ForbiddenException as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


# --------------------------------------------------------------------------
# Interview evaluations (private recruiter scorecards)
# --------------------------------------------------------------------------


def _evaluation_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EntityNotFoundException):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ConflictException):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, ForbiddenException):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error"
    )


@router.post(
    "/{application_id}/interviews/{interview_id}/evaluations",
    response_model=InterviewEvaluationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_interview_evaluation(
    application_id: uuid.UUID,
    interview_id: uuid.UUID,
    data: InterviewEvaluationCreate,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> InterviewEvaluationRead:
    """Submit the caller's scorecard for an interview. Recruiter/admin only."""
    try:
        return await InterviewEvaluationService(db).create_evaluation(
            current_user=current_user,
            application_id=application_id,
            interview_id=interview_id,
            data=data,
        )
    except (EntityNotFoundException, ConflictException, ForbiddenException) as exc:
        raise _evaluation_http_error(exc) from exc


@router.get(
    "/{application_id}/interviews/{interview_id}/evaluations",
    response_model=list[InterviewEvaluationRead],
)
async def list_interview_evaluations(
    application_id: uuid.UUID,
    interview_id: uuid.UUID,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> list[InterviewEvaluationRead]:
    """List an interview's evaluations. Recruiter/admin only."""
    try:
        return await InterviewEvaluationService(db).list_by_interview(
            current_user=current_user,
            application_id=application_id,
            interview_id=interview_id,
        )
    except (EntityNotFoundException, ConflictException, ForbiddenException) as exc:
        raise _evaluation_http_error(exc) from exc


@router.get(
    "/{application_id}/evaluations",
    response_model=list[InterviewEvaluationRead],
)
async def list_application_evaluations(
    application_id: uuid.UUID,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> list[InterviewEvaluationRead]:
    """List all evaluations for an application. Recruiter/admin only."""
    try:
        return await InterviewEvaluationService(db).list_by_application(
            current_user=current_user,
            application_id=application_id,
        )
    except (EntityNotFoundException, ConflictException, ForbiddenException) as exc:
        raise _evaluation_http_error(exc) from exc


@router.patch(
    "/{application_id}/evaluations/{evaluation_id}",
    response_model=InterviewEvaluationRead,
)
async def update_interview_evaluation(
    application_id: uuid.UUID,
    evaluation_id: uuid.UUID,
    data: InterviewEvaluationUpdate,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> InterviewEvaluationRead:
    """Update a scorecard. Only the evaluator or an admin may do this."""
    try:
        return await InterviewEvaluationService(db).update_evaluation(
            current_user=current_user,
            application_id=application_id,
            evaluation_id=evaluation_id,
            data=data,
        )
    except (EntityNotFoundException, ConflictException, ForbiddenException) as exc:
        raise _evaluation_http_error(exc) from exc


@router.delete(
    "/{application_id}/evaluations/{evaluation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_interview_evaluation(
    application_id: uuid.UUID,
    evaluation_id: uuid.UUID,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a scorecard. Only the evaluator or an admin may do this."""
    try:
        await InterviewEvaluationService(db).delete_evaluation(
            current_user=current_user,
            application_id=application_id,
            evaluation_id=evaluation_id,
        )
    except (EntityNotFoundException, ConflictException, ForbiddenException) as exc:
        raise _evaluation_http_error(exc) from exc


# --------------------------------------------------------------------------
# Activity history
# --------------------------------------------------------------------------


@router.get(
    "/{application_id}/activities",
    response_model=list[ApplicationActivityRead],
)
async def list_application_activities(
    application_id: uuid.UUID,
    skip: int = _SKIP_QUERY,
    limit: int = _LIMIT_QUERY,
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
) -> list[ApplicationActivityRead]:
    """List an application's full history (newest first). Recruiter/admin only."""
    try:
        return await ApplicationActivityService(db).list_activities(
            current_user=current_user,
            application_id=application_id,
            skip=skip,
            limit=limit,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/mine/{application_id}/timeline",
    response_model=list[CandidateApplicationActivityRead],
)
async def list_my_application_timeline(
    application_id: uuid.UUID,
    skip: int = _SKIP_QUERY,
    limit: int = _LIMIT_QUERY,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> list[CandidateApplicationActivityRead]:
    """List the candidate-visible timeline for one of the caller's applications.

    Only candidate-relevant events are returned (never internal notes, private
    evaluations, actor identities or free-form metadata).
    """
    try:
        return await ApplicationActivityService(db).list_candidate_timeline(
            current_user=current_user,
            application_id=application_id,
            skip=skip,
            limit=limit,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
