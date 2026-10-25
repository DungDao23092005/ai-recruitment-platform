from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import status
from sqlalchemy import select

from app.database.session import async_session_factory
from app.domain.enums import (
    ApplicationStatus,
    InterviewStatus,
    JobStatus,
    OutboxStatus,
    SubscriptionStatus,
)
from app.models import (
    Application,
    EmailOutbox,
    Interview,
    Job,
    RecruitmentPlan,
    Resume,
    Subscription,
)
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.ai_matching_service import AIMatchingService
from app.services.email_outbox_worker import EmailOutboxWorker
from app.services.job_service import JobService
from app.services.payment_providers.vnpay import VNPAYProvider
from app.services.pipeline_email_service import (
    EVENT_APPLICATION_STATUS,
    EVENT_INTERVIEW_LIFECYCLE,
)
from app.services.subscription_email_service import EVENT_PAYMENT_RECEIPT
from tests.integration.api.conftest import API_V1, PASSWORD


async def _seed_plan() -> RecruitmentPlan:
    plan = RecruitmentPlan(
        name=f"E2E Plan {uuid.uuid4().hex[:10]}",
        description="Single job post end-to-end plan",
        price=1_500_000,
        currency="VND",
        duration_days=30,
        max_job_posts=1,
        max_candidate_searches=0,
        max_ai_features=0,
        is_active=True,
        display_order=0,
    )
    async with async_session_factory() as session:
        session.add(plan)
        await session.commit()
        await session.refresh(plan)
        return plan


async def _outbox_rows() -> list[EmailOutbox]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(EmailOutbox).order_by(EmailOutbox.created_at)
        )
        return list(result.scalars().all())


async def _get_subscription(subscription_id: uuid.UUID) -> Subscription | None:
    async with async_session_factory() as session:
        return await session.get(Subscription, subscription_id)


async def _get_job(job_id: uuid.UUID) -> Job | None:
    async with async_session_factory() as session:
        return await session.get(Job, job_id)


async def _get_application(application_id: uuid.UUID) -> Application | None:
    async with async_session_factory() as session:
        return await session.get(Application, application_id)


async def _get_interview(interview_id: uuid.UUID) -> Interview | None:
    async with async_session_factory() as session:
        return await session.get(Interview, interview_id)


async def _get_resume(resume_id: uuid.UUID) -> Resume | None:
    async with async_session_factory() as session:
        return await session.get(Resume, resume_id)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_and_login(client, run_async, *, email: str, role: str) -> str:
    registered = run_async(
        client.post(
            f"{API_V1}/auth/register",
            json={"email": email, "password": PASSWORD, "role": role},
        )
    )
    assert registered.status_code == status.HTTP_201_CREATED, registered.text

    logged_in = run_async(
        client.post(
            f"{API_V1}/auth/login",
            data={"username": email, "password": PASSWORD},
        )
    )
    assert logged_in.status_code == status.HTTP_200_OK, logged_in.text
    return logged_in.json()["access_token"]


def _payment_ipn_params(
    provider: VNPAYProvider,
    *,
    internal_order_id: str,
    amount: int,
) -> dict[str, str]:
    params = {
        "vnp_Version": "2.1.0",
        "vnp_Command": "pay",
        "vnp_TmnCode": provider.tmn_code,
        "vnp_Amount": str(amount * 100),
        "vnp_CurrCode": "VND",
        "vnp_TxnRef": internal_order_id,
        "vnp_OrderInfo": f"Payment for {internal_order_id}",
        "vnp_OrderType": "other",
        "vnp_TransactionNo": str(uuid.uuid4().int % 10**10),
        "vnp_TransactionStatus": "00",
        "vnp_ResponseCode": "00",
        "vnp_PayDate": "20260101120000",
        "vnp_BankCode": "NCB",
        "vnp_BankTranNo": f"BANK{uuid.uuid4().hex[:10]}",
    }
    params["vnp_SecureHash"] = provider.generate_secure_hash(params)
    return params


