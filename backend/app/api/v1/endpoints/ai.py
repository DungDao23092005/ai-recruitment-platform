from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.embedding_service import (
    EmbeddingService,
    SentenceTransformerEmbeddingProvider,
)
from app.ai.interfaces.base_provider import BaseVectorRepository
from app.ai.vector_db.qdrant_client import QdrantVectorRepository
from app.api.deps import (
    ensure_not_interviewer,
    get_current_active_user,
    get_db,
    get_optional_workspace,
    require_admin,
    require_candidate,
    require_recruiter,
)
from app.core.exceptions import (
    AIError,
    AIProviderQuotaExceededError,
    AIProviderUnavailableError,
    CandidateQuotaExhaustedException,
    ConflictException,
    EmptyDocumentError,
    EntityNotFoundException,
    ForbiddenException,
    InvalidDocumentError,
    PDFWorkerUnavailableError,
)
from app.core.rate_limit import (
    RateLimitResult,
    ai_chat_rate_limit,
    match_rate_limit,
    parse_jd_rate_limit,
    parse_resume_rate_limit,
    recommendations_rate_limit,
)
from app.core.request_limits import release_upload_permit
from app.domain.enums import (
    MembershipRole,
    MembershipStatus,
    SubscriptionUsageFeatureType,
    UserRole,
)
from app.models import CompanyMembership, User
from app.schemas.ai_chat import ChatRequest, ChatResponse
from app.schemas.ai_explanation import ExplainMatchRequest
from app.schemas.ai_interview import (
    GenerateInterviewQuestionsRequest,
    GenerateInterviewQuestionsResponse,
)
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_matching import (
    CandidateMatchRecommendation,
    JobMatchRecommendation,
)
from app.schemas.ai_resume import ParsedResumeSchema
from app.schemas.ai_search import SemanticSearchResult
from app.schemas.resume import ResumeRead
from app.services.ai_evaluation_service import (
    AIEvaluationService,
    EvaluationSample,
    RelevanceLabel,
)
from app.services.ai_matching_service import AIMatchingService
from app.services.explainable_ai_service import ExplainableAIService
from app.services.interview_generator_service import InterviewGeneratorService
from app.services.job_service import JobService
from app.services.notification_service import NotificationService
from app.services.quota_enforcement_service import (
    QuotaEnforcementService,
    ReservationResult,
)
from app.services.rag_chat_service import RAGChatService
from app.services.semantic_search_service import SemanticSearchService
from app.services.workspace_service import WorkspaceContext

logger = logging.getLogger(__name__)

router = APIRouter()

# Constants for file upload hardening
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_FILENAME_LENGTH = 255
ALLOWED_EXTENSIONS = {".pdf"}
PDF_MAGIC_HEADER = b"%PDF"
MAX_EXTRACTED_TEXT_CHARS = 30000
MAX_PDF_PAGES = 15


