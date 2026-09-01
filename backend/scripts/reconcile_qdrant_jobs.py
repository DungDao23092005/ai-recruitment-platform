#!/usr/bin/env python3
"""Reconcile Qdrant job vectors with Azure SQL Server.

This script scans all job vectors in Qdrant Cloud and removes stale vectors
whose corresponding Job UUID no longer exists in Azure SQL Server.

Usage:
    python -m backend.scripts.reconcile_qdrant_jobs --dry-run
    python -m backend.scripts.reconcile_qdrant_jobs
"""

import argparse
import asyncio
import logging
import sys
import uuid

from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.ai.vector_db.qdrant_client import QdrantVectorRepository
from app.core.config import settings
from app.database.session import async_session_factory
from app.models import Job
from sqlalchemy import select

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def run_reconcile(dry_run: bool = True) -> dict:
    """Reconcile Qdrant job vectors with Azure SQL Server.

    Args:
        dry_run: If True, only identify stale vectors without deleting.

    Returns:
        Dictionary with reconciliation counters.
    """
    logger.info("Starting Qdrant job vector reconciliation...")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    logger.info("Target collection: jobs")

    # Initialize Qdrant repository
    repo = QdrantVectorRepository()

    # Initialize counters
    total_scanned = 0
    valid_count = 0
    stale_count = 0
    deleted_count = 0
    failed_count = 0
    failed_points = []

    # Get all job IDs from Azure SQL Server
    logger.info("Fetching job IDs from Azure SQL Server...")
    async with async_session_factory() as session:
        sql_job_ids: set[uuid.UUID] = set()
        try:
            # Only fetch non-deleted jobs
            stmt = select(Job.id).where(Job.is_deleted == False)
            result = await session.execute(stmt)
            sql_job_ids = set(result.scalars().all())
        except Exception as e:
            logger.error(f"CRITICAL: Failed to fetch jobs from SQL Server: {e}")
            logger.error("Aborting reconciliation - cannot verify job existence without SQL Server")
            return {
                "sql_jobs": 0,
                "scanned": 0,
                "valid": 0,
                "stale": 0,
                "deleted": 0,
                "failed": 0,
            }

    logger.info(f"SQL Server jobs (is_deleted=False): {len(sql_job_ids)}")

    # Scroll through all job points in Qdrant
    logger.info("Scanning Qdrant jobs collection...")
    limit = 100
    offset = None
    collection_name = "jobs"

    while True:
        try:
            # Scroll through points in the jobs collection
            scroll_result = await repo.client.scroll(
                collection_name=collection_name,
                limit=limit,
                offset=offset,
                with_payload=True,
                with_vectors=False,
                scroll_filter=Filter(
                    must_not=[
                        FieldCondition(
                            key="is_deleted",
                            match=MatchValue(value=True),
                        )
                    ]
                ),
            )

            points = scroll_result[0]
            offset = scroll_result[1]

            if not points:
                break

            for point in points:
                total_scanned += 1
                point_id = point.id
                payload = point.payload or {}

                # Extract job_id from payload or use point ID
                job_id_str = payload.get("job_id") or str(point_id)

                try:
                    job_id = uuid.UUID(job_id_str)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid job_id in point {point_id}: {job_id_str}")
                    failed_count += 1
                    failed_points.append(str(point_id))
                    continue

                # Check if job exists in SQL Server
                if job_id in sql_job_ids:
                    valid_count += 1
                else:
                    stale_count += 1
                    logger.info(f"Stale vector found: {job_id} (point_id={point_id})")

                    if not dry_run:
                        try:
                            await repo.delete_vector(collection_name, point_id)
                            deleted_count += 1
                        except Exception as e:
                            failed_count += 1
                            failed_points.append(str(point_id))
                            logger.error(f"Failed to delete stale vector {point_id}: {e}")

            # Continue pagination
            if offset is None:
                break

        except Exception as e:
            logger.error(f"Error during Qdrant scroll: {e}")
            logger.error("Aborting reconciliation due to Qdrant error")
            return {
                "sql_jobs": len(sql_job_ids),
                "scanned": total_scanned,
                "valid": valid_count,
                "stale": stale_count,
                "deleted": deleted_count,
                "failed": failed_count,
            }

    # Summary
    logger.info("\n=== Reconciliation Summary ===")
    logger.info(f"Scanned:    {total_scanned}")
    logger.info(f"Valid:      {valid_count}")
    logger.info(f"Stale:      {stale_count}")
    if not dry_run:
        logger.info(f"Deleted:    {deleted_count}")
    else:
        logger.info(f"Would delete: {stale_count}")
    logger.info(f"Failed:     {failed_count}")

    if failed_points:
        logger.info("\nFailed points:")
        for pid in failed_points:
            logger.info(f"- {pid}")

    if dry_run:
        logger.info("\nDRY RUN completed. No vectors were deleted.")
        logger.info("Run without --dry-run to execute deletions.")

    return {
        "sql_jobs": len(sql_job_ids),
        "scanned": total_scanned,
        "valid": valid_count,
        "stale": stale_count,
        "deleted": deleted_count,
        "failed": failed_count,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Reconcile Qdrant job vectors with Azure SQL Server"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Identify stale vectors without deleting (default: True)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete stale vectors",
    )
    args = parser.parse_args()

    # Default to dry-run unless --execute is specified
    dry_run = not args.execute

    asyncio.run(run_reconcile(dry_run=dry_run))


if __name__ == "__main__":
    main()