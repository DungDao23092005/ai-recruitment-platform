from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import AIError, EmptyDocumentError, InvalidDocumentError
from app.domain.enums import UserRole
from app.schemas.ai_chat import ChatMessage, ChatResponse, ChatSource
from app.services.rag_chat_service import RAGChatService


def make_embedding_service():
    svc = MagicMock()
    svc.embed_text = MagicMock(return_value=[0.1, 0.2, 0.3])
    return svc


def make_vector_repo(jobs=None, resumes=None):
    repo = MagicMock()
    repo.search_similar = AsyncMock(side_effect=[jobs or [], resumes or []])
    return repo


def make_llm(response=None):
    provider = MagicMock()
    provider.generate_structured_output = AsyncMock(
        return_value=response or make_response()
    )
    return provider


def make_service(
    embedding_service=None,
    vector_repository=None,
    llm_provider=None,
):
    return RAGChatService(
        embedding_service=embedding_service,
        vector_repository=vector_repository,
        llm_provider=llm_provider,
    )


def make_job_point(
    point_id=None,
    score=0.87,
    skills=None,
):
    return {
        "id": point_id or str(uuid.uuid4()),
        "score": score,
        "payload": {
            "job_id": point_id or str(uuid.uuid4()),
            "skills": skills or ["Python", "FastAPI"],
            "is_deleted": False,
        },
    }


def make_resume_point(
    point_id=None,
    score=0.75,
    skills=None,
):
    return {
        "id": point_id or str(uuid.uuid4()),
        "score": score,
        "payload": {
            "candidate_id": point_id or str(uuid.uuid4()),
            "skills": skills or ["React", "TypeScript"],
            "is_deleted": False,
        },
    }


def make_response():
    return ChatResponse(
        answer="Dựa trên các tin tuyển dụng phù hợp, bạn nên tập trung phát triển kỹ năng Python và FastAPI.",
        confidence=0.9,
        sources=[
            ChatSource(
                source_type="job",
                entity_id=uuid.uuid4(),
                title="Job abc12345",
                relevance_score=0.87,
                skills=["Python", "FastAPI"],
            )
        ],
        suggested_followups=["Lộ trình phát triển kỹ năng AI Engineer?"],
    )


def make_service_with_jobs(jobs_points):
    embed = make_embedding_service()
    repo = make_vector_repo(jobs=jobs_points)
    llm = make_llm()
    return make_service(embed, repo, llm)


@pytest.fixture
def service_with_jobs():
    job_point = make_job_point()
    return make_service_with_jobs([job_point]), job_point


class TestSuccessfulChat:
    def test_returns_chat_response(self):
        embed = make_embedding_service()
        repo = make_vector_repo(jobs=[make_job_point()])
        llm = make_llm()
        service = make_service(embed, repo, llm)

        result = asyncio.run(
            service.chat("Tư vấn lộ trình AI Engineer", UserRole.CANDIDATE)
        )

        assert result.answer == (
            "Dựa trên các tin tuyển dụng phù hợp, bạn nên tập trung "
            "phát triển kỹ năng Python và FastAPI."
        )
        assert isinstance(result.sources, list)
        assert isinstance(result.suggested_followups, list)
        assert 0.0 <= result.confidence <= 1.0

    def test_embedding_called_with_message(self):
        embed = make_embedding_service()
        repo = make_vector_repo(jobs=[make_job_point()])
        llm = make_llm()
        service = make_service(embed, repo, llm)

        asyncio.run(
            service.chat("Tìm việc python", UserRole.CANDIDATE)
        )

        embed.embed_text.assert_called_once_with("Tìm việc python")

    def test_qdrant_retrieval_jobs_collection(self):
        embed = make_embedding_service()
        repo = make_vector_repo(jobs=[make_job_point()])
        llm = make_llm()
        service = make_service(embed, repo, llm)

        asyncio.run(service.chat("python job", UserRole.CANDIDATE))

        repo.search_similar.assert_awaited_once_with(
            collection_name="jobs",
            query_vector=[0.1, 0.2, 0.3],
            limit=3,
        )

    def test_prompt_contains_retrieved_context(self):
        embed = make_embedding_service()
        job_point = make_job_point()
        repo = make_vector_repo(jobs=[job_point])
        llm = make_llm()
        service = make_service(embed, repo, llm)

        asyncio.run(service.chat("python job", UserRole.CANDIDATE))

        prompt = llm.generate_structured_output.await_args.kwargs["prompt"]
        assert "RETRIEVED CONTEXT" in prompt
        assert "Python" in prompt

    def test_prompt_contains_history(self):
        embed = make_embedding_service()
        repo = make_vector_repo(jobs=[make_job_point()])
        llm = make_llm()
        service = make_service(embed, repo, llm)
        history = [
            ChatMessage(role="user", content="Xin chào"),
            ChatMessage(role="assistant", content="Chào bạn!"),
        ]

        asyncio.run(
            service.chat(
                "Tôi cần tư vấn",
                UserRole.CANDIDATE,
                history=history,
            )
        )

        prompt = llm.generate_structured_output.await_args.kwargs["prompt"]
        assert "CONVERSATION HISTORY" in prompt
        assert "Xin chào" in prompt
        assert "Chào bạn!" in prompt


