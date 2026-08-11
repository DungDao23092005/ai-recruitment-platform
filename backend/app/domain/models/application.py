from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import ClassVar

from app.domain.enums import ApplicationStatus
from app.domain.models.base import BaseDomainEntity, DomainException


@dataclass(kw_only=True)
class Application(BaseDomainEntity):
    candidate_id: uuid.UUID
    job_id: uuid.UUID
    status: ApplicationStatus = ApplicationStatus.APPLIED

    _ALLOWED_TRANSITIONS: ClassVar[dict[ApplicationStatus, set[ApplicationStatus]]] = {
        ApplicationStatus.APPLIED: {
            ApplicationStatus.UNDER_REVIEW,
            ApplicationStatus.WITHDRAWN,
        },
        ApplicationStatus.UNDER_REVIEW: {
            ApplicationStatus.SHORTLISTED,
            ApplicationStatus.WITHDRAWN,
        },
        ApplicationStatus.SHORTLISTED: {
            ApplicationStatus.INTERVIEWING,
            ApplicationStatus.WITHDRAWN,
        },
        ApplicationStatus.INTERVIEWING: {
            ApplicationStatus.ACCEPTED,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        },
        ApplicationStatus.ACCEPTED: set(),
        ApplicationStatus.REJECTED: set(),
        ApplicationStatus.WITHDRAWN: set(),
    }

    def transition_to(self, new_status: ApplicationStatus) -> None:
        if not isinstance(new_status, ApplicationStatus):
            raise DomainException(
                f"new_status must be an ApplicationStatus, got: {new_status!r}"
            )
        allowed = self._ALLOWED_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise DomainException(
                f"Invalid Application status transition "
                f"from {self.status.value!r} to {new_status.value!r}."
            )
        self.status = new_status
        self.mark_updated()
