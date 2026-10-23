"""Vietnam-local (UTC+7, no DST) day helpers for analytics.

Vietnam has observed a fixed UTC+7 offset without daylight saving since 1975,
so a fixed offset is both correct and dependency-free (no ``tzdata`` needed on
Windows). All persisted timestamps remain UTC; only day bucketing is local.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

VIETNAM_TZ = timezone(timedelta(hours=7), "Asia/Ho_Chi_Minh")
VIETNAM_UTC_OFFSET_MINUTES = 420


def to_utc(value: datetime) -> datetime:
    """Treat naive database timestamps as UTC and return an aware datetime."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def vietnam_now(now: datetime | None = None) -> datetime:
    return (to_utc(now) if now is not None else datetime.now(timezone.utc)).astimezone(
        VIETNAM_TZ
    )


def vietnam_today(now: datetime | None = None) -> date:
    return vietnam_now(now).date()


def day_start_utc(day: date) -> datetime:
    """UTC instant of 00:00 Vietnam local time on ``day``."""
    return datetime.combine(day, time.min, tzinfo=VIETNAM_TZ).astimezone(
        timezone.utc
    )


def day_end_exclusive_utc(day: date) -> datetime:
    """UTC instant of 00:00 Vietnam local time on the day after ``day``."""
    return day_start_utc(day + timedelta(days=1))


def vietnam_date_of(value: datetime) -> date:
    return to_utc(value).astimezone(VIETNAM_TZ).date()