def _get_ai_service(
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


def _get_explainable_ai_service() -> ExplainableAIService:
    return ExplainableAIService()


def _get_semantic_search_service() -> SemanticSearchService:
    return SemanticSearchService()


def _get_rag_chat_service() -> RAGChatService:
    return RAGChatService()


def _get_interview_generator_service() -> InterviewGeneratorService:
    return InterviewGeneratorService()


async def resolve_recruiter_ai_quota_company(
    db: AsyncSession,
    current_user: User,
    workspace: WorkspaceContext | None,
    referenced_company_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    """Resolve the verified company quota scope for metered Recruiter AI calls.

    Returns ``workspace.company_id`` when a verified Workspace context exists,
    or ``None`` when the caller is a legacy Recruiter operating on a genuinely
    legacy (non-Workspace) company. Raises ``ForbiddenException`` whenever
    authorization fails so no request can silently fall back to personal quota.
    """
    if current_user.role != UserRole.RECRUITER:
        raise ForbiddenException("Not enough permissions")

    job_service = JobService(db)

    if workspace is not None:
        if getattr(workspace, "is_platform_admin", False):
            raise ForbiddenException("Not enough permissions")
        role = getattr(workspace, "role", None)
        if role == MembershipRole.INTERVIEWER:
            raise ForbiddenException("Not enough permissions")
        if isinstance(db, AsyncSession) and role not in {
            MembershipRole.ADMIN,
            MembershipRole.RECRUITER,
        }:
            raise ForbiddenException("Not enough permissions")
        if (
            referenced_company_id is not None
            and referenced_company_id != workspace.company_id
        ):
            raise ForbiddenException(
                "Resource does not belong to the active company workspace."
            )
        return workspace.company_id

    if isinstance(db, AsyncSession):
        revoked_count = await db.scalar(
            select(func.count())
            .select_from(CompanyMembership)
            .where(
                CompanyMembership.user_id == current_user.id,
                CompanyMembership.is_deleted == False,  # noqa: E712
                CompanyMembership.status != MembershipStatus.ACTIVE,
            )
        )
        if int(revoked_count or 0) > 0:
            raise ForbiddenException(
                "Workspace membership is not active."
            )

    profile = await job_service._resolve_recruiter_profile(current_user)
    if profile is None or getattr(profile, "company_id", None) is None:
        raise ForbiddenException("Recruiter company profile is required.")

    target_company_id = profile.company_id
    if (
        referenced_company_id is not None
        and referenced_company_id != target_company_id
    ):
        raise ForbiddenException(
            "Resource does not belong to the recruiter's company."
        )

    if await job_service._company_has_active_workspace(target_company_id):
        raise ForbiddenException(
            "This company is managed via a Company Workspace. Please provide a valid X-Company-ID header."
        )

    return None


async def _release_ai_reservation_safe(
    db: AsyncSession,
    quota_service: QuotaEnforcementService,
    reservation: ReservationResult | None,
) -> None:
    """Roll back uncommitted work and release a quota reservation safely.

    Creates a dedicated cleanup task and awaits it via ``asyncio.shield`` in a
    loop so repeated task cancellations cannot abandon the release sequence.
    Logs cleanup failures without masking the caller's original exception or
    ``CancelledError``.
    """
    usage_id = (
        getattr(reservation, "usage_id", None)
        if reservation is not None
        else None
    )

    async def _do_cleanup() -> None:
        try:
            await db.rollback()
        except Exception as rollback_exc:  # noqa: BLE001
            logger.error(
                "ai_quota_release_rollback_failed usage_id=%s error=%s",
                usage_id,
                type(rollback_exc).__name__,
            )
        if usage_id is None:
            return
        await quota_service.release_reservation(usage_id)
        await db.commit()

    cleanup_task = asyncio.create_task(_do_cleanup())
    while not cleanup_task.done():
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            continue
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "ai_quota_release_cleanup_failed usage_id=%s error=%s",
                usage_id,
                type(exc).__name__,
            )
            return


async def _notify_candidate_quota_exhausted(
    db: AsyncSession,
    user: User,
    exc: CandidateQuotaExhaustedException,
) -> None:
    """Best-effort period/tier-scoped notification for an exhausted quota.

    Notification persistence must never turn a quota rejection into a server
    error, so failures are rolled back and logged. The quota decision itself is
    already final when this helper runs.
    """
    try:
        notifications = NotificationService(db)
        if exc.is_free:
            if exc.period_key is None:
                return
            await notifications.notify_candidate_free_quota_exhausted(
                user_id=user.id,
                subscription_id=exc.subscription_id,
                period_key=exc.period_key,
            )
        else:
            await notifications.notify_candidate_paid_quota_exhausted(
                user_id=user.id,
                subscription_id=exc.subscription_id,
                plan_name=exc.plan_name,
            )
        await db.commit()
    except Exception as notify_exc:  # noqa: BLE001
        try:
            await db.rollback()
        except Exception:
            pass
        logger.warning(
            "candidate_quota_notification_failed user_id=%s error=%s",
            user.id,
            type(notify_exc).__name__,
        )


async def _reserve_candidate_ai_quota(
    db: AsyncSession,
    user: User,
    feature_type: SubscriptionUsageFeatureType,
    idempotency_key: str | None,
    reference_id: uuid.UUID | None = None,
) -> tuple[QuotaEnforcementService, ReservationResult]:
    quota_service = QuotaEnforcementService(db)
    try:
        reservation = await quota_service.reserve_candidate_ai_quota(
            candidate_id=user.id,
            feature_type=feature_type,
            amount=1,
            idempotency_key=idempotency_key,
            reference_id=reference_id,
        )
        await db.commit()
    except CandidateQuotaExhaustedException as exc:
        await _notify_candidate_quota_exhausted(db, user, exc)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    return quota_service, reservation


@router.post(
    "/parse-resume",
    response_model=ResumeRead,
    status_code=status.HTTP_200_OK,
)
async def parse_resume(
    file: UploadFile,
    request: Request,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    service: AIMatchingService = Depends(_get_ai_service),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    _: RateLimitResult = Depends(parse_resume_rate_limit),
) -> ResumeRead:
    # Filename validation
    filename = file.filename or ""
    if len(filename) > MAX_FILENAME_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Filename exceeds maximum length of {MAX_FILENAME_LENGTH} characters",
        )

    # Extension validation (case-insensitive)
    if not any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .pdf files are allowed",
        )

    # Pre-read size validation to prevent memory DoS
    # Check file size using the underlying file object BEFORE reading into memory
    try:
        file.file.seek(0, 2)  # Seek to end
        actual_size = file.file.tell()
        file.file.seek(0)  # Reset to beginning
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to determine file size",
        ) from exc

    if actual_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum limit of {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB",
        )

    # Read file and validate magic header
    pdf_bytes = await file.read()

    # Validate PDF magic header
    if len(pdf_bytes) < len(PDF_MAGIC_HEADER) or not pdf_bytes.startswith(PDF_MAGIC_HEADER):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid PDF header: missing '%PDF' magic header",
        )

    # Starlette has finished parsing and spooling the multipart body by now.
    # Hand the upload slot back before any database or AI work so a slow LLM
    # cannot starve the bounded upload pool.
    release_upload_permit(request)

    candidate_profile = await current_user.awaitable_attrs.candidate_profile
    if candidate_profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Candidate profile required",
        )

    quota_service, reservation = await _reserve_candidate_ai_quota(
        db,
        current_user,
        SubscriptionUsageFeatureType.CANDIDATE_PARSE_RESUME,
        idempotency_key,
    )
    try:
        try:
            draft = await service.parse_and_save_resume_draft(
                candidate_id=candidate_profile.id,
                pdf_source=pdf_bytes,
                session=db,
                source_name=file.filename,
            )
        except (Exception, asyncio.CancelledError):
            await _release_ai_reservation_safe(
                db, quota_service, reservation
            )
            raise

        try:
            await quota_service.finalize_reservation(reservation.usage_id)
            await db.commit()
        except (Exception, asyncio.CancelledError):
            await _release_ai_reservation_safe(
                db, quota_service, reservation
            )
            raise
        return ResumeRead.model_validate(draft)
    except EmptyDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except InvalidDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except PDFWorkerUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after or 10)},
        ) from exc
    except AIProviderUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after) if exc.retry_after else "60"},
        ) from exc
    except AIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


