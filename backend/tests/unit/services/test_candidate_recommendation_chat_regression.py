from __future__ import annotations

import logging
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.embeddings.embedding_service import EmbeddingService
from app.ai.interfaces.base_provider import BaseReranker, BaseVectorRepository, RerankResult
from app.ai.matching.matching_engine import MatchingEngine
from app.ai.parsers.job_parser import JobParser
from app.ai.parsers.resume_parser import ResumeParser
from app.core.exceptions import (
    AIError,
    AIProviderQuotaExceededError,
    AIProviderUnavailableError,
)
from app.domain.enums import JobStatus, UserRole
from app.models import CandidateProfile, Resume, User
from app.schemas.ai_chat import ChatIntent, ChatMessage, ChatSource
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.ai_matching_service import AIMatchingService
from app.services.rag_chat_service import (
    CV_UPLOAD_PATH,
    ChatIntentResponse,
    FactCheckResponse,
    LLMChatResponse,
    RAGChatService,
    RAGContext,
    UngroundedAnswerError,
)


def _make_candidate_user() -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.role = UserRole.CANDIDATE
    return user


def _make_reranker() -> BaseReranker:
    reranker = MagicMock(spec=BaseReranker)
    reranker.rerank = AsyncMock(
        side_effect=lambda query, candidates: [
            RerankResult(entity_id=c.entity_id, rerank_score=c.original_relevance_score)
            for c in candidates
        ]
    )
    return reranker


def _make_embedding_service() -> EmbeddingService:
    svc = MagicMock(spec=EmbeddingService)
    svc.embed_text = AsyncMock(return_value=[0.5, 0.5, 0.5])
    svc.embed_resume = AsyncMock(return_value=[0.5, 0.5, 0.5])
    svc.embed_job = AsyncMock(return_value=[0.5, 0.5, 0.5])
    return svc


def _make_session_factory(candidate_profile=None, primary_resume=None, draft_resume=None):
    """Build an async session factory supporting CandidateProfile & Resume queries cleanly."""
    session = MagicMock()

    async def _execute(stmt):
        compiled = str(stmt).lower()
        res = MagicMock()
        if "from candidate_profiles" in compiled:
            res.scalar_one_or_none.return_value = candidate_profile
            res.scalars.return_value.first.return_value = candidate_profile
            res.scalars.return_value.all.return_value = [candidate_profile] if candidate_profile else []
        elif "from resumes" in compiled:
            if "is_confirmed = true" in compiled or "is_primary = true" in compiled:
                res.scalar_one_or_none.return_value = primary_resume
                res.scalars.return_value.first.return_value = primary_resume
                res.scalars.return_value.all.return_value = [primary_resume] if primary_resume else []
            elif "is_confirmed = false" in compiled:
                res.scalar_one_or_none.return_value = draft_resume
                res.scalars.return_value.first.return_value = draft_resume
                res.scalars.return_value.all.return_value = [draft_resume] if draft_resume else []
            else:
                target = primary_resume or draft_resume
                res.scalar_one_or_none.return_value = target
                res.scalars.return_value.first.return_value = target
                res.scalars.return_value.all.return_value = [target] if target else []
        else:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.first.return_value = None
            res.scalars.return_value.all.return_value = []
        return res

    session.execute = AsyncMock(side_effect=_execute)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


def _make_resolver(jobs_dict=None, resumes_dict=None):
    resolver = MagicMock()
    resolver.resolve_jobs = AsyncMock(
        side_effect=lambda job_ids, actor_user: {
            jid: jobs_dict[jid] for jid in job_ids if jid in (jobs_dict or {})
        }
    )
    resolver.resolve_resumes = AsyncMock(
        side_effect=lambda candidate_ids, actor_user, **kwargs: {
            cid: resumes_dict[cid] for cid in candidate_ids if cid in (resumes_dict or {})
        }
    )
    resolver.resolve_knowledge = AsyncMock(return_value={})
    return resolver


# ==============================================================================
# TEST GROUP A: Intent classification for Vietnamese Candidate recommendation
# ==============================================================================


APPROVED_VERBATIM_RECOMMENDATION_QUERIES = [
    "cv của tôi hiện tại phù hợp với những công việc gì có trong hệ thống",
    "Dựa trên CV của tôi, hãy gợi ý các công việc phù hợp.",
    "Tôi nên ứng tuyển vào vị trí nào dựa trên hồ sơ hiện tại?",
    "Tìm các việc làm phù hợp với kỹ năng và kinh nghiệm của tôi.",
    "Hồ sơ của tôi có thể ứng tuyển những công việc nào?",
]


class TestGroupAIntentRouting:
    @pytest.mark.parametrize("query", APPROVED_VERBATIM_RECOMMENDATION_QUERIES)
    def test_five_approved_queries_detected_deterministically(self, query):
        assert RAGChatService._is_personal_recommendation_query(query) is True

    @pytest.mark.parametrize("query", APPROVED_VERBATIM_RECOMMENDATION_QUERIES)
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "llm_misclassified_intent",
        [ChatIntent.EXHAUSTIVE, ChatIntent.SEMANTIC, ChatIntent.KNOWLEDGE],
    )
    async def test_five_approved_queries_route_to_recommendation_for_candidate(
        self, query, llm_misclassified_intent
    ):
        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(
            return_value=ChatIntentResponse(intent=llm_misclassified_intent)
        )
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=llm,
            session_factory=_make_session_factory(),
            reranker=_make_reranker(),
        )

        intent_resp, _, _ = await service._classify_intent(
            query, actor_user=_make_candidate_user()
        )
        assert intent_resp.intent == ChatIntent.RECOMMENDATION

    @pytest.mark.parametrize("query", APPROVED_VERBATIM_RECOMMENDATION_QUERIES)
    @pytest.mark.asyncio
    async def test_non_candidate_actor_does_not_trigger_candidate_recommendation_override(
        self, query
    ):
        recruiter = MagicMock(spec=User)
        recruiter.id = uuid.uuid4()
        recruiter.role = UserRole.RECRUITER
        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(
            return_value=ChatIntentResponse(intent=ChatIntent.SEMANTIC)
        )
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=llm,
            session_factory=_make_session_factory(),
            reranker=_make_reranker(),
        )

        intent_resp, _, _ = await service._classify_intent(query, actor_user=recruiter)
        assert intent_resp.intent == ChatIntent.SEMANTIC

    @pytest.mark.asyncio
    async def test_intent_fallback_logs_warning_and_keeps_personal_recommendation(self, caplog):
        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(side_effect=RuntimeError("parse error"))
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=llm,
            session_factory=_make_session_factory(),
            reranker=_make_reranker(),
        )

        with caplog.at_level(logging.WARNING):
            rec_resp, _, _ = await service._classify_intent(
                "Tôi nên ứng tuyển vào vị trí nào dựa trên hồ sơ hiện tại?",
                actor_user=_make_candidate_user(),
            )
            sem_resp, _, _ = await service._classify_intent(
                "Tìm việc Backend Engineer",
                actor_user=_make_candidate_user(),
            )

        assert rec_resp.intent == ChatIntent.RECOMMENDATION
        assert sem_resp.intent == ChatIntent.SEMANTIC
        assert any(
            rec.message == "chat_intent_classification_fallback"
            for rec in caplog.records
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query, expected_intent",
        [
            ("Liệt kê tất cả vị trí thực tập", ChatIntent.EXHAUSTIVE),
            ("Liệt kê tất cả các công việc Backend đang tuyển", ChatIntent.EXHAUSTIVE),
            ("Có bao nhiêu việc remote?", ChatIntent.EXHAUSTIVE),
            ("Tìm việc Backend Engineer", ChatIntent.SEMANTIC),
            ("Có những công việc React nào ở TP.HCM?", ChatIntent.SEMANTIC),
            ("Tôi muốn xem chi tiết công việc Python Developer", ChatIntent.SEMANTIC),
            ("Hồ sơ ứng viên trong hệ thống gồm những thông tin gì?", ChatIntent.KNOWLEDGE),
            ("RAG là gì?", ChatIntent.KNOWLEDGE),
            ("Cách tối ưu hóa CV để tăng điểm đối sánh tuyển dụng?", ChatIntent.KNOWLEDGE),
        ],
    )
    async def test_standalone_non_recommendation_queries_are_not_hijacked(
        self, query, expected_intent
    ):
        assert RAGChatService._is_personal_recommendation_query(query) is False

        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(
            return_value=ChatIntentResponse(intent=expected_intent)
        )
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=llm,
            session_factory=_make_session_factory(),
            reranker=_make_reranker(),
        )

        intent_resp, _, _ = await service._classify_intent(
            query, actor_user=_make_candidate_user()
        )
        assert intent_resp.intent == expected_intent


# ==============================================================================
# TEST GROUP B: Attempt 1 & Attempt 2 Grounding + Metadata Alignment
# ==============================================================================


class TestGroupBAttemptOneAndTwoGrounding:
    def test_attempt_one_and_two_prompts_use_identical_canonical_metadata(self):
        job_id = uuid.uuid4()
        resume_id = uuid.uuid4()
        job = ParsedJobSchema(
            title="Senior Python Backend Engineer",
            required_skills=["Python", "FastAPI", "PostgreSQL"],
        )
        resume = ParsedResumeSchema(skills=["Python", "FastAPI"], total_years_experience=3.0)
        match = MatchResultSchema(
            entity_id=job_id,
            overall_score=86.5,
            cosine_similarity=0.88,
            skill_coverage_score=0.67,
            preferred_skill_coverage_score=0.5,
            experience_match_score=1.0,
            education_score=1.0,
            project_score=0.5,
            has_required_skills=True,
            matching_skills=["Python", "FastAPI"],
            skill_gap=["PostgreSQL"],
            match_reasons=["Khớp 2/3 kỹ năng bắt buộc"],
        )
        rag_context = RAGContext(
            jobs=[job],
            candidates=[resume],
            match_results=[match],
            sources=[
                ChatSource(
                    source_type="job",
                    entity_id=job_id,
                    title="Senior Python Backend Engineer",
                    relevance_score=0.865,
                    skills=["Python", "FastAPI", "PostgreSQL"],
                ),
                ChatSource(
                    source_type="resume",
                    entity_id=resume_id,
                    title="CV Backend",
                    relevance_score=1.0,
                    skills=["Python", "FastAPI"],
                ),
            ],
        )

        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=MagicMock(),
            session_factory=_make_session_factory(),
            reranker=_make_reranker(),
        )

        canonical_metadata = RAGChatService._build_source_metadata_text(rag_context)
        attempt1_prompt = service._build_prompt(
            "cv của tôi phù hợp với công việc nào", [], rag_context
        )
        attempt2_prompt = service._build_self_correction_prompt(
            original_prompt=attempt1_prompt,
            failed_answer="bad draft",
            failed_citations=[],
            failed_evidence=[],
            evaluator_feedback="No valid evidence quotes found",
            rag_context=rag_context,
        )

        assert canonical_metadata in attempt1_prompt
        assert canonical_metadata in attempt2_prompt
        assert "[1] source_type=" not in attempt2_prompt
        assert "Không đủ bằng chứng để trả lời câu hỏi này." not in attempt2_prompt
        assert "  Job Title: Senior Python Backend Engineer" in attempt1_prompt
        assert "  Job Title: Senior Python Backend Engineer" in attempt2_prompt
        assert "\n  Overall Score: 86.5 (86.5%)\n" in attempt1_prompt

        # Canonical metadata quote AND verbatim recommendation quote both validate!
        canonical_quote = (
            f"SOURCE\n  canonical_id: {job_id}\n  source_type: job\n"
            f"  title: Senior Python Backend Engineer\n  relevance_score: 0.865\n"
            f"  skills: Python, FastAPI, PostgreSQL"
        )
        llm_resp = LLMChatResponse(
            answer="Vị trí Senior Python Backend Engineer phù hợp 86.5% với CV của bạn.",
            cited_source_ids=[job_id, resume_id],
            evidence_quotes=[
                canonical_quote,
                "  Job Title: Senior Python Backend Engineer\n  Required Skills: Python, FastAPI, PostgreSQL",
                "  Matching Skills: Python, FastAPI",
            ],
            claims=["Senior Python Backend Engineer có điểm phù hợp 86.5"],
            suggested_followups=[],
        )
        validated, valid_quotes = RAGChatService._validate_response(llm_resp, rag_context)
        assert len(valid_quotes) == 3
        assert {s.entity_id for s in validated.sources} == {job_id, resume_id}

    @pytest.mark.asyncio
    async def test_attempt_one_failure_triggers_attempt_two_and_succeeds(self):
        user = _make_candidate_user()
        candidate_id = uuid.uuid4()
        job_id = uuid.uuid4()
        profile = SimpleNamespace(id=candidate_id, user_id=user.id)
        primary_resume = SimpleNamespace(
            id=uuid.uuid4(),
            candidate_id=candidate_id,
            is_primary=True,
            is_confirmed=True,
            parsed_data={"skills": ["Python", "FastAPI"]},
            confirmed_at=None,
        )
        parsed_job = ParsedJobSchema(
            title="Python Developer",
            required_skills=["Python", "FastAPI"],
        )

        vector_repo = MagicMock(spec=BaseVectorRepository)
        vector_repo.retrieve_vector = AsyncMock(
            return_value={"vector": [0.5, 0.5, 0.5], "payload": {"skills": ["Python", "FastAPI"]}}
        )
        vector_repo.search_similar = AsyncMock(
            return_value=[{"id": str(job_id), "score": 0.9, "payload": {"status": "published"}}]
        )
        resolver = _make_resolver(
            jobs_dict={job_id: parsed_job},
            resumes_dict={candidate_id: ParsedResumeSchema(skills=["Python", "FastAPI"])},
        )
        matching_svc = AIMatchingService(
            resume_parser=AsyncMock(spec=ResumeParser),
            job_parser=AsyncMock(spec=JobParser),
            embedding_service=_make_embedding_service(),
            vector_repository=vector_repo,
            matching_engine=MatchingEngine(),
            context_resolver=resolver,
        )

        prompts_seen: list[str] = []
        gen_count = 0

        async def _mock_llm(prompt, response_schema, system_instruction):
            nonlocal gen_count
            if response_schema is ChatIntentResponse:
                return ChatIntentResponse(intent=ChatIntent.RECOMMENDATION)
            if response_schema is FactCheckResponse:
                return FactCheckResponse(is_faithful=True, contradictions=[])
            gen_count += 1
            prompts_seen.append(prompt)
            if gen_count == 1:
                # Bad evidence format on Attempt 1
                return LLMChatResponse(
                    answer="Phù hợp Python Developer.",
                    cited_source_ids=[job_id],
                    evidence_quotes=["[1] source_type=job, entity_id=bad"],
                    claims=["Python Developer"],
                    suggested_followups=[],
                )
            # Canonical quote on Attempt 2
            return LLMChatResponse(
                answer="CV của bạn phù hợp với vị trí Python Developer.",
                cited_source_ids=[job_id, candidate_id],
                evidence_quotes=[
                    "  Job Title: Python Developer",
                    "  Matching Skills: Python, FastAPI",
                ],
                claims=["CV có kỹ năng Python và FastAPI phù hợp Python Developer"],
                suggested_followups=[],
            )

        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(side_effect=_mock_llm)

        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=vector_repo,
            llm_provider=llm,
            session_factory=_make_session_factory(
                candidate_profile=profile,
                primary_resume=primary_resume,
            ),
            context_resolver=resolver,
            reranker=_make_reranker(),
            matching_service=matching_svc,
        )

        response = await service.chat(
            "cv của tôi hiện tại phù hợp với những công việc gì có trong hệ thống",
            user,
        )
        assert gen_count == 2
        assert "[1] source_type=" not in prompts_seen[1]
        assert "Python Developer" in response.answer
        assert response.recommended_job_ids == [job_id]
        assert response._charge_quota is True


