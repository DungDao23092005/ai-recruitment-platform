from __future__ import annotations

import uuid

from app.services.analytics_service import AnalyticsService


def _row(
    job_id,
    status,
    *,
    review=False,
    interviewing=False,
    offered=False,
    accepted=False,
):
    return {
        "job_id": job_id,
        "status": status,
        "reached_review": 1 if review else 0,
        "reached_interviewing": 1 if interviewing else 0,
        "reached_offered": 1 if offered else 0,
        "reached_accepted": 1 if accepted else 0,
    }


def test_rejected_and_withdrawn_still_count_as_applied():
    job = uuid.uuid4()
    counts, by_job, jobs = AnalyticsService._funnel(
        [
            _row(job, "rejected"),
            _row(job, "withdrawn"),
        ]
    )
    assert counts == {
        "applied": 2,
        "under_review": 0,
        "interviewing": 0,
        "offered": 0,
        "accepted": 0,
    }
    assert by_job[job] == 2
    assert jobs == {job}


def test_activity_milestones_are_respected_for_later_statuses():
    job = uuid.uuid4()
    counts, _, _ = AnalyticsService._funnel(
        [
            _row(
                job,
                "withdrawn",
                review=True,
                interviewing=True,
                offered=True,
            )
        ]
    )
    assert counts["applied"] == 1
    assert counts["under_review"] == 1
    assert counts["interviewing"] == 1
    assert counts["offered"] == 1
    assert counts["accepted"] == 0


def test_status_implies_reached_stage_even_without_activity_rows():
    job = uuid.uuid4()
    counts, _, _ = AnalyticsService._funnel(
        [
            _row(job, "under_review"),
            _row(job, "shortlisted"),
            _row(job, "interviewing"),
            _row(job, "offered"),
            _row(job, "accepted"),
        ]
    )
    assert counts == {
        "applied": 5,
        "under_review": 5,
        "interviewing": 3,
        "offered": 2,
        "accepted": 1,
    }


def test_direct_interviewing_to_accepted_hire_keeps_funnel_monotonic():
    job = uuid.uuid4()
    counts, _, _ = AnalyticsService._funnel(
        [
            _row(
                job,
                "accepted",
                interviewing=True,
                accepted=True,
            )
        ]
    )
    assert counts["applied"] == 1
    assert counts["under_review"] == 1
    assert counts["interviewing"] == 1
    assert counts["offered"] == 1
    assert counts["accepted"] == 1


def test_funnel_counts_are_monotonic_across_mixed_cohort():
    job = uuid.uuid4()
    rows = [
        _row(job, "applied"),
        _row(job, "under_review"),
        _row(job, "interviewing"),
        _row(job, "accepted", accepted=True),
        _row(job, "rejected"),
        _row(job, "withdrawn"),
    ]
    counts, _, _ = AnalyticsService._funnel(rows)
    ordered = [
        counts["applied"],
        counts["under_review"],
        counts["interviewing"],
        counts["offered"],
        counts["accepted"],
    ]
    assert ordered == sorted(ordered, reverse=True)
    assert counts["applied"] == 6
    assert counts["accepted"] == 1


def test_applications_are_grouped_by_job():
    job_a, job_b = uuid.uuid4(), uuid.uuid4()
    counts, by_job, jobs = AnalyticsService._funnel(
        [
            _row(job_a, "applied"),
            _row(job_a, "under_review"),
            _row(job_b, "rejected"),
        ]
    )
    assert counts["applied"] == 3
    assert by_job == {job_a: 2, job_b: 1}
    assert jobs == {job_a, job_b}
