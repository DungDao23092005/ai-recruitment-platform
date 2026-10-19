"""Hiring-pipeline ``ApplicationActivity`` vocabulary.

``action_type`` values are a closed, versioned vocabulary shared by every
service that appends to the append-only application history. Keeping them here
(rather than scattering string literals) makes the recruiter projection and the
candidate-visible allowlist auditable in one place.

``CANDIDATE_VISIBLE_ACTIVITY_TYPES`` is the *only* set of action types the
candidate timeline may ever expose. It is enforced at the SQL level by
``ApplicationActivityRepository.list_by_application`` so a future action type
that carries internal data can never leak by default: new types are invisible
to candidates until they are explicitly added here.
"""

from __future__ import annotations

STATUS_CHANGED = "status_changed"
CANDIDATE_WITHDREW = "candidate_withdrew"

NOTE_ADDED = "note_added"
NOTE_UPDATED = "note_updated"
NOTE_DELETED = "note_deleted"

EVALUATION_ADDED = "evaluation_added"
EVALUATION_UPDATED = "evaluation_updated"
EVALUATION_DELETED = "evaluation_deleted"

INTERVIEW_SCHEDULED = "interview_scheduled"
INTERVIEW_RESCHEDULED = "interview_rescheduled"
INTERVIEW_CANCELLED = "interview_cancelled"
INTERVIEW_CONFIRMED = "interview_confirmed"
INTERVIEW_DECLINED = "interview_declined"

# Recruiter-facing history may serialise any of the vocabulary above; this set
# exists to make that intent explicit and testable.
RECRUITER_VISIBLE_ACTIVITY_TYPES = frozenset(
    {
        STATUS_CHANGED,
        CANDIDATE_WITHDREW,
        NOTE_ADDED,
        NOTE_UPDATED,
        NOTE_DELETED,
        EVALUATION_ADDED,
        EVALUATION_UPDATED,
        EVALUATION_DELETED,
        INTERVIEW_SCHEDULED,
        INTERVIEW_RESCHEDULED,
        INTERVIEW_CANCELLED,
        INTERVIEW_CONFIRMED,
        INTERVIEW_DECLINED,
    }
)

# The candidate timeline only ever exposes events the candidate is a party to
# (their own status changes, withdrawal and interview lifecycle). Internal notes
# and private interview evaluations are deliberately excluded.
CANDIDATE_VISIBLE_ACTIVITY_TYPES = frozenset(
    {
        STATUS_CHANGED,
        CANDIDATE_WITHDREW,
        INTERVIEW_SCHEDULED,
        INTERVIEW_RESCHEDULED,
        INTERVIEW_CANCELLED,
        INTERVIEW_CONFIRMED,
        INTERVIEW_DECLINED,
    }
)