# ==============================================================================
# TEST GROUP C: Candidate CV States, Self-Healing, Constructor Wiring, No Jobs
# ==============================================================================


class TestGroupCCandidateCVStatesAndWiring:
    def test_constructor_forwards_vector_repository_to_matching_service(self):
        custom_repo = MagicMock(spec=BaseVectorRepository)
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=custom_repo,
            llm_provider=MagicMock(),
            session_factory=_make_session_factory(),
            reranker=_make_reranker(),
        )
        assert service._matching_service.vector_repository is custom_repo

    @pytest.mark.asyncio
    async def test_no_candidate_profile_returns_upload_guidance_without_charging_quota(self):
        user = _make_candidate_user()
        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(
            return_value=ChatIntentResponse(intent=ChatIntent.RECOMMENDATION)
        )
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=llm,
            session_factory=_make_session_factory(candidate_profile=None),
            reranker=_make_reranker(),
        )

        response = await service.chat("cv của tôi phù hợp với công việc nào", user)
        assert "Không đủ bằng chứng" not in response.answer
        assert CV_UPLOAD_PATH in response.answer
        assert response._charge_quota is False

    @pytest.mark.asyncio
    async def test_no_cv_at_all_returns_clear_guidance_and_no_quota_charge(self):
        user = _make_candidate_user()
        profile = SimpleNamespace(id=uuid.uuid4(), user_id=user.id)
        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(
            return_value=ChatIntentResponse(intent=ChatIntent.RECOMMENDATION)
        )
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=llm,
            session_factory=_make_session_factory(
                candidate_profile=profile,
                primary_resume=None,
                draft_resume=None,
            ),
            reranker=_make_reranker(),
        )

        response = await service.chat("cv của tôi phù hợp với công việc nào", user)
        assert "chưa có CV" in response.answer
        assert CV_UPLOAD_PATH in response.answer
        assert "Không đủ bằng chứng" not in response.answer
        assert response._charge_quota is False

    @pytest.mark.asyncio
    async def test_unconfirmed_draft_cv_points_to_cv_upload_without_charging_quota(self):
        user = _make_candidate_user()
        cid = uuid.uuid4()
        profile = SimpleNamespace(id=cid, user_id=user.id)
        draft = SimpleNamespace(
            id=uuid.uuid4(),
            candidate_id=cid,
            is_primary=False,
            is_confirmed=False,
            parsed_data={"skills": ["Python"]},
        )
        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(
            return_value=ChatIntentResponse(intent=ChatIntent.RECOMMENDATION)
        )
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=llm,
            session_factory=_make_session_factory(
                candidate_profile=profile,
                primary_resume=None,
                draft_resume=draft,
            ),
            reranker=_make_reranker(),
        )

        response = await service.chat("cv của tôi phù hợp với công việc nào", user)
        assert "chưa xác nhận" in response.answer
        assert CV_UPLOAD_PATH in response.answer
        assert "Không đủ bằng chứng" not in response.answer
        assert response._charge_quota is False

    @pytest.mark.asyncio
    async def test_corrupt_confirmed_cv_returns_safe_guidance_without_traceback(self):
        user = _make_candidate_user()
        cid = uuid.uuid4()
        profile = SimpleNamespace(id=cid, user_id=user.id)
        corrupt_resume = SimpleNamespace(
            id=uuid.uuid4(),
            candidate_id=cid,
            is_primary=True,
            is_confirmed=True,
            parsed_data={"skills": "not-a-list"},
        )
        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(
            return_value=ChatIntentResponse(intent=ChatIntent.RECOMMENDATION)
        )
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=llm,
            session_factory=_make_session_factory(
                candidate_profile=profile,
                primary_resume=corrupt_resume,
            ),
            reranker=_make_reranker(),
        )

        response = await service.chat("cv của tôi phù hợp với công việc nào", user)
        assert "Traceback" not in response.answer
        assert "ValidationError" not in response.answer
        assert CV_UPLOAD_PATH in response.answer
        assert response._charge_quota is False

    @pytest.mark.asyncio
    async def test_confirmed_cv_missing_vector_triggers_self_healing_and_returns_jobs(self):
        user = _make_candidate_user()
        cid = uuid.uuid4()
        job_id = uuid.uuid4()
        profile = SimpleNamespace(id=cid, user_id=user.id)
        primary = SimpleNamespace(
            id=uuid.uuid4(),
            candidate_id=cid,
            is_primary=True,
            is_confirmed=True,
            parsed_data={"skills": ["Python", "Docker"]},
            confirmed_at=None,
        )
        vector_repo = MagicMock(spec=BaseVectorRepository)
        vector_repo.retrieve_vector = AsyncMock(return_value=None)
        vector_repo.upsert_vector = AsyncMock()
        vector_repo.search_similar = AsyncMock(
            return_value=[{"id": str(job_id), "score": 0.91, "payload": {"status": "published"}}]
        )
        resolver = _make_resolver(
            jobs_dict={job_id: ParsedJobSchema(title="DevOps Engineer", required_skills=["Python", "Docker"])},
            resumes_dict={cid: ParsedResumeSchema(skills=["Python", "Docker"])},
        )
        matching_svc = AIMatchingService(
            resume_parser=AsyncMock(spec=ResumeParser),
            job_parser=AsyncMock(spec=JobParser),
            embedding_service=_make_embedding_service(),
            vector_repository=vector_repo,
            matching_engine=MatchingEngine(),
            context_resolver=resolver,
        )

        async def _mock_llm(prompt, response_schema, system_instruction):
            if response_schema is ChatIntentResponse:
                return ChatIntentResponse(intent=ChatIntent.RECOMMENDATION)
            if response_schema is FactCheckResponse:
                return FactCheckResponse(is_faithful=True, contradictions=[])
            return LLMChatResponse(
                answer="Bạn phù hợp với vị trí DevOps Engineer.",
                cited_source_ids=[job_id, cid],
                evidence_quotes=["  Job Title: DevOps Engineer"],
                claims=["CV phù hợp DevOps Engineer"],
                suggested_followups=[],
            )

        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(side_effect=_mock_llm)
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=vector_repo,
            llm_provider=llm,
            session_factory=_make_session_factory(
                candidate_profile=profile,
                primary_resume=primary,
            ),
            context_resolver=resolver,
            reranker=_make_reranker(),
            matching_service=matching_svc,
        )

        response = await service.chat("tôi phù hợp với những vị trí nào", user)
        vector_repo.upsert_vector.assert_awaited_once()
        assert "DevOps Engineer" in response.answer
        assert response.recommended_job_ids == [job_id]
        assert response._charge_quota is True

    @pytest.mark.asyncio
    async def test_confirmed_cv_with_no_eligible_jobs_keeps_contract(self):
        user = _make_candidate_user()
        cid = uuid.uuid4()
        profile = SimpleNamespace(id=cid, user_id=user.id)
        primary = SimpleNamespace(
            id=uuid.uuid4(),
            candidate_id=cid,
            is_primary=True,
            is_confirmed=True,
            parsed_data={"skills": ["Rust"]},
            confirmed_at=None,
        )
        vector_repo = MagicMock(spec=BaseVectorRepository)
        vector_repo.retrieve_vector = AsyncMock(
            return_value={"vector": [0.5, 0.5, 0.5], "payload": {"skills": ["Rust"]}}
        )
        vector_repo.search_similar = AsyncMock(return_value=[])
        matching_svc = AIMatchingService(
            resume_parser=AsyncMock(spec=ResumeParser),
            job_parser=AsyncMock(spec=JobParser),
            embedding_service=_make_embedding_service(),
            vector_repository=vector_repo,
            matching_engine=MatchingEngine(),
            context_resolver=_make_resolver(),
        )
        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(
            return_value=ChatIntentResponse(intent=ChatIntent.RECOMMENDATION)
        )
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=vector_repo,
            llm_provider=llm,
            session_factory=_make_session_factory(
                candidate_profile=profile,
                primary_resume=primary,
            ),
            reranker=_make_reranker(),
            matching_service=matching_svc,
        )

        response = await service.chat("gợi ý việc làm phù hợp với cv của tôi", user)
        assert response.answer.startswith("Hiện chưa tìm thấy công việc nào phù hợp")

    @pytest.mark.asyncio
    async def test_multi_turn_followup_preserves_previous_recommended_job_ids(self):
        user = _make_candidate_user()
        cid = uuid.uuid4()
        job_a = uuid.uuid4()
        job_b = uuid.uuid4()
        profile = SimpleNamespace(id=cid, user_id=user.id)
        primary = SimpleNamespace(
            id=uuid.uuid4(),
            candidate_id=cid,
            is_primary=True,
            is_confirmed=True,
            parsed_data={"skills": ["Python", "FastAPI"]},
            confirmed_at=None,
        )
        vector_repo = MagicMock(spec=BaseVectorRepository)
        vector_repo.retrieve_vector = AsyncMock(
            return_value={"vector": [0.5, 0.5, 0.5], "payload": {"skills": ["Python", "FastAPI"]}}
        )
        vector_repo.search_similar = AsyncMock(
            return_value=[
                {"id": str(job_a), "score": 0.9, "payload": {"status": "published"}},
                {"id": str(job_b), "score": 0.7, "payload": {"status": "published"}},
            ]
        )
        resolver = _make_resolver(
            jobs_dict={
                job_a: ParsedJobSchema(title="AI Engineer", required_skills=["Python", "PyTorch"]),
                job_b: ParsedJobSchema(title="Java Dev", required_skills=["Java"]),
            },
            resumes_dict={cid: ParsedResumeSchema(skills=["Python", "FastAPI"])},
        )
        matching_svc = AIMatchingService(
            resume_parser=AsyncMock(spec=ResumeParser),
            job_parser=AsyncMock(spec=JobParser),
            embedding_service=_make_embedding_service(),
            vector_repository=vector_repo,
            matching_engine=MatchingEngine(),
            context_resolver=resolver,
        )

        captured_prompts: list[str] = []

        async def _mock_llm(prompt, response_schema, system_instruction):
            if response_schema is ChatIntentResponse:
                return ChatIntentResponse(intent=ChatIntent.RECOMMENDATION)
            if response_schema is FactCheckResponse:
                return FactCheckResponse(is_faithful=True, contradictions=[])
            captured_prompts.append(prompt)
            return LLMChatResponse(
                answer="Bạn cần bổ sung PyTorch cho vị trí AI Engineer.",
                cited_source_ids=[job_a, cid],
                evidence_quotes=["  Job Title: AI Engineer", "Skills: Python, FastAPI"],
                claims=["AI Engineer yêu cầu PyTorch"],
                suggested_followups=[],
            )

        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(side_effect=_mock_llm)
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=vector_repo,
            llm_provider=llm,
            session_factory=_make_session_factory(
                candidate_profile=profile,
                primary_resume=primary,
            ),
            context_resolver=resolver,
            reranker=_make_reranker(),
            matching_service=matching_svc,
        )

        history = [
            ChatMessage(role="user", content="cv của tôi phù hợp với công việc nào"),
            ChatMessage(
                role="assistant",
                content="AI Engineer phù hợp nhất.",
                recommended_job_ids=[job_a],
            ),
        ]
        response = await service.chat("Tôi còn thiếu kỹ năng gì?", user, history=history)
        assert response.recommended_job_ids == [job_a]
        assert "AI Engineer" in captured_prompts[-1]
        assert "Java Dev" not in captured_prompts[-1]

    def test_flat_context_keeps_distinct_job_blocks_without_cross_contamination(self):
        job_a = uuid.uuid4()
        job_b = uuid.uuid4()
        ctx = RAGContext(
            jobs=[
                ParsedJobSchema(title="Job Alpha", required_skills=["Python"]),
                ParsedJobSchema(title="Job Beta", required_skills=["Go"]),
            ],
            candidates=[],
            match_results=[
                MatchResultSchema(
                    entity_id=job_a,
                    overall_score=91.0,
                    cosine_similarity=0.9,
                    skill_coverage_score=1.0,
                    experience_match_score=1.0,
                    matching_skills=["Python"],
                    skill_gap=[],
                    match_reasons=["Khớp Python"],
                ),
                MatchResultSchema(
                    entity_id=job_b,
                    overall_score=42.0,
                    cosine_similarity=0.4,
                    skill_coverage_score=0.0,
                    experience_match_score=0.5,
                    matching_skills=[],
                    skill_gap=["Go"],
                    match_reasons=["Thiếu Go"],
                ),
            ],
            sources=[
                ChatSource(source_type="job", entity_id=job_a, title="Job Alpha", relevance_score=0.91, skills=["Python"]),
                ChatSource(source_type="job", entity_id=job_b, title="Job Beta", relevance_score=0.42, skills=["Go"]),
            ],
        )
        flat = RAGChatService._build_flat_context_text(ctx)
        rec_section = flat.split("--- RECOMMENDATION MATCH RESULTS ---")[1]
        rec1, rec2 = rec_section.split("Recommendation #2:")
        assert "Job Title: Job Alpha" in rec1 and "Overall Score: 91.0" in rec1 and "Matching Skills: Python" in rec1
        assert "Job Beta" not in rec1 and "42.0" not in rec1
        assert "Job Title: Job Beta" in rec2 and "Overall Score: 42.0" in rec2 and "Missing Skills: Go" in rec2
        assert "Job Alpha" not in rec2 and "91.0" not in rec2

    @pytest.mark.asyncio
    async def test_entity_not_found_from_matching_returns_safe_guidance_not_error(self):
        user = _make_candidate_user()
        cid = uuid.uuid4()
        profile = SimpleNamespace(id=cid, user_id=user.id)
        primary = SimpleNamespace(
            id=uuid.uuid4(),
            candidate_id=cid,
            is_primary=True,
            is_confirmed=True,
            parsed_data={"skills": ["Python"]},
            confirmed_at=None,
        )
        matching_svc = MagicMock()
        from app.core.exceptions import EntityNotFoundException
        matching_svc.recommend_jobs_for_candidate = AsyncMock(
            side_effect=EntityNotFoundException("CV của bạn chưa được số hoá thành công.")
        )
        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(
            return_value=ChatIntentResponse(intent=ChatIntent.RECOMMENDATION)
        )
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=llm,
            session_factory=_make_session_factory(
                candidate_profile=profile,
                primary_resume=primary,
            ),
            reranker=_make_reranker(),
            matching_service=matching_svc,
        )

        response = await service.chat("cv của tôi phù hợp với công việc nào", user)
        assert CV_UPLOAD_PATH in response.answer
        assert "Không đủ bằng chứng" not in response.answer
        assert response._charge_quota is False