class ParseJDRequest(BaseModel):
    job_title: str
    job_description: str = Field(..., max_length=MAX_EXTRACTED_TEXT_CHARS)
    job_id: uuid.UUID | None = None


class MatchRequest(BaseModel):
    parsed_resume: ParsedResumeSchema
    parsed_job: ParsedJobSchema
    resume_vector: list[float] | None = None
    job_vector: list[float] | None = None


@router.post(
    "/parse-jd",
    response_model=ParsedJobSchema,
    status_code=status.HTTP_200_OK,
)
async def parse_jd(
    data: ParseJDRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: User = Depends(require_recruiter),
    workspace: WorkspaceContext | None = Depends(get_optional_workspace),
    db: AsyncSession = Depends(get_db),
    service: AIMatchingService = Depends(_get_ai_service),
    _: RateLimitResult = Depends(parse_jd_rate_limit),
) -> ParsedJobSchema:
    ensure_not_interviewer(workspace)
    quota_service = QuotaEnforcementService(db)
    reservation: ReservationResult | None = None
    is_admin = current_user.role == UserRole.ADMIN

    try:
        referenced_company_id: uuid.UUID | None = None
        if data.job_id is not None and isinstance(db, AsyncSession):
            existing_job = await JobService(db).jobs.get_by_id(data.job_id)
            if existing_job is not None:
                referenced_company_id = existing_job.company_id

        if is_admin:
            quota_company_id = (
                workspace.company_id if workspace is not None else None
            )
        else:
            quota_company_id = await resolve_recruiter_ai_quota_company(
                db,
                current_user,
                workspace,
                referenced_company_id=referenced_company_id,
            )

        reservation = await quota_service.reserve_ai_quota(
            user_id=current_user.id,
            idempotency_key=idempotency_key,
            reference_id=data.job_id,
            company_id=quota_company_id,
            is_admin=is_admin,
        )
        # Persist the reservation and release DB locks before the external call.
        await db.commit()

        result = await service.process_and_index_job(
            job_id=data.job_id or uuid.uuid4(),
            job_title=data.job_title,
            job_description=data.job_description,
        )

        await quota_service.finalize_reservation(
            reservation.usage_id, success=True
        )
        await db.commit()
        reservation = None
        return result

    except asyncio.CancelledError:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise
    except ConflictException as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except EmptyDocumentError as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except InvalidDocumentError as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except AIProviderQuotaExceededError as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after) if exc.retry_after else "60"},
        ) from exc
    except AIProviderUnavailableError as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after) if exc.retry_after else "60"},
        ) from exc
    except ForbiddenException as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except AIError as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except HTTPException:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise
    except Exception:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise


@router.post(
    "/match",
    response_model=MatchResultSchema,
    status_code=status.HTTP_200_OK,
)
async def match_candidate_and_job(
    data: MatchRequest,
    current_user: User = Depends(get_current_active_user),
    service: AIMatchingService = Depends(_get_ai_service),
    _: RateLimitResult = Depends(match_rate_limit),
) -> MatchResultSchema:
    return await service.match_candidate_with_job(
        parsed_resume=data.parsed_resume,
        parsed_job=data.parsed_job,
        resume_vector=data.resume_vector,
        job_vector=data.job_vector,
    )


@router.post(
    "/explain-match",
    status_code=status.HTTP_410_GONE,
    response_model=None,
    deprecated=True,
    summary="Retired: explain a match (fail-closed)",
    responses={
        status.HTTP_410_GONE: {
            "description": (
                "The endpoint is permanently retired. It fails closed for "
                "every authenticated caller and never calls an AI provider, "
                "the quota system, or vector search."
            ),
            "content": {
                "application/json": {
                    "example": {
                        "detail": (
                            "POST /api/v1/ai/explain-match has been retired "
                            "for security reasons. Use "
                            "GET /api/v1/applications/{application_id}/"
                            "match-explanation."
                        )
                    }
                }
            },
        }
    },
)
async def explain_match(
    data: ExplainMatchRequest,
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Deprecated: retired for security reasons (fail-closed).

    The original implementation explained a caller-supplied
    ``match_result`` / ``candidate`` / ``job`` payload. None of that data is
    tied to a trusted server-side resource, so the endpoint could not verify
    ownership and would happily run the LLM on arbitrary, attacker-controlled
    content (prompt injection, quota abuse, cross-tenant data shaped by the
    caller).

    It is replaced by the application-scoped, ownership-enforced
    ``GET /api/v1/applications/{application_id}/match-explanation``. This
    route now fails closed for every authenticated caller and never contacts
    an AI provider.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "POST /api/v1/ai/explain-match has been retired for security "
            "reasons. Use "
            "GET /api/v1/applications/{application_id}/match-explanation."
        ),
    )


@router.post(
    "/generate-interview-questions",
    response_model=GenerateInterviewQuestionsResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_interview_questions(
    data: GenerateInterviewQuestionsRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: User = Depends(require_recruiter),
    workspace: WorkspaceContext | None = Depends(get_optional_workspace),
    db: AsyncSession = Depends(get_db),
    service: InterviewGeneratorService = Depends(
        _get_interview_generator_service
    ),
) -> GenerateInterviewQuestionsResponse:
    ensure_not_interviewer(workspace)
    quota_service = QuotaEnforcementService(db)
    reservation: ReservationResult | None = None
    is_admin = current_user.role == UserRole.ADMIN
    try:
        if is_admin:
            quota_company_id = (
                workspace.company_id if workspace is not None else None
            )
        else:
            quota_company_id = await resolve_recruiter_ai_quota_company(
                db, current_user, workspace
            )

        reservation = await quota_service.reserve_ai_quota(
            user_id=current_user.id,
            idempotency_key=idempotency_key,
            company_id=quota_company_id,
            is_admin=is_admin,
        )
        await db.commit()

        result = await service.generate_questions(data)

        await quota_service.finalize_reservation(
            reservation.usage_id, success=True
        )
        await db.commit()
        reservation = None
        return result

    except asyncio.CancelledError:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise
    except ConflictException as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except EmptyDocumentError as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except InvalidDocumentError as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except AIProviderQuotaExceededError as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after) if exc.retry_after else "60"},
        ) from exc
    except AIProviderUnavailableError as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after) if exc.retry_after else "60"},
        ) from exc
    except ForbiddenException as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except AIError as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except HTTPException:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise
    except Exception as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI service internal error",
        ) from exc


