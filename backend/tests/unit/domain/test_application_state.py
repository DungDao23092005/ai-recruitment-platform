import uuid

import pytest

from app.domain.enums import ApplicationStatus
from app.domain.models import Application
from app.domain.models.base import DomainException


def make_application(status: ApplicationStatus = ApplicationStatus.APPLIED) -> Application:
    return Application(
        candidate_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        status=status,
    )


@pytest.mark.parametrize(
    "initial,next_status",
    [
        (ApplicationStatus.APPLIED, ApplicationStatus.UNDER_REVIEW),
        (ApplicationStatus.APPLIED, ApplicationStatus.WITHDRAWN),
        (ApplicationStatus.UNDER_REVIEW, ApplicationStatus.SHORTLISTED),
        (ApplicationStatus.UNDER_REVIEW, ApplicationStatus.WITHDRAWN),
        (ApplicationStatus.SHORTLISTED, ApplicationStatus.INTERVIEWING),
        (ApplicationStatus.SHORTLISTED, ApplicationStatus.WITHDRAWN),
        (ApplicationStatus.INTERVIEWING, ApplicationStatus.ACCEPTED),
        (ApplicationStatus.INTERVIEWING, ApplicationStatus.REJECTED),
        (ApplicationStatus.INTERVIEWING, ApplicationStatus.WITHDRAWN),
    ],
)
def test_valid_transitions(initial, next_status):
    application = make_application(initial)

    application.transition_to(next_status)

    assert application.status is next_status


@pytest.mark.parametrize(
    "initial,next_status",
    [
        (ApplicationStatus.APPLIED, ApplicationStatus.ACCEPTED),
        (ApplicationStatus.APPLIED, ApplicationStatus.REJECTED),
        (ApplicationStatus.UNDER_REVIEW, ApplicationStatus.INTERVIEWING),
        (ApplicationStatus.UNDER_REVIEW, ApplicationStatus.ACCEPTED),
        (ApplicationStatus.SHORTLISTED, ApplicationStatus.ACCEPTED),
        (ApplicationStatus.SHORTLISTED, ApplicationStatus.APPLIED),
        (ApplicationStatus.INTERVIEWING, ApplicationStatus.APPLIED),
        (ApplicationStatus.INTERVIEWING, ApplicationStatus.UNDER_REVIEW),
        (ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED),
        (ApplicationStatus.REJECTED, ApplicationStatus.INTERVIEWING),
        (ApplicationStatus.WITHDRAWN, ApplicationStatus.APPLIED),
    ],
)
def test_invalid_transitions_raise_domain_exception(initial, next_status):
    application = make_application(initial)

    with pytest.raises(DomainException):
        application.transition_to(next_status)


@pytest.mark.parametrize(
    "terminal",
    [ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN],
)
def test_terminal_states_have_no_outgoing_transitions(terminal):
    application = make_application(terminal)

    for status in ApplicationStatus:
        with pytest.raises(DomainException):
            application.transition_to(status)


def test_transition_updates_timestamp():
    application = make_application()
    original_updated_at = application.updated_at

    application.transition_to(ApplicationStatus.UNDER_REVIEW)

    assert application.updated_at >= original_updated_at
    assert application.status is ApplicationStatus.UNDER_REVIEW


def test_invalid_transition_does_not_change_status():
    application = make_application(ApplicationStatus.APPLIED)

    with pytest.raises(DomainException):
        application.transition_to(ApplicationStatus.ACCEPTED)

    assert application.status is ApplicationStatus.APPLIED


def test_non_enum_status_raises_domain_exception():
    application = make_application()

    with pytest.raises(DomainException):
        application.transition_to("accepted")  # type: ignore[arg-type]


def test_domain_exception_is_a_value_error():
    assert issubclass(DomainException, ValueError)
