"""Unit tests for transaction-safe pipeline invalidation events."""

from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.domain.enums import ApplicationStatus
from app.services.pipeline_realtime import (
    ACTION_APPLICATION_STATUS_CHANGED,
    ACTION_INTERVIEW_SCHEDULED,
    CANDIDATE_PIPELINE_UPDATED_EVENT,
    PIPELINE_UPDATED_EVENT,
    build_candidate_pipeline_event,
    build_company_pipeline_event,
    company_pipeline_channel,
    is_candidate_pipeline_message,
    is_company_pipeline_message,
    schedule_application_pipeline_event,
    schedule_candidate_pipeline_event,
    schedule_company_pipeline_event,
    user_pipeline_channel,
)

_PUBSUB_TARGET = "app.services.pipeline_realtime.pubsub_manager"


def _manager() -> MagicMock:
    manager = MagicMock()
    manager.publish = AsyncMock()
    return manager


def _company_event(**overrides) -> dict:
    values = {
        "company_id": uuid.uuid4(),
        "job_id": uuid.uuid4(),
        "application_id": uuid.uuid4(),
        "action": ACTION_APPLICATION_STATUS_CHANGED,
        "from_status": ApplicationStatus.APPLIED,
        "to_status": ApplicationStatus.UNDER_REVIEW,
    }
    values.update(overrides)
    return build_company_pipeline_event(**values)


def _application() -> SimpleNamespace:
    job_id = uuid.uuid4()
    return SimpleNamespace(
        id=uuid.uuid4(),
        candidate_id=uuid.uuid4(),
        job_id=job_id,
        job=SimpleNamespace(id=job_id, company_id=uuid.uuid4()),
    )


def _double() -> SimpleNamespace:
    return SimpleNamespace(sync_session=Session())


def _run(coro) -> None:
    asyncio.run(coro)


def test_company_and_candidate_payloads_are_minimal_and_valid():
    company_id = uuid.uuid4()
    job_id = uuid.uuid4()
    application_id = uuid.uuid4()

    company = build_company_pipeline_event(
        company_id=company_id,
        job_id=job_id,
        application_id=application_id,
        action=ACTION_INTERVIEW_SCHEDULED,
        from_status=ApplicationStatus.SHORTLISTED,
        to_status=ApplicationStatus.INTERVIEWING,
    )
    candidate = build_candidate_pipeline_event(
        job_id=job_id,
        application_id=application_id,
        action=ACTION_INTERVIEW_SCHEDULED,
        from_status=ApplicationStatus.SHORTLISTED,
        to_status=ApplicationStatus.INTERVIEWING,
    )

    assert set(company) == {
        "type",
        "company_id",
        "job_id",
        "application_id",
        "action",
        "from_status",
        "to_status",
        "timestamp",
    }
    assert company["type"] == PIPELINE_UPDATED_EVENT
    assert candidate["type"] == CANDIDATE_PIPELINE_UPDATED_EVENT
    assert is_company_pipeline_message(json.dumps(company), company_id=company_id)
    assert is_candidate_pipeline_message(json.dumps(candidate))
    serialized = f"{company} {candidate}".lower()
    for forbidden in ("email", "full_name", "phone", "resume", "candidate_name"):
        assert forbidden not in serialized


def test_validation_rejects_extra_keys_wrong_company_and_malformed_data():
    event = _company_event()

    assert is_company_pipeline_message(event)
    assert not is_company_pipeline_message({**event, "email": "a@b.c"})
    assert not is_company_pipeline_message(
        event, company_id=uuid.uuid4()
    )
    assert not is_company_pipeline_message("not-json")
    assert not is_company_pipeline_message({**event, "to_status": "bogus"})
    assert not is_candidate_pipeline_message({**event, "type": "other"})


def test_builders_reject_unknown_action_or_status():
    with pytest.raises(ValueError):
        build_company_pipeline_event(
            company_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            application_id=uuid.uuid4(),
            action="unknown",
        )
    with pytest.raises(ValueError):
        build_candidate_pipeline_event(
            job_id=uuid.uuid4(),
            application_id=uuid.uuid4(),
            action=ACTION_APPLICATION_STATUS_CHANGED,
            to_status="bogus",
        )