class TestResumeRetrieval:
    def test_recruiter_candidate_query_retrieves_resumes(self):
        embed = make_embedding_service()
        repo = make_vector_repo(
            jobs=[make_job_point()], resumes=[make_resume_point()]
        )
        llm = make_llm()
        service = make_service(embed, repo, llm)

        asyncio.run(
            service.chat(
                "Tìm ứng viên react developer",
                UserRole.RECRUITER,
            )
        )

        assert repo.search_similar.await_count == 2
        collections = [
            call.kwargs["collection_name"]
            for call in repo.search_similar.await_args_list
        ]
        assert collections == ["jobs", "resumes"]

    def test_recruiter_non_candidate_query_only_jobs(self):
        embed = make_embedding_service()
        repo = make_vector_repo(jobs=[make_job_point()])
        llm = make_llm()
        service = make_service(embed, repo, llm)

        asyncio.run(
            service.chat(
                "Tư vấn chiến lược tuyển dụng",
                UserRole.RECRUITER,
            )
        )

        assert repo.search_similar.await_count == 1
        assert (
            repo.search_similar.await_args.kwargs["collection_name"]
            == "jobs"
        )

    def test_candidate_never_retrieves_resumes(self):
        embed = make_embedding_service()
        repo = make_vector_repo(jobs=[make_job_point()])
        llm = make_llm()
        service = make_service(embed, repo, llm)

        asyncio.run(
            service.chat(
                "Tìm ứng viên react",
                UserRole.CANDIDATE,
            )
        )

        assert repo.search_similar.await_count == 1
        assert (
            repo.search_similar.await_args.kwargs["collection_name"]
            == "jobs"
        )


class TestSourceMapping:
    def test_qdrant_score_preserved(self):
        embed = make_embedding_service()
        job_point = make_job_point(score=0.9123)
        repo = make_vector_repo(jobs=[job_point])
        llm = make_llm()
        service = make_service(embed, repo, llm)

        result = asyncio.run(
            service.chat("python job", UserRole.CANDIDATE)
        )

        assert result.sources[0].relevance_score == 0.9123

    def test_source_mapping_fields(self):
        embed = make_embedding_service()
        job_id = str(uuid.uuid4())
        job_point = make_job_point(point_id=job_id, score=0.87)
        repo = make_vector_repo(jobs=[job_point])
        llm = make_llm()
        service = make_service(embed, repo, llm)

        result = asyncio.run(
            service.chat("python job", UserRole.CANDIDATE)
        )

        source = result.sources[0]
        assert source.source_type == "job"
        assert str(source.entity_id) == job_id
        assert source.skills == ["Python", "FastAPI"]
        assert source.title.startswith("Job")

    def test_no_fabricated_sources_when_context_empty(self):
        embed = make_embedding_service()
        repo = make_vector_repo(jobs=[])
        llm = make_llm(
            ChatResponse(
                answer="Không đủ dữ liệu để trả lời.",
                confidence=0.0,
                sources=[],
                suggested_followups=[],
            )
        )
        service = make_service(embed, repo, llm)

        result = asyncio.run(
            service.chat("hỏi gì đó", UserRole.CANDIDATE)
        )

        assert result.sources == []
        prompt = llm.generate_structured_output.await_args.kwargs["prompt"]
        assert "không có context phù hợp" in prompt

    def test_skips_non_uuid_points(self):
        embed = make_embedding_service()
        repo = make_vector_repo(
            jobs=[
                {"id": "not-a-uuid", "score": 0.5, "payload": {"skills": []}}
            ]
        )
        llm = make_llm()
        service = make_service(embed, repo, llm)

        result = asyncio.run(
            service.chat("python", UserRole.CANDIDATE)
        )

        assert result.sources == []

    def test_llm_hallucinated_sources_replaced_by_retrieved(self):
        embed = make_embedding_service()
        job_id = str(uuid.uuid4())
        job_point = make_job_point(point_id=job_id, score=0.87)
        repo = make_vector_repo(jobs=[job_point])
        llm = make_llm(
            ChatResponse(
                answer="có citation",
                confidence=0.5,
                sources=[
                    ChatSource(
                        source_type="job",
                        entity_id=uuid.uuid4(),
                        title="Fake source",
                        relevance_score=0.99,
                        skills=["Fake"],
                    )
                ],
                suggested_followups=[],
            )
        )
        service = make_service(embed, repo, llm)

        result = asyncio.run(
            service.chat("python", UserRole.CANDIDATE)
        )

        assert len(result.sources) == 1
        assert str(result.sources[0].entity_id) == job_id
        assert result.sources[0].title.startswith("Job")
        assert result.sources[0].skills == ["Python", "FastAPI"]