# ==============================================================================
# TEST GROUP D & F: Fallbacks, Provider Error Propagation & process_and_index_job
# ==============================================================================


class TestGroupDGroundingFallbackAndProviderErrors:
    @pytest.mark.asyncio
    async def test_recommendation_grounding_failure_returns_verified_deterministic_fallback(self):
        user = _make_candidate_user()
        cid = uuid.uuid4()
        job_id = uuid.uuid4()
        profile = SimpleNamespace(id=cid, user_id=user.id)
        primary = SimpleNamespace(
            id=uuid.uuid4(),
            candidate_id=cid,
            is_primary=True,
            is_confirmed=True,
            parsed_data={"skills": ["Python"]},
            confirmed_at=None,
        )
        vector_repo = MagicMock(spec=BaseVectorRepository)
        vector_repo.retrieve_vector = AsyncMock(
            return_value={"vector": [0.5, 0.5, 0.5], "payload": {"skills": ["Python"]}}
        )
        vector_repo.search_similar = AsyncMock(
            return_value=[{"id": str(job_id), "score": 0.88, "payload": {"status": "published"}}]
        )
        resolver = _make_resolver(
            jobs_dict={job_id: ParsedJobSchema(title="AI Backend Engineer", required_skills=["Python"])},
            resumes_dict={cid: ParsedResumeSchema(skills=["Python"])},
        )
        matching_svc = AIMatchingService(
            resume_parser=AsyncMock(spec=ResumeParser),
            job_parser=AsyncMock(spec=JobParser),
            embedding_service=_make_embedding_service(),
            vector_repository=vector_repo,
            matching_engine=MatchingEngine(),
            context_resolver=resolver,
        )

        async def _mock_llm(prompt, response_schema, system_instruction):
            if response_schema is ChatIntentResponse:
                return ChatIntentResponse(intent=ChatIntent.RECOMMENDATION)
            # Fail validation on BOTH Attempt 1 and Attempt 2 (no valid evidence)
            return LLMChatResponse(
                answer="Fake ungrounded claim",
                cited_source_ids=[],
                evidence_quotes=[],
                claims=["Fake claim"],
                suggested_followups=[],
            )

        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(side_effect=_mock_llm)
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=vector_repo,
            llm_provider=llm,
            session_factory=_make_session_factory(
                candidate_profile=profile,
                primary_resume=primary,
            ),
            context_resolver=resolver,
            reranker=_make_reranker(),
            matching_service=matching_svc,
        )

        response = await service.chat("dựa trên hồ sơ của tôi hãy đề xuất công việc phù hợp", user)
        assert "Không đủ bằng chứng" not in response.answer
        assert "AI Backend Engineer" in response.answer
        assert job_id in response.recommended_job_ids
        assert response._charge_quota is False

    @pytest.mark.asyncio
    async def test_provider_unavailable_and_quota_exceeded_propagate(self):
        user = _make_candidate_user()
        llm_unavail = MagicMock()
        llm_unavail.generate_structured_output = AsyncMock(
            side_effect=AIProviderUnavailableError("Gemini down")
        )
        service1 = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=llm_unavail,
            session_factory=_make_session_factory(),
            reranker=_make_reranker(),
        )
        with pytest.raises(AIProviderUnavailableError):
            await service1.chat("cv của tôi phù hợp với công việc nào", user)

        llm_quota = MagicMock()
        llm_quota.generate_structured_output = AsyncMock(
            side_effect=AIProviderQuotaExceededError("Rate limit")
        )
        service2 = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=llm_quota,
            session_factory=_make_session_factory(),
            reranker=_make_reranker(),
        )
        with pytest.raises(AIProviderQuotaExceededError):
            await service2.chat("cv của tôi phù hợp với công việc nào", user)

    @pytest.mark.asyncio
    async def test_process_and_index_job_includes_status_in_payload(self):
        job_id = uuid.uuid4()
        job_parser = AsyncMock(spec=JobParser)
        job_parser.parse = AsyncMock(
            return_value=ParsedJobSchema(title="ML Engineer", required_skills=["Python"])
        )
        vector_repo = AsyncMock(spec=BaseVectorRepository)
        matching_svc = AIMatchingService(
            resume_parser=AsyncMock(spec=ResumeParser),
            job_parser=job_parser,
            embedding_service=_make_embedding_service(),
            vector_repository=vector_repo,
            matching_engine=MatchingEngine(),
        )

        await matching_svc.process_and_index_job(
            job_id=job_id,
            job_title="ML Engineer",
            job_description="Build ML models",
        )
        default_payload = vector_repo.upsert_vector.call_args.kwargs["payload"]
        assert default_payload["status"] == JobStatus.PUBLISHED.value

        await matching_svc.process_and_index_job(
            job_id=job_id,
            job_title="ML Engineer",
            job_description="Build ML models",
            status=JobStatus.DRAFT,
        )
        draft_payload = vector_repo.upsert_vector.call_args.kwargs["payload"]
        assert draft_payload["status"] == JobStatus.DRAFT.value


# ==============================================================================
# TEST GROUP G: Candidate Follow-Up Routing, Focused Prompts, Context & Fallback
# ==============================================================================


APPROVED_FOLLOWUP_QUERIES = [
    "Vị trí nào liên quan nhiều nhất đến AI?",
    "Tôi cần bổ sung kỹ năng gì để ứng tuyển vị trí Machine Learning Engineer?",
    "Tại sao tôi phù hợp với vị trí phù hợp nhất?",
    "Tôi còn thiếu kỹ năng gì cho các vị trí trên?",
    "Chi tiết mức độ phù hợp cho từng vị trí là bao nhiêu?",
    "Tôi cần bổ sung kỹ năng gì cho vị trí Backend Developer (Python)?",
]