@router.get(
    "/recommendations/jobs",
    response_model=list[JobMatchRecommendation],
    status_code=status.HTTP_200_OK,
)
async def recommend_jobs_for_candidate(
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    service: AIMatchingService = Depends(_get_ai_service),
    limit: int = Query(default=10, ge=1, le=100),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    _: RateLimitResult = Depends(recommendations_rate_limit),
) -> list[JobMatchRecommendation]:
    candidate_profile = await current_user.awaitable_attrs.candidate_profile
    if candidate_profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Candidate profile required",
        )

    quota_service, reservation = await _reserve_candidate_ai_quota(
        db,
        current_user,
        SubscriptionUsageFeatureType.CANDIDATE_JOB_RECOMMENDATIONS,
        idempotency_key,
    )
    try:
        try:
            recommendations = await service.recommend_jobs_for_candidate(
                candidate_id=candidate_profile.id,
                limit=limit,
                session=db,
                actor_user=current_user,
            )
        except (Exception, asyncio.CancelledError):
            await _release_ai_reservation_safe(
                db, quota_service, reservation
            )
            raise

        try:
            await quota_service.finalize_reservation(reservation.usage_id)
            await db.commit()
        except (Exception, asyncio.CancelledError):
            await _release_ai_reservation_safe(
                db, quota_service, reservation
            )
            raise
        return recommendations
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
)
async def ai_chat(
    data: ChatRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    service: RAGChatService = Depends(_get_rag_chat_service),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    _: RateLimitResult = Depends(ai_chat_rate_limit),
) -> ChatResponse:
    quota_service: QuotaEnforcementService | None = None
    reservation: ReservationResult | None = None
    if current_user.role == UserRole.CANDIDATE:
        quota_service, reservation = await _reserve_candidate_ai_quota(
            db,
            current_user,
            SubscriptionUsageFeatureType.CANDIDATE_CHAT,
            idempotency_key,
        )

    try:
        try:
            response = await service.chat(
                message=data.message,
                actor_user=current_user,
                history=data.history,
            )
        except (Exception, asyncio.CancelledError):
            if quota_service is not None and reservation is not None:
                await _release_ai_reservation_safe(
                    db, quota_service, reservation
                )
            raise

        if quota_service is not None and reservation is not None:
            try:
                await quota_service.finalize_reservation(
                    reservation.usage_id
                )
                await db.commit()
            except (Exception, asyncio.CancelledError):
                await _release_ai_reservation_safe(
                    db, quota_service, reservation
                )
                raise
        return response
    except EmptyDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except InvalidDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except AIProviderQuotaExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after) if exc.retry_after else "60"},
        ) from exc
    except AIProviderUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after) if exc.retry_after else "60"},
        ) from exc
    except AIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "/search/jobs",
    response_model=list[SemanticSearchResult],
    status_code=status.HTTP_200_OK,
)
async def semantic_search_jobs(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=10, ge=1, le=100),
    score_threshold: float | None = Query(default=None, ge=0.0, le=1.0),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    service: SemanticSearchService = Depends(_get_semantic_search_service),
) -> list[SemanticSearchResult]:
    try:
        from app.models import Job
        from app.repositories import BaseRepository

        job_repo = BaseRepository(db, Job)
        return await service.search_jobs(
            query=q,
            limit=limit,
            score_threshold=score_threshold,
            job_repository=job_repo,
            actor_user=current_user,
        )
    except EmptyDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (InvalidDocumentError, AIError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "/search/candidates",
    response_model=list[SemanticSearchResult],
    status_code=status.HTTP_200_OK,
)
async def semantic_search_candidates(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=10, ge=1, le=100),
    score_threshold: float | None = Query(default=None, ge=0.0, le=1.0),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: User = Depends(require_recruiter),
    workspace: WorkspaceContext | None = Depends(get_optional_workspace),
    db: AsyncSession = Depends(get_db),
    service: SemanticSearchService = Depends(_get_semantic_search_service),
) -> list[SemanticSearchResult]:
    ensure_not_interviewer(workspace)
    quota_service = QuotaEnforcementService(db)
    reservation: ReservationResult | None = None
    is_admin = current_user.role == UserRole.ADMIN
    try:
        if is_admin:
            quota_company_id = (
                workspace.company_id if workspace is not None else None
            )
        else:
            quota_company_id = await resolve_recruiter_ai_quota_company(
                db, current_user, workspace
            )

        reservation = await quota_service.reserve_search_quota(
            user_id=current_user.id,
            idempotency_key=idempotency_key,
            company_id=quota_company_id,
            is_admin=is_admin,
        )
        await db.commit()

        from app.models import CandidateProfile
        from app.repositories import BaseRepository

        candidate_repo = BaseRepository(db, CandidateProfile)
        results = await service.search_candidates(
            query=q,
            limit=limit,
            score_threshold=score_threshold,
            candidate_repository=candidate_repo,
            actor_user=current_user,
        )

        await quota_service.finalize_reservation(
            reservation.usage_id, success=True
        )
        await db.commit()
        reservation = None
        return results

    except asyncio.CancelledError:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise
    except ConflictException as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except EmptyDocumentError as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ForbiddenException as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except (InvalidDocumentError, AIError) as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except HTTPException:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise
    except Exception as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI service internal error",
        ) from exc