class TestSensitiveDataGrounding:
    def test_prompt_contains_system_instruction(self):
        embed = make_embedding_service()
        repo = make_vector_repo(jobs=[make_job_point()])
        llm = make_llm()
        service = make_service(embed, repo, llm)

        asyncio.run(service.chat("python", UserRole.CANDIDATE))

        kwargs = llm.generate_structured_output.await_args.kwargs
        assert "CHỈ sử dụng các dữ kiện nằm trong ngữ cảnh" in kwargs[
            "system_instruction"
        ]

    def test_no_secrets_in_prompt(self):
        embed = make_embedding_service()
        repo = make_vector_repo(jobs=[make_job_point()])
        llm = make_llm()
        service = make_service(embed, repo, llm)

        asyncio.run(service.chat("python", UserRole.CANDIDATE))

        prompt = llm.generate_structured_output.await_args.kwargs["prompt"]
        assert "GEMINI_API_KEY" not in prompt
        assert "api_key" not in prompt.lower()


class TestFailures:
    def test_empty_message_raises(self):
        embed = make_embedding_service()
        repo = make_vector_repo(jobs=[])
        llm = make_llm()
        service = make_service(embed, repo, llm)

        with pytest.raises(EmptyDocumentError):
            asyncio.run(service.chat("", UserRole.CANDIDATE))

    def test_whitespace_message_raises(self):
        embed = make_embedding_service()
        repo = make_vector_repo(jobs=[])
        llm = make_llm()
        service = make_service(embed, repo, llm)

        with pytest.raises(EmptyDocumentError):
            asyncio.run(service.chat("   ", UserRole.CANDIDATE))

    def test_llm_failure_propagates(self):
        embed = make_embedding_service()
        repo = make_vector_repo(jobs=[make_job_point()])
        llm = make_llm()
        llm.generate_structured_output.side_effect = InvalidDocumentError(
            "Gemini API request failed"
        )
        service = make_service(embed, repo, llm)

        with pytest.raises(InvalidDocumentError):
            asyncio.run(service.chat("python", UserRole.CANDIDATE))

    def test_qdrant_failure_propagates(self):
        embed = make_embedding_service()
        repo = make_vector_repo(jobs=[])
        repo.search_similar.side_effect = AIError("Qdrant down")
        llm = make_llm()
        service = make_service(embed, repo, llm)

        with pytest.raises(AIError):
            asyncio.run(service.chat("python", UserRole.CANDIDATE))

    def test_unexpected_llm_failure_maps(self):
        embed = make_embedding_service()
        repo = make_vector_repo(jobs=[make_job_point()])
        llm = make_llm()
        llm.generate_structured_output.side_effect = RuntimeError("boom")
        service = make_service(embed, repo, llm)

        with pytest.raises(InvalidDocumentError):
            asyncio.run(service.chat("python", UserRole.CANDIDATE))

    def test_empty_reply_validation(self):
        embed = make_embedding_service()
        repo = make_vector_repo(jobs=[make_job_point()])
        llm = make_llm(
            ChatResponse(
                answer=" ",
                confidence=0.5,
                sources=[],
                suggested_followups=[],
            )
        )
        service = make_service(embed, repo, llm)

        with pytest.raises(InvalidDocumentError):
            asyncio.run(service.chat("python", UserRole.CANDIDATE))
