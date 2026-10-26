from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    EntityNotFoundException,
    InvalidTransitionException,
)
from app.domain import hiring
from app.domain.enums import ApplicationStatus, InterviewStatus, InterviewType
from app.domain.models import Application as DomainApplication
from app.domain.models.base import DomainException
from app.models import Application, Interview, Job, User
from app.repositories import ApplicationRepository, InterviewRepository
from app.schemas.interview import (
    CandidateInterviewRead,
    InterviewActionRequest,
    InterviewCreate,
    InterviewRead,
    InterviewUpdate,
)
from app.services.application_activity_service import record_activity
from app.services.job_service import JobService
from app.services.notification_service import NotificationService
from app.services.pipeline_email_service import schedule_interview_email
from app.services.pipeline_realtime import (
    ACTION_INTERVIEW_CANCELLED,
    ACTION_INTERVIEW_CONFIRMED,
    ACTION_INTERVIEW_DECLINED,
    ACTION_INTERVIEW_SCHEDULED,
    ACTION_INTERVIEW_UPDATED,
    schedule_application_pipeline_event,
)
from app.services.user_service import UserService

# An interview in any of these states still requires the application to remain
# in the INTERVIEWING stage. Declined/cancelled outcomes are terminal, while
# soft-deleted interviews are excluded by the repository query itself.
ACTIVE_INTERVIEW_STATUSES = frozenset(
    {
        InterviewStatus.SCHEDULED,
        InterviewStatus.CANDIDATE_CONFIRMED,
        InterviewStatus.COMPLETED,
    }
)

