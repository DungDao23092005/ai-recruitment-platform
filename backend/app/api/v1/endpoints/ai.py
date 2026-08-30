from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.embedding_service import (
    EmbeddingService,
    SentenceTransformerEmbeddingProvider,
)
from app.ai.interfaces.base_provider import BaseVectorRepository
from app.ai.vector_db.qdrant_client import QdrantVectorRepository
from app.api.deps import (
    get_current_active_user,
    get_db,
    require_candidate,
    require_recruiter,
    require_admin,
)
from app.core.exceptions import (
    AIError,
    AIProviderQuotaExceededError,
    EmptyDocumentError,
    EntityNotFoundException,
    InvalidDocumentError,
)
from app.models import User
from app.schemas.ai_chat import ChatRequest, ChatResponse
from app.schemas.ai_explanation import ExplainMatchRequest, ExplainMatchResponse
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
from app.models.user import User
from app.schemas.ai_search import SemanticSearchResult
from app.services.ai_matching_service import AIMatchingService
from app.services.explainable_ai_service import ExplainableAIService
from app.services.interview_generator_service import InterviewGeneratorService
from app.services.job_service import JobService
from app.services.rag_chat_service import RAGChatService
from app.services.semantic_search_service import SemanticSearchService

router = APIRouter()


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


@router.post(
    "/parse-resume",
    response_model=ParsedResumeSchema,
    status_code=status.HTTP_200_OK,
)
async def parse_resume(
    file: UploadFile,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    service: AIMatchingService = Depends(_get_ai_service),
) -> ParsedResumeSchema:
    pdf_bytes = await file.read()
    candidate_profile = await current_user.awaitable_attrs.candidate_profile
    if candidate_profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Candidate profile required",
        )
    try:
        return await service.process_and_index_resume(
            candidate_id=candidate_profile.id,
            pdf_source=pdf_bytes,
            session=db,
            source_name=file.filename,
        )
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
    except AIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


class ParseJDRequest(BaseModel):
    job_title: str
    job_description: str
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
    current_user: User = Depends(require_recruiter),
    service: AIMatchingService = Depends(_get_ai_service),
) -> ParsedJobSchema:
    try:
        return await service.process_and_index_job(
            job_id=data.job_id or uuid.uuid4(),
            job_title=data.job_title,
            job_description=data.job_description,
        )
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


@router.post(
    "/match",
    response_model=MatchResultSchema,
    status_code=status.HTTP_200_OK,
)
async def match_candidate_and_job(
    data: MatchRequest,
    current_user: User = Depends(get_current_active_user),
    service: AIMatchingService = Depends(_get_ai_service),
) -> MatchResultSchema:
    return await service.match_candidate_with_job(
        parsed_resume=data.parsed_resume,
        parsed_job=data.parsed_job,
        resume_vector=data.resume_vector,
        job_vector=data.job_vector,
    )


@router.post(
    "/explain-match",
    response_model=ExplainMatchResponse,
    status_code=status.HTTP_200_OK,
)
async def explain_match(
    data: ExplainMatchRequest,
    current_user: User = Depends(get_current_active_user),
    service: ExplainableAIService = Depends(_get_explainable_ai_service),
) -> ExplainMatchResponse:
    try:
        return await service.explain_match(
            match_result=data.match_result,
            candidate=data.candidate,
            job=data.job,
        )
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


@router.post(
    "/generate-interview-questions",
    response_model=GenerateInterviewQuestionsResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_interview_questions(
    data: GenerateInterviewQuestionsRequest,
    current_user: User = Depends(require_recruiter),
    service: InterviewGeneratorService = Depends(
        _get_interview_generator_service
    ),
) -> GenerateInterviewQuestionsResponse:
    try:
        return await service.generate_questions(data)
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
    except AIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
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
) -> list[JobMatchRecommendation]:
    candidate_profile = await current_user.awaitable_attrs.candidate_profile
    if candidate_profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Candidate profile required",
        )

    try:
        return await service.recommend_jobs_for_candidate(
            candidate_id=candidate_profile.id,
            limit=limit,
            session=db,
            actor_user=current_user,
        )
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
    service: RAGChatService = Depends(_get_rag_chat_service),
) -> ChatResponse:
    try:
        return await service.chat(
            message=data.message,
            actor_user=current_user,
            history=data.history,
        )
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
    except AIProviderQuotaExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
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
    service: SemanticSearchService = Depends(_get_semantic_search_service),
) -> list[SemanticSearchResult]:
    try:
        return await service.search_jobs(
            query=q,
            limit=limit,
            score_threshold=score_threshold,
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
    current_user: User = Depends(require_recruiter),
    db: AsyncSession = Depends(get_db),
    service: SemanticSearchService = Depends(_get_semantic_search_service),
) -> list[SemanticSearchResult]:
    try:
        from app.repositories import BaseRepository
        from app.models import CandidateProfile

        candidate_repo = BaseRepository(db, CandidateProfile)
        return await service.search_candidates(
            query=q,
            limit=limit,
            score_threshold=score_threshold,
            candidate_repository=candidate_repo,
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
    "/recommendations/candidates",
    response_model=list[CandidateMatchRecommendation],
    status_code=status.HTTP_200_OK,
)
async def recommend_candidates_for_job(
    current_user: User = Depends(require_recruiter),
    service: AIMatchingService = Depends(_get_ai_service),
    db: AsyncSession = Depends(get_db),
    job_id: uuid.UUID = Query(...),
    limit: int = Query(default=10, ge=1, le=100),
) -> list[CandidateMatchRecommendation]:
    try:
        job = await JobService(db).get_recruiter_job_by_id(current_user, job_id)
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    parsed_job = ParsedJobSchema(
        title=job.title,
        summary=job.description,
        required_skills=[skill.name for skill in job.skills],
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

    return await service.recommend_candidates_for_job(
        job_id=job_id,
        parsed_job=parsed_job,
        job_vector=job_vector,
        limit=limit,
        session=db,
        actor_user=current_user,
    )
from app.services.ai_evaluation_service import AIEvaluationService, EvaluationSample, RelevanceLabel

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
        "message": "Evaluation infrastructure implemented; production metric unavailable because no labeled benchmark dataset exists."
    }
