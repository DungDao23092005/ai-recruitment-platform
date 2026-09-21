#!/usr/bin/env python3
"""Synchronize published SQL Server jobs to Qdrant jobs collection.

This script indexes current valid (PUBLISHED, non-deleted) jobs from SQL Server
into the Qdrant 'jobs' collection using the project's existing embedding and
indexing architecture. It does NOT delete orphan Qdrant vectors.

Usage:
    python -m backend.scripts.sync_jobs_qdrant --dry-run
    python -m backend.scripts.sync_jobs_qdrant
"""

import argparse
import asyncio
import logging
import sys
import uuid

from sqlalchemy import func, select

from app.ai.vector_db.qdrant_client import QdrantVectorRepository
from app.database.session import async_session_factory
from app.domain.enums import JobStatus
from app.models import Job
from app.services.job_service import JobService

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def run_sync(dry_run: bool = False) -> dict:
    """Sync published SQL Server jobs to Qdrant jobs collection.

    Args:
        dry_run: If True, only inspect and report intended actions without writing.

    Returns:
        Dictionary with synchronization counters.
    """
    logger.info("Starting SQL Server -> Qdrant jobs synchronization...")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    logger.info("Target: Qdrant jobs collection (via JobService/QdrantVectorRepository)")

    # Initialize Qdrant repository for inspection
    repo = QdrantVectorRepository()

    # Get Qdrant collection info and current point IDs
    logger.info("Inspecting Qdrant jobs collection...")
    collection_info = await repo.client.get_collection(collection_name="jobs")
    qdrant_dimension = collection_info.config.params.vectors.size
    qdrant_points_count = collection_info.points_count

    # Scroll to get all existing job IDs in Qdrant (non-deleted)
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    qdrant_job_ids: set[uuid.UUID] = set()
    limit = 500  # Increased to reduce pagination calls
    offset = None
    while True:
        scroll_result = await repo.client.scroll(
            collection_name="jobs",
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
            scroll_filter=Filter(
                must_not=[
                    FieldCondition(key="is_deleted", match=MatchValue(value=True))
                ]
            ),
        )
        points = scroll_result[0]
        offset = scroll_result[1]

        if not points:
            break

        for point in points:
            payload = point.payload or {}
            job_id_str = payload.get("job_id") or str(point.id)
            try:
                qdrant_job_ids.add(uuid.UUID(job_id_str))
            except (ValueError, TypeError):
                logger.warning(f"Invalid job_id in Qdrant point {point.id}: {job_id_str}")

        if offset is None:
            break

    logger.info(f"Qdrant jobs collection: {qdrant_points_count} points, {qdrant_dimension} dimensions")
    logger.info(f"Qdrant valid job IDs (non-deleted): {len(qdrant_job_ids)}")

    # Fetch published, non-deleted jobs from SQL Server (for planning)
    logger.info("Fetching published jobs from SQL Server...")
    async with async_session_factory() as session:
        stmt = select(Job).where(
            Job.status == JobStatus.PUBLISHED,
            Job.is_deleted == False,  # noqa: E712
        )
        result = await session.execute(stmt)
        sql_jobs = list(result.scalars().all())

    sql_job_ids = {job.id for job in sql_jobs}
    logger.info(f"SQL Server published jobs (non-deleted): {len(sql_jobs)}")

    # Compute reconciliation stats
    already_indexed = sql_job_ids & qdrant_job_ids
    missing = sql_job_ids - qdrant_job_ids
    orphans = qdrant_job_ids - sql_job_ids

    logger.info("\n=== Synchronization Plan ===")
    logger.info(f"SQL published jobs:           {len(sql_jobs)}")
    logger.info(f"Qdrant points (total):        {qdrant_points_count}")
    logger.info(f"Qdrant valid job IDs:         {len(qdrant_job_ids)}")
    logger.info(f"Already indexed (intersection): {len(already_indexed)}")
    logger.info(f"Missing (need upsert):        {len(missing)}")
    logger.info(f"Orphan Qdrant IDs (detected): {len(orphans)}")

    if dry_run:
        if missing:
            logger.info("\nJobs that would be indexed:")
            for job in sql_jobs:
                if job.id in missing:
                    logger.info(f"  - {job.id} - {job.title}")
        else:
            logger.info("\nAll SQL published jobs already indexed in Qdrant.")
        logger.info("\nDRY RUN completed. No vectors were written.")
        logger.info("Orphan Qdrant vectors were NOT deleted (preserved per policy).")

        return {
            "sql_jobs": len(sql_jobs),
            "qdrant_points_total": qdrant_points_count,
            "qdrant_valid_job_ids": len(qdrant_job_ids),
            "already_indexed": len(already_indexed),
            "missing": len(missing),
            "orphans": len(orphans),
            "upserted": 0,
            "failed": 0,
        }

    # Execute synchronization: upsert missing jobs
    if not missing:
        logger.info("\nAll SQL published jobs already indexed. Nothing to do.")
        return {
            "sql_jobs": len(sql_jobs),
            "qdrant_points_total": qdrant_points_count,
            "qdrant_valid_job_ids": len(qdrant_job_ids),
            "already_indexed": len(already_indexed),
            "missing": 0,
            "orphans": len(orphans),
            "upserted": 0,
            "failed": 0,
        }

    logger.info(f"\nUpserting {len(missing)} missing job(s) to Qdrant...")

    # Use JobService to reindex (handles embedding + upsert with correct schema)
    # Fetch jobs within the same session to avoid "not persistent" errors
    async with async_session_factory() as session:
        service = JobService(session=session)

        # Re-fetch the missing jobs in this session with skills loaded
        from sqlalchemy.orm import selectinload
        stmt = (
            select(Job)
            .options(
                selectinload(Job.skills),
                selectinload(Job.required_skills),
                selectinload(Job.preferred_skills),
                selectinload(Job.job_skills),
            )
            .where(
                Job.id.in_(missing),
                Job.status == JobStatus.PUBLISHED,
                Job.is_deleted == False,  # noqa: E712
            )
        )
        result = await session.execute(stmt)
        jobs_to_index = list(result.scalars().unique().all())

        success = 0
        failed = 0
        failed_jobs = []

        for job in jobs_to_index:
            try:
                await service._reindex_job(job)
                success += 1
                if success % 10 == 0 or success == len(jobs_to_index):
                    logger.info(f"[{success}/{len(jobs_to_index)}] upserted")
            except Exception as e:
                failed += 1
                failed_jobs.append(str(job.id))
                logger.error(f"Failed to index job {job.id} ({job.title}): {e}")

    logger.info("\n=== Synchronization Summary ===")
    logger.info(f"SQL published jobs:           {len(sql_jobs)}")
    logger.info(f"Qdrant points before:         {qdrant_points_count}")
    logger.info(f"Already indexed:              {len(already_indexed)}")
    logger.info(f"Missing (targeted):           {len(missing)}")
    logger.info(f"Successfully upserted:        {success}")
    logger.info(f"Failed:                       {failed}")
    logger.info(f"Orphan Qdrant IDs (preserved): {len(orphans)}")

    if failed_jobs:
        logger.info("\nFailed jobs:")
        for jid in failed_jobs:
            logger.info(f"  - {jid}")

    logger.info("\nOrphan Qdrant vectors were NOT deleted (preserved per policy).")

    return {
        "sql_jobs": len(sql_jobs),
        "qdrant_points_total": qdrant_points_count,
        "qdrant_valid_job_ids": len(qdrant_job_ids),
        "already_indexed": len(already_indexed),
        "missing": len(missing),
        "orphans": len(orphans),
        "upserted": success,
        "failed": failed,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Sync published SQL Server jobs to Qdrant jobs collection"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect and report intended actions without writing to Qdrant",
    )
    args = parser.parse_args()

    asyncio.run(run_sync(dry_run=args.dry_run))


if __name__ == "__main__":
    main()