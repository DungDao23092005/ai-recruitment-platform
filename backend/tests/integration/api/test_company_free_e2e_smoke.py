"""End-to-End Integration Smoke Tests for Company Free V1 Freemium Lifecycle.

Exercised lifecycles:
1. Canonical Plan Fixture: Validates and idempotently seeds the canonical Company Free plan.
2. Scenario A — Recruiter Signup & Workspace Creation:
   Recruiter registers -> logs in -> creates company workspace -> automatic Company Free
   subscription provisioning with zero initial usage and full quota snapshot.
3. Scenario B — Job Posting Quota:
   Draft creation (unmetered) -> Publish (consumes 1) -> Re-publish (idempotent, retains 1) ->
   Exhaustion guard (publishing 2nd job raises 403 Forbidden).
4. Scenario C — Candidate Search Quota:
   Session 1 consumes 1 -> Replay retains 1 -> 9 more distinct sessions consume up to 10 ->
   11th distinct session raises 403 Forbidden.
5. Scenario D — Recruitment AI Quota:
   Shared 5/month pool across Parse JD, Generate Questions, Match Explanation Refresh,
   and Recruiter AI Chat with Redis caching and replay. Failed calls safely refund reservation.
   Candidate AI chat uses personal quota without affecting company usage.
6. Scenario E — Multi-Tenant Sharing & Permissions:
   Invited recruiter shares company subscription without duplicating it.
   Invitee actions debit shared company quota.
   Recruiter creating second company receives independent Company Free subscription.
   Interviewer membership is rejected with 403 from manager-scoped operations.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import uuid

import httpx
import pytest
from sqlalchemy import func, select

from app.core.exceptions import AIProviderUnavailableError
from app.database.session import async_session_factory
from app.domain.enums import (
    JobStatus,
    JobType,
    MembershipRole,
    MembershipStatus,
    PlanAudience,
    SubscriptionScope,
    SubscriptionStatus,
    SubscriptionUsageFeatureType,
    SubscriptionUsageStatus,
    UserRole,
    WorkplaceType,
)
from app.domain.models.base import utc_now
from app.main import app
from app.models import (
    Application,
    Company,
    CompanyMembership,
    EmailOutbox,
    Job,
    RecruiterProfile,
    RecruitmentPlan,
    Subscription,
    SubscriptionUsage,
    User,
)
from app.schemas.ai_chat import ChatResponse, ChatSource
from app.schemas.ai_explanation import (
    ApplicationMatchExplanationResponse,
    ScoreBreakdown,
)
from app.schemas.ai_interview import (
    GenerateInterviewQuestionsResponse,
    InterviewQuestion,
)
from app.schemas.ai_job import ParsedJobSchema
from app.services.company_entitlement_service import COMPANY_CALENDAR_TIMEZONE
from tests.integration.api.conftest import (
    API_V1,
    PASSWORD,
    seed_confirmed_resume,
)
from tests.integration.company_billing_helpers import (
    CANONICAL_COMPANY_FREE_NAME,
    _seed_canonical_company_free_plan,
)
from tests.integration.conftest import _assert_not_development_database

pytestmark = pytest.mark.integration


# ==============================================================================
# External Service Mocks & Test Helpers
# ==============================================================================

@pytest.fixture(autouse=True)
def _mock_ai_and_vector_backends():
    """Mock external vector database and embedding services to ensure zero external cost."""
    with (
        patch(
            "app.ai.vector_db.qdrant_client.QdrantVectorRepository.upsert_job_vector",
            new_callable=AsyncMock,
        ),
        patch(
            "app.ai.vector_db.qdrant_client.QdrantVectorRepository.retrieve_vector",
            new_callable=AsyncMock,
            return_value={"vector": [0.1] * 384},
        ),
        patch(
            "app.ai.vector_db.qdrant_client.QdrantVectorRepository.delete_vector",
            new_callable=AsyncMock,
        ),
        patch(
            "app.ai.embeddings.embedding_service.EmbeddingService.embed_text",
            new_callable=AsyncMock,
            return_value=[0.1] * 384,
        ),
        patch(
            "app.ai.embeddings.embedding_service.EmbeddingService.embed_job",
            new_callable=AsyncMock,
            return_value=[0.1] * 384,
        ),
        patch(
            "app.ai.embeddings.embedding_service.EmbeddingService.embed_resume",
            new_callable=AsyncMock,
            return_value=[0.1] * 384,
        ),
    ):
        yield


async def _register_and_login(
    anon_client: httpx.AsyncClient,
    email: str,
    password: str = PASSWORD,
    role: str = "recruiter",
) -> tuple[dict, str, httpx.AsyncClient]:
    """Register and login a user via HTTP endpoints, returning user dict, token, and auth client."""
    reg_resp = await anon_client.post(
        f"{API_V1}/auth/register",
        json={"email": email, "password": password, "role": role},
    )
    assert reg_resp.status_code == 201, reg_resp.text
    user_data = reg_resp.json()

    login_resp = await anon_client.post(
        f"{API_V1}/auth/login",
        data={"username": email, "password": password},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]

    auth_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )
    return user_data, token, auth_client


async def _create_workspace(
    auth_client: httpx.AsyncClient,
    *,
    name: str = "Acme Global",
    slug: str | None = None,
    tax_code: str | None = None,
    size: str = "startup",
) -> dict:
    """Create a company workspace for the authenticated recruiter."""
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": name,
        "slug": slug or f"acme-{suffix}",
        "tax_code": tax_code or f"TX-{suffix.upper()}",
        "size": size,
    }
    resp = await auth_client.post(f"{API_V1}/companies", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _extract_invitation_token(email: str) -> str:
    """Extract plain invitation token from the durable transactional EmailOutbox."""
    async with async_session_factory() as session:
        outbox = await session.scalar(
            select(EmailOutbox)
            .where(EmailOutbox.to_email == email)
            .order_by(EmailOutbox.created_at.desc())
        )
        assert outbox is not None, f"No email outbox entry found for {email}"
        raw = outbox.text_body.split("#token=", 1)[1].splitlines()[0]
        return raw.split("&", 1)[0]


# ==============================================================================
# Plan Fixture Validation Test
# ==============================================================================

def test_canonical_company_free_plan_fixture(run_async):
    """Verify that the fixture creates the canonical plan and validates configuration."""
    async def _run():
        _assert_not_development_database()
        async with async_session_factory() as session:
            plan = await session.scalar(
                select(RecruitmentPlan).where(
                    RecruitmentPlan.plan_audience == PlanAudience.COMPANY,
                    RecruitmentPlan.is_free == True,  # noqa: E712
                    RecruitmentPlan.is_active == True,  # noqa: E712
                    RecruitmentPlan.is_deleted == False,  # noqa: E712
                )
            )
            assert plan is not None
            assert plan.name == CANONICAL_COMPANY_FREE_NAME
            assert plan.price == 0
            assert plan.currency == "VND"
            assert plan.duration_days == 30
            assert plan.max_job_posts == 1
            assert plan.max_candidate_searches == 10
            assert plan.max_ai_features == 5

            # Idempotency: calling again returns the existing plan
            plan2 = await _seed_canonical_company_free_plan()
            assert plan2.id == plan.id

    run_async(_run())


# ==============================================================================
# Scenario A — Recruiter Signup and Workspace Creation
# ==============================================================================

def test_scenario_a_recruiter_signup_and_workspace_creation(client, run_async):
    """Scenario A: Recruiter signup, login, workspace creation & auto Company Free provisioning."""
    async def _run():
        recruiter_email = f"recruiter-a-{uuid.uuid4().hex[:8]}@example.com"

        # 1. Recruiter registers via POST /api/v1/auth/register (role=recruiter)
        user_data, token, auth_client = await _register_and_login(
            client, recruiter_email, role="recruiter"
        )
        recruiter_id = uuid.UUID(user_data["id"])

        try:
            # 2. Verify Recruiter does NOT receive Candidate Free subscription
            async with async_session_factory() as session:
                cand_sub = await session.scalar(
                    select(Subscription).where(
                        Subscription.user_id == recruiter_id,
                        Subscription.scope == SubscriptionScope.CANDIDATE_PERSONAL,
                    )
                )
                assert cand_sub is None, "Recruiter must not receive candidate personal subscription"

            # 3. Recruiter creates company workspace via POST /api/v1/companies
            company_slug = f"acme-a-{uuid.uuid4().hex[:8]}"
            company_tax = f"TX-A-{uuid.uuid4().hex[:8].upper()}"
            company_data = await _create_workspace(
                auth_client,
                name="Acme Alpha",
                slug=company_slug,
                tax_code=company_tax,
                size="startup",
            )
            company_id = uuid.UUID(company_data["id"])

            # 4. Verify in DB:
            async with async_session_factory() as session:
                # 4.1 Exactly 1 Company record
                company = await session.get(Company, company_id)
                assert company is not None
                assert company.name == "Acme Alpha"
                assert company.slug == company_slug
                assert company.tax_code == company_tax

                # 4.2 Exactly 1 CompanyMembership record (ADMIN, ACTIVE)
                memberships = list(
                    (
                        await session.execute(
                            select(CompanyMembership).where(
                                CompanyMembership.company_id == company_id,
                                CompanyMembership.is_deleted == False,  # noqa: E712
                            )
                        )
                    ).scalars().all()
                )
                assert len(memberships) == 1
                assert memberships[0].user_id == recruiter_id
                assert memberships[0].role == MembershipRole.ADMIN
                assert memberships[0].status == MembershipStatus.ACTIVE

                # 4.3 RecruiterProfile linked to company.id
                profile = await session.scalar(
                    select(RecruiterProfile).where(
                        RecruiterProfile.user_id == recruiter_id,
                        RecruiterProfile.is_deleted == False,  # noqa: E712
                    )
                )
                assert profile is not None
                assert profile.company_id == company_id

                # 4.4 Exactly 1 Company Free subscription
                subscriptions = list(
                    (
                        await session.execute(
                            select(Subscription).where(
                                Subscription.company_id == company_id,
                                Subscription.is_deleted == False,  # noqa: E712
                            )
                        )
                    ).scalars().all()
                )
                assert len(subscriptions) == 1
                sub = subscriptions[0]
                assert sub.scope == SubscriptionScope.COMPANY_RECRUITING
                assert sub.is_free is True
                assert sub.status == SubscriptionStatus.ACTIVE
                assert sub.expires_at is None
                assert sub.max_job_posts == 1
                assert sub.max_candidate_searches == 10
                assert sub.max_ai_features == 5
                assert sub.job_posts_used == 0
                assert sub.candidate_searches_used == 0
                assert sub.ai_features_used == 0

                expected_period = datetime.now(timezone.utc).astimezone(
                    COMPANY_CALENDAR_TIMEZONE
                ).strftime("%Y-%m")
                assert sub.current_period_key == expected_period

        finally:
            await auth_client.aclose()

    run_async(_run())


# ==============================================================================
# Scenario B — Job Posting Quota
# ==============================================================================

def test_scenario_b_job_posting_quota(client, run_async):
    """Scenario B: Draft creation, publish, re-publish (idempotent), and exhaustion guard."""
    async def _run():
        recruiter_email = f"recruiter-b-{uuid.uuid4().hex[:8]}@example.com"
        _, _, auth_client = await _register_and_login(
            client, recruiter_email, role="recruiter"
        )

        try:
            company_data = await _create_workspace(
                auth_client, name="Beta Technologies"
            )
            company_id = uuid.UUID(company_data["id"])
            headers = {"X-Company-ID": str(company_id)}

            # 1. Create draft 1 via POST /api/v1/jobs -> 201, quota unmetered
            draft1_payload = {
                "title": "Backend Python Engineer",
                "description": "Design and build microservices with FastAPI",
                "job_type": "full_time",
                "workplace_type": "remote",
                "location": "Ho Chi Minh City",
                "status": "draft",
            }
            resp_d1 = await auth_client.post(
                f"{API_V1}/jobs", headers=headers, json=draft1_payload
            )
            assert resp_d1.status_code == 201, resp_d1.text
            job1_id = resp_d1.json()["id"]

            async with async_session_factory() as session:
                sub = await session.scalar(
                    select(Subscription).where(
                        Subscription.company_id == company_id,
                        Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                    )
                )
                assert sub.job_posts_used == 0

            # 2. Publish job 1 via PATCH /api/v1/jobs/mine/{job_id}/status -> 200, used becomes 1
            resp_pub1 = await auth_client.patch(
                f"{API_V1}/jobs/mine/{job1_id}/status",
                headers=headers,
                json={"status": "published"},
            )
            assert resp_pub1.status_code == 200, resp_pub1.text
            assert resp_pub1.json()["status"] == "published"

            async with async_session_factory() as session:
                sub = await session.scalar(
                    select(Subscription).where(
                        Subscription.company_id == company_id,
                        Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                    )
                )
                assert sub.job_posts_used == 1

            # 3. Re-publish job 1: close then re-publish -> 200, counter remains 1 (idempotent)
            resp_close = await auth_client.patch(
                f"{API_V1}/jobs/mine/{job1_id}/status",
                headers=headers,
                json={"status": "closed"},
            )
            assert resp_close.status_code == 200, resp_close.text

            resp_repub = await auth_client.patch(
                f"{API_V1}/jobs/mine/{job1_id}/status",
                headers=headers,
                json={"status": "published"},
            )
            assert resp_repub.status_code == 200, resp_repub.text
            assert resp_repub.json()["status"] == "published"

            async with async_session_factory() as session:
                sub = await session.scalar(
                    select(Subscription).where(
                        Subscription.company_id == company_id,
                        Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                    )
                )
                assert sub.job_posts_used == 1

            # 4. Create draft 2 via POST /api/v1/jobs -> 201, counter remains 1
            draft2_payload = {
                "title": "Frontend React Engineer",
                "description": "Build high-performance web applications",
                "job_type": "full_time",
                "workplace_type": "remote",
                "location": "Ho Chi Minh City",
                "status": "draft",
            }
            resp_d2 = await auth_client.post(
                f"{API_V1}/jobs", headers=headers, json=draft2_payload
            )
            assert resp_d2.status_code == 201, resp_d2.text
            job2_id = resp_d2.json()["id"]

            async with async_session_factory() as session:
                sub = await session.scalar(
                    select(Subscription).where(
                        Subscription.company_id == company_id,
                        Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                    )
                )
                assert sub.job_posts_used == 1

            # 5. Publish job 2 -> 403 Forbidden (quota limit exceeded), counter remains 1
            resp_pub2 = await auth_client.patch(
                f"{API_V1}/jobs/mine/{job2_id}/status",
                headers=headers,
                json={"status": "published"},
            )
            assert resp_pub2.status_code == 403, resp_pub2.text
            assert "hết lượt đăng tin" in resp_pub2.text

            async with async_session_factory() as session:
                sub = await session.scalar(
                    select(Subscription).where(
                        Subscription.company_id == company_id,
                        Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                    )
                )
                assert sub.job_posts_used == 1

            # Direct publish creation attempt also fails closed with 403
            resp_direct_pub = await auth_client.post(
                f"{API_V1}/jobs",
                headers=headers,
                json={
                    "title": "Direct Published Job",
                    "description": "Attempting direct publish beyond quota",
                    "job_type": "full_time",
                    "workplace_type": "remote",
                    "location": "Ho Chi Minh City",
                    "status": "published",
                },
            )
            assert resp_direct_pub.status_code == 403, resp_direct_pub.text

            async with async_session_factory() as session:
                sub = await session.scalar(
                    select(Subscription).where(
                        Subscription.company_id == company_id,
                        Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                    )
                )
                assert sub.job_posts_used == 1

        finally:
            await auth_client.aclose()

    run_async(_run())


# ==============================================================================
# Scenario C — Candidate Search Quota
# ==============================================================================

def test_scenario_c_candidate_search_quota(client, run_async):
    """Scenario C: Semantic search, recommendations, idempotency replay, and exhaustion guard."""
    async def _run():
        recruiter_email = f"recruiter-c-{uuid.uuid4().hex[:8]}@example.com"
        _, _, auth_client = await _register_and_login(
            client, recruiter_email, role="recruiter"
        )

        try:
            company_data = await _create_workspace(
                auth_client, name="Gamma Corp"
            )
            company_id = uuid.UUID(company_data["id"])
            headers = {"X-Company-ID": str(company_id)}

            # Publish a job to use with candidate recommendations
            job_resp = await auth_client.post(
                f"{API_V1}/jobs",
                headers=headers,
                json={
                    "title": "Data Engineer",
                    "description": "SQL, Spark, Python",
                    "job_type": "full_time",
                    "workplace_type": "remote",
                    "location": "Da Nang",
                    "status": "published",
                },
            )
            assert job_resp.status_code == 201, job_resp.text
            job_id = job_resp.json()["id"]

            with (
                patch(
                    "app.services.semantic_search_service.SemanticSearchService.search_candidates",
                    new_callable=AsyncMock,
                    return_value=[],
                ),
                patch(
                    "app.services.ai_matching_service.AIMatchingService.recommend_candidates_for_job",
                    new_callable=AsyncMock,
                    return_value=[],
                ),
            ):
                # 1. Session 1: GET /api/v1/ai/search/candidates -> counter becomes 1
                session1_key = f"sess-{uuid.uuid4().hex[:8]}"
                resp_s1 = await auth_client.get(
                    f"{API_V1}/ai/search/candidates",
                    params={"q": "Python", "limit": 5},
                    headers={**headers, "Idempotency-Key": session1_key},
                )
                assert resp_s1.status_code == 200, resp_s1.text

                async with async_session_factory() as session:
                    sub = await session.scalar(
                        select(Subscription).where(
                            Subscription.company_id == company_id,
                            Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                        )
                    )
                    assert sub.candidate_searches_used == 1

                # 2. Replay Session 1 (retry/pagination with same key) -> counter remains 1
                resp_replay = await auth_client.get(
                    f"{API_V1}/ai/search/candidates",
                    params={"q": "Python", "limit": 5},
                    headers={**headers, "Idempotency-Key": session1_key},
                )
                assert resp_replay.status_code == 200, resp_replay.text

                async with async_session_factory() as session:
                    sub = await session.scalar(
                        select(Subscription).where(
                            Subscription.company_id == company_id,
                            Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                        )
                    )
                    assert sub.candidate_searches_used == 1

                # 3. 9 more distinct sessions across search (4 calls) & recommendations (5 calls)
                for i in range(2, 6):
                    resp = await auth_client.get(
                        f"{API_V1}/ai/search/candidates",
                        params={"q": f"Skill-{i}", "limit": 5},
                        headers={
                            **headers,
                            "Idempotency-Key": f"sess-search-{i}-{uuid.uuid4().hex[:6]}",
                        },
                    )
                    assert resp.status_code == 200, resp.text

                for i in range(6, 11):
                    resp = await auth_client.get(
                        f"{API_V1}/ai/recommendations/candidates",
                        params={"job_id": job_id, "limit": 5},
                        headers={
                            **headers,
                            "Idempotency-Key": f"sess-rec-{i}-{uuid.uuid4().hex[:6]}",
                        },
                    )
                    assert resp.status_code == 200, resp.text

                # Quota reached max limit (10)
                async with async_session_factory() as session:
                    sub = await session.scalar(
                        select(Subscription).where(
                            Subscription.company_id == company_id,
                            Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                        )
                    )
                    assert sub.candidate_searches_used == 10

                # 4. 11th distinct session -> 403 Forbidden, counter remains 10
                resp_exhausted = await auth_client.get(
                    f"{API_V1}/ai/search/candidates",
                    params={"q": "Exhausted", "limit": 5},
                    headers={
                        **headers,
                        "Idempotency-Key": f"sess-11-{uuid.uuid4().hex[:6]}",
                    },
                )
                assert resp_exhausted.status_code == 403, resp_exhausted.text
                assert "hết lượt tìm kiếm ứng viên" in resp_exhausted.text

                async with async_session_factory() as session:
                    sub = await session.scalar(
                        select(Subscription).where(
                            Subscription.company_id == company_id,
                            Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                        )
                    )
                    assert sub.candidate_searches_used == 10

        finally:
            await auth_client.aclose()

    run_async(_run())


# ==============================================================================
# Scenario D — Recruitment AI Quota
# ==============================================================================

def test_scenario_d_recruitment_ai_quota(client, run_async):
    """Scenario D: Shared 5/month AI pool across Parse JD, Question Gen, Match Explanation, and Chat."""
    async def _run():
        recruiter_email = f"recruiter-d-{uuid.uuid4().hex[:8]}@example.com"
        cand_email = f"candidate-d-{uuid.uuid4().hex[:8]}@example.com"

        _, _, auth_client = await _register_and_login(
            client, recruiter_email, role="recruiter"
        )
        cand_user, cand_token, cand_client = await _register_and_login(
            client, cand_email, role="candidate"
        )

        try:
            company_data = await _create_workspace(
                auth_client, name="Delta AI Innovations"
            )
            company_id = uuid.UUID(company_data["id"])
            headers = {"X-Company-ID": str(company_id)}

            # Publish a job and seed candidate application for Match Explanation Refresh
            job_resp = await auth_client.post(
                f"{API_V1}/jobs",
                headers=headers,
                json={
                    "title": "Machine Learning Engineer",
                    "description": "Train and deploy PyTorch models",
                    "job_type": "full_time",
                    "workplace_type": "remote",
                    "location": "Hanoi",
                    "status": "published",
                },
            )
            assert job_resp.status_code == 201, job_resp.text
            job_id = job_resp.json()["id"]

            # Candidate profile & confirmed resume
            cand_profile_resp = await cand_client.post(
                f"{API_V1}/users/me/candidate-profile",
                json={"full_name": "Nguyen Van A", "title": "ML Engineer"},
            )
            assert cand_profile_resp.status_code == 201, cand_profile_resp.text
            cand_profile_id = uuid.UUID(cand_profile_resp.json()["id"])

            await seed_confirmed_resume(
                cand_profile_id,
                parsed_data={
                    "full_name": "Nguyen Van A",
                    "email": cand_email,
                    "skills": ["Python", "PyTorch", "Docker"],
                    "total_years_experience": 4.0,
                },
            )

            apply_resp = await cand_client.post(
                f"{API_V1}/applications",
                json={"job_id": job_id},
            )
            assert apply_resp.status_code == 201, apply_resp.text
            app_id = uuid.UUID(apply_resp.json()["id"])

            mock_explanation = ApplicationMatchExplanationResponse(
                application_id=app_id,
                overall_score=0.88,
                score_breakdown=ScoreBreakdown(
                    overall_score=0.88,
                    cosine_similarity=0.85,
                    skill_coverage_score=0.9,
                    preferred_skill_coverage_score=0.85,
                    experience_match_score=0.9,
                    education_score=0.8,
                    project_score=0.85,
                ),
                summary="Strong alignment with ML engineering requirements.",
                summary_source="ai_generated",
                skill_evaluations=[],
                experience_evaluations=[],
                evidence=[],
                generated_at=utc_now(),
            )

            mock_questions = GenerateInterviewQuestionsResponse(
                job_title="Machine Learning Engineer",
                total_questions=1,
                questions=[
                    InterviewQuestion(
                        question="Giải thích sự khác biệt giữa overfitting và underfitting?",
                        category="technical",
                        difficulty="medium",
                        reason="Đánh giá kiến thức nền tảng về huấn luyện mô hình",
                        target_skill_or_topic="Machine Learning",
                        evaluation_criteria="Nêu rõ khái niệm và phương pháp khắc phục",
                        sample_answer_points=["Regularization", "Cross-validation"],
                    )
                ],
            )

            with (
                patch(
                    "app.services.ai_matching_service.AIMatchingService.process_and_index_job",
                    new_callable=AsyncMock,
                    return_value=ParsedJobSchema(
                        title="ML Engineer", summary="Job description summary"
                    ),
                ),
                patch(
                    "app.services.interview_generator_service.InterviewGeneratorService.generate_questions",
                    new_callable=AsyncMock,
                    return_value=mock_questions,
                ) as mock_gen_q,
                patch(
                    "app.services.match_explanation_service.MatchExplanationService.build_refresh_explanation",
                    new_callable=AsyncMock,
                    return_value=mock_explanation,
                ),
                patch(
                    "app.services.rag_chat_service.RAGChatService.chat",
                    new_callable=AsyncMock,
                    return_value=ChatResponse(
                        answer="To evaluate an ML engineer, ask about model architecture.",
                        confidence=0.92,
                        sources=[
                            ChatSource(
                                source_type="job",
                                entity_id=job_id,
                                title="Machine Learning Engineer",
                                relevance_score=0.95,
                                skills=["Python", "PyTorch"],
                            )
                        ],
                        suggested_followups=["How to evaluate coding skills?"],
                        recommended_job_ids=[job_id],
                    ),
                ) as mock_chat,
            ):
                # 1. Parse JD -> counter becomes 1
                resp_pjd = await auth_client.post(
                    f"{API_V1}/ai/parse-jd",
                    headers=headers,
                    json={
                        "job_title": "ML Engineer",
                        "job_description": "PyTorch, Docker, Kubernetes experience required",
                    },
                )
                assert resp_pjd.status_code == 200, resp_pjd.text

                async with async_session_factory() as session:
                    sub = await session.scalar(
                        select(Subscription).where(
                            Subscription.company_id == company_id,
                            Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                        )
                    )
                    assert sub.ai_features_used == 1

                # 2. Generate Interview Questions -> counter becomes 2
                resp_gen_q = await auth_client.post(
                    f"{API_V1}/ai/generate-interview-questions",
                    headers=headers,
                    json={
                        "job": {
                            "title": "ML Engineer",
                            "summary": "PyTorch, Docker, Kubernetes",
                        },
                        "num_questions": 1,
                    },
                )
                assert resp_gen_q.status_code == 200, resp_gen_q.text

                async with async_session_factory() as session:
                    sub = await session.scalar(
                        select(Subscription).where(
                            Subscription.company_id == company_id,
                            Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                        )
                    )
                    assert sub.ai_features_used == 2

                # 3. Failed AI call: Provider unavailable -> 503, reservation refunded, counter remains 2
                mock_gen_q.side_effect = AIProviderUnavailableError("Gemini down")
                resp_failed_ai = await auth_client.post(
                    f"{API_V1}/ai/generate-interview-questions",
                    headers=headers,
                    json={
                        "job": {
                            "title": "ML Engineer",
                            "summary": "PyTorch, Docker, Kubernetes",
                        },
                        "num_questions": 1,
                    },
                )
                assert resp_failed_ai.status_code == 503, resp_failed_ai.text

                async with async_session_factory() as session:
                    sub = await session.scalar(
                        select(Subscription).where(
                            Subscription.company_id == company_id,
                            Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                        )
                    )
                    assert sub.ai_features_used == 2
                mock_gen_q.side_effect = None

                # 4. Match Explanation Refresh -> counter becomes 3
                resp_expl = await auth_client.post(
                    f"{API_V1}/applications/{app_id}/match-explanation/refresh",
                    headers={
                        **headers,
                        "Idempotency-Key": f"ref-{uuid.uuid4().hex[:8]}",
                    },
                )
                assert resp_expl.status_code == 200, resp_expl.text

                async with async_session_factory() as session:
                    sub = await session.scalar(
                        select(Subscription).where(
                            Subscription.company_id == company_id,
                            Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                        )
                    )
                    assert sub.ai_features_used == 3

                # 5. Recruiter AI Chat -> counter becomes 4
                chat_key = f"chat-{uuid.uuid4().hex[:8]}"
                chat_payload = {
                    "message": "How to structure an ML interview?",
                    "history": [],
                }
                resp_chat = await auth_client.post(
                    f"{API_V1}/ai/chat",
                    headers={**headers, "Idempotency-Key": chat_key},
                    json=chat_payload,
                )
                assert resp_chat.status_code == 200, resp_chat.text
                assert mock_chat.call_count == 1

                async with async_session_factory() as session:
                    sub = await session.scalar(
                        select(Subscription).where(
                            Subscription.company_id == company_id,
                            Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                        )
                    )
                    assert sub.ai_features_used == 4

                # 6. Replay Recruiter AI Chat with same key -> cached in Redis, LLM not called, counter remains 4
                resp_chat_replay = await auth_client.post(
                    f"{API_V1}/ai/chat",
                    headers={**headers, "Idempotency-Key": chat_key},
                    json=chat_payload,
                )
                assert resp_chat_replay.status_code == 200, resp_chat_replay.text
                assert mock_chat.call_count == 1  # Provider was NOT invoked again

                async with async_session_factory() as session:
                    sub = await session.scalar(
                        select(Subscription).where(
                            Subscription.company_id == company_id,
                            Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                        )
                    )
                    assert sub.ai_features_used == 4

                # 7. 5th AI Action (Parse JD) -> counter becomes 5 (limit reached)
                resp_pjd5 = await auth_client.post(
                    f"{API_V1}/ai/parse-jd",
                    headers=headers,
                    json={
                        "job_title": "Data Architect",
                        "job_description": "Data governance and warehouse architecture",
                    },
                )
                assert resp_pjd5.status_code == 200, resp_pjd5.text

                async with async_session_factory() as session:
                    sub = await session.scalar(
                        select(Subscription).where(
                            Subscription.company_id == company_id,
                            Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                        )
                    )
                    assert sub.ai_features_used == 5

                # 8. 6th AI Action attempt -> 403 Forbidden, counter remains 5
                resp_exhausted = await auth_client.post(
                    f"{API_V1}/ai/parse-jd",
                    headers=headers,
                    json={
                        "job_title": "Exhausted AI Role",
                        "job_description": "Should fail closed",
                    },
                )
                assert resp_exhausted.status_code == 403, resp_exhausted.text
                assert "hết lượt sử dụng AI" in resp_exhausted.text

                async with async_session_factory() as session:
                    sub = await session.scalar(
                        select(Subscription).where(
                            Subscription.company_id == company_id,
                            Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                        )
                    )
                    assert sub.ai_features_used == 5

                # 9. Candidate Chat: verify candidate calling ai/chat uses Candidate personal quota
                resp_cand_chat = await cand_client.post(
                    f"{API_V1}/ai/chat",
                    json={"message": "Can you give me career advice?", "history": []},
                )
                assert resp_cand_chat.status_code == 200, resp_cand_chat.text

                # Company quota remains untouched at 5
                async with async_session_factory() as session:
                    co_sub = await session.scalar(
                        select(Subscription).where(
                            Subscription.company_id == company_id,
                            Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                        )
                    )
                    assert co_sub.ai_features_used == 5

                    cand_sub = await session.scalar(
                        select(Subscription).where(
                            Subscription.user_id == uuid.UUID(cand_user["id"]),
                            Subscription.scope == SubscriptionScope.CANDIDATE_PERSONAL,
                        )
                    )
                    assert cand_sub is not None
                    assert cand_sub.ai_features_used == 1

        finally:
            await auth_client.aclose()
            await cand_client.aclose()

    run_async(_run())


# ==============================================================================
# Scenario E — Multi-Tenant Sharing & Permissions
# ==============================================================================

def test_scenario_e_multi_tenant_sharing(client, run_async):
    """Scenario E: Workspace member invitation, subscription reuse, shared quota consumption, and interviewer RBAC."""
    async def _run():
        recruiter_a_email = f"recruiter-ea-{uuid.uuid4().hex[:8]}@example.com"
        recruiter_b_email = f"invitee-eb-{uuid.uuid4().hex[:8]}@example.com"
        interviewer_email = f"interviewer-ec-{uuid.uuid4().hex[:8]}@example.com"

        user_a, _, auth_client_a = await _register_and_login(
            client, recruiter_a_email, role="recruiter"
        )
        user_b, _, auth_client_b = await _register_and_login(
            client, recruiter_b_email, role="recruiter"
        )
        user_c, _, auth_client_c = await _register_and_login(
            client, interviewer_email, role="recruiter"
        )

        try:
            # 1. Recruiter A creates Company 1
            company_data = await _create_workspace(
                auth_client_a, name="Epsilon Enterprise"
            )
            company_id = uuid.UUID(company_data["id"])
            headers = {"X-Company-ID": str(company_id)}

            # 2. Recruiter A invites Recruiter B as RECRUITER
            inv_resp = await auth_client_a.post(
                f"{API_V1}/workspaces/invitations",
                headers=headers,
                json={"email": recruiter_b_email, "role": "recruiter"},
            )
            assert inv_resp.status_code == 201, inv_resp.text

            # 3. Extract invitation token from EmailOutbox and Recruiter B accepts
            token_b = await _extract_invitation_token(recruiter_b_email)
            accept_resp_b = await auth_client_b.post(
                f"{API_V1}/invitations/accept",
                json={"token": token_b},
            )
            assert accept_resp_b.status_code == 200, accept_resp_b.text
            assert accept_resp_b.json()["workspace"]["company_id"] == str(company_id)

            # 4. Assert in DB: Exactly 1 company subscription exists (shared; no duplicate created)
            async with async_session_factory() as session:
                subs = list(
                    (
                        await session.execute(
                            select(Subscription).where(
                                Subscription.company_id == company_id,
                                Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                                Subscription.is_deleted == False,  # noqa: E712
                            )
                        )
                    ).scalars().all()
                )
                assert len(subs) == 1
                co_sub = subs[0]
                assert co_sub.candidate_searches_used == 0

            # 5. Invitee (Recruiter B) performs quota action -> debits shared company quota
            with patch(
                "app.services.semantic_search_service.SemanticSearchService.search_candidates",
                new_callable=AsyncMock,
                return_value=[],
            ):
                search_resp = await auth_client_b.get(
                    f"{API_V1}/ai/search/candidates",
                    params={"q": "Golang", "limit": 5},
                    headers={
                        **headers,
                        "Idempotency-Key": f"inv-search-{uuid.uuid4().hex[:8]}",
                    },
                )
                assert search_resp.status_code == 200, search_resp.text

            async with async_session_factory() as session:
                co_sub = await session.get(Subscription, co_sub.id)
                assert co_sub is not None
                assert co_sub.candidate_searches_used == 1

                # Verify usage record references Invitee B and Company 1
                usage = await session.scalar(
                    select(SubscriptionUsage).where(
                        SubscriptionUsage.subscription_id == co_sub.id,
                        SubscriptionUsage.user_id == uuid.UUID(user_b["id"]),
                    )
                )
                assert usage is not None
                assert usage.company_id == company_id
                assert usage.scope == SubscriptionScope.COMPANY_RECRUITING
                assert usage.status == SubscriptionUsageStatus.COMPLETED

            # 6. Recruiter A creates a second company workspace -> receives independent Company Free sub
            company2_data = await _create_workspace(
                auth_client_a, name="Epsilon Secondary"
            )
            company2_id = uuid.UUID(company2_data["id"])

            async with async_session_factory() as session:
                sub2 = await session.scalar(
                    select(Subscription).where(
                        Subscription.company_id == company2_id,
                        Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                        Subscription.is_deleted == False,  # noqa: E712
                    )
                )
                assert sub2 is not None
                assert sub2.id != co_sub.id
                assert sub2.is_free is True
                assert sub2.max_job_posts == 1
                assert sub2.max_candidate_searches == 10
                assert sub2.max_ai_features == 5
                assert sub2.job_posts_used == 0
                assert sub2.candidate_searches_used == 0
                assert sub2.ai_features_used == 0

            # 7. Interviewer role RBAC test
            inv_interviewer_resp = await auth_client_a.post(
                f"{API_V1}/workspaces/invitations",
                headers=headers,
                json={"email": interviewer_email, "role": "interviewer"},
            )
            assert inv_interviewer_resp.status_code == 201, inv_interviewer_resp.text

            token_c = await _extract_invitation_token(interviewer_email)
            accept_resp_c = await auth_client_c.post(
                f"{API_V1}/invitations/accept",
                json={"token": token_c},
            )
            assert accept_resp_c.status_code == 200, accept_resp_c.text
            assert accept_resp_c.json()["workspace"]["role"] == "interviewer"

            # Interviewer attempts recruiter quota operation (create job) -> 403 Forbidden
            job_attempt = await auth_client_c.post(
                f"{API_V1}/jobs",
                headers=headers,
                json={
                    "title": "Interviewer Job Attempt",
                    "description": "Should be rejected",
                    "job_type": "full_time",
                    "workplace_type": "remote",
                    "location": "HCM",
                    "status": "draft",
                },
            )
            assert job_attempt.status_code == 403, job_attempt.text

            # Interviewer attempts recruiter AI operation (Parse JD) -> 403 Forbidden
            parse_attempt = await auth_client_c.post(
                f"{API_V1}/ai/parse-jd",
                headers=headers,
                json={
                    "job_title": "Interviewer JD Attempt",
                    "job_description": "Should be rejected",
                },
            )
            assert parse_attempt.status_code == 403, parse_attempt.text

        finally:
            await auth_client_a.aclose()
            await auth_client_b.aclose()
            await auth_client_c.aclose()

    run_async(_run())
