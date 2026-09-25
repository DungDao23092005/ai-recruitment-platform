#!/usr/bin/env python3
"""Synchronize non-deleted SQL Server resumes (active candidates with primary resume) to Qdrant resumes collection.

This script indexes current valid (non-deleted) resumes from SQL Server
into the Qdrant 'resumes' collection using the project's existing embedding and
indexing architecture. It also handles orphan vector cleanup.

Usage:
    python -m backend.scripts.sync_resumes_qdrant --dry-run
    python -m backend.scripts.sync_resumes_qdrant
"""

import argparse
import asyncio
import logging
import sys
import uuid

from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.ai.embeddings.embedding_service import EmbeddingService, SentenceTransformerEmbeddingProvider
from app.ai.vector_db.qdrant_client import QdrantVectorRepository
from app.database.session import async_session_factory
from app.models import CandidateProfile, Resume, User
from app.repositories import ResumeRepository
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.ai_matching_service import AIMatchingService
from sqlalchemy import select
from sqlalchemy.orm import selectinload

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def run_sync(
    dry_run: bool = False,
    matching_service: AIMatchingService | None = None,
    repo: QdrantVectorRepository | None = None,
) -> dict:
    """Sync active SQL Server resumes to Qdrant resumes collection.

    Args:
        dry_run: If True, only inspect and report intended actions without writing.
        matching_service: Optional pre-configured AIMatchingService for testing.
        repo: Optional pre-configured QdrantVectorRepository for testing.

    Returns:
        Dictionary with synchronization counters.
    """
    logger.info("Starting SQL Server -> Qdrant resumes synchronization...")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    logger.info("Target: Qdrant resumes collection (via AIMatchingService/QdrantVectorRepository)")

    # Initialize services (use provided instances for testing, otherwise create new)
    if matching_service is None:
        matching_service = AIMatchingService()
    if repo is None:
        repo = QdrantVectorRepository()

    # Get Qdrant collection info and current point IDs
    logger.info("Inspecting Qdrant resumes collection...")
    try:
        collection_info = await repo.client.get_collection(collection_name="resumes")
        qdrant_dimension = collection_info.config.params.vectors.size
        qdrant_points_count = collection_info.points_count
    except Exception as e:
        logger.warning(f"Qdrant collection 'resumes' may not exist yet: {e}")
        qdrant_dimension = 0
        qdrant_points_count = 0

    # Scroll to get all existing resume IDs in Qdrant (non-deleted)
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    qdrant_resume_ids: set[uuid.UUID] = set()
    limit = 500  # Increased to reduce pagination calls
    offset = None
    while True:
        scroll_result = await repo.client.scroll(
            collection_name="resumes",
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
            resume_id_str = payload.get("candidate_id") or str(point.id)
            try:
                qdrant_resume_ids.add(uuid.UUID(resume_id_str))
            except (ValueError, TypeError):
                logger.warning(f"Invalid candidate_id in Qdrant point {point.id}: {resume_id_str}")

        if offset is None:
            break

    logger.info(f"Qdrant resumes collection: {qdrant_points_count} points, {qdrant_dimension} dimensions")
    logger.info(f"Qdrant valid resume IDs (non-deleted): {len(qdrant_resume_ids)}")

    # Fetch active resumes from SQL Server
    # We need candidates that:
    # 1. Have a primary resume (is_primary=True, is_deleted=False)
    # 2. The candidate profile is not deleted (is_deleted=False)
    # 3. The user is active (is_active=True)
    logger.info("Fetching active primary resumes from SQL Server...")
    async with async_session_factory() as session:
        stmt = select(Resume).options(selectinload(Resume.candidate).selectinload(CandidateProfile.user)).where(
            Resume.is_primary == True,  # noqa: E712
            Resume.is_deleted == False,  # noqa: E712
            CandidateProfile.is_deleted == False,  # noqa: E712
            User.is_active == True,  # noqa: E712
        )
        result = await session.execute(stmt)
        sql_resumes = list(result.scalars().all())

    sql_resume_ids = {resume.candidate_id for resume in sql_resumes}
    logger.info(f"SQL Server active primary resumes: {len(sql_resumes)}")

    # Compute reconciliation stats
    already_indexed = sql_resume_ids & qdrant_resume_ids
    missing = sql_resume_ids - qdrant_resume_ids
    orphans = qdrant_resume_ids - sql_resume_ids

    logger.info("\n=== Synchronization Plan ===")
    logger.info(f"SQL active primary resumes: {len(sql_resumes)}")
    logger.info(f"Qdrant points (total):              {qdrant_points_count}")
    logger.info(f"Qdrant valid resume IDs:               {len(qdrant_resume_ids)}")
    logger.info(f"Already indexed (intersection):     {len(already_indexed)}")
    logger.info(f"Missing (need upsert):              {len(missing)}")
    logger.info(f"Orphan Qdrant IDs (detected):       {len(orphans)}")

    if dry_run:
        if missing:
            logger.info("\nResumes that would be indexed:")
            for resume in sql_resumes:
                if resume.candidate_id in missing:
                    candidate = resume.candidate
                    logger.info(f"  - {resume.candidate_id} - {candidate.user.email if candidate and candidate.user else 'unknown'} ({candidate.full_name or 'unnamed'})")
        else:
            logger.info("\nAll SQL active primary resumes already indexed in Qdrant.")
        logger.info("\nDRY RUN completed. No vectors were written.")
        logger.info("Orphan Qdrant vectors were NOT deleted (preserved per policy).")

        return {
            "sql_resumes": len(sql_resumes),
            "qdrant_points_total": qdrant_points_count,
            "qdrant_valid_resume_ids": len(qdrant_resume_ids),
            "already_indexed": len(already_indexed),
            "missing": len(missing),
            "orphans": len(orphans),
            "upserted": 0,
            "failed": 0,
        }

    # Execute synchronization: upsert missing resumes
    if not missing:
        logger.info("\nAll SQL active primary resumes already indexed. Nothing to do.")
        return {
            "sql_resumes": len(sql_resumes),
            "qdrant_points_total": qdrant_points_count,
            "qdrant_valid_resume_ids": len(qdrant_resume_ids),
            "already_indexed": len(already_indexed),
            "missing": 0,
            "orphans": len(orphans),
            "upserted": 0,
            "failed": 0,
        }

    logger.info(f"\nUpserting {len(missing)} missing resume(s) to Qdrant...")

    # Use the provided AIMatchingService (or the one created above) to reindex
    # matching_service is already initialized above (either passed or created)

    # Fetch the missing resumes with full data needed for embedding
    # We need: candidate_id, parsed_data, and candidate info for email/name
    async with async_session_factory() as session:
        stmt = (
            select(Resume)
            .options(
                selectinload(Resume.candidate).selectinload(CandidateProfile.user),
            )
            .where(
                Resume.candidate_id.in_(missing),
                Resume.is_primary == True,  # noqa: E712
                Resume.is_deleted == False,  # noqa: E712
                CandidateProfile.is_deleted == False,  # noqa: E712
                User.is_active == True,  # noqa: E712
            )
        )
        result = await session.execute(stmt)
        resumes_to_index = list(result.scalars().unique().all())

    success = 0
    failed = 0
    failed_resumes = []

    for resume in resumes_to_index:
        try:
            candidate = resume.candidate
            # Reconstruct ParsedResumeSchema from stored parsed_data
            parsed_data = resume.parsed_data or {}
            parsed_resume = ParsedResumeSchema(**parsed_data) if parsed_data else ParsedResumeSchema(skills=[])

            # Use the canonical reindex method
            await matching_service._reindex_resume(
                candidate_id=resume.candidate_id,
                parsed_resume=parsed_resume,
                is_deleted=False,
            )
            success += 1
            if success % 10 == 0 or success == len(resumes_to_index):
                logger.info(f"[{success}/{len(resumes_to_index)}] upserted")
        except Exception as e:
            failed += 1
            failed_resumes.append(str(resume.candidate_id))
            logger.error(f"Failed to index resume for candidate {resume.candidate_id}: {e}")

    logger.info("\n=== Synchronization Summary ===")
    logger.info(f"SQL active primary resumes: {len(sql_resumes)}")
    logger.info(f"Qdrant points before:              {qdrant_points_count}")
    logger.info(f"Already indexed:                    {len(already_indexed)}")
    logger.info(f"Missing (targeted):                 {len(missing)}")
    logger.info(f"Successfully upserted:              {success}")
    logger.info(f"Failed:                             {failed}")
    logger.info(f"Orphan Qdrant IDs (preserved):      {len(orphans)}")

    if failed_resumes:
        logger.info("\nFailed resumes:")
        for rid in failed_resumes:
            logger.info(f"  - {rid}")

    logger.info("\nOrphan Qdrant vectors were NOT deleted (preserved per policy).")

    return {
        "sql_resumes": len(sql_resumes),
        "qdrant_points_total": qdrant_points_count,
        "qdrant_valid_resume_ids": len(qdrant_resume_ids),
        "already_indexed": len(already_indexed),
        "missing": len(missing),
        "orphans": len(orphans),
        "upserted": success,
        "failed": failed,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Sync active SQL Server primary resumes to Qdrant resumes collection"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect and report intended actions without writing to Qdrant",
    )
    args = parser.parse_args()

    asyncio.run(run_sync(dry_run=args.dry_run))


# Expose callable function for testing
async def sync_resumes(
    dry_run: bool = False,
    matching_service: AIMatchingService | None = None,
    repo: QdrantVectorRepository | None = None,
) -> dict:
    """Callable entry point for resume synchronization.
    
    Args:
        dry_run: If True, only inspect and report without writing.
        matching_service: Optional pre-configured AIMatchingService for testing.
        repo: Optional pre-configured QdrantVectorRepository for testing.
        
    Returns:
        Dictionary with synchronization counters.
    """
    return await run_sync(dry_run=dry_run, matching_service=matching_service, repo=repo)


if __name__ == "__main__":
    main()