def _build_multi_job_recommendation_fixture():
    ml_job_id = uuid.uuid4()
    be_job_id = uuid.uuid4()
    fe_job_id = uuid.uuid4()
    cid = uuid.uuid4()

    jobs_dict = {
        ml_job_id: ParsedJobSchema(
            title="Machine Learning Engineer",
            summary="Build production NLP, LLM, and RAG pipelines with PyTorch.",
            required_skills=["Python", "PyTorch", "NLP"],
            preferred_skills=["MLOps"],
        ),
        be_job_id: ParsedJobSchema(
            title="Backend Developer (Python)",
            summary="Develop REST APIs using Python and FastAPI.",
            required_skills=["Python", "FastAPI", "Docker"],
            preferred_skills=["Redis"],
        ),
        fe_job_id: ParsedJobSchema(
            title="Frontend Engineer (React)",
            summary="Build responsive React web interfaces.",
            required_skills=["React", "TypeScript"],
            preferred_skills=[],
        ),
    }

    match_results = [
        MatchResultSchema(
            entity_id=be_job_id,
            overall_score=88.5,
            cosine_similarity=0.89,
            skill_coverage_score=0.67,
            preferred_skill_coverage_score=0.0,
            experience_match_score=0.95,
            education_score=0.0,
            project_score=0.0,
            has_required_skills=True,
            has_preferred_skills=True,
            has_experience_requirement=True,
            has_education_requirement=False,
            matching_skills=["Python", "FastAPI"],
            skill_gap=["Docker"],
            match_reasons=["Khớp 2/3 kỹ năng bắt buộc Backend Python", "Kinh nghiệm đạt yêu cầu"],
        ),
        MatchResultSchema(
            entity_id=ml_job_id,
            overall_score=74.0,
            cosine_similarity=0.82,
            skill_coverage_score=0.33,
            preferred_skill_coverage_score=0.0,
            experience_match_score=0.80,
            education_score=0.0,
            project_score=0.0,
            has_required_skills=True,
            has_preferred_skills=False,
            has_experience_requirement=True,
            has_education_requirement=False,
            matching_skills=["Python"],
            skill_gap=["PyTorch", "NLP"],
            match_reasons=["Có nền tảng Python cho ML"],
        ),
        MatchResultSchema(
            entity_id=fe_job_id,
            overall_score=35.0,
            cosine_similarity=0.40,
            skill_coverage_score=0.0,
            preferred_skill_coverage_score=0.0,
            experience_match_score=0.0,
            education_score=0.0,
            project_score=0.0,
            has_required_skills=True,
            has_preferred_skills=False,
            has_experience_requirement=False,
            has_education_requirement=False,
            matching_skills=[],
            skill_gap=["React", "TypeScript"],
            match_reasons=["Chưa có kỹ năng frontend bắt buộc"],
        ),
    ]

    sources = [
        ChatSource(
            source_type="job",
            entity_id=be_job_id,
            title="Backend Developer (Python)",
            relevance_score=0.885,
            skills=["Python", "FastAPI", "Docker", "Redis"],
        ),
        ChatSource(
            source_type="job",
            entity_id=ml_job_id,
            title="Machine Learning Engineer",
            relevance_score=0.74,
            skills=["Python", "PyTorch", "NLP", "MLOps"],
        ),
        ChatSource(
            source_type="job",
            entity_id=fe_job_id,
            title="Frontend Engineer (React)",
            relevance_score=0.35,
            skills=["React", "TypeScript"],
        ),
        ChatSource(
            source_type="resume",
            entity_id=cid,
            title="CV Python Backend",
            relevance_score=1.0,
            skills=["Python", "FastAPI"],
        ),
    ]

    rag_context = RAGContext(
        jobs=[jobs_dict[be_job_id], jobs_dict[ml_job_id], jobs_dict[fe_job_id]],
        candidates=[ParsedResumeSchema(title="CV Python Backend", skills=["Python", "FastAPI"])],
        match_results=match_results,
        sources=sources,
    )
    return cid, be_job_id, ml_job_id, fe_job_id, jobs_dict, rag_context


