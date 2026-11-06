"""Unit tests for the Phase 2 hiring-pipeline services (mocked persistence).

These pin the *rules* the services own - author/evaluator authorization, the
one-scorecard-per-evaluator conflict, the non-enumerating ownership checks and
the candidate/timeline allowlist - independently of SQL Server.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
)
from app.domain import hiring
from app.domain.enums import UserRole
from app.schemas.application_note import ApplicationNoteCreate
from app.schemas.interview_evaluation import (
    InterviewEvaluationCreate,
    InterviewEvaluationUpdate,
)
from app.services import application_activity_service as activity_module
from app.services.application_activity_service import (
    ApplicationActivityService,
    record_activity,
)
from app.services.application_note_service import ApplicationNoteService
from app.services.interview_evaluation_service import InterviewEvaluationService


def make_user(role=UserRole.RECRUITER, user_id=None):
    return MagicMock(id=user_id or uuid.uuid4(), role=role)


def make_session():
    session = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


def _noop_activity(monkeypatch, dotted_module):
    async def _record(*args, **kwargs):
        return MagicMock()

    monkeypatch.setattr(f"{dotted_module}.record_activity", _record)


class TestRecordActivity:
    @pytest.mark.asyncio
    async def test_serialises_metadata_without_ascii_escape(self, monkeypatch):
        appended = MagicMock()
        append = AsyncMock(return_value=appended)
        monkeypatch.setattr(
            activity_module.ApplicationActivityRepository, "append", append
        )

        result = await record_activity(
            make_session(),
            application_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            action_type=hiring.NOTE_ADDED,
            metadata={"label": "Ưu tiên"},
        )

        assert result is appended
        activity = append.await_args.args[0]
        assert activity.metadata_json == json.dumps(
            {"label": "Ưu tiên"}, ensure_ascii=False
        )

    @pytest.mark.asyncio
    async def test_none_metadata_stays_null(self, monkeypatch):
        append = AsyncMock(return_value=MagicMock())
        monkeypatch.setattr(
            activity_module.ApplicationActivityRepository, "append", append
        )
        await record_activity(
            make_session(),
            application_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            action_type=hiring.STATUS_CHANGED,
        )
        assert append.await_args.args[0].metadata_json is None


class TestActivityServiceAllowlists:
    @pytest.mark.asyncio
    async def test_candidate_timeline_filters_at_sql_level(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.application_activity_service.require_candidate_application",
            AsyncMock(return_value=MagicMock()),
        )
        service = ApplicationActivityService(make_session())
        service.activities.list_by_application = AsyncMock(return_value=[])

        await service.list_candidate_timeline(
            current_user=make_user(UserRole.CANDIDATE),
            application_id=uuid.uuid4(),
        )

        kwargs = service.activities.list_by_application.await_args.kwargs
        assert kwargs["action_types"] == hiring.CANDIDATE_VISIBLE_ACTIVITY_TYPES

    @pytest.mark.asyncio
    async def test_recruiter_history_has_no_filter(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.application_activity_service.require_recruiter_application",
            AsyncMock(return_value=MagicMock()),
        )
        service = ApplicationActivityService(make_session())
        service.activities.list_by_application = AsyncMock(return_value=[])

        await service.list_activities(
            current_user=make_user(),
            application_id=uuid.uuid4(),
        )

        kwargs = service.activities.list_by_application.await_args.kwargs
        assert kwargs.get("action_types") is None


class TestNoteAuthorization:
    def test_rejects_non_author(self):
        note = MagicMock(author_id=uuid.uuid4())
        with pytest.raises(ForbiddenException):
            ApplicationNoteService._authorize_mutation(make_user(), note)

    def test_accepts_author(self):
        user = make_user()
        ApplicationNoteService._authorize_mutation(user, MagicMock(author_id=user.id))

    def test_admin_bypasses_ownership(self):
        ApplicationNoteService._authorize_mutation(
            make_user(UserRole.ADMIN), MagicMock(author_id=uuid.uuid4())
        )

    @pytest.mark.asyncio
    async def test_update_missing_note_is_404(self, monkeypatch):
        _noop_activity(monkeypatch, "app.services.application_note_service")
        monkeypatch.setattr(
            "app.services.application_note_service.require_recruiter_application",
            AsyncMock(return_value=MagicMock()),
        )
        service = ApplicationNoteService(make_session())
        service.notes.get_by_id_and_application = AsyncMock(return_value=None)

        with pytest.raises(EntityNotFoundException):
            await service.update_note(
                current_user=make_user(),
                application_id=uuid.uuid4(),
                note_id=uuid.uuid4(),
                content="x",
            )

    @pytest.mark.asyncio
    async def test_create_records_note_added_activity(self, monkeypatch):
        recorded = {}

        async def _record(session, **kwargs):
            recorded.update(kwargs)
            return MagicMock()

        monkeypatch.setattr(
            "app.services.application_note_service.record_activity", _record
        )
        monkeypatch.setattr(
            "app.services.application_note_service.require_recruiter_application",
            AsyncMock(return_value=MagicMock()),
        )
        monkeypatch.setattr(
            "app.services.application_note_service.ApplicationNoteRead",
            MagicMock(model_validate=lambda obj: obj),
        )
        session = make_session()
        service = ApplicationNoteService(session)
        user = make_user()
        application_id = uuid.uuid4()

        note = await service.create_note(
            current_user=user,
            application_id=application_id,
            data=ApplicationNoteCreate(content="hello"),
        )

        assert recorded["action_type"] == hiring.NOTE_ADDED
        assert recorded["application_id"] == application_id
        assert note.content == "hello"


class TestEvaluationAuthorization:
    def test_rejects_non_evaluator(self):
        evaluation = MagicMock(evaluator_id=uuid.uuid4())
        with pytest.raises(ForbiddenException):
            InterviewEvaluationService._authorize_author(
                uuid.uuid4(), evaluation
            )

    def test_accepts_evaluator(self):
        user = make_user()
        InterviewEvaluationService._authorize_author(
            user.id, MagicMock(evaluator_id=user.id)
        )

    def test_admin_does_not_bypass_ownership(self):
        with pytest.raises(ForbiddenException):
            InterviewEvaluationService._authorize_author(
                uuid.uuid4(), MagicMock(evaluator_id=uuid.uuid4())
            )

    def test_submitted_evaluation_is_immutable(self):
        with pytest.raises(ConflictException):
            InterviewEvaluationService._ensure_draft(
                MagicMock(status="submitted")
            )

    def test_draft_evaluation_is_mutable(self):
        InterviewEvaluationService._ensure_draft(MagicMock(status="draft"))

    @pytest.mark.asyncio
    async def test_duplicate_active_scorecard_conflicts(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.interview_evaluation_service.require_recruiter_application",
            AsyncMock(return_value=MagicMock()),
        )
        application_id = uuid.uuid4()
        interview_id = uuid.uuid4()
        service = InterviewEvaluationService(make_session())
        service.interviews.get_by_id_with_application = AsyncMock(
            return_value=MagicMock(application_id=application_id)
        )
        service.evaluations.get_by_interview_and_evaluator = AsyncMock(
            return_value=MagicMock()
        )

        with pytest.raises(ConflictException):
            await service.create_evaluation(
                current_user=make_user(),
                application_id=application_id,
                interview_id=interview_id,
                data=InterviewEvaluationCreate(rating=4),
            )

    @pytest.mark.asyncio
    async def test_update_missing_evaluation_is_404(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.interview_evaluation_service.require_recruiter_application",
            AsyncMock(return_value=MagicMock()),
        )
        service = InterviewEvaluationService(make_session())
        service.evaluations.get_by_id_and_application = AsyncMock(return_value=None)

        with pytest.raises(EntityNotFoundException):
            await service.update_evaluation(
                current_user=make_user(),
                application_id=uuid.uuid4(),
                evaluation_id=uuid.uuid4(),
                data=InterviewEvaluationUpdate(rating=5),
            )

    @pytest.mark.asyncio
    async def test_create_records_evaluation_added_activity(self, monkeypatch):
        recorded = {}

        async def _record(session, **kwargs):
            recorded.update(kwargs)
            return MagicMock()

        monkeypatch.setattr(
            "app.services.interview_evaluation_service.record_activity", _record
        )
        monkeypatch.setattr(
            "app.services.interview_evaluation_service.require_recruiter_application",
            AsyncMock(return_value=MagicMock()),
        )
        monkeypatch.setattr(
            "app.services.interview_evaluation_service.InterviewEvaluationRead",
            MagicMock(model_validate=lambda obj: obj),
        )
        service = InterviewEvaluationService(make_session())
        application_id = uuid.uuid4()
        interview_id = uuid.uuid4()
        service.interviews.get_by_id_with_application = AsyncMock(
            return_value=MagicMock(
                application_id=application_id, id=interview_id
            )
        )
        service.evaluations.get_by_interview_and_evaluator = AsyncMock(
            return_value=None
        )

        await service.create_evaluation(
            current_user=make_user(),
            application_id=application_id,
            interview_id=interview_id,
            data=InterviewEvaluationCreate(rating=5),
        )

        assert recorded["action_type"] == hiring.EVALUATION_ADDED
        assert recorded["metadata"]["interview_id"] == str(interview_id)

    def test_visible_evaluations_hides_own_draft_when_not_actively_assigned(self):
        viewer_id = uuid.uuid4()
        peer_id = uuid.uuid4()
        interview_id = uuid.uuid4()
        own_draft = MagicMock(
            id=uuid.uuid4(),
            interview_id=interview_id,
            evaluator_id=viewer_id,
            status="draft",
        )
        peer_draft = MagicMock(
            id=uuid.uuid4(),
            interview_id=interview_id,
            evaluator_id=peer_id,
            status="draft",
        )
        peer_submitted = MagicMock(
            id=uuid.uuid4(),
            interview_id=interview_id,
            evaluator_id=peer_id,
            status="submitted",
        )
        rows = [own_draft, peer_draft, peer_submitted]

        visible_while_assigned = InterviewEvaluationService._visible_evaluations(
            rows,
            viewer_id,
            blind=False,
            active_interview_ids={interview_id},
        )
        assert visible_while_assigned == [own_draft, peer_submitted]

        visible_after_unassignment = (
            InterviewEvaluationService._visible_evaluations(
                rows,
                viewer_id,
                blind=False,
                active_interview_ids=set(),
            )
        )
        assert visible_after_unassignment == [peer_submitted]
