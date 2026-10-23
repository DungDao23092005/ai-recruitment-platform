from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException, ValidationError
from app.domain.enums import ApplicationStatus, SubscriptionStatus
from app.models import RecruiterProfile, RecruitmentPlan, Subscription, User
from app.repositories.analytics_repository import AnalyticsRepository
from app.schemas.analytics import (
    ANALYTICS_TIMEZONE,
    AnalyticsDailyPoint,
    AnalyticsDataQuality,
    AnalyticsFunnelStage,
    AnalyticsJobRow,
    AnalyticsKpis,
    AnalyticsQuotaLine,
    AnalyticsQuotaStatus,
    RecruiterAnalyticsResponse,
)
from app.services.analytics_time import (
    day_end_exclusive_utc,
    day_start_utc,
    vietnam_today,
)

MAX_ANALYTICS_RANGE_DAYS = 366
DEFAULT_ANALYTICS_RANGE_DAYS = 30

_STATUS_REVIEW = {
    ApplicationStatus.UNDER_REVIEW.value,
    ApplicationStatus.SHORTLISTED.value,
    ApplicationStatus.INTERVIEWING.value,
    ApplicationStatus.OFFERED.value,
    ApplicationStatus.ACCEPTED.value,
}
_STATUS_INTERVIEWING = {
    ApplicationStatus.INTERVIEWING.value,
    ApplicationStatus.OFFERED.value,
    ApplicationStatus.ACCEPTED.value,
}
_STATUS_OFFERED = {
    ApplicationStatus.OFFERED.value,
    ApplicationStatus.ACCEPTED.value,
}
_STATUS_ACCEPTED = {ApplicationStatus.ACCEPTED.value}