@router.get(
    "/recommendations/candidates",
    response_model=list[CandidateMatchRecommendation],
    status_code=status.HTTP_200_OK,
)
async def recommend_candidates_for_job(
    current_user: User = Depends(require_recruiter),
    workspace: WorkspaceContext | None = Depends(get_optional_workspace),
    service: AIMatchingService = Depends(_get_ai_service),
    db: AsyncSession = Depends(get_db),
    job_id: uuid.UUID = Query(...),
    limit: int = Query(default=10, ge=1, le=100),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    _: RateLimitResult = Depends(recommendations_rate_limit),
) -> list[CandidateMatchRecommendation]:
    ensure_not_interviewer(workspace)
    quota_service = QuotaEnforcementService(db)
    reservation: ReservationResult | None = None
    is_admin = current_user.role == UserRole.ADMIN
    try:
        referenced_company_id: uuid.UUID | None = None
        if isinstance(db, AsyncSession):
            target_job = await JobService(db).jobs.get_by_id(job_id)
            if target_job is not None:
                referenced_company_id = target_job.company_id

        if is_admin:
            quota_company_id = (
                workspace.company_id if workspace is not None else None
            )
        else:
            quota_company_id = await resolve_recruiter_ai_quota_company(
                db,
                current_user,
                workspace,
                referenced_company_id=referenced_company_id,
            )

        reservation = await quota_service.reserve_search_quota(
            user_id=current_user.id,
            idempotency_key=idempotency_key,
            reference_id=job_id,
            company_id=quota_company_id,
            is_admin=is_admin,
        )
        await db.commit()

        job = await JobService(db).get_recruiter_job_by_id(
            current_user, job_id
        )

        parsed_job = ParsedJobSchema(
            title=job.title,
            summary=job.description,
            required_skills=[skill.name for skill in job.required_skills] if job.required_skills else [],
            preferred_skills=[skill.name for skill in job.preferred_skills] if job.preferred_skills else [],
            minimum_years_experience=job.minimum_years_experience,
            education_level=job.education_level,
        )

        try:
            retrieved = await service.vector_repository.retrieve_vector(
                collection_name="jobs",
                point_id=job_id,
            )
        except Exception:
            retrieved = None
        if retrieved is not None:
            job_vector = retrieved["vector"]
        else:
            job_vector = await service.embedding_service.embed_job(parsed_job)

        result = await service.recommend_candidates_for_job(
            job_id=job_id,
            parsed_job=parsed_job,
            job_vector=job_vector,
            limit=limit,
            session=db,
            actor_user=current_user,
        )

        await quota_service.finalize_reservation(
            reservation.usage_id, success=True
        )
        await db.commit()
        reservation = None
        return result

    except asyncio.CancelledError:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise
    except EntityNotFoundException as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ConflictException as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ForbiddenException as exc:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except HTTPException:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise
    except Exception:
        await _release_ai_reservation_safe(db, quota_service, reservation)
        reservation = None
        raise


@router.post(
    "/evaluation/run",
    response_model=dict,
    summary="Run Offline AI Evaluation",
    description="Run offline evaluation metrics for the AI Matching Engine. Currently returns unavailable due to lack of labeled dataset.",
)
async def run_ai_evaluation(
    current_user: User = Depends(require_admin),
) -> dict:
    """Run offline evaluation. Requires admin role."""
    return {
        "status": "success",
        "message": "Evaluation infrastructure implemented; production metric unavailable because no labeled benchmark dataset exists.",
    }