class TestFullRecruitmentLifecycleE2E:
    def test_subscription_publish_hire_accept_and_outbox_delivery(
        self, client, run_async
    ):
        suffix = uuid.uuid4().hex[:10]
        recruiter_email = f"e2e-recruiter-{suffix}@example.com"
        candidate_email = f"e2e-candidate-{suffix}@example.com"
        plan = run_async(_seed_plan())

        fake_worker = SimpleNamespace(dispatch_now=AsyncMock())
        with patch(
            "app.services.email_outbox_worker.get_default_worker",
            return_value=fake_worker,
        ), patch.object(
            JobService, "_reindex_job", new=AsyncMock()
        ):
            recruiter_token = _register_and_login(
                client,
                run_async,
                email=recruiter_email,
                role="recruiter",
            )
            recruiter_headers = _auth_headers(recruiter_token)

            company_response = run_async(
                client.post(
                    f"{API_V1}/companies",
                    json={
                        "name": f"E2E Company {suffix}",
                        "slug": f"e2e-company-{suffix}",
                        "tax_code": f"TAX-{suffix}",
                        "size": "sme",
                    },
                    headers=recruiter_headers,
                )
            )
            assert company_response.status_code == status.HTTP_201_CREATED, (
                company_response.text
            )
            company_id = company_response.json()["id"]

            job_payload = {
                "company_id": company_id,
                "title": f"Backend Engineer {suffix}",
                "description": "Build and maintain recruitment APIs.",
                "job_type": "full_time",
                "workplace_type": "remote",
                "location": "Remote",
                "status": "draft",
                "required_skills": ["Python", "FastAPI"],
                "preferred_skills": ["SQL Server"],
                "minimum_years_experience": 2,
                "education_level": "Bachelor",
            }
            job_response = run_async(
                client.post(
                    f"{API_V1}/jobs",
                    json=job_payload,
                    headers=recruiter_headers,
                )
            )
            assert job_response.status_code == status.HTTP_201_CREATED, (
                job_response.text
            )
            job_id = uuid.UUID(job_response.json()["id"])
            assert job_response.json()["status"] == "draft"

            blocked_publish = run_async(
                client.patch(
                    f"{API_V1}/jobs/mine/{job_id}/status",
                    json={"status": "published"},
                    headers=recruiter_headers,
                )
            )
            assert blocked_publish.status_code == status.HTTP_403_FORBIDDEN, (
                blocked_publish.text
            )

            payment_response = run_async(
                client.post(
                    f"{API_V1}/payments/vnpay/create",
                    json={"plan_id": str(plan.id)},
                    headers=recruiter_headers,
                )
            )
            assert payment_response.status_code == status.HTTP_201_CREATED, (
                payment_response.text
            )
            payment_body = payment_response.json()
            internal_order_id = payment_body["internal_order_id"]
            subscription_id = uuid.UUID(payment_body["subscription_id"])

            provider = VNPAYProvider()
            ipn_response = run_async(
                client.get(
                    f"{API_V1}/payments/vnpay/ipn",
                    params=_payment_ipn_params(
                        provider,
                        internal_order_id=internal_order_id,
                        amount=plan.price,
                    ),
                )
            )
            assert ipn_response.status_code == status.HTTP_200_OK, ipn_response.text
            assert ipn_response.json()["RspCode"] == "00"

            payment_status = run_async(
                client.get(
                    f"{API_V1}/payments/vnpay/status/{internal_order_id}",
                    headers=recruiter_headers,
                )
            )
            assert payment_status.status_code == status.HTTP_200_OK, (
                payment_status.text
            )
            payment_status_body = payment_status.json()
            assert payment_status_body["is_successful"] is True
            assert payment_status_body["is_activated"] is True
            assert payment_status_body["subscription_status"] == "active"

            subscription = run_async(_get_subscription(subscription_id))
            assert subscription is not None
            assert subscription.status == SubscriptionStatus.ACTIVE
            assert subscription.max_job_posts == 1
            assert subscription.job_posts_used == 0

            publish_response = run_async(
                client.patch(
                    f"{API_V1}/jobs/mine/{job_id}/status",
                    json={"status": "published"},
                    headers=recruiter_headers,
                )
            )
            assert publish_response.status_code == status.HTTP_200_OK, (
                publish_response.text
            )
            assert publish_response.json()["status"] == "published"

            subscription = run_async(_get_subscription(subscription_id))
            assert subscription is not None
            assert subscription.job_posts_used == 1

            candidate_token = _register_and_login(
                client,
                run_async,
                email=candidate_email,
                role="candidate",
            )
            candidate_headers = _auth_headers(candidate_token)
            profile_response = run_async(
                client.post(
                    f"{API_V1}/users/me/candidate-profile",
                    json={
                        "full_name": "E2E Candidate",
                        "phone": "0123456789",
                        "title": "Backend Engineer",
                    },
                    headers=candidate_headers,
                )
            )
            assert profile_response.status_code == status.HTTP_201_CREATED, (
                profile_response.text
            )

            parsed_resume = ParsedResumeSchema(
                full_name="E2E Candidate",
                email=candidate_email,
                phone="0123456789",
                title="Backend Engineer",
                skills=["Python", "FastAPI"],
                languages=["English"],
            )
            with patch(
                "app.services.ai_matching_service.extract_pdf_text_isolated",
                new=AsyncMock(return_value="E2E candidate resume text"),
            ), patch(
                "app.services.ai_matching_service.ResumeParser.parse",
                new=AsyncMock(return_value=parsed_resume),
            ), patch.object(
                AIMatchingService,
                "index_confirmed_resume",
                new=AsyncMock(),
            ):
                upload_response = run_async(
                    client.post(
                        f"{API_V1}/ai/parse-resume",
                        files={
                            "file": (
                                "resume.pdf",
                                b"%PDF-1.7 E2E candidate resume",
                                "application/pdf",
                            )
                        },
                        headers=candidate_headers,
                    )
                )
                assert upload_response.status_code == status.HTTP_200_OK, (
                    upload_response.text
                )
                upload_body = upload_response.json()
                resume_id = uuid.UUID(upload_body["id"])
                assert upload_body["is_confirmed"] is False
                assert upload_body["is_primary"] is False

                confirm_resume_response = run_async(
                    client.post(
                        f"{API_V1}/users/me/resume/{resume_id}/confirm",
                        headers=candidate_headers,
                    )
                )
                assert confirm_resume_response.status_code == status.HTTP_200_OK, (
                    confirm_resume_response.text
                )
                confirm_body = confirm_resume_response.json()
                assert confirm_body["indexing_status"] == "indexed"
                assert confirm_body["resume"]["is_confirmed"] is True
                assert confirm_body["resume"]["is_primary"] is True

            application_response = run_async(
                client.post(
                    f"{API_V1}/applications",
                    json={"job_id": str(job_id)},
                    headers=candidate_headers,
                )
            )
            assert application_response.status_code == status.HTTP_201_CREATED, (
                application_response.text
            )
            application_body = application_response.json()
            application_id = uuid.UUID(application_body["id"])
            assert application_body["status"] == "applied"

            duplicate_application = run_async(
                client.post(
                    f"{API_V1}/applications",
                    json={"job_id": str(job_id)},
                    headers=candidate_headers,
                )
            )
            assert duplicate_application.status_code == status.HTTP_400_BAD_REQUEST

            for next_status in ("under_review", "shortlisted"):
                transition = run_async(
                    client.patch(
                        f"{API_V1}/applications/{application_id}/status",
                        json={"status": next_status},
                        headers=recruiter_headers,
                    )
                )
                assert transition.status_code == status.HTTP_200_OK, transition.text
                assert transition.json()["status"] == next_status

            scheduled_at = datetime.now(timezone.utc) + timedelta(days=2)
            interview_response = run_async(
                client.post(
                    f"{API_V1}/applications/{application_id}/interviews",
                    json={
                        "scheduled_at": scheduled_at.isoformat(),
                        "duration_minutes": 60,
                        "interview_type": "technical",
                        "meeting_url": "https://meet.example.com/e2e",
                        "location": "Online",
                        "notes": "Internal interview notes",
                    },
                    headers=recruiter_headers,
                )
            )
            assert interview_response.status_code == status.HTTP_201_CREATED, (
                interview_response.text
            )
            interview_body = interview_response.json()
            interview_id = uuid.UUID(interview_body["id"])
            assert interview_body["status"] == "scheduled"
            assert interview_body["notes"] == "Internal interview notes"

            application_detail = run_async(
                client.get(
                    f"{API_V1}/applications/{application_id}",
                    headers=recruiter_headers,
                )
            )
            assert application_detail.status_code == status.HTTP_200_OK, (
                application_detail.text
            )
            assert application_detail.json()["status"] == "interviewing"

            candidate_interview_response = run_async(
                client.patch(
                    f"{API_V1}/applications/{application_id}/interviews/"
                    f"{interview_id}/action",
                    json={
                        "action": "confirm",
                        "candidate_notes": "Looking forward to it",
                    },
                    headers=candidate_headers,
                )
            )
            assert candidate_interview_response.status_code == status.HTTP_200_OK, (
                candidate_interview_response.text
            )
            candidate_interview_body = candidate_interview_response.json()
            assert candidate_interview_body["status"] == "candidate_confirmed"
            assert candidate_interview_body["candidate_notes"] == (
                "Looking forward to it"
            )
            assert "notes" not in candidate_interview_body

            offer_response = run_async(
                client.patch(
                    f"{API_V1}/applications/{application_id}/status",
                    json={"status": "offered"},
                    headers=recruiter_headers,
                )
            )
            assert offer_response.status_code == status.HTTP_200_OK, offer_response.text
            assert offer_response.json()["status"] == "offered"

            accepted_response = run_async(
                client.patch(
                    f"{API_V1}/applications/mine/{application_id}/offer",
                    json={"action": "accept", "notes": "Offer accepted"},
                    headers=candidate_headers,
                )
            )
            assert accepted_response.status_code == status.HTTP_200_OK, (
                accepted_response.text
            )
            assert accepted_response.json()["status"] == "accepted"

            final_application = run_async(_get_application(application_id))
            assert final_application is not None
            assert final_application.status == ApplicationStatus.ACCEPTED

            final_interview = run_async(_get_interview(interview_id))
            assert final_interview is not None
            assert final_interview.status == InterviewStatus.CANDIDATE_CONFIRMED

            final_resume = run_async(_get_resume(resume_id))
            assert final_resume is not None
            assert final_resume.is_confirmed is True
            assert final_resume.is_primary is True

            final_job = run_async(_get_job(job_id))
            assert final_job is not None
            assert final_job.status == JobStatus.PUBLISHED

        pending_rows = run_async(_outbox_rows())
        assert len(pending_rows) == 3, [
            (row.event_type, row.to_email, row.idempotency_key)
            for row in pending_rows
        ]
        assert {row.event_type for row in pending_rows} == {
            EVENT_PAYMENT_RECEIPT,
            EVENT_INTERVIEW_LIFECYCLE,
            EVENT_APPLICATION_STATUS,
        }
        assert {row.idempotency_key for row in pending_rows} == {
            f"payment_receipt:{internal_order_id}",
            f"interview:{interview_id}:scheduled",
            f"application-status:{application_id}:offered",
        }
        assert all(row.status == OutboxStatus.PENDING.value for row in pending_rows)
        assert all(row.attempts == 0 for row in pending_rows)

        rows_by_event = {row.event_type: row for row in pending_rows}
        assert rows_by_event[EVENT_PAYMENT_RECEIPT].to_email == recruiter_email
        assert rows_by_event[EVENT_INTERVIEW_LIFECYCLE].to_email == candidate_email
        assert rows_by_event[EVENT_APPLICATION_STATUS].to_email == candidate_email
        assert plan.name in rows_by_event[EVENT_PAYMENT_RECEIPT].subject
        assert job_payload["title"] in (
            rows_by_event[EVENT_INTERVIEW_LIFECYCLE].text_body
        )
        assert job_payload["title"] in rows_by_event[EVENT_APPLICATION_STATUS].text_body

        transport = SimpleNamespace(send_email=AsyncMock())
        worker = EmailOutboxWorker(
            session_factory=async_session_factory,
            email_service=transport,
            batch_size=10,
        )
        sent_count = run_async(worker.process_due_messages())
        assert sent_count == 3
        assert transport.send_email.await_count == 3

        sent_rows = run_async(_outbox_rows())
        assert len(sent_rows) == 3
        assert all(row.status == OutboxStatus.SENT.value for row in sent_rows)
        assert all(row.attempts == 1 for row in sent_rows)
        assert all(row.sent_at is not None for row in sent_rows)
        assert all(row.processing_started_at is None for row in sent_rows)
        assert all(row.last_error is None for row in sent_rows)

        recipients = [call.args[0] for call in transport.send_email.await_args_list]
        assert recipients.count(recruiter_email) == 1
        assert recipients.count(candidate_email) == 2