def resolve_analytics_range(
    start_date: date | None,
    end_date: date | None,
    *,
    now: datetime | None = None,
) -> tuple[date, date]:
    """Default to the last 30 Vietnam-local days and validate the range."""
    today = vietnam_today(now)
    resolved_end = end_date or today
    resolved_start = start_date or (
        resolved_end - timedelta(days=DEFAULT_ANALYTICS_RANGE_DAYS - 1)
    )
    if resolved_start > resolved_end:
        raise ValidationError("start_date must be on or before end_date")
    span = (resolved_end - resolved_start).days + 1
    if span > MAX_ANALYTICS_RANGE_DAYS:
        raise ValidationError(
            f"Analytics date range cannot exceed {MAX_ANALYTICS_RANGE_DAYS} days"
        )
    return resolved_start, resolved_end


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = AnalyticsRepository(session)

    async def _resolve_company_id(
        self, current_user: User, job_id: uuid.UUID | None = None
    ) -> uuid.UUID:
        company_id = await self.session.scalar(
            select(RecruiterProfile.company_id).where(
                RecruiterProfile.user_id == current_user.id,
                RecruiterProfile.is_deleted == False,  # noqa: E712
            )
        )
        if company_id is None:
            raise EntityNotFoundException("Recruiter company not found")

        if job_id is not None:
            from app.models import Job

            owned = await self.session.scalar(
                select(Job.id).where(
                    Job.id == job_id,
                    Job.company_id == company_id,
                )
            )
            if owned is None:
                raise EntityNotFoundException(f"Job {job_id} not found")
        return company_id

    async def _quota_status(self, user_id: uuid.UUID) -> AnalyticsQuotaStatus:
        subscription = await self.session.scalar(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.is_deleted == False,  # noqa: E712
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at > datetime.now(timezone.utc),
            )
            .order_by(Subscription.expires_at.desc())
            .limit(1)
        )
        if subscription is None:
            return AnalyticsQuotaStatus()

        plan = await self.session.get(RecruitmentPlan, subscription.plan_id)

        def line(limit: int, used: int) -> AnalyticsQuotaLine:
            return AnalyticsQuotaLine(
                limit=int(limit),
                used=int(used),
                remaining=max(0, int(limit) - int(used)),
            )

        return AnalyticsQuotaStatus(
            subscription_status="active",
            plan_name=plan.name if plan is not None else None,
            expires_at=subscription.expires_at,
            job_posts=line(
                subscription.max_job_posts, subscription.job_posts_used
            ),
            candidate_searches=line(
                subscription.max_candidate_searches,
                subscription.candidate_searches_used,
            ),
            ai_features=line(
                subscription.max_ai_features,
                subscription.ai_features_used,
            ),
        )

    async def get_recruiter_dashboard(
        self,
        current_user: User,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        job_id: uuid.UUID | None = None,
    ) -> RecruiterAnalyticsResponse:
        company_id = await self._resolve_company_id(current_user, job_id)
        start_day, end_day = resolve_analytics_range(start_date, end_date)
        today = vietnam_today()

        start_utc = day_start_utc(start_day)
        end_utc = day_end_exclusive_utc(end_day)

        aggregated_rows = await self.repository.aggregate_view_counts(
            company_id, start_day, end_day
        )
        raw_rows = await self.repository.raw_view_counts(
            company_id, start_utc, end_utc
        )

        def key_of(row: dict[str, Any]) -> tuple[uuid.UUID, date]:
            return (row["job_id"], row["view_date"])

        if job_id is not None:
            aggregated_rows = [
                row for row in aggregated_rows if row["job_id"] == job_id
            ]
            raw_rows = [
                row for row in raw_rows if row["job_id"] == job_id
            ]

        aggregated = {key_of(row): row for row in aggregated_rows}
        raw = {key_of(row): row for row in raw_rows}

        merged: dict[tuple[uuid.UUID, date], dict[str, Any]] = {}
        raw_fallback_dates: set[date] = set()
        for key in set(aggregated) | set(raw):
            _, view_day = key
            if view_day == today:
                # Today is live: raw events are always authoritative so a
                # partial rollup can never double count.
                row = raw.get(key)
            elif key in aggregated:
                row = aggregated[key]
            else:
                row = raw.get(key)
                if row is not None:
                    raw_fallback_dates.add(view_day)
            if row is not None:
                merged[key] = row

        totals_by_day: dict[date, list[int]] = defaultdict(
            lambda: [0, 0, 0]
        )
        per_job_views: dict[uuid.UUID, list[int]] = defaultdict(
            lambda: [0, 0, 0]
        )
        job_ids: set[uuid.UUID] = set()
        for (view_job_id, view_day), row in merged.items():
            job_ids.add(view_job_id)
            totals = (
                int(row["total_views"]),
                int(row["unique_views"]),
                int(row["unverified_views"]),
            )
            bucket = totals_by_day[view_day]
            job_bucket = per_job_views[view_job_id]
            for index in range(3):
                bucket[index] += totals[index]
                job_bucket[index] += totals[index]

        daily_views: list[AnalyticsDailyPoint] = []
        cursor = start_day
        while cursor <= end_day:
            total, unique, unverified = totals_by_day.get(cursor, [0, 0, 0])
            daily_views.append(
                AnalyticsDailyPoint(
                    date=cursor,
                    total_views=total,
                    unique_views=unique,
                    unverified_views=unverified,
                )
            )
            cursor += timedelta(days=1)

        funnel_rows = await self.repository.funnel_rows(
            company_id, start_utc, end_utc
        )
        if job_id is not None:
            funnel_rows = [
                row for row in funnel_rows if row["job_id"] == job_id
            ]
        funnel_counts, applications_by_job, funnel_job_ids = self._funnel(
            funnel_rows
        )
        job_ids.update(funnel_job_ids)

        hires_by_job = await self.repository.hires_by_job(
            company_id, start_utc, end_utc
        )
        if job_id is not None:
            hires_by_job = {
                key: value
                for key, value in hires_by_job.items()
                if key == job_id
            }
        job_ids.update(hires_by_job)
        avg_time_to_hire = await self.repository.avg_time_to_hire_days(
            company_id, start_utc, end_utc, job_id=job_id
        )

        job_metadata = await self.repository.job_metadata(sorted(job_ids))
        job_rows: list[AnalyticsJobRow] = []
        for row_job_id in job_ids:
            job = job_metadata.get(row_job_id)
            views = per_job_views.get(row_job_id, [0, 0, 0])
            job_rows.append(
                AnalyticsJobRow(
                    job_id=row_job_id,
                    job_title=job.title if job is not None else "—",
                    job_status=(
                        job.status.value if job is not None else "unknown"
                    ),
                    total_views=views[0],
                    unique_views=views[1],
                    unverified_views=views[2],
                    applications=applications_by_job.get(row_job_id, 0),
                    hires=hires_by_job.get(row_job_id, 0),
                )
            )
        job_rows.sort(
            key=lambda row: (
                -row.total_views,
                -row.applications,
                row.job_title.lower(),
            )
        )

        total_views = sum(point.total_views for point in daily_views)
        unique_views = sum(point.unique_views for point in daily_views)
        unverified_views = sum(
            point.unverified_views for point in daily_views
        )
        total_applications = funnel_counts["applied"]
        hires = sum(hires_by_job.values())
        conversion_rate = (
            round((hires / total_applications) * 100.0, 2)
            if total_applications > 0
            else 0.0
        )

        quota = await self._quota_status(current_user.id)

        return RecruiterAnalyticsResponse(
            timezone=ANALYTICS_TIMEZONE,
            start_date=start_day,
            end_date=end_day,
            generated_at=datetime.now(timezone.utc),
            kpis=AnalyticsKpis(
                total_views=total_views,
                unique_views=unique_views,
                unverified_views=unverified_views,
                total_applications=total_applications,
                hires=hires,
                conversion_rate=conversion_rate,
                avg_time_to_hire_days=(
                    round(avg_time_to_hire, 2)
                    if avg_time_to_hire is not None
                    else None
                ),
            ),
            funnel=[
                AnalyticsFunnelStage(stage=stage, count=count)
                for stage, count in funnel_counts.items()
            ],
            daily_views=daily_views,
            jobs=job_rows,
            quota=quota,
            data_quality=AnalyticsDataQuality(
                unique_views_reliable=unverified_views == 0,
                raw_fallback_dates=sorted(raw_fallback_dates),
                note=(
                    "Lượt xem hôm nay được tính trực tiếp từ sự kiện thô. "
                    "Số liệu các ngày trước dùng bảng tổng hợp theo ngày "
                    "(múi giờ Việt Nam)."
                ),
            ),
        )

    @staticmethod
    def _funnel(
        rows: list[dict[str, Any]],
    ) -> tuple[dict[str, int], dict[uuid.UUID, int], set[uuid.UUID]]:
        applied = len(rows)
        review = interviewing = offered = accepted = 0
        applications_by_job: dict[uuid.UUID, int] = defaultdict(int)
        job_ids: set[uuid.UUID] = set()

        for row in rows:
            status = str(row["status"])
            applications_by_job[row["job_id"]] += 1
            job_ids.add(row["job_id"])
            if row["reached_review"] or status in _STATUS_REVIEW:
                review += 1
            if row["reached_interviewing"] or status in _STATUS_INTERVIEWING:
                interviewing += 1
            if row["reached_offered"] or status in _STATUS_OFFERED:
                offered += 1
            if row["reached_accepted"] or status in _STATUS_ACCEPTED:
                accepted += 1

        # Direct hires (interviewing -> accepted) skip the offered milestone in
        # the audit trail. Clamp the funnel so stage counts stay monotonic.
        offered = max(offered, accepted)
        interviewing = max(interviewing, offered)
        review = max(review, interviewing)
        applied = max(applied, review)

        return (
            {
                "applied": applied,
                "under_review": review,
                "interviewing": interviewing,
                "offered": offered,
                "accepted": accepted,
            },
            dict(applications_by_job),
            job_ids,
        )
