from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Sequence

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, JobViewDailyAggregate, JobViewEvent

# SQL Server has no timezone-aware date truncation, so the fixed UTC+7 offset
# (Vietnam has no DST) is applied explicitly. Keep this in sync with
# ``app.services.analytics_time.VIETNAM_UTC_OFFSET_MINUTES``.
_VN_DATE_SQL = "CAST(DATEADD(minute, 420, {column}) AS date)"

RAW_VIEW_COUNTS_SQL = text(
    f"""
    SELECT job_id,
           {_VN_DATE_SQL.format(column="viewed_at")} AS view_date,
           COUNT(*) AS total_views,
           COALESCE(SUM(CASE WHEN is_unique = 1 THEN 1 ELSE 0 END), 0)
               AS unique_views,
           COALESCE(SUM(CASE WHEN is_unique IS NULL THEN 1 ELSE 0 END), 0)
               AS unverified_views
    FROM job_view_events
    WHERE company_id = :company_id
      AND viewed_at >= :start_utc
      AND viewed_at < :end_utc
    GROUP BY job_id, {_VN_DATE_SQL.format(column="viewed_at")}
    """
)

RAW_VIEW_COUNTS_FOR_DAY_SQL = text(
    f"""
    SELECT company_id,
           job_id,
           {_VN_DATE_SQL.format(column="viewed_at")} AS view_date,
           COUNT(*) AS total_views,
           COALESCE(SUM(CASE WHEN is_unique = 1 THEN 1 ELSE 0 END), 0)
               AS unique_views,
           COALESCE(SUM(CASE WHEN is_unique IS NULL THEN 1 ELSE 0 END), 0)
               AS unverified_views
    FROM job_view_events
    WHERE viewed_at >= :start_utc
      AND viewed_at < :end_utc
    GROUP BY company_id, job_id, {_VN_DATE_SQL.format(column="viewed_at")}
    """
)

AGGREGATE_VIEW_COUNTS_SQL = text(
    """
    SELECT job_id,
           view_date,
           total_views,
           unique_views,
           unverified_views,
           raw_pruned
    FROM job_view_daily_aggregates
    WHERE company_id = :company_id
      AND view_date >= :start_date
      AND view_date <= :end_date
    """
)

EXISTING_AGGREGATES_SQL = text(
    """
    SELECT job_id, raw_pruned
    FROM job_view_daily_aggregates
    WHERE view_date = :view_date
    """
)

UPSERT_AGGREGATE_SQL = text(
    """
    UPDATE job_view_daily_aggregates
    SET total_views = :total_views,
        unique_views = :unique_views,
        unverified_views = :unverified_views,
        aggregated_at = :aggregated_at,
        updated_at = :aggregated_at
    WHERE job_id = :job_id
      AND view_date = :view_date
    """
)

MARK_RAW_PRUNED_SQL = text(
    """
    UPDATE job_view_daily_aggregates
    SET raw_pruned = 1,
        updated_at = :now
    WHERE view_date < :cutoff_date
      AND raw_pruned = 0
      AND EXISTS (
          SELECT 1
          FROM job_view_events e
          WHERE e.job_id = job_view_daily_aggregates.job_id
            AND CAST(DATEADD(minute, 420, e.viewed_at) AS date) =
                job_view_daily_aggregates.view_date
      )
    """
)

DELETE_PRUNED_EVENTS_SQL = text(
    """
    DELETE e
    FROM job_view_events AS e
    WHERE e.viewed_at < :cutoff_utc
      AND EXISTS (
          SELECT 1
          FROM job_view_daily_aggregates a
          WHERE a.job_id = e.job_id
            AND a.view_date =
                CAST(DATEADD(minute, 420, e.viewed_at) AS date)
            AND a.raw_pruned = 1
      )
    """
)

