from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import suppress
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AIError,
    ConflictException,
    EntityNotFoundException,
    InvalidTransitionException,
    MatchExplanationRefreshError,
    MatchExplanationRefreshInputError,
)
from app.domain import hiring
from app.domain.enums import ApplicationStatus, UserRole
from app.domain.models import Application as DomainApplication
from app.domain.models.base import DomainException, utc_now
from app.models import Application, Job, Resume, User
from app.models.ai_match_explanation import (
    AIMatchExplanationApplicationLease,
    AIMatchExplanationIdempotency,
)
from app.repositories import (
    ApplicationRepository,
    JobRepository,
    ResumeRepository,
)
from app.schemas.ai_explanation import ApplicationMatchExplanationResponse
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.ai_matching_service import AIMatchingService
from app.services.application_activity_service import record_activity
from app.services.job_service import JobService
from app.services.match_explanation_cache import MatchExplanationCache
from app.services.match_explanation_coordinator import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_IN_PROGRESS,
    MatchExplanationCoordinator,
    hash_idempotency_key,
)
from app.services.match_explanation_service import MatchExplanationService
from app.services.notification_service import NotificationService
from app.services.pipeline_email_service import schedule_application_status_email
from app.services.quota_enforcement_service import (
    QuotaEnforcementService,
    ReservationResult,
)
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

RECRUITER_MANAGED_STATUSES = frozenset(
    {
        ApplicationStatus.UNDER_REVIEW,
        ApplicationStatus.SHORTLISTED,
        ApplicationStatus.INTERVIEWING,
        ApplicationStatus.OFFERED,
        ApplicationStatus.ACCEPTED,
        ApplicationStatus.REJECTED,
    }
)

# Transitions the public recruiter status endpoint is allowed to publish.
#
# The pipeline model (see ``app.domain.models.application``) now records an
# atomic ``ApplicationActivity`` alongside every status change, so the full
# canonical pipeline is exposed deliberately. Every entry here is also a
# domain-valid transition (enforced by ``DomainApplication.transition_to``),
# and each is covered by tests. The list stays a strict allow-list - not simply
# "whatever the domain allows" - so a future domain change cannot silently
# widen the public API. In particular the "bypass" transitions
# (``UNDER_REVIEW -> OFFERED``, ``SHORTLISTED -> OFFERED``,
# ``UNDER_REVIEW -> INTERVIEWING``) and ``OFFERED -> INTERVIEWING`` are
# intentionally absent: they skip canonical stages and must not be reachable.
_PUBLISHED_RECRUITER_TRANSITIONS = frozenset(
    {
        (ApplicationStatus.APPLIED, ApplicationStatus.UNDER_REVIEW),
        (ApplicationStatus.APPLIED, ApplicationStatus.REJECTED),
        (ApplicationStatus.UNDER_REVIEW, ApplicationStatus.SHORTLISTED),
        (ApplicationStatus.UNDER_REVIEW, ApplicationStatus.REJECTED),
        (ApplicationStatus.SHORTLISTED, ApplicationStatus.INTERVIEWING),
        (ApplicationStatus.SHORTLISTED, ApplicationStatus.REJECTED),
        (ApplicationStatus.INTERVIEWING, ApplicationStatus.UNDER_REVIEW),
        (ApplicationStatus.INTERVIEWING, ApplicationStatus.OFFERED),
        (ApplicationStatus.INTERVIEWING, ApplicationStatus.ACCEPTED),
        (ApplicationStatus.INTERVIEWING, ApplicationStatus.REJECTED),
        (ApplicationStatus.OFFERED, ApplicationStatus.ACCEPTED),
        (ApplicationStatus.OFFERED, ApplicationStatus.REJECTED),
    }
)


@dataclass
class _ApplicationMatchInputs:
    """Server-resolved inputs shared by the match and explanation endpoints."""

    application: Application
    job: Job
    resume: Resume | None
    parsed_resume: ParsedResumeSchema | None
    parsed_job: ParsedJobSchema
    resume_vector: list[float] | None
    job_vector: list[float] | None


class ApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.applications = ApplicationRepository(session, Application)
        self.jobs = JobRepository(session, Job)

    async def apply_job(
        self,
        candidate_id: uuid.UUID,
        job_id: uuid.UUID,
    ) -> Application:
        job = await self.jobs.get_job_with_company_and_recruiters(job_id)
        if job is None:
            raise EntityNotFoundException(f"Job {job_id} not found")

        existing = await self.applications.get_by_candidate_and_job(
            candidate_id,
            job_id,
        )
        if existing is not None:
            raise ConflictException(
                f"Candidate {candidate_id} already applied to job {job_id}"
            )

        application = Application(
            candidate_id=candidate_id,
            job_id=job_id,
        )
        self.session.add(application)
        await self.session.flush()
        try:
            # Notify recruiter(s) about new application BEFORE commit
            notification_service = NotificationService(self.session)
            if job.company and job.company.recruiters:
                for recruiter in job.company.recruiters:
                    if recruiter.user_id:
                        await notification_service.create_notification(
                            user_id=recruiter.user_id,
                            title="Đơn ứng tuyển mới",
                            content=f"Ứng viên đã nộp đơn cho vị trí {job.title}",
                            notification_type="new_application",
                            entity_type="application",
                            entity_id=application.id,
                        )

            await self.session.commit()
            await self.session.refresh(
                application, attribute_names=["candidate"]
            )

        except Exception:
            await self.session.rollback()
            raise
        return application

    async def update_application_status(
        self,
        current_user: User,
        application_id: uuid.UUID,
        new_status: ApplicationStatus,
    ) -> Application:
        application = await self.applications.get_by_id_with_candidate_user_and_job(
            application_id
        )
        if application is None:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            )

        try:
            await JobService(self.session).get_recruiter_job_by_id(
                current_user,
                application.job_id,
            )
        except EntityNotFoundException:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            ) from None

        if new_status not in RECRUITER_MANAGED_STATUSES:
            raise InvalidTransitionException(
                f"Invalid Application status transition: "
                f"status {new_status.value!r} is not recruiter-managed."
            )

        old_status = application.status
        domain = DomainApplication(
            candidate_id=application.candidate_id,
            job_id=application.job_id,
            status=application.status,
        )
        try:
            domain.transition_to(new_status)
        except DomainException as exc:
            raise InvalidTransitionException(str(exc)) from exc

        # The domain accepts richer pipeline transitions than the API is
        # allowed to publish yet (see ``_PUBLISHED_RECRUITER_TRANSITIONS``).
        # Keep the pre-existing externally reachable behaviour until atomic
        # activity logging lands in the follow-on phase.
        if (old_status, new_status) not in _PUBLISHED_RECRUITER_TRANSITIONS:
            raise InvalidTransitionException(
                f"Invalid Application status transition from "
                f"{old_status.value!r} to {new_status.value!r}: this "
                f"transition is not available through this endpoint yet."
            )

        # Atomic conditional update to prevent lost updates
        # Only proceed if the status is still what we validated
        updated = await self.applications.try_update_status(
            application_id=application_id,
            expected_status=old_status,
            new_status=new_status,
        )
        if not updated:
            # Concurrent modification detected - the application status changed
            # after we read it but before we could update it
            raise ConflictException(
                f"Application {application_id} was modified concurrently. "
                f"Expected status {old_status.value}, but it has changed. "
                f"Please refresh and try again."
            )

        # Update local object and record the change + notifications atomically.
        # Everything below runs in the same transaction as the conditional
        # UPDATE: if the activity insert or the outbox enqueue fails, the status
        # change is rolled back with it.
        application.status = new_status
        job_title = application.job.title if application.job else "N/A"
        candidate = application.candidate
        candidate_user_id = candidate.user_id if candidate else None
        candidate_email = (
            candidate.user.email if candidate and candidate.user else None
        )
        try:
            await record_activity(
                self.session,
                application_id=application_id,
                actor_id=current_user.id,
                action_type=hiring.STATUS_CHANGED,
                from_status=old_status.value,
                to_status=new_status.value,
            )

            # Durably enqueue a candidate email for outcome statuses (offer /
            # accepted / rejected); other statuses are silent. Never contacts
            # the provider here - the outbox worker delivers after commit.
            await schedule_application_status_email(
                self.session,
                to_email=candidate_email,
                job_title=job_title,
                new_status=new_status,
                idempotency_key=(
                    f"application-status:{application_id}:{new_status.value}"
                ),
            )

            # Notify candidate about status change BEFORE commit
            notification_service = NotificationService(self.session)
            if candidate_user_id:
                await notification_service.create_notification(
                    user_id=candidate_user_id,
                    title="Cập nhật trạng thái đơn ứng tuyển",
                    content=f"Đơn ứng tuyển của bạn cho vị trí {job_title} đã thay đổi từ {old_status.value} sang {new_status.value}",
                    notification_type="application_status_changed",
                    entity_type="application",
                    entity_id=application.id,
                )

            await self.session.commit()
            await self.session.refresh(
                application, attribute_names=["candidate"]
            )

        except Exception:
            await self.session.rollback()
            raise
        return application

    async def withdraw_application(
        self,
        current_user: User,
        application_id: uuid.UUID,
    ) -> Application:
        """Candidate-owned withdrawal of their own application.

        Ownership is resolved from the DB (current_user -> candidate_profile
        -> application.candidate_id). Missing/foreign/nonexistent applications
        all surface as 404 so existence is never leaked across tenants.
        """
        user = await UserService(self.session).get_user_with_profile(
            current_user.id
        )
        if user is None or user.candidate_profile is None:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            )

        application = await self.applications.get_by_id_with_job_company_and_recruiters(application_id)
        if application is None:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            )
        if application.candidate_id != user.candidate_profile.id:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            )

        old_status = application.status
        domain = DomainApplication(
            candidate_id=application.candidate_id,
            job_id=application.job_id,
            status=application.status,
        )
        try:
            domain.transition_to(ApplicationStatus.WITHDRAWN)
        except DomainException as exc:
            raise InvalidTransitionException(str(exc)) from exc

        # Atomic conditional update: only withdraw while the application is
        # still in the status we validated, so a concurrent recruiter status
        # change cannot be silently overwritten (lost update).
        updated = await self.applications.try_update_status(
            application_id=application_id,
            expected_status=old_status,
            new_status=ApplicationStatus.WITHDRAWN,
        )
        if not updated:
            raise ConflictException(
                f"Application {application_id} was modified concurrently. "
                f"Please refresh and try again."
            )

        application.status = ApplicationStatus.WITHDRAWN
        try:
            await record_activity(
                self.session,
                application_id=application_id,
                actor_id=current_user.id,
                action_type=hiring.CANDIDATE_WITHDREW,
                from_status=old_status.value,
                to_status=ApplicationStatus.WITHDRAWN.value,
            )

            # Notify recruiter(s) about application withdrawal BEFORE commit
            notification_service = NotificationService(self.session)
            if application.job and application.job.company and application.job.company.recruiters:
                for recruiter in application.job.company.recruiters:
                    if recruiter.user_id:
                        await notification_service.create_notification(
                            user_id=recruiter.user_id,
                            title="Ứng viên rút đơn",
                            content=f"Ứng viên đã rút đơn ứng tuyển cho vị trí {application.job.title}",
                            notification_type="application_withdrawn",
                            entity_type="application",
                            entity_id=application.id,
                        )

            await self.session.commit()
            await self.session.refresh(
                application, attribute_names=["candidate"]
            )

        except Exception:
            await self.session.rollback()
            raise
        return application

    async def list_applications_by_job(
        self,
        job_id: uuid.UUID,
    ) -> list[Application]:
        return await self.applications.list_by_job(job_id)

    async def get_application_detail(
        self,
        current_user: User,
        application_id: uuid.UUID,
    ) -> tuple[Application, Resume | None]:
        """Resolve an application for a recruiter/admin with ownership enforced.

        Admin may access any application; a recruiter may only access
        applications on their own company's jobs. Missing, soft-deleted, or
        unowned applications all surface as 404 so existence is never leaked.
        Returns the application together with the candidate's primary resume
        (``None`` when the candidate has no resume), so the digital CV can be
        rendered from ``Resume.parsed_data``.
        """
        application = await self.applications.get_by_id_with_candidate(
            application_id
        )
        if application is None:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            )

        try:
            await JobService(self.session).get_recruiter_job_by_id(
                current_user,
                application.job_id,
            )
        except EntityNotFoundException:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            ) from None

        resume = await ResumeRepository(self.session, Resume).get_primary_by_candidate(
            application.candidate_id
        )
        return application, resume

    async def verify_application_access(
        self,
        current_user: User,
        application_id: uuid.UUID,
    ) -> Application:
        """Verify recruiter/admin ownership before any refresh side effect.

        Missing and foreign applications deliberately collapse to the same
        404. This method performs no Redis, idempotency-registry or quota
        operation, so an unauthorized request cannot touch coordination state.
        """
        application = await self.applications.get_by_id_with_candidate(
            application_id
        )
        if application is None:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            )
        try:
            await JobService(self.session).get_recruiter_job_by_id(
                current_user,
                application.job_id,
            )
        except EntityNotFoundException:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            ) from None
        return application

    async def _resolve_match_inputs(
        self,
        current_user: User,
        application_id: uuid.UUID,
        matching_service: AIMatchingService,
        *,
        resolve_vectors: bool = True,
    ) -> _ApplicationMatchInputs:
        """Resolve every input the matching/explanation flow needs.

        Recruiter/admin only, with ownership enforced exactly like
        ``get_application_detail`` (foreign/missing applications surface as
        404). The candidate resume and job are resolved server-side from the
        application. Vectors are resolved from the vector repository (falling
        back to on-demand embedding) only when ``resolve_vectors`` is true, so
        a cache lookup can happen before any embedding work. Missing or
        unparseable resume data degrades gracefully instead of crashing.
        """
        application = await self.applications.get_by_id_with_candidate(
            application_id
        )
        if application is None:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            )

        try:
            job = await JobService(self.session).get_recruiter_job_by_id(
                current_user,
                application.job_id,
            )
        except EntityNotFoundException:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            ) from None

        resume = await ResumeRepository(self.session, Resume).get_primary_by_candidate(
            application.candidate_id
        )

        parsed_resume = None
        if resume is not None and resume.parsed_data:
            try:
                parsed_resume = ParsedResumeSchema.model_validate(
                    resume.parsed_data
                )
            except ValidationError:
                parsed_resume = None

        parsed_job = ParsedJobSchema(
            title=job.title,
            summary=job.description,
            required_skills=[skill.name for skill in job.required_skills] if job.required_skills else [],
            preferred_skills=[skill.name for skill in job.preferred_skills] if job.preferred_skills else [],
            minimum_years_experience=job.minimum_years_experience,
            education_level=job.education_level,
            employment_type=job.job_type.value if hasattr(job.job_type, 'value') else job.job_type,
            workplace_type=job.workplace_type.value if hasattr(job.workplace_type, 'value') else job.workplace_type,
            location=job.location,
            city=job.location,
        )

        inputs = _ApplicationMatchInputs(
            application=application,
            job=job,
            resume=resume,
            parsed_resume=parsed_resume,
            parsed_job=parsed_job,
            resume_vector=None,
            job_vector=None,
        )
        if resolve_vectors:
            await self._resolve_match_vectors(inputs, matching_service)
        return inputs

    async def _resolve_match_vectors(
        self,
        inputs: _ApplicationMatchInputs,
        matching_service: AIMatchingService,
    ) -> None:
        """Populate missing resume/job vectors on the resolved inputs."""
        if inputs.parsed_resume is not None and inputs.resume_vector is None:
            inputs.resume_vector = await self._resolve_vector(
                matching_service,
                "resumes",
                inputs.application.candidate_id,
            )
            if inputs.resume_vector is None:
                inputs.resume_vector = (
                    await matching_service.embedding_service.embed_resume(
                        inputs.parsed_resume
                    )
                )
        if inputs.job_vector is None:
            inputs.job_vector = await self._resolve_vector(
                matching_service,
                "jobs",
                inputs.application.job_id,
            )
            if inputs.job_vector is None:
                inputs.job_vector = (
                    await matching_service.embedding_service.embed_job(
                        inputs.parsed_job
                    )
                )

    async def get_application_match(
        self,
        current_user: User,
        application_id: uuid.UUID,
        matching_service: AIMatchingService,
    ) -> MatchResultSchema:
        """Compute the deterministic AI match score for an application.

        Scoring is delegated to the existing ``MatchingEngine`` (no duplicated
        logic here); ownership and data resolution happen in
        ``_resolve_match_inputs``.
        """
        inputs = await self._resolve_match_inputs(
            current_user, application_id, matching_service
        )
        return matching_service.matching_engine.match_resume_to_job(
            resume=inputs.parsed_resume,
            job=inputs.parsed_job,
            resume_vector=inputs.resume_vector,
            job_vector=inputs.job_vector,
        )

    async def get_application_match_explanation(
        self,
        current_user: User,
        application_id: uuid.UUID,
        matching_service: AIMatchingService,
        explanation_service: MatchExplanationService | None = None,
        cache_service: MatchExplanationCache | None = None,
    ) -> ApplicationMatchExplanationResponse:
        """Build an evidence-grounded explanation for an application match.

        Recruiter/admin only, with the same ownership guarantees as
        ``get_application_match``. Ownership and trusted data are resolved
        before any cache lookup. The regular GET path always uses the explicit
        deterministic-only build path: a cache miss or Redis failure can never
        invoke an external AI provider.

        The overall score is computed by the existing ``MatchingEngine`` and
        copied verbatim into the explanation; it is never recalculated by the
        explanation layer.
        """
        inputs = await self._resolve_match_inputs(
            current_user,
            application_id,
            matching_service,
            resolve_vectors=False,
        )
        service = explanation_service or MatchExplanationService()

        cache_key = None
        if cache_service is not None:
            cache_key = cache_service.build_key(
                inputs.application.id,
                inputs.parsed_resume,
                inputs.parsed_job,
            )
            if cache_key is not None:
                cached = await cache_service.get(
                    cache_key, application_id=inputs.application.id
                )
                if (
                    cached is not None
                    and cached.application_id == inputs.application.id
                ):
                    return cached

        await self._resolve_match_vectors(inputs, matching_service)
        match_result = matching_service.matching_engine.match_resume_to_job(
            resume=inputs.parsed_resume,
            job=inputs.parsed_job,
            resume_vector=inputs.resume_vector,
            job_vector=inputs.job_vector,
        )
        response = await service.build_deterministic_explanation(
            application_id=inputs.application.id,
            match_result=match_result,
            parsed_resume=inputs.parsed_resume,
            parsed_job=inputs.parsed_job,
        )

        if cache_service is not None and cache_key is not None:
            await cache_service.store(
                cache_key, response, application_id=inputs.application.id
            )
        return response

    async def refresh_application_match_explanation(
        self,
        current_user: User,
        application_id: uuid.UUID,
        *,
        idempotency_key: str,
        matching_service: AIMatchingService,
        explanation_service: MatchExplanationService,
        cache_service: MatchExplanationCache,
        quota_service: QuotaEnforcementService | None = None,
        coordinator: MatchExplanationCoordinator | None = None,
    ) -> ApplicationMatchExplanationResponse:
        """Run the quota-controlled AI refresh for one application.

        Without ``coordinator`` this preserves the internal 2C-1 behavior used
        by service-level callers. Supplying a coordinator enables the full 2C-2
        durable idempotency, SQL application lease, Redis lock, heartbeat,
        pre-quota/pre-provider fences and fenced cache publication contract.

        Ownership, trusted application/CV/job data and the content-addressed
        cache key are resolved server-side before any quota or provider work.
        A valid, validated AI narrative consumes one quota unit; provider or
        narrative failures release the reservation and raise a typed
        ``MatchExplanationRefreshError``. Cache-write failures never turn a
        successful AI generation into a quota refund.
        """
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise MatchExplanationRefreshInputError(
                "An idempotency key is required for an AI match refresh."
            )
        if len(idempotency_key) > 255:
            raise MatchExplanationRefreshInputError(
                "The idempotency key is too long for an AI match refresh."
            )

        if coordinator is not None:
            return await self._refresh_application_match_explanation_2c2(
                current_user=current_user,
                application_id=application_id,
                idempotency_key=idempotency_key.strip(),
                matching_service=matching_service,
                explanation_service=explanation_service,
                cache_service=cache_service,
                quota_service=quota_service,
                coordinator=coordinator,
            )

        inputs = await self._resolve_match_inputs(
            current_user,
            application_id,
            matching_service,
            resolve_vectors=False,
        )
        if inputs.parsed_resume is None:
            if inputs.resume is None or not inputs.resume.parsed_data:
                raise MatchExplanationRefreshInputError(
                    "A parsed CV is required to refresh the match explanation."
                )
            raise MatchExplanationRefreshInputError(
                "The candidate CV could not be parsed for an AI match refresh."
            )

        try:
            cache_key = cache_service.build_key(
                inputs.application.id,
                inputs.parsed_resume,
                inputs.parsed_job,
            )
        except Exception as exc:  # noqa: BLE001 - defensive cache boundary
            raise MatchExplanationRefreshInputError(
                "The trusted CV and job data cannot be cached safely."
            ) from exc
        if cache_key is None:
            raise MatchExplanationRefreshInputError(
                "The trusted CV and job data cannot be cached safely."
            )

        await self._resolve_match_vectors(inputs, matching_service)
        match_result = matching_service.matching_engine.match_resume_to_job(
            resume=inputs.parsed_resume,
            job=inputs.parsed_job,
            resume_vector=inputs.resume_vector,
            job_vector=inputs.job_vector,
        )

        quota = quota_service or QuotaEnforcementService(self.session)
        reservation = await quota.reserve_ai_quota(
            user_id=current_user.id,
            idempotency_key=idempotency_key,
            reference_id=inputs.application.id,
            is_admin=current_user.role == UserRole.ADMIN,
        )
        await self._commit_refresh()

        try:
            response = await explanation_service.build_refresh_explanation(
                application_id=inputs.application.id,
                match_result=match_result,
                parsed_resume=inputs.parsed_resume,
                parsed_job=inputs.parsed_job,
            )
            if (
                response.summary_source != "ai_generated"
                or not response.summary.strip()
            ):
                raise MatchExplanationRefreshError("narrative_rejected")
        except asyncio.CancelledError:
            await self._release_refresh_reservation_on_cancellation(
                quota, reservation
            )
            raise
        except MatchExplanationRefreshError:
            await self._release_refresh_reservation(quota, reservation)
            raise
        except AIError as exc:
            await self._release_refresh_reservation(quota, reservation)
            raise MatchExplanationRefreshError("provider_error") from exc
        except Exception as exc:
            await self._release_refresh_reservation(quota, reservation)
            raise MatchExplanationRefreshError("explanation_failed") from exc

        try:
            await quota.finalize_reservation(
                reservation.usage_id, success=True
            )
            await self._commit_refresh()
        except asyncio.CancelledError:
            await self._release_refresh_reservation_on_cancellation(
                quota, reservation
            )
            raise
        except Exception as exc:
            await self._rollback_refresh()
            try:
                await self._release_refresh_reservation(quota, reservation)
            except MatchExplanationRefreshError as release_exc:
                raise release_exc from exc
            raise MatchExplanationRefreshError(
                "quota_finalize_failed"
            ) from exc

        stored = False
        try:
            stored = await cache_service.store(
                cache_key,
                response,
                application_id=inputs.application.id,
            )
        except Exception as exc:  # noqa: BLE001 - never fail a valid refresh
            logger.warning(
                "match_explanation_refresh_cache_set_failed "
                "application_id=%s error=%s",
                inputs.application.id,
                type(exc).__name__,
            )

        if stored:
            return response.model_copy(update={"cache_state": "cached"})
        return response

    async def _refresh_application_match_explanation_2c2(
        self,
        *,
        current_user: User,
        application_id: uuid.UUID,
        idempotency_key: str,
        matching_service: AIMatchingService,
        explanation_service: MatchExplanationService,
        cache_service: MatchExplanationCache,
        quota_service: QuotaEnforcementService | None,
        coordinator: MatchExplanationCoordinator,
    ) -> ApplicationMatchExplanationResponse:
        inputs = await self._resolve_match_inputs(
            current_user,
            application_id,
            matching_service,
            resolve_vectors=False,
        )
        if inputs.parsed_resume is None:
            if inputs.resume is None or not inputs.resume.parsed_data:
                raise MatchExplanationRefreshInputError(
                    "A parsed CV is required to refresh the match explanation."
                )
            raise MatchExplanationRefreshInputError(
                "The candidate CV could not be parsed for an AI match refresh."
            )

        try:
            cache_key = cache_service.build_key(
                inputs.application.id,
                inputs.parsed_resume,
                inputs.parsed_job,
            )
        except Exception as exc:  # noqa: BLE001 - defensive cache boundary
            raise MatchExplanationRefreshInputError(
                "The trusted CV and job data cannot be cached safely."
            ) from exc
        if cache_key is None:
            raise MatchExplanationRefreshInputError(
                "The trusted CV and job data cannot be cached safely."
            )

        key_hash = hash_idempotency_key(current_user.id, idempotency_key)

        await coordinator.ensure_redis_available()
        cached = await coordinator.read_idempotency_cache(
            current_user.id,
            key_hash,
            inputs.application.id,
        )
        if cached is not None:
            return cached

        current_task = asyncio.current_task()
        active_task = coordinator.get_active_task(inputs.application.id)
        if (
            active_task is not None
            and active_task is not current_task
            and not active_task.done()
        ):
            raise MatchExplanationRefreshError(
                "application_refresh_in_progress",
                http_status=409,
                retry_after=5,
            )

        owner_token = str(uuid.uuid4())
        await coordinator.acquire_lock(inputs.application.id, owner_token)

        quota = quota_service or QuotaEnforcementService(self.session)
        reservation: ReservationResult | None = None
        record_id: uuid.UUID | None = None
        heartbeat_task: asyncio.Task[None] | None = None
        finalized = False

        try:
            record_id, replay = await coordinator.register_refresh(
                self.session,
                user_id=current_user.id,
                key_hash=key_hash,
                application_id=inputs.application.id,
                owner_token=owner_token,
            )
            if replay is not None:
                await self._rollback_refresh()
                return replay
            await self._commit_refresh()

            await self._assert_active_ownership(
                record_id=record_id,
                application_id=inputs.application.id,
                owner_token=owner_token,
            )

            await self._resolve_match_vectors(inputs, matching_service)
            match_result = (
                matching_service.matching_engine.match_resume_to_job(
                    resume=inputs.parsed_resume,
                    job=inputs.parsed_job,
                    resume_vector=inputs.resume_vector,
                    job_vector=inputs.job_vector,
                )
            )

            reservation = await quota.reserve_ai_quota(
                user_id=current_user.id,
                idempotency_key=idempotency_key,
                reference_id=inputs.application.id,
                is_admin=current_user.role == UserRole.ADMIN,
            )
            await self._commit_refresh()

            await self._assert_active_ownership(
                record_id=record_id,
                application_id=inputs.application.id,
                owner_token=owner_token,
            )

            if current_task is not None:
                heartbeat_task = coordinator.start_heartbeat(
                    worker_task=current_task,
                    record_id=record_id,
                    application_id=inputs.application.id,
                    user_id=current_user.id,
                    key_hash=key_hash,
                    owner_token=owner_token,
                )

            response = await explanation_service.build_refresh_explanation(
                application_id=inputs.application.id,
                match_result=match_result,
                parsed_resume=inputs.parsed_resume,
                parsed_job=inputs.parsed_job,
            )
            if (
                response.summary_source != "ai_generated"
                or not response.summary.strip()
            ):
                raise MatchExplanationRefreshError("narrative_rejected")

            await self._stop_heartbeat(heartbeat_task)
            heartbeat_task = None

            await self._finalize_refresh(
                record_id=record_id,
                application_id=inputs.application.id,
                owner_token=owner_token,
                reservation=reservation,
                quota=quota,
                response=response,
                cache_service=cache_service,
            )
            finalized = True

            await coordinator.publish_fenced_cache(
                application_id=inputs.application.id,
                content_key=cache_key,
                user_id=current_user.id,
                key_hash=key_hash,
                owner_token=owner_token,
                response=response,
            )
            # This request generated the response; only replay paths report a
            # cached state. Cache publication is opportunistic and never turns
            # a fresh generation into a cache hit.
            return response
        except asyncio.CancelledError:
            if record_id is not None and not finalized:
                try:
                    await self._fenced_release_reservation(
                        record_id=record_id,
                        application_id=inputs.application.id,
                        owner_token=owner_token,
                        reservation=reservation,
                        quota=quota,
                    )
                except Exception:  # noqa: BLE001 - preserve cancellation
                    logger.error(
                        "match_explanation_refresh_cancel_cleanup_failed "
                        "application_id=%s",
                        inputs.application.id,
                    )
            elif record_id is None:
                await self._rollback_refresh()
            raise
        except BaseException:
            if record_id is not None and not finalized:
                await self._fenced_release_reservation(
                    record_id=record_id,
                    application_id=inputs.application.id,
                    owner_token=owner_token,
                    reservation=reservation,
                    quota=quota,
                )
            elif record_id is None:
                await self._rollback_refresh()
            raise
        finally:
            await self._stop_heartbeat(heartbeat_task)
            await coordinator.release_lock(
                inputs.application.id, owner_token
            )

    async def _assert_active_ownership(
        self,
        *,
        record_id: uuid.UUID,
        application_id: uuid.UUID,
        owner_token: str,
    ) -> None:
        now = utc_now()
        idempotency_id = await self.session.scalar(
            select(AIMatchExplanationIdempotency.id)
            .where(
                AIMatchExplanationIdempotency.id == record_id,
                AIMatchExplanationIdempotency.application_id
                == application_id,
                AIMatchExplanationIdempotency.owner_token == owner_token,
                AIMatchExplanationIdempotency.status == STATUS_IN_PROGRESS,
                AIMatchExplanationIdempotency.lease_expires_at > now,
            )
            .limit(1)
        )
        if idempotency_id is None:
            raise MatchExplanationRefreshError(
                "refresh_ownership_lost",
                http_status=409,
                retry_after=5,
            )
        lease_application_id = await self.session.scalar(
            select(AIMatchExplanationApplicationLease.application_id)
            .where(
                AIMatchExplanationApplicationLease.application_id
                == application_id,
                AIMatchExplanationApplicationLease.owner_token
                == owner_token,
                AIMatchExplanationApplicationLease.lease_expires_at > now,
            )
            .limit(1)
        )
        if lease_application_id is None:
            raise MatchExplanationRefreshError(
                "refresh_ownership_lost",
                http_status=409,
                retry_after=5,
            )

    async def _fenced_release_reservation(
        self,
        *,
        record_id: uuid.UUID,
        application_id: uuid.UUID,
        owner_token: str,
        reservation: ReservationResult | None,
        quota: QuotaEnforcementService,
    ) -> bool:
        await self._rollback_refresh()
        try:
            result = await self.session.execute(
                update(AIMatchExplanationIdempotency)
                .where(
                    AIMatchExplanationIdempotency.id == record_id,
                    AIMatchExplanationIdempotency.owner_token == owner_token,
                    AIMatchExplanationIdempotency.status
                    == STATUS_IN_PROGRESS,
                )
                .values(
                    status=STATUS_FAILED,
                    response_payload=None,
                    completed_at=None,
                    updated_at=utc_now(),
                )
            )
            if result.rowcount != 1:
                await self._rollback_refresh()
                logger.warning(
                    "match_explanation_refresh_fenced_out application_id=%s",
                    application_id,
                )
                return False

            if reservation is not None:
                await quota.release_reservation(reservation.usage_id)

            await self.session.execute(
                delete(AIMatchExplanationApplicationLease).where(
                    AIMatchExplanationApplicationLease.application_id
                    == application_id,
                    AIMatchExplanationApplicationLease.owner_token
                    == owner_token,
                )
            )
            await self._commit_refresh()
            return True
        except asyncio.CancelledError:
            await self._rollback_refresh()
            raise
        except Exception as exc:  # noqa: BLE001 - surface controlled cleanup
            await self._rollback_refresh()
            logger.error(
                "match_explanation_refresh_cleanup_failed application_id=%s "
                "error=%s",
                application_id,
                type(exc).__name__,
            )
            raise MatchExplanationRefreshError(
                "refresh_cleanup_failed", http_status=503
            ) from exc

    async def _finalize_refresh(
        self,
        *,
        record_id: uuid.UUID,
        application_id: uuid.UUID,
        owner_token: str,
        reservation: ReservationResult,
        quota: QuotaEnforcementService,
        response: ApplicationMatchExplanationResponse,
        cache_service: MatchExplanationCache,
    ) -> None:
        now = utc_now()
        try:
            payload = cache_service.serialize_response(response)
        except Exception as exc:  # noqa: BLE001 - never finalize unserializable
            raise MatchExplanationRefreshError(
                "refresh_response_serialization_failed", http_status=500
            ) from exc

        try:
            result = await self.session.execute(
                update(AIMatchExplanationIdempotency)
                .where(
                    AIMatchExplanationIdempotency.id == record_id,
                    AIMatchExplanationIdempotency.owner_token == owner_token,
                    AIMatchExplanationIdempotency.status
                    == STATUS_IN_PROGRESS,
                    AIMatchExplanationIdempotency.lease_expires_at > now,
                )
                .values(
                    status=STATUS_COMPLETED,
                    response_payload=payload,
                    completed_at=now,
                    updated_at=now,
                )
            )
            if result.rowcount != 1:
                await self._rollback_refresh()
                raise MatchExplanationRefreshError(
                    "refresh_ownership_lost",
                    http_status=409,
                    retry_after=5,
                )

            await quota.finalize_reservation(
                reservation.usage_id, success=True
            )
            lease_result = await self.session.execute(
                delete(AIMatchExplanationApplicationLease).where(
                    AIMatchExplanationApplicationLease.application_id
                    == application_id,
                    AIMatchExplanationApplicationLease.owner_token
                    == owner_token,
                )
            )
            if lease_result.rowcount != 1:
                await self._rollback_refresh()
                raise MatchExplanationRefreshError(
                    "refresh_ownership_lost",
                    http_status=409,
                    retry_after=5,
                )
            await self._commit_refresh()
        except asyncio.CancelledError:
            await self._rollback_refresh()
            raise
        except MatchExplanationRefreshError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface controlled failure
            await self._rollback_refresh()
            logger.error(
                "match_explanation_refresh_finalize_failed application_id=%s "
                "error=%s",
                application_id,
                type(exc).__name__,
            )
            raise MatchExplanationRefreshError(
                "refresh_finalize_failed", http_status=503
            ) from exc

    @staticmethod
    async def _stop_heartbeat(
        heartbeat_task: asyncio.Task[None] | None,
    ) -> None:
        if heartbeat_task is None or heartbeat_task.done():
            return
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task

    async def _commit_refresh(self) -> None:
        try:
            await self.session.commit()
        except BaseException:
            await self._rollback_refresh()
            raise

    async def _rollback_refresh(self) -> None:
        try:
            await self.session.rollback()
        except Exception:  # noqa: BLE001 - preserve the original failure
            logger.error("match_explanation_refresh_rollback_failed")

    async def _release_refresh_reservation(
        self,
        quota_service: QuotaEnforcementService,
        reservation: ReservationResult,
    ) -> None:
        try:
            await quota_service.release_reservation(reservation.usage_id)
            await self.session.commit()
        except asyncio.CancelledError:
            await self._rollback_refresh()
            raise
        except Exception as exc:  # noqa: BLE001 - surface a controlled error
            await self._rollback_refresh()
            logger.error(
                "match_explanation_refresh_quota_release_failed "
                "usage_id=%s error=%s",
                reservation.usage_id,
                type(exc).__name__,
            )
            raise MatchExplanationRefreshError(
                "quota_release_failed", http_status=503
            ) from exc

    async def _release_refresh_reservation_on_cancellation(
        self,
        quota_service: QuotaEnforcementService,
        reservation: ReservationResult,
    ) -> None:
        try:
            await self._release_refresh_reservation(
                quota_service, reservation
            )
        except BaseException as exc:  # noqa: BLE001 - preserve cancellation
            logger.error(
                "match_explanation_refresh_quota_release_failed_on_cancel "
                "usage_id=%s error=%s",
                reservation.usage_id,
                type(exc).__name__,
            )

    @staticmethod
    async def _resolve_vector(
        matching_service: AIMatchingService,
        collection_name: str,
        point_id: uuid.UUID,
    ) -> list[float] | None:
        """Return the stored vector for a point or ``None`` when missing.

        Qdrant connectivity failures raise ``AIError`` (surfaced by the API
        layer as a controlled error); only a missing point is treated as
        ``None`` so the caller can embed on demand.
        """
        retrieved = await matching_service.vector_repository.retrieve_vector(
            collection_name=collection_name,
            point_id=point_id,
        )
        if retrieved is None:
            return None
        return retrieved["vector"]

    async def list_my_applications(
        self,
        current_user: User,
        skip: int = 0,
        limit: int = 20,
        job_id: uuid.UUID | None = None,
    ) -> list[Application]:
        """Return the authenticated candidate's applications, newest first.

        Ownership is always resolved from the DB (current_user ->
        candidate_profile.id). A user without a candidate profile has no
        applications, so it is treated as an empty history.

        If job_id is provided, filters to only return the application for that job.
        """
        user = await UserService(self.session).get_user_with_profile(
            current_user.id
        )
        if user is None or user.candidate_profile is None:
            return []

        if job_id is not None:
            application = await self.applications.get_by_candidate_and_job(
                user.candidate_profile.id,
                job_id,
            )
            return [application] if application else []

        return await self.applications.list_by_candidate_paginated(
            user.candidate_profile.id,
            skip=skip,
            limit=limit,
        )
