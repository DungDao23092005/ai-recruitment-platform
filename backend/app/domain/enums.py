from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    CANDIDATE = "candidate"
    RECRUITER = "recruiter"


class JobStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"
    EXPIRED = "expired"


class JobType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"


class WorkplaceType(str, Enum):
    ON_SITE = "on_site"
    HYBRID = "hybrid"
    REMOTE = "remote"


class ApplicationStatus(str, Enum):
    """Lifecycle of a job application.

    The canonical recruiting pipeline is ``APPLIED`` -> ``UNDER_REVIEW`` ->
    ``INTERVIEWING`` -> ``OFFERED`` -> ``ACCEPTED`` / ``REJECTED``, with
    ``WITHDRAWN`` available as a candidate-initiated terminal state.

    ``SHORTLISTED`` predates the explicit ``OFFERED`` stage. It is retained for
    storage and API backward compatibility and is presented as a screening
    stage (see :func:`canonical_stage`); it is never mass-rewritten to a new
    value.
    """

    APPLIED = "applied"
    UNDER_REVIEW = "under_review"
    SHORTLISTED = "shortlisted"
    INTERVIEWING = "interviewing"
    OFFERED = "offered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


# Statuses a candidate moves through during screening. ``SHORTLISTED`` is a
# legacy alias that belongs to the same screening stage as ``UNDER_REVIEW``.
SCREENING_STAGE_ALIASES = frozenset(
    {ApplicationStatus.UNDER_REVIEW, ApplicationStatus.SHORTLISTED}
)

# Maps legacy/alias statuses onto the canonical pipeline stage used for display.
_CANONICAL_STAGE: dict[ApplicationStatus, ApplicationStatus] = {
    ApplicationStatus.SHORTLISTED: ApplicationStatus.UNDER_REVIEW,
}


def canonical_stage(status: ApplicationStatus) -> ApplicationStatus:
    """Return the display stage for ``status``.

    Legacy statuses (currently only ``SHORTLISTED``) collapse onto their
    canonical stage so the pipeline reads as the six documented stages, while
    the stored value is preserved untouched.
    """
    return _CANONICAL_STAGE.get(status, status)


class ProficiencyLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class CompanySize(str, Enum):
    SEED = "seed"
    STARTUP = "startup"
    SME = "sme"
    ENTERPRISE = "enterprise"


class InterviewType(str, Enum):
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    HR = "hr"
    CASE_STUDY = "case_study"


class InterviewStatus(str, Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    CANDIDATE_CONFIRMED = "candidate_confirmed"
    CANDIDATE_DECLINED = "candidate_declined"


class RecruitmentPlanStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PENDING = "pending"


class PaymentProvider(str, Enum):
    MOMO = "momo"
    VNPAY = "vnpay"


class PaymentOrderStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PaymentTransactionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"


class SubscriptionAuditAction(str, Enum):
    PROVISION = "provision"
    CHANGE_PLAN = "change_plan"
    REVOKE = "revoke"


class SubscriptionUsageFeatureType(str, Enum):
    JOB_POST = "job_post"
    CANDIDATE_SEARCH = "candidate_search"
    AI_FEATURE = "ai_feature"


class SubscriptionUsageStatus(str, Enum):
    RESERVED = "reserved"
    COMPLETED = "completed"
    FAILED = "failed"


class OutboxStatus(str, Enum):
    """Lifecycle of a durable transactional-outbox email.

    ``PENDING``   - stored and waiting for a free worker, or scheduled to retry.
    ``PROCESSING``- claimed by a worker (a lease is held until it is released).
    ``SENT``      - the provider accepted the message; terminal success.
    ``FAILED``    - the retry budget was exhausted; terminal failure.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
