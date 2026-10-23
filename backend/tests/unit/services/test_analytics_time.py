from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.exceptions import ValidationError
from app.services.analytics_service import resolve_analytics_range
from app.services.analytics_time import (
    VIETNAM_TZ,
    day_end_exclusive_utc,
    day_start_utc,
    to_utc,
    vietnam_date_of,
    vietnam_now,
    vietnam_today,
)


def test_vietnam_day_boundaries_are_utc_plus_seven():
    assert day_start_utc(date(2026, 1, 1)) == datetime(
        2025, 12, 31, 17, 0, tzinfo=timezone.utc
    )
    assert day_end_exclusive_utc(date(2026, 1, 1)) == datetime(
        2026, 1, 1, 17, 0, tzinfo=timezone.utc
    )


def test_utc_boundary_assigns_events_to_the_correct_vietnam_day():
    before = datetime(2026, 1, 1, 16, 59, 59, tzinfo=timezone.utc)
    at_boundary = datetime(2026, 1, 1, 17, 0, 0, tzinfo=timezone.utc)
    assert vietnam_date_of(before) == date(2026, 1, 1)
    assert vietnam_date_of(at_boundary) == date(2026, 1, 2)


def test_naive_timestamps_are_treated_as_utc():
    naive = datetime(2026, 1, 1, 17, 0, 0)
    assert to_utc(naive).tzinfo is timezone.utc
    assert vietnam_date_of(naive) == date(2026, 1, 2)


def test_vietnam_now_and_today_use_fixed_offset():
    moment = datetime(2026, 1, 1, 17, 0, tzinfo=timezone.utc)
    local = vietnam_now(moment)
    assert local.tzinfo == VIETNAM_TZ
    assert local.hour == 0
    assert vietnam_today(moment) == date(2026, 1, 2)


def test_resolve_range_defaults_to_thirty_inclusive_days():
    now = datetime(2026, 2, 15, 3, 0, tzinfo=timezone.utc)
    start, end = resolve_analytics_range(None, None, now=now)
    assert end == date(2026, 2, 15)
    assert start == date(2026, 2, 15) - timedelta(days=29)


def test_resolve_range_uses_explicit_dates():
    start, end = resolve_analytics_range(
        date(2026, 1, 1), date(2026, 1, 31)
    )
    assert (start, end) == (date(2026, 1, 1), date(2026, 1, 31))


def test_resolve_range_defaults_start_from_end_date():
    start, end = resolve_analytics_range(None, date(2026, 1, 31))
    assert end == date(2026, 1, 31)
    assert start == date(2026, 1, 2)


def test_reversed_range_is_rejected():
    with pytest.raises(ValidationError):
        resolve_analytics_range(date(2026, 1, 2), date(2026, 1, 1))


def test_range_longer_than_a_year_is_rejected():
    with pytest.raises(ValidationError):
        resolve_analytics_range(date(2024, 1, 1), date(2026, 1, 1))


def test_maximum_range_is_allowed():
    start, end = resolve_analytics_range(date(2025, 1, 1), date(2025, 12, 31))
    assert (end - start).days + 1 == 365