def test_commit_publishes_company_and_candidate_once():
    manager = _manager()
    session = _double()
    application = _application()
    candidate_user_id = uuid.uuid4()

    async def _run_test():
        session.sync_session.begin()
        with patch(_PUBSUB_TARGET, manager):
            await schedule_application_pipeline_event(
                session,
                application=application,
                action=ACTION_APPLICATION_STATUS_CHANGED,
                from_status=ApplicationStatus.APPLIED,
                to_status=ApplicationStatus.SHORTLISTED,
                candidate_user_id=candidate_user_id,
            )
            session.sync_session.commit()
            await asyncio.sleep(0.01)

    _run(_run_test())

    assert manager.publish.await_count == 2
    channels = [call.args[0] for call in manager.publish.await_args_list]
    assert company_pipeline_channel(application.job.company_id) in channels
    assert user_pipeline_channel(candidate_user_id) in channels


def test_duplicate_scheduling_is_coalesced_per_channel():
    manager = _manager()
    session = _double()
    event = _company_event()

    async def _run_test():
        session.sync_session.begin()
        with patch(_PUBSUB_TARGET, manager):
            schedule_company_pipeline_event(session, event)
            schedule_company_pipeline_event(session, event)
            session.sync_session.commit()
            await asyncio.sleep(0.01)

    _run(_run_test())

    assert manager.publish.await_count == 1
    channel, message = manager.publish.await_args.args
    assert channel == company_pipeline_channel(event["company_id"])
    assert message["application_id"] == event["application_id"]


def test_rollback_discards_events_and_later_commit_publishes_nothing():
    manager = _manager()
    session = _double()
    event = _company_event()

    async def _run_test():
        session.sync_session.begin()
        with patch(_PUBSUB_TARGET, manager):
            schedule_company_pipeline_event(session, event)
            session.sync_session.rollback()
            session.sync_session.begin()
            session.sync_session.commit()
            await asyncio.sleep(0.01)

    _run(_run_test())

    manager.publish.assert_not_awaited()


def test_rollback_then_new_event_publishes_only_the_new_event():
    manager = _manager()
    session = _double()
    stale = _company_event()
    fresh = _company_event()

    async def _run_test():
        session.sync_session.begin()
        with patch(_PUBSUB_TARGET, manager):
            schedule_company_pipeline_event(session, stale)
            session.sync_session.rollback()
            session.sync_session.begin()
            schedule_company_pipeline_event(session, fresh)
            session.sync_session.commit()
            await asyncio.sleep(0.01)

    _run(_run_test())

    manager.publish.assert_awaited_once()
    _, message = manager.publish.await_args.args
    assert message["application_id"] == fresh["application_id"]
    assert message["application_id"] != stale["application_id"]


def test_publish_failure_is_swallowed():
    manager = _manager()
    manager.publish.side_effect = RuntimeError("redis down")
    session = _double()
    event = _company_event()

    async def _run_test():
        session.sync_session.begin()
        with patch(_PUBSUB_TARGET, manager):
            schedule_company_pipeline_event(session, event)
            session.sync_session.commit()
            await asyncio.sleep(0.01)

    _run(_run_test())

    manager.publish.assert_awaited_once()


def test_candidate_event_uses_personal_channel():
    manager = _manager()
    session = _double()
    user_id = uuid.uuid4()
    event = build_candidate_pipeline_event(
        job_id=uuid.uuid4(),
        application_id=uuid.uuid4(),
        action=ACTION_APPLICATION_STATUS_CHANGED,
        to_status=ApplicationStatus.SHORTLISTED,
    )

    async def _run_test():
        session.sync_session.begin()
        with patch(_PUBSUB_TARGET, manager):
            schedule_candidate_pipeline_event(
                session, candidate_user_id=user_id, message=event
            )
            session.sync_session.commit()
            await asyncio.sleep(0.01)

    _run(_run_test())

    manager.publish.assert_awaited_once()
    channel, message = manager.publish.await_args.args
    assert channel == user_pipeline_channel(user_id)
    assert message["type"] == CANDIDATE_PIPELINE_UPDATED_EVENT