class TestGroupGFollowUpIntentAndFocusedResponses:
    @pytest.mark.parametrize("query", APPROVED_FOLLOWUP_QUERIES)
    @pytest.mark.asyncio
    async def test_followup_queries_require_recommendation_history_and_route_deterministically(
        self, query
    ):
        # Without recommendation history: deterministic override stays False
        assert RAGChatService._is_personal_recommendation_query(query, history=None) is False
        assert (
            RAGChatService._is_personal_recommendation_query(
                query,
                history=[ChatMessage(role="user", content="Xin chào")],
            )
            is False
        )

        # With previous recommended_job_ids: routes to RECOMMENDATION even if LLM returns another intent
        history_with_rec = [
            ChatMessage(role="user", content="cv của tôi hiện tại phù hợp với những công việc gì"),
            ChatMessage(
                role="assistant",
                content="Các vị trí phù hợp gồm ML Engineer và Backend Developer (Python).",
                recommended_job_ids=[uuid.uuid4()],
            ),
        ]
        assert RAGChatService._is_personal_recommendation_query(query, history=history_with_rec) is True

        for misclassified in (ChatIntent.EXHAUSTIVE, ChatIntent.SEMANTIC, ChatIntent.KNOWLEDGE):
            llm = MagicMock()
            llm.generate_structured_output = AsyncMock(
                return_value=ChatIntentResponse(intent=misclassified)
            )
            service = RAGChatService(
                embedding_service=_make_embedding_service(),
                vector_repository=MagicMock(spec=BaseVectorRepository),
                llm_provider=llm,
                session_factory=_make_session_factory(),
                reranker=_make_reranker(),
            )
            intent_resp, _, _ = await service._classify_intent(
                query,
                history=history_with_rec,
                actor_user=_make_candidate_user(),
            )
            assert intent_resp.intent == ChatIntent.RECOMMENDATION

            # Non-Candidate actors must never hit Candidate recommendation override
            recruiter = MagicMock(spec=User)
            recruiter.id = uuid.uuid4()
            recruiter.role = UserRole.RECRUITER
            rec_intent, _, _ = await service._classify_intent(
                query,
                history=history_with_rec,
                actor_user=recruiter,
            )
            assert rec_intent.intent == misclassified

    @pytest.mark.parametrize(
        "query, expected_intent",
        [
            ("Tìm việc AI Engineer lương cao", ChatIntent.SEMANTIC),
            ("Lộ trình học Machine Learning Engineer như thế nào?", ChatIntent.KNOWLEDGE),
            ("Các kỹ năng cần thiết cho vị trí Backend Developer (Python) là gì?", ChatIntent.KNOWLEDGE),
            ("Liệt kê tất cả vị trí AI đang mở", ChatIntent.EXHAUSTIVE),
        ],
    )
    @pytest.mark.asyncio
    async def test_standalone_queries_not_hijacked_even_with_recommendation_history(
        self, query, expected_intent
    ):
        history_with_rec = [
            ChatMessage(
                role="assistant",
                content="Các vị trí gợi ý trước đó.",
                recommended_job_ids=[uuid.uuid4()],
            )
        ]
        assert RAGChatService._is_personal_recommendation_query(query, history=history_with_rec) is False

        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(
            return_value=ChatIntentResponse(intent=expected_intent)
        )
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=llm,
            session_factory=_make_session_factory(),
            reranker=_make_reranker(),
        )
        intent_resp, _, _ = await service._classify_intent(
            query,
            history=history_with_rec,
            actor_user=_make_candidate_user(),
        )
        assert intent_resp.intent == expected_intent

    def test_flat_context_formats_clear_per_job_blocks_and_available_subscores_only(self):
        _, be_job_id, ml_job_id, _, _, rag_context = _build_multi_job_recommendation_fixture()
        flat = RAGChatService._build_flat_context_text(rag_context)

        assert "Recommendation #1:" in flat
        assert "  Job Index: 1" in flat
        assert f"  Entity ID: {be_job_id}" in flat
        assert "  Job Title: Backend Developer (Python)" in flat
        assert "  Overall Score: 88.5 (88.5%)" in flat
        assert "  Cosine Similarity: 0.89 (89.0%)" in flat
        assert "  Skill Coverage Score: 0.67 (67.0%)" in flat
        assert "  Preferred Skill Coverage Score: 0.0 (0.0%)" in flat
        assert "  Experience Match Score: 0.95 (95.0%)" in flat

        # Verify ML job (has_education_requirement=False, has_preferred_skills=False, no projects) omits unavailable subscores
        rec2 = flat.split("Recommendation #2:")[1].split("Recommendation #3:")[0]
        assert f"  Entity ID: {ml_job_id}" in rec2
        assert "  Job Title: Machine Learning Engineer" in rec2
        assert "  Summary: Build production NLP, LLM, and RAG pipelines with PyTorch." in rec2
        assert "  Required Skills: Python, PyTorch, NLP" in rec2
        assert "  Preferred Skills: MLOps" in rec2
        assert "  Overall Score: 74.0 (74.0%)" in rec2
        assert "Education Score:" not in rec2
        assert "Preferred Skill Coverage Score:" not in rec2
        assert "Project Score:" not in rec2

    @pytest.mark.parametrize(
        "query, expected_focus_terms, focused_answer_fn",
        [
            (
                "Vị trí nào liên quan nhiều nhất đến AI?",
                ["Machine Learning Engineer", "NLP"],
                lambda be_id, ml_id, cid: (
                    "Vị trí liên quan nhiều nhất đến AI là Machine Learning Engineer (Summary: NLP, LLM, RAG, PyTorch).",
                    [ml_id, cid],
                    ["  Job Title: Machine Learning Engineer", "  Summary: Build production NLP, LLM, and RAG pipelines with PyTorch."],
                    ["Machine Learning Engineer có mô tả NLP, LLM, RAG và PyTorch"],
                ),
            ),
            (
                "Tôi cần bổ sung kỹ năng gì để ứng tuyển vị trí Machine Learning Engineer?",
                ["Machine Learning Engineer", "PyTorch", "NLP"],
                lambda be_id, ml_id, cid: (
                    "Để ứng tuyển Machine Learning Engineer, bạn cần bổ sung PyTorch và NLP.",
                    [ml_id, cid],
                    ["  Job Title: Machine Learning Engineer", "  Missing Skills: PyTorch, NLP"],
                    ["Vị trí Machine Learning Engineer còn thiếu PyTorch, NLP"],
                ),
            ),
            (
                "Tại sao tôi phù hợp với vị trí phù hợp nhất?",
                ["Backend Developer (Python)", "88.5"],
                lambda be_id, ml_id, cid: (
                    "Bạn phù hợp nhất với Backend Developer (Python) đạt 88.5% nhờ kỹ năng Python và FastAPI.",
                    [be_id, cid],
                    ["  Job Title: Backend Developer (Python)", "  Overall Score: 88.5 (88.5%)", "  Matching Skills: Python, FastAPI"],
                    ["Backend Developer (Python) có điểm 88.5 và khớp Python, FastAPI"],
                ),
            ),
            (
                "Tôi còn thiếu kỹ năng gì cho các vị trí trên?",
                ["Docker", "PyTorch"],
                lambda be_id, ml_id, cid: (
                    "Bạn còn thiếu Docker cho Backend Developer (Python), PyTorch và NLP cho Machine Learning Engineer, và React/TypeScript cho Frontend.",
                    [be_id, ml_id, cid],
                    ["  Missing Skills: Docker", "  Missing Skills: PyTorch, NLP"],
                    ["Thiếu Docker và PyTorch, NLP"],
                ),
            ),
            (
                "Chi tiết mức độ phù hợp cho từng vị trí là bao nhiêu?",
                ["88.5%", "74.0%"],
                lambda be_id, ml_id, cid: (
                    "Backend Developer (Python): 88.5% (Cosine 89.0%); Machine Learning Engineer: 74.0% (Cosine 82.0%).",
                    [be_id, ml_id, cid],
                    ["  Overall Score: 88.5 (88.5%)", "  Overall Score: 74.0 (74.0%)"],
                    ["Backend 88.5%, Machine Learning 74.0%"],
                ),
            ),
            (
                "Tôi cần bổ sung kỹ năng gì cho vị trí Backend Developer (Python)?",
                ["Backend Developer (Python)", "Docker"],
                lambda be_id, ml_id, cid: (
                    "Cho vị trí Backend Developer (Python), bạn cần bổ sung Docker.",
                    [be_id, cid],
                    ["  Job Title: Backend Developer (Python)", "  Missing Skills: Docker"],
                    ["Backend Developer (Python) thiếu Docker"],
                ),
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_six_followups_produce_focused_answers_via_llm_and_deterministic_fallback(
        self, query, expected_focus_terms, focused_answer_fn
    ):
        cid, be_id, ml_id, fe_id, jobs_dict, rag_context = _build_multi_job_recommendation_fixture()
        user = _make_candidate_user()
        profile = SimpleNamespace(id=cid, user_id=user.id)
        primary = SimpleNamespace(
            id=uuid.uuid4(),
            candidate_id=cid,
            is_primary=True,
            is_confirmed=True,
            parsed_data={"skills": ["Python", "FastAPI"]},
            confirmed_at=None,
        )
        history = [
            ChatMessage(role="user", content="cv của tôi hiện tại phù hợp với những công việc gì"),
            ChatMessage(
                role="assistant",
                content="Danh sách gợi ý ban đầu.",
                recommended_job_ids=[be_id, ml_id, fe_id],
            ),
        ]

        # 1) Focused LLM synthesis path
        ans_text, cite_ids, quotes, claims = focused_answer_fn(be_id, ml_id, cid)
        captured_prompts: list[str] = []

        async def _mock_llm_success(prompt, response_schema, system_instruction):
            if response_schema is ChatIntentResponse:
                return ChatIntentResponse(intent=ChatIntent.RECOMMENDATION)
            if response_schema is FactCheckResponse:
                return FactCheckResponse(is_faithful=True, contradictions=[])
            captured_prompts.append(prompt)
            return LLMChatResponse(
                answer=ans_text,
                cited_source_ids=cite_ids,
                evidence_quotes=quotes,
                claims=claims,
                suggested_followups=[],
            )

        matching_svc = MagicMock()
        from app.schemas.ai_matching import JobMatchRecommendation
        recs = [
            JobMatchRecommendation(
                job_id=m.entity_id,
                parsed_job=jobs_dict[m.entity_id],
                match_result=m,
            )
            for m in rag_context.match_results
        ]
        matching_svc.recommend_jobs_for_candidate = AsyncMock(return_value=recs)
        resolver = _make_resolver(
            jobs_dict=jobs_dict,
            resumes_dict={cid: ParsedResumeSchema(title="CV Python Backend", skills=["Python", "FastAPI"])},
        )
        llm_ok = MagicMock()
        llm_ok.generate_structured_output = AsyncMock(side_effect=_mock_llm_success)

        service_ok = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=llm_ok,
            session_factory=_make_session_factory(candidate_profile=profile, primary_resume=primary),
            context_resolver=resolver,
            reranker=_make_reranker(),
            matching_service=matching_svc,
        )
        llm_result = await service_ok.chat(query, user, history=history)
        assert "--- RESPONSE FOCUS INSTRUCTIONS (RECOMMENDATION) ---" in captured_prompts[0]
        assert "<history>" in captured_prompts[0] and "<user_input>" in captured_prompts[0]
        for term in expected_focus_terms:
            assert term in llm_result.answer
        assert not llm_result.answer.startswith("Dựa trên CV đã xác nhận và dữ liệu đối sánh trong hệ thống, dưới đây là các công việc phù hợp hiện có:")

        # 2) Deterministic fallback when BOTH synthesis attempts fail grounding
        async def _mock_llm_ungrounded(prompt, response_schema, system_instruction):
            if response_schema is ChatIntentResponse:
                return ChatIntentResponse(intent=ChatIntent.RECOMMENDATION)
            return LLMChatResponse(
                answer="Bad ungrounded response",
                cited_source_ids=[],
                evidence_quotes=[],
                claims=["Unsupported"],
                suggested_followups=[],
            )

        llm_fail = MagicMock()
        llm_fail.generate_structured_output = AsyncMock(side_effect=_mock_llm_ungrounded)
        service_fb = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=llm_fail,
            session_factory=_make_session_factory(candidate_profile=profile, primary_resume=primary),
            context_resolver=resolver,
            reranker=_make_reranker(),
            matching_service=matching_svc,
        )
        fb_result = await service_fb.chat(query, user, history=history)
        for term in expected_focus_terms:
            assert term in fb_result.answer
        assert not fb_result.answer.startswith("Dựa trên CV đã xác nhận và dữ liệu đối sánh trong hệ thống, dưới đây là các công việc phù hợp hiện có:")
        assert fb_result.recommended_job_ids == [be_id, ml_id, fe_id]
        assert fb_result._charge_quota is False
        if query == "Tôi cần bổ sung kỹ năng gì cho vị trí Backend Developer (Python)?":
            assert "Python" in fb_result.answer and "FastAPI" in fb_result.answer
            assert "88.5" in fb_result.answer
            assert "Machine Learning Engineer" not in fb_result.answer
            assert "Frontend Engineer (React)" not in fb_result.answer
            assert [s.entity_id for s in fb_result.sources if s.source_type == "job"] == [be_id]

    def test_deterministic_fallback_absent_named_job_and_no_ai_evidence(self):
        _, be_id, _, fe_id, jobs_dict, _ = _build_multi_job_recommendation_fixture()
        non_ai_ctx = RAGContext(
            jobs=[jobs_dict[be_id], jobs_dict[fe_id]],
            candidates=[],
            match_results=[
                MatchResultSchema(
                    entity_id=be_id,
                    overall_score=88.5,
                    cosine_similarity=0.89,
                    skill_coverage_score=0.67,
                    experience_match_score=0.95,
                    has_required_skills=True,
                    has_experience_requirement=True,
                    matching_skills=["Python", "FastAPI"],
                    skill_gap=["Docker"],
                ),
                MatchResultSchema(
                    entity_id=fe_id,
                    overall_score=35.0,
                    cosine_similarity=0.40,
                    skill_coverage_score=0.0,
                    experience_match_score=0.0,
                    has_required_skills=True,
                    matching_skills=[],
                    skill_gap=["React", "TypeScript"],
                ),
            ],
            sources=[
                ChatSource(
                    source_type="job",
                    entity_id=be_id,
                    title="Backend Developer (Python)",
                    relevance_score=0.885,
                    skills=["Python", "FastAPI", "Docker"],
                ),
                ChatSource(
                    source_type="job",
                    entity_id=fe_id,
                    title="Frontend Engineer (React)",
                    relevance_score=0.35,
                    skills=["React", "TypeScript"],
                ),
            ],
        )

        # Named job NOT in authorized recommendation context
        absent_resp = RAGChatService._build_deterministic_recommendation_response(
            non_ai_ctx,
            message="Tôi cần bổ sung kỹ năng gì cho vị trí DevOps Architect?",
        )
        assert "DevOps Architect" in absent_resp.answer
        assert "không nằm trong danh sách" in absent_resp.answer
        assert "Backend Developer (Python)" in absent_resp.answer
        assert "Frontend Engineer (React)" in absent_resp.answer

        # AI comparison when NO retrieved job mentions AI (note FastAPI must not false-match 'ai')
        no_ai_resp = RAGChatService._build_deterministic_recommendation_response(
            non_ai_ctx,
            message="Vị trí nào liên quan nhiều nhất đến AI?",
        )
        assert "chưa có bằng chứng rõ ràng" in no_ai_resp.answer
        assert "Backend Developer (Python)" in no_ai_resp.answer

    @pytest.mark.asyncio
    async def test_handle_recommendation_intent_preserves_previous_job_past_limit_10(self):
        cid = uuid.uuid4()
        user = _make_candidate_user()
        from app.schemas.ai_matching import JobMatchRecommendation

        top_10 = [
            JobMatchRecommendation(
                job_id=uuid.uuid4(),
                parsed_job=ParsedJobSchema(title=f"Job {i}", required_skills=["Python"]),
                match_result=MatchResultSchema(
                    overall_score=90.0 - i,
                    cosine_similarity=0.8,
                    skill_coverage_score=1.0,
                    experience_match_score=1.0,
                ),
            )
            for i in range(10)
        ]
        prev_rank_11_id = uuid.uuid4()
        rank_11_job = JobMatchRecommendation(
            job_id=prev_rank_11_id,
            parsed_job=ParsedJobSchema(title="Machine Learning Engineer", required_skills=["PyTorch"]),
            match_result=MatchResultSchema(
                overall_score=70.0,
                cosine_similarity=0.75,
                skill_coverage_score=0.5,
                experience_match_score=0.8,
                matching_skills=["Python"],
                skill_gap=["PyTorch"],
            ),
        )

        async def _recommend(candidate_id, limit, session, actor_user):
            return top_10 if limit <= 10 else top_10 + [rank_11_job]

        matching_svc = MagicMock()
        matching_svc.recommend_jobs_for_candidate = AsyncMock(side_effect=_recommend)
        resolver = _make_resolver(
            resumes_dict={cid: ParsedResumeSchema(skills=["Python"])}
        )
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=MagicMock(),
            session_factory=_make_session_factory(),
            context_resolver=resolver,
            reranker=_make_reranker(),
            matching_service=matching_svc,
        )

        ctx = await service._handle_recommendation_intent(
            candidate_id=cid,
            actor_user=user,
            limit=10,
            previous_job_ids=[prev_rank_11_id],
        )
        assert len(ctx.jobs) == 1
        assert ctx.jobs[0].title == "Machine Learning Engineer"
        assert ctx.match_results[0].entity_id == prev_rank_11_id
        assert [c.kwargs["limit"] for c in matching_svc.recommend_jobs_for_candidate.call_args_list] == [10, 100]

    @pytest.mark.asyncio
    async def test_complete_authorized_recommended_job_ids_preserved_and_survives_history_truncation(self):
        cid = uuid.uuid4()
        user = _make_candidate_user()
        profile = SimpleNamespace(id=cid, user_id=user.id)
        primary = SimpleNamespace(
            id=uuid.uuid4(),
            candidate_id=cid,
            is_primary=True,
            is_confirmed=True,
            parsed_data={"skills": ["Python", "FastAPI"]},
            confirmed_at=None,
        )
        from app.schemas.ai_matching import JobMatchRecommendation

        seven_ids = [uuid.uuid4() for _ in range(7)]
        jobs_dict = {
            jid: ParsedJobSchema(
                title=f"Role {i + 1}",
                required_skills=["Python", f"Skill{i + 1}"],
            )
            for i, jid in enumerate(seven_ids)
        }
        recs = [
            JobMatchRecommendation(
                job_id=jid,
                parsed_job=jobs_dict[jid],
                match_result=MatchResultSchema(
                    entity_id=jid,
                    overall_score=90.0 - i,
                    cosine_similarity=0.8123456789,
                    skill_coverage_score=0.5,
                    experience_match_score=0.8,
                    has_required_skills=True,
                    has_experience_requirement=True,
                    matching_skills=["Python"],
                    skill_gap=[f"Skill{i + 1}"],
                ),
            )
            for i, jid in enumerate(seven_ids)
        ]

        matching_svc = MagicMock()
        matching_svc.recommend_jobs_for_candidate = AsyncMock(return_value=recs)
        resolver = _make_resolver(
            jobs_dict=jobs_dict,
            resumes_dict={cid: ParsedResumeSchema(title="CV Full", skills=["Python", "FastAPI"])},
        )

        # LLM cites ONLY the first job in sources, yet all 7 authorized IDs must remain in recommended_job_ids
        async def _mock_llm_partial_cite(prompt, response_schema, system_instruction):
            if response_schema is ChatIntentResponse:
                return ChatIntentResponse(intent=ChatIntent.RECOMMENDATION)
            if response_schema is FactCheckResponse:
                return FactCheckResponse(is_faithful=True, contradictions=[])
            return LLMChatResponse(
                answer="Gợi ý gồm Role 1 đến Role 7 phù hợp với CV.",
                cited_source_ids=[seven_ids[0], cid],
                evidence_quotes=["  Job Title: Role 1", "  Overall Score: 90.0 (90.0%)"],
                claims=["Role 1 đạt 90.0%"],
                suggested_followups=[],
            )

        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(side_effect=_mock_llm_partial_cite)
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=llm,
            session_factory=_make_session_factory(candidate_profile=profile, primary_resume=primary),
            context_resolver=resolver,
            reranker=_make_reranker(),
            matching_service=matching_svc,
        )

        initial_resp = await service.chat(
            "cv của tôi hiện tại phù hợp với những công việc gì có trong hệ thống",
            user,
        )
        assert initial_resp.recommended_job_ids == seven_ids
        assert [s.entity_id for s in initial_resp.sources] == [seven_ids[0], cid]

        # Even if visible 10-message history no longer contains the initial recommendation message,
        # passing recommended_job_ids routes the follow-up cleanly and preserves all 7 jobs in fallback!
        truncated_history = [
            ChatMessage(role="user", content=f"msg {i}") for i in range(10)
        ]
        async def _mock_llm_fail(prompt, response_schema, system_instruction):
            if response_schema is ChatIntentResponse:
                return ChatIntentResponse(intent=ChatIntent.SEMANTIC)  # test override via session recommended_job_ids
            return LLMChatResponse(
                answer="Ungrounded",
                cited_source_ids=[],
                evidence_quotes=[],
                claims=["Unsupported"],
                suggested_followups=[],
            )

        llm_fail = MagicMock()
        llm_fail.generate_structured_output = AsyncMock(side_effect=_mock_llm_fail)
        service_fb = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=llm_fail,
            session_factory=_make_session_factory(candidate_profile=profile, primary_resume=primary),
            context_resolver=resolver,
            reranker=_make_reranker(),
            matching_service=matching_svc,
        )
        followup_resp = await service_fb.chat(
            "Tôi còn thiếu kỹ năng gì cho các vị trí trên?",
            user,
            history=truncated_history,
            recommended_job_ids=seven_ids,
        )
        for i in range(1, 8):
            assert f"Role {i}" in followup_resp.answer
            assert f"Skill{i}" in followup_resp.answer
        assert followup_resp.recommended_job_ids == seven_ids

    def test_ai_comparison_prefers_actual_ai_relevance_over_highest_overall_score(self):
        high_score_backend_id = uuid.uuid4()
        lower_score_ai_id = uuid.uuid4()
        ctx = RAGContext(
            jobs=[
                ParsedJobSchema(
                    title="Backend Developer (Python)",
                    summary="Xây dựng API microservices và hỗ trợ tích hợp hệ thống AI nội bộ.",
                    required_skills=["Python", "FastAPI", "PostgreSQL"],
                    preferred_skills=["Docker"],
                ),
                ParsedJobSchema(
                    title="Machine Learning Engineer",
                    summary="Phát triển mô hình NLP, LLM và RAG triển khai production.",
                    required_skills=["Python", "PyTorch", "TensorFlow", "NLP"],
                    preferred_skills=["MLOps"],
                ),
            ],
            candidates=[],
            match_results=[
                MatchResultSchema(
                    entity_id=high_score_backend_id,
                    overall_score=94.0,
                    cosine_similarity=0.91,
                    skill_coverage_score=1.0,
                    experience_match_score=1.0,
                    has_required_skills=True,
                ),
                MatchResultSchema(
                    entity_id=lower_score_ai_id,
                    overall_score=62.0,
                    cosine_similarity=0.72,
                    skill_coverage_score=0.5,
                    experience_match_score=0.7,
                    has_required_skills=True,
                ),
            ],
            sources=[
                ChatSource(
                    source_type="job",
                    entity_id=high_score_backend_id,
                    title="Backend Developer (Python)",
                    relevance_score=0.94,
                    skills=["Python", "FastAPI"],
                ),
                ChatSource(
                    source_type="job",
                    entity_id=lower_score_ai_id,
                    title="Machine Learning Engineer",
                    relevance_score=0.62,
                    skills=["Python", "PyTorch", "TensorFlow", "NLP"],
                ),
            ],
        )

        resp = RAGChatService._build_deterministic_recommendation_response(
            ctx,
            message="Vị trí nào liên quan nhiều nhất đến AI?",
        )
        assert "Machine Learning Engineer" in resp.answer
        assert [s.entity_id for s in resp.sources if s.source_type == "job"] == [lower_score_ai_id]
        assert resp.recommended_job_ids == [high_score_backend_id, lower_score_ai_id]

    @pytest.mark.asyncio
    async def test_cv_summary_followup_summarizes_cv_without_single_job_anchoring(self):
        cid = uuid.uuid4()
        user = _make_candidate_user()
        job_a = uuid.uuid4()
        job_b = uuid.uuid4()
        profile = SimpleNamespace(id=cid, user_id=user.id)
        primary = SimpleNamespace(
            id=uuid.uuid4(),
            candidate_id=cid,
            is_primary=True,
            is_confirmed=True,
            parsed_data={
                "title": "Senior Python Engineer",
                "skills": ["Python", "FastAPI", "PostgreSQL"],
                "total_years_experience": 4.0,
            },
            confirmed_at=None,
        )
        matching_svc = MagicMock()
        # Even if previous jobs yield 0 recs or a narrow set, CV summary summarizes verified CV cleanly
        matching_svc.recommend_jobs_for_candidate = AsyncMock(return_value=[])
        resolver = _make_resolver(
            jobs_dict={
                job_a: ParsedJobSchema(title="Job A"),
                job_b: ParsedJobSchema(title="Job B"),
            },
            resumes_dict={
                cid: ParsedResumeSchema(
                    title="Senior Python Engineer",
                    summary="4 năm phát triển hệ thống backend Python hiệu năng cao.",
                    skills=["Python", "FastAPI", "PostgreSQL"],
                    total_years_experience=4.0,
                )
            },
        )

        async def _mock_llm_fail(prompt, response_schema, system_instruction):
            if response_schema is ChatIntentResponse:
                return ChatIntentResponse(intent=ChatIntent.SEMANTIC)
            return LLMChatResponse(
                answer="Bad",
                cited_source_ids=[],
                evidence_quotes=[],
                claims=["Bad"],
                suggested_followups=[],
            )

        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(side_effect=_mock_llm_fail)
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=llm,
            session_factory=_make_session_factory(candidate_profile=profile, primary_resume=primary),
            context_resolver=resolver,
            reranker=_make_reranker(),
            matching_service=matching_svc,
        )

        resp = await service.chat(
            "Hãy tóm tắt hồ sơ của tôi",
            user,
            history=[
                ChatMessage(
                    role="assistant",
                    content="Gợi ý ban đầu",
                    recommended_job_ids=[job_a, job_b],
                )
            ],
        )
        assert "Senior Python Engineer" in resp.answer
        assert "Python, FastAPI, PostgreSQL" in resp.answer
        assert "4.0 năm" in resp.answer
        assert "Job A" not in resp.answer
        assert "Job B" not in resp.answer
        assert [s.source_type for s in resp.sources] == ["resume"]
        assert resp.recommended_job_ids == [job_a, job_b]

    def test_subscore_formatting_bounds_floating_point_precision(self):
        job_id = uuid.uuid4()
        ctx = RAGContext(
            jobs=[ParsedJobSchema(title="AI Engineer", required_skills=["Python"])],
            candidates=[],
            match_results=[
                MatchResultSchema(
                    entity_id=job_id,
                    overall_score=74.33333333333333,
                    cosine_similarity=0.8123456789012345,
                    skill_coverage_score=0.6666666666666666,
                    experience_match_score=0.5,
                    has_required_skills=True,
                    has_experience_requirement=True,
                )
            ],
            sources=[
                ChatSource(
                    source_type="job",
                    entity_id=job_id,
                    title="AI Engineer",
                    relevance_score=0.743,
                    skills=["Python"],
                )
            ],
        )
        flat = RAGChatService._build_flat_context_text(ctx)
        assert "74.33 (74.3%)" in flat
        assert "0.81 (81.2%)" in flat
        assert "0.67 (66.7%)" in flat
        assert "74.3333" not in flat
        assert "0.81234" not in flat
        assert "0.66666" not in flat

        fb = RAGChatService._build_deterministic_recommendation_response(
            ctx,
            message="Chi tiết mức độ phù hợp cho từng vị trí là bao nhiêu?",
        )
        assert "74.33 (74.3%)" in fb.answer
        assert "0.81 (81.2%)" in fb.answer
        assert "0.67 (66.7%)" in fb.answer
        assert "74.3333" not in fb.answer
        assert "0.81234" not in fb.answer