FUNNEL_ROWS_SQL = text(
    """
    SELECT a.id AS application_id,
           a.job_id AS job_id,
           a.status AS status,
           MAX(CASE WHEN aa.to_status IN ('under_review', 'shortlisted')
                    THEN 1 ELSE 0 END) AS reached_review,
           MAX(CASE WHEN aa.to_status = 'interviewing'
                    THEN 1 ELSE 0 END) AS reached_interviewing,
           MAX(CASE WHEN aa.to_status = 'offered'
                    THEN 1 ELSE 0 END) AS reached_offered,
           MAX(CASE WHEN aa.to_status = 'accepted'
                    THEN 1 ELSE 0 END) AS reached_accepted
    FROM applications a
    JOIN jobs j ON j.id = a.job_id
    LEFT JOIN application_activities aa ON aa.application_id = a.id
    WHERE j.company_id = :company_id
      AND a.is_deleted = 0
      AND a.created_at >= :start_utc
      AND a.created_at < :end_utc
    GROUP BY a.id, a.job_id, a.status
    """
)

AVG_TIME_TO_HIRE_SQL = text(
    """
    SELECT AVG(
               CAST(
                   CASE
                       WHEN f.first_accepted >= a.created_at
                       THEN DATEDIFF(minute, a.created_at, f.first_accepted)
                   END
                   AS float
               ) / 1440.0
           ) AS avg_days
    FROM applications a
    JOIN jobs j ON j.id = a.job_id
    CROSS APPLY (
        SELECT MIN(aa.created_at) AS first_accepted
        FROM application_activities aa
        WHERE aa.application_id = a.id
          AND aa.to_status = 'accepted'
    ) f
    WHERE j.company_id = :company_id
      AND a.is_deleted = 0
      AND f.first_accepted IS NOT NULL
      AND f.first_accepted >= :start_utc
      AND f.first_accepted < :end_utc
    """
)

HIRES_BY_JOB_SQL = text(
    """
    SELECT a.job_id AS job_id, COUNT(*) AS hires
    FROM applications a
    JOIN jobs j ON j.id = a.job_id
    CROSS APPLY (
        SELECT MIN(aa.created_at) AS first_accepted
        FROM application_activities aa
        WHERE aa.application_id = a.id
          AND aa.to_status = 'accepted'
    ) f
    WHERE j.company_id = :company_id
      AND a.is_deleted = 0
      AND f.first_accepted IS NOT NULL
      AND f.first_accepted >= :start_utc
      AND f.first_accepted < :end_utc
    GROUP BY a.job_id
    """
)