MUTABLE_INTERVIEW_STATUSES = frozenset(
    {
        InterviewStatus.SCHEDULED,
        InterviewStatus.CANDIDATE_CONFIRMED,
    }
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InterviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.interviews = InterviewRepository(session, Interview)
        self.applications = ApplicationRepository(session, Application)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def _ends_at(
        cls,
        scheduled_at: datetime,
        duration_minutes: int,
    ) -> datetime:
        return cls._as_utc(scheduled_at) + timedelta(minutes=duration_minutes)

    @classmethod
    def _has_ended(
        cls,
        scheduled_at: datetime,
        duration_minutes: int,
    ) -> bool:
        return cls._ends_at(scheduled_at, duration_minutes) <= cls._as_utc(
            _utc_now()
        )

    @staticmethod
    def _candidate_email(application: Application) -> str | None:
        """Return the candidate's email from the eagerly-loaded relationship.

        ``application`` is loaded via
        ``get_by_id_with_candidate_job_company_and_recruiters``, which eager-loads
        ``candidate.user``, so this never triggers a lazy load (and never a
        ``MissingGreenlet``) in async code.
        """
        candidate = application.candidate
        if candidate is None or candidate.user is None:
            return None
        return candidate.user.email

    async def _reconcile_application_interview_stage(
        self,
        application: Application,
    ) -> bool:
        """Return an application to screening when no active interviews remain.

        The decline/cancellation mutation must already be flushed so the
        repository query sees its terminal outcome. Soft-deleted interviews are
        excluded by ``list_by_application``. The status update is conditional on
        the application still being ``interviewing`` so a concurrent transition
        is never overwritten.

        Returns ``True`` only when this call performed the transition.
        """
        if application.status != ApplicationStatus.INTERVIEWING:
            return False

        remaining = await self.interviews.list_by_application(application.id)
        if any(
            interview.status in ACTIVE_INTERVIEW_STATUSES
            for interview in remaining
        ):
            return False

        domain = DomainApplication(
            candidate_id=application.candidate_id,
            job_id=application.job_id,
            status=application.status,
        )
        try:
            domain.transition_to(ApplicationStatus.UNDER_REVIEW)
        except DomainException as exc:
            raise InvalidTransitionException(str(exc)) from exc

        updated = await self.applications.try_update_status(
            application_id=application.id,
            expected_status=ApplicationStatus.INTERVIEWING,
            new_status=ApplicationStatus.UNDER_REVIEW,
        )
        if not updated:
            # A concurrent request changed the stage first. Reload the
            # authoritative value so callers publish the real final status.
            await self.session.refresh(application, attribute_names=["status"])
            return False

        application.status = ApplicationStatus.UNDER_REVIEW
        return True

    async def schedule_interview(
        self,
        current_user: User,
        application_id: uuid.UUID,
        data: InterviewCreate,
    ) -> InterviewRead:
        """Schedule a new interview for an application.

        Recruiter/admin only. Ownership is enforced via JobService.
        Validates scheduled_at is not in the past.
        Transitions application to INTERVIEWING if not already in that state.
        """
        # Validate scheduled_at is not in the past
        if self._as_utc(data.scheduled_at) < _utc_now():
            raise InvalidTransitionException(
                "Không thể lên lịch phỏng vấn trong quá khứ. Vui lòng chọn thời gian trong tương lai."
            )

        application = await self.applications.get_by_id_with_candidate_job_company_and_recruiters(application_id)
        if application is None:
            raise EntityNotFoundException(f"Application {application_id} not found")

        # Verify ownership
        try:
            await JobService(self.session).get_recruiter_job_by_id(
                current_user,
                application.job_id,
            )
        except EntityNotFoundException:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            ) from None

        # Create interview
        interview = Interview(
            application_id=application_id,
            scheduled_at=data.scheduled_at,
            duration_minutes=data.duration_minutes,
            interview_type=InterviewType(data.interview_type),
            meeting_url=str(data.meeting_url) if data.meeting_url else None,
            location=data.location,
            notes=data.notes,
            status=InterviewStatus.SCHEDULED,
        )
        self.session.add(interview)
        await self.session.flush()

        previous_app_status = application.status

        # Transition application to INTERVIEWING if not already
        if application.status != ApplicationStatus.INTERVIEWING:
            domain = DomainApplication(
                candidate_id=application.candidate_id,
                job_id=application.job_id,
                status=application.status,
            )
            try:
                if domain.status == ApplicationStatus.APPLIED:
                    domain.transition_to(ApplicationStatus.UNDER_REVIEW)
                if domain.status == ApplicationStatus.UNDER_REVIEW:
                    domain.transition_to(ApplicationStatus.SHORTLISTED)
                
                domain.transition_to(ApplicationStatus.INTERVIEWING)
            except DomainException as exc:
                raise InvalidTransitionException(str(exc)) from exc
            application.status = domain.status

        job_title = application.job.title if application.job else "N/A"

        try:
            if application.status != previous_app_status:
                await record_activity(
                    self.session,
                    application_id=application_id,
                    actor_id=current_user.id,
                    action_type=hiring.STATUS_CHANGED,
                    from_status=previous_app_status.value,
                    to_status=application.status.value,
                )
            await record_activity(
                self.session,
                application_id=application_id,
                actor_id=current_user.id,
                action_type=hiring.INTERVIEW_SCHEDULED,
                metadata={"interview_id": str(interview.id)},
            )

            await schedule_interview_email(
                self.session,
                to_email=self._candidate_email(application),
                job_title=job_title,
                scheduled_at=interview.scheduled_at,
                event="scheduled",
                idempotency_key=f"interview:{interview.id}:scheduled",
            )

            # Notify candidate about scheduled interview BEFORE commit
            notification_service = NotificationService(self.session)
            candidate_user_id = application.candidate.user_id if application.candidate else None
            if candidate_user_id:
                await notification_service.create_notification(
                    user_id=candidate_user_id,
                    title="Lịch phỏng vấn mới",
                    content=f"Bạn đã được mời phỏng vấn cho vị trí {job_title} vào lúc {interview.scheduled_at.strftime('%d/%m/%Y %H:%M')}",
                    notification_type="interview_scheduled",
                    entity_type="interview",
                    entity_id=interview.id,
                )

            await schedule_application_pipeline_event(
                self.session,
                application=application,
                action=ACTION_INTERVIEW_SCHEDULED,
                from_status=previous_app_status,
                to_status=application.status,
                candidate_user_id=candidate_user_id,
            )

            await self.session.commit()
            await self.session.refresh(interview)

        except Exception:
            await self.session.rollback()
            raise

        return InterviewRead.model_validate(interview)

    async def update_interview(
        self,
        current_user: User,
        interview_id: uuid.UUID,
        data: InterviewUpdate,
    ) -> InterviewRead:
        """Update an existing interview.

        Recruiter/admin only. Ownership enforced via application -> job.
        Reschedule keeps status as SCHEDULED.
        """
        interview = await self.interviews.get_by_id_with_application(interview_id)
        if interview is None:
            raise EntityNotFoundException(f"Interview {interview_id} not found")

        # Verify ownership through application -> job
        application = await self.applications.get_by_id_with_candidate_job_company_and_recruiters(interview.application_id)
        if application is None:
            raise EntityNotFoundException(
                f"Application {interview.application_id} not found"
            )

        try:
            await JobService(self.session).get_recruiter_job_by_id(
                current_user,
                application.job_id,
            )
        except EntityNotFoundException:
            raise EntityNotFoundException(
                f"Interview {interview_id} not found"
            ) from None

        if interview.status not in MUTABLE_INTERVIEW_STATUSES:
            raise InvalidTransitionException(
                "Không thể cập nhật buổi phỏng vấn ở trạng thái "
                f"{interview.status.value}."
            )
        if self._has_ended(
            interview.scheduled_at,
            interview.duration_minutes,
        ):
            raise InvalidTransitionException(
                "Không thể cập nhật buổi phỏng vấn đã kết thúc."
            )

        now = _utc_now()
        if (
            data.scheduled_at is not None
            and self._as_utc(data.scheduled_at) < now
        ):
            raise InvalidTransitionException(
                "Không thể lên lịch phỏng vấn trong quá khứ. Vui lòng chọn thời gian trong tương lai."
            )

        proposed_scheduled_at = (
            data.scheduled_at
            if data.scheduled_at is not None
            else interview.scheduled_at
        )
        proposed_duration = (
            data.duration_minutes
            if data.duration_minutes is not None
            else interview.duration_minutes
        )
        if self._ends_at(proposed_scheduled_at, proposed_duration) <= now:
            raise InvalidTransitionException(
                "Không thể lên lịch phỏng vấn đã kết thúc. Vui lòng chọn thời gian trong tương lai."
            )

        original_scheduled_at = interview.scheduled_at

        # Update fields
        if data.scheduled_at is not None:
            interview.scheduled_at = data.scheduled_at
        if data.duration_minutes is not None:
            interview.duration_minutes = data.duration_minutes
        if data.interview_type is not None:
            interview.interview_type = InterviewType(data.interview_type)
        if data.meeting_url is not None:
            interview.meeting_url = str(data.meeting_url)
        if data.location is not None:
            interview.location = data.location
        if data.notes is not None:
            interview.notes = data.notes

        rescheduled = interview.scheduled_at != original_scheduled_at
        job_title = application.job.title if application.job else "N/A"

        try:
            if rescheduled:
                await record_activity(
                    self.session,
                    application_id=interview.application_id,
                    actor_id=current_user.id,
                    action_type=hiring.INTERVIEW_RESCHEDULED,
                    metadata={"interview_id": str(interview.id)},
                )
                await schedule_interview_email(
                    self.session,
                    to_email=self._candidate_email(application),
                    job_title=job_title,
                    scheduled_at=interview.scheduled_at,
                    event="rescheduled",
                    idempotency_key=(
                        f"interview:{interview.id}:rescheduled:"
                        f"{interview.scheduled_at.isoformat()}"
                    ),
                )

            # Notify candidate about interview update BEFORE commit
            notification_service = NotificationService(self.session)
            candidate_user_id = application.candidate.user_id if application.candidate else None
            if candidate_user_id:
                await notification_service.create_notification(
                    user_id=candidate_user_id,
                    title="Cập nhật lịch phỏng vấn",
                    content=f"Lịch phỏng vấn cho vị trí {job_title} đã được cập nhật. Thời gian mới: {interview.scheduled_at.strftime('%d/%m/%Y %H:%M')}",
                    notification_type="interview_updated",
                    entity_type="interview",
                    entity_id=interview.id,
                )

            await schedule_application_pipeline_event(
                self.session,
                application=application,
                action=ACTION_INTERVIEW_UPDATED,
                from_status=application.status,
                to_status=application.status,
                candidate_user_id=candidate_user_id,
            )

            await self.session.commit()
            await self.session.refresh(interview)

        except Exception:
            await self.session.rollback()
            raise

        return InterviewRead.model_validate(interview)

    async def cancel_interview(
        self,
        current_user: User,
        interview_id: uuid.UUID,
    ) -> InterviewRead:
        """Cancel an interview.

        Recruiter/admin only. Sets status to CANCELLED and soft-deletes.
        """
        interview = await self.interviews.get_by_id_with_application(interview_id)
        if interview is None:
            raise EntityNotFoundException(f"Interview {interview_id} not found")

        # Verify ownership through application -> job
        application = await self.applications.get_by_id_with_candidate_job_company_and_recruiters(interview.application_id)
        if application is None:
            raise EntityNotFoundException(
                f"Application {interview.application_id} not found"
            )

        try:
            await JobService(self.session).get_recruiter_job_by_id(
                current_user,
                application.job_id,
            )
        except EntityNotFoundException:
            raise EntityNotFoundException(
                f"Interview {interview_id} not found"
            ) from None

        if interview.status not in MUTABLE_INTERVIEW_STATUSES:
            raise InvalidTransitionException(
                "Không thể hủy buổi phỏng vấn ở trạng thái "
                f"{interview.status.value}."
            )
        if self._has_ended(
            interview.scheduled_at,
            interview.duration_minutes,
        ):
            raise InvalidTransitionException(
                "Không thể hủy buổi phỏng vấn đã kết thúc."
            )

        previous_app_status = application.status

        # Set status to CANCELLED and soft delete
        interview.status = InterviewStatus.CANCELLED
        await self.interviews.soft_delete(interview)

        job_title = application.job.title if application.job else "N/A"

        try:
            await record_activity(
                self.session,
                application_id=interview.application_id,
                actor_id=current_user.id,
                action_type=hiring.INTERVIEW_CANCELLED,
                metadata={"interview_id": str(interview.id)},
            )

            reconciled = await self._reconcile_application_interview_stage(
                application
            )
            if reconciled:
                await record_activity(
                    self.session,
                    application_id=interview.application_id,
                    actor_id=current_user.id,
                    action_type=hiring.STATUS_CHANGED,
                    from_status=ApplicationStatus.INTERVIEWING.value,
                    to_status=ApplicationStatus.UNDER_REVIEW.value,
                    note=(
                        "Tự động chuyển hồ sơ về Đang xem xét sau khi hủy "
                        "phỏng vấn."
                    ),
                )

            await schedule_interview_email(
                self.session,
                to_email=self._candidate_email(application),
                job_title=job_title,
                scheduled_at=interview.scheduled_at,
                event="cancelled",
                idempotency_key=f"interview:{interview.id}:cancelled",
            )

            # Notify candidate about interview cancellation BEFORE commit
            notification_service = NotificationService(self.session)
            candidate_user_id = application.candidate.user_id if application.candidate else None
            if candidate_user_id:
                content = f"Phỏng vấn cho vị trí {job_title} đã bị hủy"
                if reconciled:
                    content += (
                        ". Hồ sơ của bạn đã được tự động chuyển về trạng thái "
                        "Đang xem xét vì không còn buổi phỏng vấn nào đang "
                        "hoạt động."
                    )
                await notification_service.create_notification(
                    user_id=candidate_user_id,
                    title="Phỏng vấn bị hủy",
                    content=content,
                    notification_type="interview_cancelled",
                    entity_type="interview",
                    entity_id=interview.id,
                )

            await schedule_application_pipeline_event(
                self.session,
                application=application,
                action=ACTION_INTERVIEW_CANCELLED,
                from_status=previous_app_status,
                to_status=application.status,
                candidate_user_id=candidate_user_id,
            )

            await self.session.commit()
            await self.session.refresh(interview)

        except Exception:
            await self.session.rollback()
            raise

        return InterviewRead.model_validate(interview)

    async def candidate_action_interview(
        self,
        current_user: User,
        application_id: uuid.UUID,
        interview_id: uuid.UUID,
        action: str,
        candidate_notes: str | None = None,
    ) -> CandidateInterviewRead:
        """Candidate confirms or declines a scheduled interview.

        Candidate only. Ownership enforced via application -> candidate profile.
        Interview must be in SCHEDULED status. Returns the candidate-facing
        projection, which excludes internal recruiter notes.
        """
        # Get candidate profile for the current user
        user_with_profile = await UserService(self.session).get_user_with_profile(current_user.id)
        if user_with_profile is None or user_with_profile.candidate_profile is None:
            raise EntityNotFoundException("Candidate profile not found")

        candidate_id = user_with_profile.candidate_profile.id

        # Get application and verify ownership
        application = await self.applications.get_by_id_with_candidate_job_company_and_recruiters(application_id)
        if application is None:
            raise EntityNotFoundException(f"Application {application_id} not found")

        if application.candidate_id != candidate_id:
            raise EntityNotFoundException(f"Application {application_id} not found")

        # Get interview and verify it belongs to the application
        interview = await self.interviews.get_by_id_with_application(interview_id)
        if interview is None:
            raise EntityNotFoundException(f"Interview {interview_id} not found")

        if interview.application_id != application_id:
            raise EntityNotFoundException(f"Interview {interview_id} not found")

        # Only allow action when status is SCHEDULED
        if interview.status != InterviewStatus.SCHEDULED:
            raise InvalidTransitionException(
                f"Cannot perform action on interview with status {interview.status.value}"
            )

        # Validate action
        if action == "confirm":
            interview.status = InterviewStatus.CANDIDATE_CONFIRMED
            interview.candidate_notes = candidate_notes
            notification_type = "interview_confirmed"
            notification_title = "Ứng viên xác nhận phỏng vấn"
            notification_content = f"Ứng viên đã xác nhận phỏng vấn cho vị trí {application.job.title if application.job else 'N/A'}"
        elif action == "decline":
            # candidate_notes is required for decline
            if not candidate_notes or not candidate_notes.strip():
                raise InvalidTransitionException("Candidate notes are required when declining an interview")
            interview.status = InterviewStatus.CANDIDATE_DECLINED
            interview.candidate_notes = candidate_notes.strip()
            notification_type = "interview_declined"
            notification_title = "Ứng viên từ chối phỏng vấn"
            notification_content = f"Ứng viên đã từ chối phỏng vấn cho vị trí {application.job.title if application.job else 'N/A'}"
        else:
            raise InvalidTransitionException(f"Invalid action: {action}. Must be 'confirm' or 'decline'")

        previous_app_status = application.status

        try:
            # Make the terminal interview outcome visible to the reconciliation
            # query; the session is configured with autoflush disabled.
            await self.session.flush()

            activity_metadata: dict[str, str] = {
                "interview_id": str(interview.id)
            }
            if action == "decline" and interview.candidate_notes:
                activity_metadata["candidate_notes"] = interview.candidate_notes
            await record_activity(
                self.session,
                application_id=application_id,
                actor_id=current_user.id,
                action_type=(
                    hiring.INTERVIEW_CONFIRMED
                    if action == "confirm"
                    else hiring.INTERVIEW_DECLINED
                ),
                metadata=activity_metadata,
            )

            reconciled = False
            if action == "decline":
                reconciled = (
                    await self._reconcile_application_interview_stage(
                        application
                    )
                )
                if reconciled:
                    await record_activity(
                        self.session,
                        application_id=application_id,
                        actor_id=current_user.id,
                        action_type=hiring.STATUS_CHANGED,
                        from_status=ApplicationStatus.INTERVIEWING.value,
                        to_status=ApplicationStatus.UNDER_REVIEW.value,
                        note=(
                            "Tự động chuyển hồ sơ về Đang xem xét sau khi "
                            "ứng viên từ chối phỏng vấn."
                        ),
                    )
                    notification_content += (
                        " Hồ sơ đã được tự động chuyển về trạng thái Đang "
                        "xem xét vì không còn buổi phỏng vấn nào đang hoạt "
                        "động."
                    )

            # Notify recruiter(s) about candidate confirm/decline BEFORE commit
            notification_service = NotificationService(self.session)
            if application.job and application.job.company and application.job.company.recruiters:
                for recruiter in application.job.company.recruiters:
                    if recruiter.user_id:
                        await notification_service.create_notification(
                            user_id=recruiter.user_id,
                            title=notification_title,
                            content=notification_content,
                            notification_type=notification_type,
                            entity_type="application",
                            entity_id=application.id,
                        )

            await schedule_application_pipeline_event(
                self.session,
                application=application,
                action=(
                    ACTION_INTERVIEW_CONFIRMED
                    if action == "confirm"
                    else ACTION_INTERVIEW_DECLINED
                ),
                from_status=previous_app_status,
                to_status=application.status,
                candidate_user_id=current_user.id,
            )

            await self.session.commit()
            await self.session.refresh(interview)

        except Exception:
            await self.session.rollback()
            raise

        return CandidateInterviewRead.model_validate(interview)


    async def list_interviews(
        self,
        current_user: User,
        application_id: uuid.UUID,
    ) -> list[InterviewRead]:
        """List all interviews for an application.

        Recruiter/admin only. Ownership enforced.
        """
        application = await self.applications.get_by_id_with_candidate_job_company_and_recruiters(application_id)
        if application is None:
            raise EntityNotFoundException(f"Application {application_id} not found")

        try:
            await JobService(self.session).get_recruiter_job_by_id(
                current_user,
                application.job_id,
            )
        except EntityNotFoundException:
            raise EntityNotFoundException(
                f"Application {application_id} not found"
            ) from None

        interviews = await self.interviews.list_by_application(application_id)
        return [InterviewRead.model_validate(i) for i in interviews]

    async def get_interview(
        self,
        current_user: User,
        interview_id: uuid.UUID,
    ) -> InterviewRead:
        """Get a single interview by ID.

        Recruiter/admin only. Ownership enforced.
        """
        interview = await self.interviews.get_by_id_with_application(interview_id)
        if interview is None:
            raise EntityNotFoundException(f"Interview {interview_id} not found")

        # Verify ownership through application -> job
        application = await self.applications.get_by_id_with_candidate_job_company_and_recruiters(interview.application_id)
        if application is None:
            raise EntityNotFoundException(
                f"Application {interview.application_id} not found"
            )

        try:
            await JobService(self.session).get_recruiter_job_by_id(
                current_user,
                application.job_id,
            )
        except EntityNotFoundException:
            raise EntityNotFoundException(
                f"Interview {interview_id} not found"
            ) from None

        return InterviewRead.model_validate(interview)