# ==============================================================================
# TEST GROUP H: Session recommended_job_ids bounds & deduplication
# ==============================================================================


class TestGroupHSessionJobIdBounds:
    def test_chat_request_accepts_exact_ten_recommended_job_ids(self):
        from app.schemas.ai_chat import MAX_RECOMMENDATION_SESSION_IDS, ChatRequest

        ten_ids = [uuid.uuid4() for _ in range(MAX_RECOMMENDATION_SESSION_IDS)]
        req = ChatRequest(message="Kiểm tra giới hạn", recommended_job_ids=ten_ids)
        assert req.recommended_job_ids == ten_ids

    def test_chat_request_rejects_more_than_ten_recommended_job_ids(self):
        from pydantic import ValidationError
        from app.schemas.ai_chat import MAX_RECOMMENDATION_SESSION_IDS, ChatRequest

        eleven_ids = [uuid.uuid4() for _ in range(MAX_RECOMMENDATION_SESSION_IDS + 1)]
        with pytest.raises(ValidationError):
            ChatRequest(message="Quá giới hạn", recommended_job_ids=eleven_ids)

    def test_chat_request_deduplicates_recommended_job_ids_preserving_order(self):
        from app.schemas.ai_chat import ChatRequest

        id_a, id_b, id_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        req = ChatRequest(
            message="Deduplicate check",
            recommended_job_ids=[id_b, id_a, id_b, id_c, id_a],
        )
        assert req.recommended_job_ids == [id_b, id_a, id_c]

    def test_merge_job_id_lists_enforces_max_cap_and_order(self):
        from app.services.rag_chat_service import _merge_job_id_lists

        first_eight = [uuid.uuid4() for _ in range(8)]
        next_five = [first_eight[2], *[uuid.uuid4() for _ in range(4)]]
        merged = _merge_job_id_lists(first_eight, next_five)
        assert len(merged) == 10
        assert merged[:8] == first_eight
        assert merged[8:] == next_five[1:3]


# ==============================================================================
# TEST GROUP I: True 8-exchange chained regression (Turn 0 + 7 follow-ups)
# ==============================================================================


