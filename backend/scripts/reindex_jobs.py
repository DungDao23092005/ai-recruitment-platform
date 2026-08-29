
"""Job Reindexing Script

This script reads jobs from SQL Server, generates embeddings using the
current async embedding service, and upserts vectors into the "jobs"
Qdrant collection. It is idempotent and safe to run multiple times.

Usage:
    python backend/scripts/reindex_jobs.py [--apply] [--limit N] [--offset N]

Options:
    --apply          Actually apply changes (default is dry-run)
    --limit N        Maximum number of jobs to process (default: all)
    --offset N       Number of jobs to skip (default: 0)
    --help           Show this help message
"""

import argparse
import asyncio
import sys
import uuid
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database.base_class import Base
from app.models.job import Job
from app.ai.embeddings.embedding_service import EmbeddingService
from app.ai.embeddings.embedding_service import SentenceTransformerEmbeddingProvider
from app.ai.vector_db.qdrant_client import QdrantVectorRepository
from app.ai.interfaces.base_provider import BaseVectorRepository
from app.core.config import settings
from app.services.job_service import JobService


def make_canonical_job_text(job: Job) -> str:
    """Generate canonical text for job embedding (same as JobService._canonical_job_text)."""
    return (
        f"Job Title: {job.title}\n"
        f"Description: {job.description}\n"
        f"Location: {job.location}"
    )


async def reindex_jobs(apply: bool = False, limit: int | None = None, offset: int = 0) -> int:
    """Reindex SQL jobs into Qdrant.

    Args:
        apply: If True, actually upsert to Qdrant. If False, dry-run only.
        limit: Maximum number of jobs to process.
        offset: Number of jobs to skip.

    Returns:
        Number of jobs successfully reindexed.

    Raises:
        SystemExit: If any job fails to index (when apply=True).
    """
    engine = create_async_engine(settings.database_uri, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Initialize services
    embedding_provider = SentenceTransformerEmbeddingProvider()
    embedding_service = EmbeddingService(embedding_provider)
    vector_repo: BaseVectorRepository = QdrantVectorRepository()

    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    failed_jobs = []
    processed_count = 0
    success_count = 0

    async with async_session() as session:
        # Build query for jobs - eagerly load skills to avoid MissingGreenlet
        stmt = (
            select(Job)
            .options(selectinload(Job.skills))
            .where(Job.is_deleted == False)
            .order_by(Job.created_at)
        )
        if offset > 0:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await session.execute(stmt)
        jobs = result.scalars().all()

        if not jobs:
            print("No jobs found to reindex.")
            return 0

        print(f"Found {len(jobs)} jobs to process")

        for job in jobs:
            processed_count += 1
            print(f"\n[{processed_count}/{len(jobs)}] Processing: {job.title} ({job.id})")

            try:
                # Generate canonical text for embedding
                text = make_canonical_job_text(job)

                # Generate embedding
                embedding = await embedding_service.embed_text(text)

                # Get skills (already loaded via selectinload)
                skills = [skill.name for skill in job.skills] if job.skills else []

                if not apply:
                    print(f"  [DRY RUN] Would upsert vector for job {job.id}")
                    print(f"  Title: {job.title}")
                    print(f"  Skills: {skills}")
                    continue

                # Upsert to Qdrant (idempotent - same job_id will overwrite)
                await vector_repo.upsert_job_vector(
                    job_id=job.id,
                    vector=embedding,
                    skills=skills,
                    created_at=job.created_at,
                )

                success_count += 1
                print(f"  Successfully reindexed: {job.title}")

            except Exception as e:
                print(f"  FAILED: {job.id} - {e}")
                failed_jobs.append((job.id, str(e)))
                if apply:
                    # Fail fast on first error when applying
                    print("\nReindexing failed. Stopping.")
                    return 1

    if failed_jobs:
        print("\n" + "=" * 60)
        print("REINDEXING FAILED")
        print("=" * 60)
        for job_id, error in failed_jobs:
            print(f"  {job_id}: {error}")
        return 1

    print("\n" + "=" * 60)
    print(f"REINDEXING COMPLETE: {success_count}/{len(jobs)} jobs indexed")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reindex SQL Jobs into Qdrant")
    parser.add_argument(
        "--apply", action="store_true", help="Apply changes (default is dry-run)"
    )
    parser.add_argument("--limit", type=int, help="Maximum number of jobs to process")
    parser.add_argument("--offset", type=int, default=0, help="Number of jobs to skip")
    args = parser.parse_args()

    exit_code = asyncio.run(reindex_jobs(apply=args.apply, limit=args.limit, offset=args.offset))
    sys.exit(exit_code)