def _as_uuid(value: Any) -> uuid.UUID:
    """Normalise a SQL Server ``uniqueidentifier`` returned as a string.

    Raw ``text()`` queries on MSSQL do not always apply the ORM ``Uuid`` type,
    so rows may contain upper-case UUID strings. The service and rollup worker
    compare these values against ``uuid.UUID`` objects, so every boundary must
    return real UUIDs.
    """
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_view(
        self,
        *,
        job_id: uuid.UUID,
        company_id: uuid.UUID,
        is_unique: bool | None,
        viewed_at: datetime,
    ) -> JobViewEvent:
        event = JobViewEvent(
            job_id=job_id,
            company_id=company_id,
            is_unique=is_unique,
            viewed_at=viewed_at,
        )
        self.session.add(event)
        return event

    async def raw_view_counts(
        self,
        company_id: uuid.UUID,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[dict[str, Any]]:
        result = await self.session.execute(
            RAW_VIEW_COUNTS_SQL,
            {
                "company_id": str(company_id),
                "start_utc": start_utc,
                "end_utc": end_utc,
            },
        )
        return [
            {**dict(row), "job_id": _as_uuid(row["job_id"])}
            for row in result.mappings().all()
        ]

    async def raw_view_counts_for_day(
        self, start_utc: datetime, end_utc: datetime
    ) -> list[dict[str, Any]]:
        result = await self.session.execute(
            RAW_VIEW_COUNTS_FOR_DAY_SQL,
            {"start_utc": start_utc, "end_utc": end_utc},
        )
        return [
            {
                **dict(row),
                "job_id": _as_uuid(row["job_id"]),
                "company_id": _as_uuid(row["company_id"]),
            }
            for row in result.mappings().all()
        ]

    async def aggregate_view_counts(
        self,
        company_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        result = await self.session.execute(
            AGGREGATE_VIEW_COUNTS_SQL,
            {
                "company_id": str(company_id),
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        return [
            {**dict(row), "job_id": _as_uuid(row["job_id"])}
            for row in result.mappings().all()
        ]

    async def aggregate_flags_for_date(
        self, view_date: date
    ) -> dict[uuid.UUID, bool]:
        result = await self.session.execute(
            EXISTING_AGGREGATES_SQL, {"view_date": view_date}
        )
        return {
            _as_uuid(row.job_id): bool(row.raw_pruned) for row in result.all()
        }

    async def upsert_daily_aggregate(
        self,
        *,
        job_id: uuid.UUID,
        company_id: uuid.UUID,
        view_date: date,
        total_views: int,
        unique_views: int,
        unverified_views: int,
        aggregated_at: datetime,
    ) -> None:
        result = await self.session.execute(
            UPSERT_AGGREGATE_SQL,
            {
                "job_id": str(job_id),
                "view_date": view_date,
                "total_views": int(total_views),
                "unique_views": int(unique_views),
                "unverified_views": int(unverified_views),
                "aggregated_at": aggregated_at,
            },
        )
        if result.rowcount:
            return
        self.session.add(
            JobViewDailyAggregate(
                job_id=job_id,
                company_id=company_id,
                view_date=view_date,
                total_views=int(total_views),
                unique_views=int(unique_views),
                unverified_views=int(unverified_views),
                aggregated_at=aggregated_at,
            )
        )

    async def mark_raw_pruned(
        self, cutoff_date: date, now: datetime
    ) -> int:
        result = await self.session.execute(
            MARK_RAW_PRUNED_SQL, {"cutoff_date": cutoff_date, "now": now}
        )
        return int(result.rowcount or 0)

    async def delete_pruned_events(self, cutoff_utc: datetime) -> int:
        result = await self.session.execute(
            DELETE_PRUNED_EVENTS_SQL, {"cutoff_utc": cutoff_utc}
        )
        return int(result.rowcount or 0)

    async def funnel_rows(
        self,
        company_id: uuid.UUID,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[dict[str, Any]]:
        result = await self.session.execute(
            FUNNEL_ROWS_SQL,
            {
                "company_id": str(company_id),
                "start_utc": start_utc,
                "end_utc": end_utc,
            },
        )
        return [
            {
                **dict(row),
                "application_id": _as_uuid(row["application_id"]),
                "job_id": _as_uuid(row["job_id"]),
            }
            for row in result.mappings().all()
        ]

    async def avg_time_to_hire_days(
        self,
        company_id: uuid.UUID,
        start_utc: datetime,
        end_utc: datetime,
        job_id: uuid.UUID | None = None,
    ) -> float | None:
        sql = AVG_TIME_TO_HIRE_SQL
        params: dict[str, Any] = {
            "company_id": str(company_id),
            "start_utc": start_utc,
            "end_utc": end_utc,
        }
        if job_id is not None:
            sql = text(
                AVG_TIME_TO_HIRE_SQL.text
                + "\n      AND a.job_id = :job_id"
            )
            params["job_id"] = str(job_id)
        value = await self.session.scalar(sql, params)
        return float(value) if value is not None else None

    async def hires_by_job(
        self,
        company_id: uuid.UUID,
        start_utc: datetime,
        end_utc: datetime,
    ) -> dict[uuid.UUID, int]:
        result = await self.session.execute(
            HIRES_BY_JOB_SQL,
            {
                "company_id": str(company_id),
                "start_utc": start_utc,
                "end_utc": end_utc,
            },
        )
        return {
            _as_uuid(row.job_id): int(row.hires) for row in result.all()
        }

    async def job_metadata(
        self, job_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, Job]:
        if not job_ids:
            return {}
        result = await self.session.execute(
            select(Job).where(Job.id.in_(list(job_ids)))
        )
        return {job.id: job for job in result.scalars().all()}