class TestGroupITrueEightExchangeChainedRegression:
    @pytest.mark.asyncio
    async def test_eight_exchange_chained_candidate_session_preserves_seven_ids_and_routes_accurately(self):
        from app.schemas.ai_matching import JobMatchRecommendation

        cid = uuid.uuid4()
        user = _make_candidate_user()
        profile = SimpleNamespace(id=cid, user_id=user.id)
        primary = SimpleNamespace(
            id=uuid.uuid4(),
            candidate_id=cid,
            is_primary=True,
            is_confirmed=True,
            parsed_data={
                "title": "Senior Python Engineer",
                "summary": "4 năm phát triển backend Python và FastAPI.",
                "skills": ["Python", "FastAPI", "PostgreSQL", "SQL", "Docker"],
                "total_years_experience": 4.0,
            },
            confirmed_at=None,
        )

        job_test = uuid.uuid4()
        job_ml = uuid.uuid4()
        job_backend = uuid.uuid4()
        job_data = uuid.uuid4()
        job_devops = uuid.uuid4()
        job_fullstack = uuid.uuid4()
        job_qa = uuid.uuid4()
        seven_ids = [job_test, job_ml, job_backend, job_data, job_devops, job_fullstack, job_qa]

        jobs_dict = {
            job_test: ParsedJobSchema(
                title="Test Job",
                summary="Phát triển dịch vụ nội bộ hiệu năng cao với Python và Docker.",
                required_skills=["Python", "SQL", "Docker", "Redis"],
            ),
            job_ml: ParsedJobSchema(
                title="Machine Learning Engineer",
                summary="Phát triển mô hình AI, NLP, LLM, PyTorch và hệ thống RAG production.",
                required_skills=["Python", "PyTorch", "TensorFlow", "NLP"],
            ),
            job_backend: ParsedJobSchema(
                title="Backend Developer (Python)",
                summary="Xây dựng REST API với FastAPI, PostgreSQL và triển khai microservices.",
                required_skills=["Python", "FastAPI", "PostgreSQL", "Kubernetes"],
            ),
            job_data: ParsedJobSchema(
                title="Data Engineer",
                summary="Xây dựng pipeline dữ liệu ETL quy mô lớn.",
                required_skills=["Python", "Airflow", "Spark"],
            ),
            job_devops: ParsedJobSchema(
                title="DevOps Engineer",
                summary="Vận hành hạ tầng cloud và CI/CD.",
                required_skills=["Docker", "Terraform"],
            ),
            job_fullstack: ParsedJobSchema(
                title="Fullstack Developer",
                summary="Phát triển ứng dụng web end-to-end.",
                required_skills=["Python", "React"],
            ),
            job_qa: ParsedJobSchema(
                title="QA Automation Engineer",
                summary="Tự động hóa kiểm thử hệ thống.",
                required_skills=["Python", "Pytest", "Selenium"],
            ),
        }

        recs = [
            JobMatchRecommendation(
                job_id=job_test,
                parsed_job=jobs_dict[job_test],
                match_result=MatchResultSchema(
                    entity_id=job_test,
                    overall_score=91.5,
                    cosine_similarity=0.9,
                    skill_coverage_score=0.75,
                    experience_match_score=1.0,
                    has_required_skills=True,
                    has_experience_requirement=True,
                    matching_skills=["Python", "SQL", "Docker"],
                    skill_gap=["Redis"],
                    match_reasons=["Phù hợp Python, SQL, Docker"],
                ),
            ),
            JobMatchRecommendation(
                job_id=job_ml,
                parsed_job=jobs_dict[job_ml],
                match_result=MatchResultSchema(
                    entity_id=job_ml,
                    overall_score=74.3333333333,
                    cosine_similarity=0.81234567,
                    skill_coverage_score=0.66666667,
                    experience_match_score=0.7,
                    has_required_skills=True,
                    has_experience_requirement=True,
                    matching_skills=["Python"],
                    skill_gap=["PyTorch", "TensorFlow", "NLP"],
                    match_reasons=["Có nền tảng Python"],
                ),
            ),
            JobMatchRecommendation(
                job_id=job_backend,
                parsed_job=jobs_dict[job_backend],
                match_result=MatchResultSchema(
                    entity_id=job_backend,
                    overall_score=86.25,
                    cosine_similarity=0.88,
                    skill_coverage_score=0.75,
                    experience_match_score=0.95,
                    has_required_skills=True,
                    has_experience_requirement=True,
                    matching_skills=["Python", "FastAPI", "PostgreSQL"],
                    skill_gap=["Kubernetes"],
                    match_reasons=["Phù hợp Python, FastAPI, PostgreSQL"],
                ),
            ),
            JobMatchRecommendation(
                job_id=job_data,
                parsed_job=jobs_dict[job_data],
                match_result=MatchResultSchema(
                    entity_id=job_data,
                    overall_score=79.5,
                    cosine_similarity=0.79,
                    skill_coverage_score=0.5,
                    experience_match_score=0.8,
                    has_required_skills=True,
                    has_experience_requirement=True,
                    matching_skills=["Python"],
                    skill_gap=["Airflow", "Spark"],
                ),
            ),
            JobMatchRecommendation(
                job_id=job_devops,
                parsed_job=jobs_dict[job_devops],
                match_result=MatchResultSchema(
                    entity_id=job_devops,
                    overall_score=72.0,
                    cosine_similarity=0.71,
                    skill_coverage_score=0.5,
                    experience_match_score=0.7,
                    has_required_skills=True,
                    has_experience_requirement=True,
                    matching_skills=["Docker"],
                    skill_gap=["Terraform"],
                ),
            ),
            JobMatchRecommendation(
                job_id=job_fullstack,
                parsed_job=jobs_dict[job_fullstack],
                match_result=MatchResultSchema(
                    entity_id=job_fullstack,
                    overall_score=69.5,
                    cosine_similarity=0.69,
                    skill_coverage_score=0.5,
                    experience_match_score=0.65,
                    has_required_skills=True,
                    has_experience_requirement=True,
                    matching_skills=["Python"],
                    skill_gap=["React"],
                ),
            ),
            JobMatchRecommendation(
                job_id=job_qa,
                parsed_job=jobs_dict[job_qa],
                match_result=MatchResultSchema(
                    entity_id=job_qa,
                    overall_score=65.0,
                    cosine_similarity=0.64,
                    skill_coverage_score=0.33,
                    experience_match_score=0.6,
                    has_required_skills=True,
                    has_experience_requirement=True,
                    matching_skills=["Python"],
                    skill_gap=["Selenium"],
                ),
            ),
        ]

        matching_svc = MagicMock()
        matching_svc.recommend_jobs_for_candidate = AsyncMock(return_value=recs)

        resolver = _make_resolver(
            jobs_dict=jobs_dict,
            resumes_dict={
                cid: ParsedResumeSchema(
                    title="Senior Python Engineer",
                    summary="4 năm phát triển backend Python và FastAPI.",
                    skills=["Python", "FastAPI", "PostgreSQL", "SQL", "Docker"],
                    total_years_experience=4.0,
                )
            },
        )

        llm_synthesis_prompts: list[str] = []
        turn_counter = {"idx": 0}

        async def _mock_llm(prompt, response_schema, system_instruction):
            if response_schema is ChatIntentResponse:
                return ChatIntentResponse(intent=ChatIntent.RECOMMENDATION)
            if response_schema is FactCheckResponse:
                return FactCheckResponse(
                    is_faithful=True,
                    unsupported_claims=[],
                    reason="Grounded in context",
                )
            llm_synthesis_prompts.append(prompt)
            # Turn 0 simulates LLM citing only 3 of the 7 retrieved jobs cleanly
            if turn_counter["idx"] == 0:
                return LLMChatResponse(
                    answer=(
                        "Các vị trí phù hợp nổi bật gồm Test Job, Machine Learning Engineer "
                        "và Backend Developer (Python)."
                    ),
                    cited_source_ids=[str(job_test), str(job_ml), str(job_backend)],
                    evidence_quotes=[
                        "Test Job",
                        "Machine Learning Engineer",
                        "Backend Developer (Python)",
                    ],
                    claims=[
                        "Test Job phù hợp với hồ sơ.",
                        "Machine Learning Engineer phù hợp với nền tảng Python.",
                        "Backend Developer (Python) phù hợp với FastAPI và PostgreSQL.",
                    ],
                    suggested_followups=["Vị trí nào liên quan nhiều nhất đến AI?"],
                )
            # Subsequent turns return empty claims/citations so deterministic synthesis handles verified logic
            return LLMChatResponse(
                answer="Không đủ thông tin.",
                cited_source_ids=[],
                evidence_quotes=[],
                claims=[],
                suggested_followups=[],
            )

        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(side_effect=_mock_llm)
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=MagicMock(spec=BaseVectorRepository),
            llm_provider=llm,
            session_factory=_make_session_factory(candidate_profile=profile, primary_resume=primary),
            context_resolver=resolver,
            reranker=_make_reranker(),
            matching_service=matching_svc,
        )

        transcript: list[ChatMessage] = []
        session_ids: list[uuid.UUID] = []

        # Exchange 1 (Turn 0): Initial recommendation lists 7 jobs, LLM cites only 3
        turn0_query = "cv của tôi hiện tại phù hợp với những công việc gì có trong hệ thống"
        resp0 = await service.chat(turn0_query, user, history=transcript[-10:], recommended_job_ids=session_ids)
        assert [s.entity_id for s in resp0.sources] == [job_test, job_ml, job_backend]
        assert resp0.recommended_job_ids == seven_ids
        transcript.extend([
            ChatMessage(role="user", content=turn0_query),
            ChatMessage(role="assistant", content=resp0.answer, recommended_job_ids=resp0.recommended_job_ids),
        ])
        session_ids = list(resp0.recommended_job_ids)
        turn_counter["idx"] = 1

        # Exchange 2 (Follow-up 1): AI-related question picks ML Engineer over higher-scoring Test Job
        q1 = "Vị trí nào liên quan nhiều nhất đến AI?"
        resp1 = await service.chat(q1, user, history=transcript[-10:], recommended_job_ids=session_ids)
        assert "Machine Learning Engineer" in resp1.answer
        assert [s.entity_id for s in resp1.sources if s.source_type == "job"] == [job_ml]
        assert resp1.recommended_job_ids == seven_ids
        transcript.extend([
            ChatMessage(role="user", content=q1),
            ChatMessage(role="assistant", content=resp1.answer, recommended_job_ids=resp1.recommended_job_ids),
        ])
        session_ids = list(resp1.recommended_job_ids)
        turn_counter["idx"] = 2

        # Exchange 3 (Follow-up 2): Specific ML Engineer skill gap
        q2 = "Tôi cần bổ sung kỹ năng gì để ứng tuyển vị trí Machine Learning Engineer?"
        resp2 = await service.chat(q2, user, history=transcript[-10:], recommended_job_ids=session_ids)
        assert "Machine Learning Engineer" in resp2.answer
        assert "PyTorch" in resp2.answer
        assert "TensorFlow" in resp2.answer
        assert "NLP" in resp2.answer
        assert "Test Job" not in resp2.answer
        assert resp2.recommended_job_ids == seven_ids
        transcript.extend([
            ChatMessage(role="user", content=q2),
            ChatMessage(role="assistant", content=resp2.answer, recommended_job_ids=resp2.recommended_job_ids),
        ])
        session_ids = list(resp2.recommended_job_ids)
        turn_counter["idx"] = 3

        # Exchange 4 (Follow-up 3): Why top match (Test Job)
        q3 = "Tại sao tôi phù hợp với vị trí phù hợp nhất?"
        resp3 = await service.chat(q3, user, history=transcript[-10:], recommended_job_ids=session_ids)
        assert "Test Job" in resp3.answer
        assert "Python" in resp3.answer
        assert resp3.recommended_job_ids == seven_ids
        transcript.extend([
            ChatMessage(role="user", content=q3),
            ChatMessage(role="assistant", content=resp3.answer, recommended_job_ids=resp3.recommended_job_ids),
        ])
        session_ids = list(resp3.recommended_job_ids)
        turn_counter["idx"] = 4

        # Exchange 5 (Follow-up 4): Intermediate CV summary without job anchoring, preserves 7 IDs
        q4 = "Hãy tóm tắt hồ sơ của tôi"
        resp4 = await service.chat(q4, user, history=transcript[-10:], recommended_job_ids=session_ids)
        assert "Senior Python Engineer" in resp4.answer
        assert "4.0 năm" in resp4.answer
        assert "Test Job" not in resp4.answer
        assert "Machine Learning Engineer" not in resp4.answer
        assert [s.source_type for s in resp4.sources] == ["resume"]
        assert resp4.recommended_job_ids == seven_ids
        transcript.extend([
            ChatMessage(role="user", content=q4),
            ChatMessage(role="assistant", content=resp4.answer, recommended_job_ids=resp4.recommended_job_ids),
        ])
        session_ids = list(resp4.recommended_job_ids)
        turn_counter["idx"] = 5

        # Exchange 6 (Follow-up 5): Sliding window is now full at 10 messages (Turn-0 leaves next)
        window_turn6 = transcript[-10:]
        assert len(window_turn6) == 10
        q5 = "Tôi còn thiếu kỹ năng gì cho các vị trí trên?"
        resp5 = await service.chat(q5, user, history=window_turn6, recommended_job_ids=session_ids)
        for expected_title in (
            "Test Job",
            "Machine Learning Engineer",
            "Backend Developer (Python)",
            "Data Engineer",
            "DevOps Engineer",
            "Fullstack Developer",
            "QA Automation Engineer",
        ):
            assert expected_title in resp5.answer
        for expected_gap in ("Redis", "PyTorch", "Kubernetes", "Airflow", "Terraform", "React", "Selenium"):
            assert expected_gap in resp5.answer
        assert resp5.recommended_job_ids == seven_ids
        transcript.extend([
            ChatMessage(role="user", content=q5),
            ChatMessage(role="assistant", content=resp5.answer, recommended_job_ids=resp5.recommended_job_ids),
        ])
        session_ids = list(resp5.recommended_job_ids)
        turn_counter["idx"] = 6

        # Exchange 7 (Follow-up 6): Match details for ALL 7 jobs with bounded float precision
        window_turn7 = transcript[-10:]
        assert len(window_turn7) == 10
        assert all(m.content != turn0_query for m in window_turn7)
        q6 = "Chi tiết mức độ phù hợp cho từng vị trí là bao nhiêu?"
        resp6 = await service.chat(q6, user, history=window_turn7, recommended_job_ids=session_ids)
        for expected_title in (
            "Test Job",
            "Machine Learning Engineer",
            "Backend Developer (Python)",
            "Data Engineer",
            "DevOps Engineer",
            "Fullstack Developer",
            "QA Automation Engineer",
        ):
            assert expected_title in resp6.answer
        assert "74.33" in resp6.answer
        assert "74.3333" not in resp6.answer
        assert "0.81234" not in resp6.answer
        assert resp6.recommended_job_ids == seven_ids
        transcript.extend([
            ChatMessage(role="user", content=q6),
            ChatMessage(role="assistant", content=resp6.answer, recommended_job_ids=resp6.recommended_job_ids),
        ])
        session_ids = list(resp6.recommended_job_ids)
        turn_counter["idx"] = 7

        # Exchange 8 (Follow-up 7): Specific role Backend Developer (Python) after Turn-0 eviction
        window_turn8 = transcript[-10:]
        assert len(window_turn8) == 10
        assert all(m.content != turn0_query for m in window_turn8)
        q7 = "Tôi cần bổ sung kỹ năng gì cho vị trí Backend Developer (Python)?"
        resp7 = await service.chat(q7, user, history=window_turn8, recommended_job_ids=session_ids)
        assert "Backend Developer (Python)" in resp7.answer
        assert "Kubernetes" in resp7.answer
        assert "FastAPI" in resp7.answer
        assert "QA Automation Engineer" not in resp7.answer
        assert resp7.recommended_job_ids == seven_ids


# ==============================================================================
# TEST GROUP J: Real ContextResolver SQL Authorization on Client job_ids
# ==============================================================================


