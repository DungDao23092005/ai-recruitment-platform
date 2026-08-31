import argparse
import asyncio
import logging
import sys

from sqlalchemy import func, select

from app.database.session import async_session_factory
from app.models import Job
from app.services.job_service import JobService

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def run_reindex(dry_run: bool = False) -> None:
    """Reindex existing active jobs from SQL Server to Qdrant Cloud."""
    logger.info("Starting job reindex...")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    logger.info("Target: Qdrant Cloud (via JobService/QdrantVectorRepository)")

    async with async_session_factory() as session:
        # Count total active jobs
        count_stmt = select(func.count(Job.id)).where(Job.is_deleted == False)
        total_jobs = await session.scalar(count_stmt) or 0

        logger.info(f"Total jobs (is_deleted=False) to index: {total_jobs}")

        if total_jobs == 0:
            logger.info("No jobs to reindex.")
            return

        service = JobService(session=session)
        batch_size = 50
        success = 0
        failed = 0
        failed_jobs = []

        for skip in range(0, total_jobs, batch_size):
            batch = await service.jobs.list_all_jobs(skip=skip, limit=batch_size)

            for job in batch:
                if dry_run:
                    logger.info(f"[DRY RUN] Would index Job: {job.id} - {job.title}")
                    success += 1
                    continue

                try:
                    await service._reindex_job(job)
                    success += 1
                    if success % 10 == 0 or success == total_jobs:
                        logger.info(f"[{success}/{total_jobs}] indexed")
                except Exception as e:
                    failed += 1
                    failed_jobs.append(str(job.id))
                    logger.error(f"Failed to index job {job.id}: {e}")

        logger.info("\nReindex completed.")
        logger.info(f"Total: {total_jobs}")
        logger.info(f"Success: {success}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Skipped: {total_jobs - success - failed}")

        if failed_jobs:
            logger.info("\nFailed jobs:")
            for jid in failed_jobs:
                logger.info(f"- {jid}")


def main():
    parser = argparse.ArgumentParser(description="Reindex active jobs into Qdrant Cloud")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print jobs that would be indexed without actually writing to Qdrant",
    )
    args = parser.parse_args()

    asyncio.run(run_reindex(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
