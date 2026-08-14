from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from app.ai.embeddings.embedding_service import (
    EmbeddingService,
    SentenceTransformerEmbeddingProvider,
)
from app.ai.interfaces.base_provider import BaseVectorRepository
from app.ai.vector_db.qdrant_client import QdrantVectorRepository
from app.api.deps import (
    get_current_active_user,
    require_candidate,
    require_recruiter,
)
from app.core.exceptions import (
    AIError,
    EmptyDocumentError,
    EntityNotFoundException,
    InvalidDocumentError,
)
from app.models import User
from app.schemas.ai_explanation import ExplainMatchRequest, ExplainMatchResponse
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_matching import (
    CandidateMatchRecommendation,
    JobMatchRecommendation,
)
from app.schemas.ai_resume import ParsedResumeSchema
from app.schemas.ai_search import SemanticSearchResult
from app.services.ai_matching_service import AIMatchingService
from app.services.explainable_ai_service import ExplainableAIService
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


@router.post(
    "/parse-resume",
    response_model=ParsedResumeSchema,
    status_code=status.HTTP_200_OK,
)
async def parse_resume(
    file: UploadFile,
    current_user: User = Depends(require_candidate),
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
    return service.match_candidate_with_job(
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


@router.get(
    "/recommendations/jobs",
    response_model=list[JobMatchRecommendation],
    status_code=status.HTTP_200_OK,
)
async def recommend_jobs_for_candidate(
    current_user: User = Depends(require_candidate),
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
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
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
    service: SemanticSearchService = Depends(_get_semantic_search_service),
) -> list[SemanticSearchResult]:
    try:
        return await service.search_candidates(
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
    "/recommendations/candidates",
    response_model=list[CandidateMatchRecommendation],
    status_code=status.HTTP_200_OK,
)
async def recommend_candidates_for_job(
    current_user: User = Depends(require_recruiter),
    service: AIMatchingService = Depends(_get_ai_service),
    job_id: uuid.UUID = Query(...),
    limit: int = Query(default=10, ge=1, le=100),
) -> list[CandidateMatchRecommendation]:
    try:
        return await service.recommend_candidates_for_job(
            job_id=job_id,
            limit=limit,
        )
    except EntityNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