def _eval_sql_where(expr, row) -> bool:
    """Evaluate compiled SQLAlchemy boolean expression clauses against an ORM/stub row."""
    from sqlalchemy.sql.elements import (
        BinaryExpression,
        BindParameter,
        BooleanClauseList,
        False_,
        Null,
        True_,
    )
    from sqlalchemy.sql import operators

    if expr is None:
        return True
    if isinstance(expr, BooleanClauseList):
        if expr.operator is operators.and_:
            return all(_eval_sql_where(clause, row) for clause in expr.clauses)
        if expr.operator is operators.or_:
            return any(_eval_sql_where(clause, row) for clause in expr.clauses)
    if isinstance(expr, BinaryExpression):
        col_name = getattr(expr.left, "key", None)
        row_val = getattr(row, col_name)
        right = expr.right
        if isinstance(right, Null):
            right_val = None
        elif isinstance(right, True_):
            right_val = True
        elif isinstance(right, False_):
            right_val = False
        elif isinstance(right, BindParameter):
            right_val = right.value
        else:
            right_val = getattr(right, "value", right)
        if expr.operator is operators.is_not:
            return row_val is not right_val
        if expr.operator is operators.is_:
            return row_val is right_val
        if expr.operator is operators.eq:
            return row_val == right_val
        if expr.operator is operators.ne:
            return row_val != right_val
        if expr.operator is operators.gt:
            return row_val is not None and row_val > right_val
        if expr.operator is operators.lt:
            return row_val is not None and row_val < right_val
        if expr.operator is operators.ge:
            return row_val is not None and row_val >= right_val
        if expr.operator is operators.le:
            return row_val is not None and row_val <= right_val
        if expr.operator is operators.in_op:
            return row_val in set(right_val or [])
    raise AssertionError(f"Unsupported SQLAlchemy clause in authorization test: {expr!r}")


def _make_job_orm_row(
    *,
    job_id: uuid.UUID,
    company_id: uuid.UUID,
    title: str,
    status: JobStatus,
    expires_at,
    is_deleted: bool,
    required_skills: list[str],
):
    from app.domain.enums import JobType, WorkplaceType
    from app.models import Job

    job = MagicMock(spec=Job)
    job.id = job_id
    job.company_id = company_id
    job.title = title
    job.description = f"JD cho {title}"
    job.status = status
    job.expires_at = expires_at
    job.is_deleted = is_deleted
    job.location = "Ha Noi"
    job.city = "Ha Noi"
    job.job_type = JobType.FULL_TIME
    job.workplace_type = WorkplaceType.ON_SITE
    job.skills = []
    job.required_skills = [SimpleNamespace(name=s) for s in required_skills]
    job.preferred_skills = []
    job.minimum_years_experience = 2
    job.education_level = None
    return job


def _make_real_auth_session_factory(
    *,
    jobs_rows: list,
    candidate_profile,
    primary_resume,
    recruiter_companies: dict[uuid.UUID, uuid.UUID] | None = None,
):
    session = MagicMock()

    async def _execute(stmt):
        compiled = str(stmt).lower()
        res = MagicMock()
        if "from jobs" in compiled:
            matched_jobs = [row for row in jobs_rows if _eval_sql_where(stmt.whereclause, row)]
            res.scalars.return_value.all.return_value = matched_jobs
            res.scalars.return_value.unique.return_value.all.return_value = matched_jobs
            res.scalar_one_or_none.return_value = matched_jobs[0] if matched_jobs else None
        elif "from company_memberships" in compiled or "from recruiter_profiles" in compiled:
            company_id = next(iter((recruiter_companies or {}).values()), None)
            membership = SimpleNamespace(company_id=company_id) if company_id else None
            res.scalar_one_or_none.return_value = membership
            res.scalars.return_value.first.return_value = membership
            res.scalars.return_value.all.return_value = [membership] if membership else []
            res.scalars.return_value.unique.return_value.all.return_value = [membership] if membership else []
        elif "from candidate_profiles" in compiled:
            res.scalar_one_or_none.return_value = candidate_profile
            res.scalars.return_value.first.return_value = candidate_profile
            res.scalars.return_value.all.return_value = [candidate_profile] if candidate_profile else []
        elif "from resumes" in compiled:
            if "from resumes" in compiled and primary_resume is not None:
                res.scalar_one_or_none.return_value = primary_resume
                res.scalars.return_value.first.return_value = primary_resume
                res.scalars.return_value.all.return_value = [primary_resume]
            else:
                res.scalar_one_or_none.return_value = None
                res.scalars.return_value.first.return_value = None
                res.scalars.return_value.all.return_value = []
        else:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.first.return_value = None
            res.scalars.return_value.all.return_value = []
        return res

    session.execute = AsyncMock(side_effect=_execute)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return session, factory


class TestGroupJClientJobIdAuthorization:
    @pytest.mark.asyncio
    async def test_client_recommended_job_ids_revalidated_against_real_context_resolver_sql(self):
        from datetime import datetime, timedelta, timezone
        from app.services.context_resolver import ContextResolver

        now = datetime.now(timezone.utc)
        cid = uuid.uuid4()
        user = _make_candidate_user()
        company_a = uuid.uuid4()
        company_b = uuid.uuid4()

        valid_job_id = uuid.uuid4()
        unrelated_valid_job_id = uuid.uuid4()
        draft_job_id = uuid.uuid4()
        expired_job_id = uuid.uuid4()
        deleted_job_id = uuid.uuid4()
        closed_job_id = uuid.uuid4()

        jobs_rows = [
            _make_job_orm_row(
                job_id=valid_job_id,
                company_id=company_a,
                title="Authorized Backend Python",
                status=JobStatus.PUBLISHED,
                expires_at=now + timedelta(days=10),
                is_deleted=False,
                required_skills=["Python", "FastAPI", "Redis"],
            ),
            _make_job_orm_row(
                job_id=unrelated_valid_job_id,
                company_id=company_b,
                title="Unrelated Published Job",
                status=JobStatus.PUBLISHED,
                expires_at=now + timedelta(days=10),
                is_deleted=False,
                required_skills=["Go"],
            ),
            _make_job_orm_row(
                job_id=draft_job_id,
                company_id=company_b,
                title="Secret Draft Job",
                status=JobStatus.DRAFT,
                expires_at=now + timedelta(days=10),
                is_deleted=False,
                required_skills=["Rust"],
            ),
            _make_job_orm_row(
                job_id=expired_job_id,
                company_id=company_a,
                title="Expired Job",
                status=JobStatus.PUBLISHED,
                expires_at=now - timedelta(days=1),
                is_deleted=False,
                required_skills=["Java"],
            ),
            _make_job_orm_row(
                job_id=deleted_job_id,
                company_id=company_a,
                title="Deleted Job",
                status=JobStatus.PUBLISHED,
                expires_at=now + timedelta(days=10),
                is_deleted=True,
                required_skills=["C++"],
            ),
            _make_job_orm_row(
                job_id=closed_job_id,
                company_id=company_b,
                title="Closed Job",
                status=JobStatus.CLOSED,
                expires_at=now + timedelta(days=10),
                is_deleted=False,
                required_skills=["Ruby"],
            ),
        ]

        profile = SimpleNamespace(id=cid, user_id=user.id)
        primary = SimpleNamespace(
            id=uuid.uuid4(),
            candidate_id=cid,
            is_primary=True,
            is_confirmed=True,
            is_deleted=False,
            parsed_data={
                "title": "Senior Python Engineer",
                "summary": "4 năm phát triển backend Python.",
                "skills": ["Python", "FastAPI"],
                "total_years_experience": 4.0,
            },
            confirmed_at=None,
        )
        session, session_factory = _make_real_auth_session_factory(
            jobs_rows=jobs_rows,
            candidate_profile=profile,
            primary_resume=primary,
            recruiter_companies={user.id: company_a},
        )
        real_resolver = ContextResolver(session)

        # Verify direct Recruiter cross-company isolation on real ContextResolver.resolve_jobs
        recruiter_a = MagicMock(spec=User)
        recruiter_a.id = uuid.uuid4()
        recruiter_a.role = UserRole.RECRUITER
        recruiter_resolved = await real_resolver.resolve_jobs(
            [valid_job_id, unrelated_valid_job_id, draft_job_id],
            recruiter_a,
        )
        assert valid_job_id in recruiter_resolved
        assert unrelated_valid_job_id not in recruiter_resolved
        assert draft_job_id not in recruiter_resolved

        # Vector repository returns ALL jobs (simulating stale Qdrant index), while real ContextResolver
        # inside AIMatchingService enforces SQL eligibility (published, unexpired, non-deleted).
        vector_repo = MagicMock(spec=BaseVectorRepository)
        vector_repo.retrieve_vector = AsyncMock(
            return_value={"id": cid, "vector": [0.5, 0.5, 0.5], "payload": {"skills": ["Python"]}}
        )
        vector_repo.search_similar = AsyncMock(
            return_value=[{"id": row.id, "score": 0.9, "payload": {"job_id": str(row.id)}} for row in jobs_rows]
        )
        matching_svc = AIMatchingService(
            embedding_service=_make_embedding_service(),
            vector_repository=vector_repo,
            matching_engine=MatchingEngine(),
            resume_parser=MagicMock(spec=ResumeParser),
            job_parser=MagicMock(spec=JobParser),
            context_resolver=real_resolver,
        )

        async def _mock_llm(prompt, response_schema, system_instruction):
            if response_schema is ChatIntentResponse:
                return ChatIntentResponse(intent=ChatIntent.RECOMMENDATION)
            return LLMChatResponse(
                answer="Không đủ thông tin.",
                cited_source_ids=[],
                evidence_quotes=[],
                claims=[],
                suggested_followups=[],
            )

        llm = MagicMock()
        llm.generate_structured_output = AsyncMock(side_effect=_mock_llm)
        service = RAGChatService(
            embedding_service=_make_embedding_service(),
            vector_repository=vector_repo,
            llm_provider=llm,
            session_factory=session_factory,
            context_resolver=real_resolver,
            reranker=_make_reranker(),
            matching_service=matching_svc,
        )

        # 1. Mixed client-supplied IDs: only valid published unexpired job is restored
        mixed_ids = [valid_job_id, draft_job_id, expired_job_id, deleted_job_id, closed_job_id]
        resp_mixed = await service.chat(
            "Tôi còn thiếu kỹ năng gì cho các vị trí trên?",
            user,
            recommended_job_ids=mixed_ids,
        )
        assert "Authorized Backend Python" in resp_mixed.answer
        assert "Redis" in resp_mixed.answer
        for forbidden_title in ("Secret Draft Job", "Expired Job", "Deleted Job", "Closed Job"):
            assert forbidden_title not in resp_mixed.answer
        assert [s.entity_id for s in resp_mixed.sources if s.source_type == "job"] == [valid_job_id]
        assert resp_mixed.recommended_job_ids == [valid_job_id]

        # 2. Only invalid IDs (0 valid remain) on non-CV follow-up: fails closed, NO unrelated jobs leaked
        only_invalid_ids = [draft_job_id, expired_job_id, deleted_job_id, closed_job_id]
        resp_zero = await service.chat(
            "Tôi còn thiếu kỹ năng gì cho các vị trí trên?",
            user,
            recommended_job_ids=only_invalid_ids,
        )
        assert resp_zero.sources == []
        assert resp_zero.recommended_job_ids == []
        assert "Unrelated Published Job" not in resp_zero.answer
        for forbidden_title in ("Secret Draft Job", "Expired Job", "Deleted Job", "Closed Job"):
            assert forbidden_title not in resp_zero.answer

        # 3. CV summary turn revalidates client IDs via real ContextResolver without leaking job content
        resp_cv_mixed = await service.chat(
            "Hãy tóm tắt hồ sơ của tôi",
            user,
            recommended_job_ids=mixed_ids,
        )
        assert "Senior Python Engineer" in resp_cv_mixed.answer
        assert "Authorized Backend Python" not in resp_cv_mixed.answer
        assert [s.source_type for s in resp_cv_mixed.sources] == ["resume"]
        assert resp_cv_mixed.recommended_job_ids == [valid_job_id]

        resp_cv_invalid = await service.chat(
            "Hãy tóm tắt hồ sơ của tôi",
            user,
            recommended_job_ids=only_invalid_ids,
        )
        assert "Senior Python Engineer" in resp_cv_invalid.answer
        assert [s.source_type for s in resp_cv_invalid.sources] == ["resume"]
        assert resp_cv_invalid.recommended_job_ids == []
