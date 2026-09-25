#!/usr/bin/env python3
"""Reconcile Qdrant resume vectors with Azure SQL Server.

This script scans all resume vectors in Qdrant and removes stale vectors
whose corresponding candidate/resume no longer exists in Azure SQL Server
or whose candidate/user is inactive/deleted.

Usage:
    python -m backend.scripts.reconcile_qdrant_resumes --dry-run
    python -m backend.scripts.reconcile_qdrant_resumes
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
from app.models import CandidateProfile, Resume, User
from sqlalchemy import select

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class ReconciliationError(Exception):
    """Base exception for reconciliation errors."""
    pass


class SourceOfTruthUnavailableError(ReconciliationError):
    """Raised when SQL source of truth is unavailable."""
    pass


class QdrantEnumerationError(ReconciliationError):
    """Raised when Qdrant enumeration fails."""
    pass


async def run_reconcile(
    dry_run: bool = True,
    repo: QdrantVectorRepository | None = None,
) -> dict:
    """Reconcile Qdrant resume vectors with Azure SQL Server.

    Args:
        dry_run: If True, only identify stale vectors without deleting.
        repo: Optional pre-configured QdrantVectorRepository for testing.

    Returns:
        Dictionary with reconciliation counters.

    Raises:
        SourceOfTruthUnavailableError: If SQL source of truth is unavailable.
        QdrantEnumerationError: If Qdrant enumeration fails.
    """
    logger.info("Starting Qdrant resume vector reconciliation...")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    logger.info("Target collection: resumes")

    # Initialize Qdrant repository (use provided instance for testing, otherwise create new)
    if repo is None:
        repo = QdrantVectorRepository()

    # Initialize counters
    total_scanned = 0
    valid_count = 0
    stale_count = 0
    deleted_count = 0
    failed_count = 0
    failed_points = []

    # Get all active candidate IDs from Azure SQL Server
    # A candidate is "active" if:
    # 1. Has a primary resume (is_primary=True, is_deleted=False)
    # 2. Candidate profile is not deleted (is_deleted=False)
    # 3. User is active (is_active=True)
    logger.info("Fetching active candidate IDs from Azure SQL Server...")
    async with async_session_factory() as session:
        sql_active_candidate_ids: set[uuid.UUID] = set()
        try:
            # Only fetch active candidates with primary resumes
            stmt = select(Resume.candidate_id).join(
                CandidateProfile, Resume.candidate_id == CandidateProfile.id
            ).join(
                User, CandidateProfile.user_id == User.id
            ).where(
                Resume.is_primary == True,  # noqa: E712
                Resume.is_deleted == False,  # noqa: E712
                CandidateProfile.is_deleted == False,  # noqa: E712
                User.is_active == True,  # noqa: E712
            )
            result = await session.execute(stmt)
            sql_active_candidate_ids = set(result.scalars().all())
        except Exception as e:
            logger.error(f"CRITICAL: Failed to fetch active candidates from SQL Server: {e}")
            logger.error("Aborting reconciliation - cannot verify candidate existence without SQL Server")
            raise SourceOfTruthUnavailableError("SQL source of truth unavailable") from e

    logger.info(f"SQL Server active primary resume candidates: {len(sql_active_candidate_ids)}")

    # Scroll through all resume points in Qdrant
    logger.info("Scanning Qdrant resumes collection...")
    limit = 100
    offset = None
    collection_name = "resumes"

    while True:
        try:
            # Scroll through points in the resumes collection
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

                # Extract candidate_id from payload or use point ID
                candidate_id_str = payload.get("candidate_id") or str(point_id)

                try:
                    candidate_id = uuid.UUID(candidate_id_str)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid candidate_id in point {point_id}: {candidate_id_str}")
                    failed_count += 1
                    failed_points.append(str(point_id))
                    continue

                # Check if candidate is active in SQL Server
                if candidate_id in sql_active_candidate_ids:
                    valid_count += 1
                else:
                    stale_count += 1
                    logger.info(f"Stale vector found: {candidate_id} (point_id={point_id})")

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
            raise QdrantEnumerationError("Qdrant enumeration failed") from e

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
        "sql_active_candidates": len(sql_active_candidate_ids),
        "scanned": total_scanned,
        "valid": valid_count,
        "stale": stale_count,
        "deleted": deleted_count,
        "failed": failed_count,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Reconcile Qdrant resume vectors with Azure SQL Server"
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


# Expose callable function for testing
async def reconcile_resumes(
    dry_run: bool = True,
    repo: QdrantVectorRepository | None = None,
) -> dict:
    """Callable entry point for resume vector reconciliation.
    
    Args:
        dry_run: If True, only identify stale vectors without deleting.
        repo: Optional pre-configured QdrantVectorRepository for testing.
        
    Returns:
        Dictionary with reconciliation counters.
        
    Raises:
        SourceOfTruthUnavailableError: If SQL source of truth is unavailable.
        QdrantEnumerationError: If Qdrant enumeration fails.
    """
    return await run_reconcile(dry_run=dry_run, repo=repo)


if __name__ == "__main__":
    main()