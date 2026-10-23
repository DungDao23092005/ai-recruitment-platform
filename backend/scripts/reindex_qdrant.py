#!/usr/bin/env python3
"""Safely rebuild Qdrant vectors from recoverable SQL Server data.

This CLI deliberately reuses the application's canonical indexing paths:

* resumes -> ``AIMatchingService._reindex_resume`` (candidate_id point id,
  confirmation payload, SentenceTransformer resume text).
* jobs -> ``JobService._reindex_job`` (job_id point id, canonical job text,
  status/is_deleted payload).
* knowledge -> the same ``EmbeddingService`` and chunking function used by
  ``scripts.seed_knowledge``; payload keeps the fields the RAG service reads
  (``document_id``, ``chunk_index``, ``category``, ``title``).

Safety rules:

* Dry-run is the default. Writes require ``--execute``.
* Existing collections are only read. This script never creates, recreates,
  deletes, or rewrites a collection, and never deletes existing points.
* Collection vector size must match ``settings.VECTOR_DIMENSION`` before any
  write. A missing collection is an error, not an invitation to create one.
* Upserts use stable point ids so a rerun overwrites the same points. Legacy
  knowledge points created with random ids are not deleted; a rerun preserves
  them and only reports the existing point count.

Source coverage:

* ``resumes``: confirmed, primary, non-deleted resumes of active candidates.
* ``jobs``: all non-deleted jobs (draft + published), matching JobService.
* ``knowledge``: published, non-deleted rows in ``knowledge_documents``. The
  current development database may have zero rows; in that case there is no
  SQL data to rebuild from and the CLI reports zero source records. The
  committed Markdown corpus is a separate seeding path (``seed_knowledge.py``),
  not a second reindex pipeline.

Usage (inside the backend container):

    python -m scripts.reindex_qdrant --dry-run
    python -m scripts.reindex_qdrant --collection jobs --execute
    python -m scripts.reindex_qdrant --collection resumes jobs knowledge --execute

Usage (host, from ``backend/`` with the project venv):

    python -m scripts.reindex_qdrant --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.embeddings.embedding_service import (
    EmbeddingService,
    SentenceTransformerEmbeddingProvider,
)
from app.ai.vector_db.qdrant_client import QdrantVectorRepository
from app.core.config import settings
from app.database.session import async_session_factory, engine
from app.models import CandidateProfile, Job, KnowledgeDocument, Resume, User
from app.models.knowledge import KnowledgeStatus
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.ai_matching_service import AIMatchingService
from app.services.job_service import JobService
from scripts.seed_knowledge import chunk_text

logger = logging.getLogger(__name__)

RESUMES = QdrantVectorRepository.RESUME_COLLECTION
JOBS = QdrantVectorRepository.JOB_COLLECTION
KNOWLEDGE = QdrantVectorRepository.KNOWLEDGE_COLLECTION
ALL_COLLECTIONS = (RESUMES, JOBS, KNOWLEDGE)
DEFAULT_BATCH_SIZE = 50


class ReindexError(RuntimeError):
    """A safety or configuration failure that prevents reindexing."""


@dataclass
class CollectionStats:
    collection: str
    source_records: int = 0
    records_processed: int = 0
    records_skipped: int = 0
    records_failed: int = 0
    vectors_planned: int = 0
    vectors_written: int = 0
    vectors_failed: int = 0
    collection_dimension: int | None = None
    existing_points: int | None = None
    failures: list[str] = field(default_factory=list)

    @property
    def has_failures(self) -> bool:
        return self.records_failed > 0 or self.vectors_failed > 0


def knowledge_point_id(document_id: uuid.UUID, chunk_index: int) -> uuid.UUID:
    """Return a stable point id for a knowledge chunk.

    The application resolves knowledge points by ``payload.document_id``; it
    does not depend on a random Qdrant id. A deterministic UUID makes reruns
    overwrite the same chunk instead of accumulating duplicates.
    """
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"ai-recruitment-platform/knowledge/{document_id}/{chunk_index}",
    )


def build_knowledge_payload(
    *,
    document_id: uuid.UUID,
    chunk_index: int,
    category: str,
    title: str,
) -> dict[str, Any]:
    """Match the payload written by the existing knowledge seeding path."""
    return {
        "document_id": str(document_id),
        "chunk_index": chunk_index,
        "category": category,
        "title": title,
    }


def validate_vector_dimension(vector: Sequence[float], expected: int) -> None:
    """Validate an embedding before it is sent to Qdrant."""
    if not isinstance(vector, (list, tuple)):
        raise ReindexError("Embedding provider returned a non-sequence vector.")
    if len(vector) != expected:
        raise ReindexError(
            f"Embedding dimension {len(vector)} does not match collection "
            f"dimension {expected}."
        )


def _collection_dimension(collection_info: Any) -> int:
    vectors = collection_info.config.params.vectors
    if hasattr(vectors, "size"):
        return int(vectors.size)
    if isinstance(vectors, dict):
        sizes = {int(value.size) for value in vectors.values()}
        if len(sizes) != 1:
            raise ReindexError(
                "Collection uses multiple named vector sizes; this CLI only "
                "supports a single unnamed vector configuration."
            )
        return sizes.pop()
    raise ReindexError("Could not read the collection vector dimension.")


async def preflight_collections(
    repository: QdrantVectorRepository,
    collections: Sequence[str],
    *,
    expected_dimension: int | None = None,
) -> dict[str, CollectionStats]:
    """Read-only preflight: collection presence, dimension and point count."""
    expected = (
        settings.VECTOR_DIMENSION if expected_dimension is None else expected_dimension
    )
    stats_by_name: dict[str, CollectionStats] = {}
    for name in collections:
        try:
            info = await repository.client.get_collection(collection_name=name)
        except Exception as exc:
            raise ReindexError(
                f"Qdrant collection '{name}' is not available. Refusing to "
                f"create or recreate it automatically: {exc}"
            ) from exc

        dimension = _collection_dimension(info)
        if dimension != expected:
            raise ReindexError(
                f"Qdrant collection '{name}' has dimension {dimension}, but "
                f"settings.VECTOR_DIMENSION is {expected}."
            )
        stats = CollectionStats(
            collection=name,
            collection_dimension=dimension,
            existing_points=int(getattr(info, "points_count", 0) or 0),
        )
        stats_by_name[name] = stats
        logger.info(
            "Preflight %s: dimension=%s, existing_points=%s",
            name,
            dimension,
            stats.existing_points,
        )
    return stats_by_name


async def _iter_batches(
    session: AsyncSession,
    statement: Any,
    id_column: Any,
    batch_size: int,
) -> AsyncIterator[list[Any]]:
    # Keyset pagination avoids SQL Server's version-dependent OFFSET/FETCH
    # rendering. A plain LIMIT compiles to TOP (?) on the MSSQL dialect.
    last_id = None
    while True:
        page_statement = statement
        if last_id is not None:
            page_statement = page_statement.where(id_column > last_id)
        page_statement = page_statement.order_by(id_column).limit(batch_size)

        page = await session.execute(page_statement)
        rows = list(page.scalars().unique().all())
        if not rows:
            return
        yield rows
        if len(rows) < batch_size:
            return
        last_id = rows[-1].id


def _resume_statement() -> Any:
    return (
        select(Resume)
        .join(CandidateProfile, Resume.candidate_id == CandidateProfile.id)
        .join(User, CandidateProfile.user_id == User.id)
        .options(
            selectinload(Resume.candidate).selectinload(CandidateProfile.user)
        )
        .where(
            Resume.is_primary == True,  # noqa: E712
            Resume.is_confirmed == True,  # noqa: E712
            Resume.is_deleted == False,  # noqa: E712
            CandidateProfile.is_deleted == False,  # noqa: E712
            User.is_active == True,  # noqa: E712
        )
    )


async def reindex_resumes(
    session: AsyncSession,
    stats: CollectionStats,
    *,
    execute: bool,
    batch_size: int,
    matching_service: AIMatchingService,
) -> CollectionStats:
    batch_number = 0
    async for batch in _iter_batches(
        session, _resume_statement(), Resume.id, batch_size
    ):
        batch_number += 1
        for resume in batch:
            stats.source_records += 1
            if not resume.parsed_data:
                stats.records_skipped += 1
                logger.warning(
                    "Skipping candidate %s: confirmed primary resume %s has no parsed_data.",
                    resume.candidate_id,
                    resume.id,
                )
                continue

            try:
                parsed_resume = ParsedResumeSchema.model_validate(
                    resume.parsed_data
                )
            except Exception as exc:
                stats.records_skipped += 1
                logger.warning(
                    "Skipping candidate %s: resume %s parsed_data is invalid (%s).",
                    resume.candidate_id,
                    resume.id,
                    exc,
                )
                continue

            stats.vectors_planned += 1
            if not execute:
                stats.records_processed += 1
                logger.debug(
                    "[dry-run] would upsert resume vector for candidate %s",
                    resume.candidate_id,
                )
                continue

            try:
                await matching_service._reindex_resume(
                    candidate_id=resume.candidate_id,
                    parsed_resume=parsed_resume,
                    is_deleted=False,
                    resume_id=resume.id,
                    confirmed_at=resume.confirmed_at,
                )
            except Exception as exc:
                stats.records_failed += 1
                stats.vectors_failed += 1
                stats.failures.append(str(resume.candidate_id))
                logger.error(
                    "Failed to index resume for candidate %s: %s",
                    resume.candidate_id,
                    exc,
                )
            else:
                stats.records_processed += 1
                stats.vectors_written += 1

        logger.info(
            "[%s] batch %d: source=%d processed=%d skipped=%d failed=%d written=%d",
            RESUMES,
            batch_number,
            stats.source_records,
            stats.records_processed,
            stats.records_skipped,
            stats.records_failed,
            stats.vectors_written,
        )
    return stats


def _job_statement() -> Any:
    return (
        select(Job).where(Job.is_deleted == False)  # noqa: E712
    )


async def reindex_jobs(
    session: AsyncSession,
    stats: CollectionStats,
    *,
    execute: bool,
    batch_size: int,
    job_service: JobService,
) -> CollectionStats:
    batch_number = 0
    async for batch in _iter_batches(
        session, _job_statement(), Job.id, batch_size
    ):
        batch_number += 1
        for job in batch:
            stats.source_records += 1
            stats.vectors_planned += 1
            if not execute:
                stats.records_processed += 1
                logger.debug("[dry-run] would upsert job vector for job %s", job.id)
                continue

            try:
                await job_service._reindex_job(job)
            except Exception as exc:
                stats.records_failed += 1
                stats.vectors_failed += 1
                stats.failures.append(str(job.id))
                logger.error("Failed to index job %s: %s", job.id, exc)
            else:
                stats.records_processed += 1
                stats.vectors_written += 1

        logger.info(
            "[%s] batch %d: source=%d processed=%d failed=%d written=%d",
            JOBS,
            batch_number,
            stats.source_records,
            stats.records_processed,
            stats.records_failed,
            stats.vectors_written,
        )
    return stats


def _knowledge_statement() -> Any:
    return (
        select(KnowledgeDocument).where(
            KnowledgeDocument.is_deleted == False,  # noqa: E712
            KnowledgeDocument.status == KnowledgeStatus.PUBLISHED,
        )
    )


async def reindex_knowledge(
    session: AsyncSession,
    stats: CollectionStats,
    *,
    execute: bool,
    batch_size: int,
    embedding_service: EmbeddingService,
    vector_repository: QdrantVectorRepository,
) -> CollectionStats:
    batch_number = 0
    expected_dimension = int(stats.collection_dimension or settings.VECTOR_DIMENSION)

    async for batch in _iter_batches(
        session, _knowledge_statement(), KnowledgeDocument.id, batch_size
    ):
        batch_number += 1
        for document in batch:
            stats.source_records += 1
            chunks = chunk_text(document.content or "")
            chunks = [chunk for chunk in chunks if chunk.strip()]
            if not chunks:
                stats.records_skipped += 1
                logger.warning(
                    "Skipping knowledge document %s: empty content.", document.id
                )
                continue

            stats.vectors_planned += len(chunks)
            if not execute:
                stats.records_processed += 1
                logger.debug(
                    "[dry-run] would upsert %d chunks for knowledge document %s",
                    len(chunks),
                    document.id,
                )
                continue

            failed_chunks = 0
            category = getattr(document.category, "value", str(document.category))
            for chunk_index, chunk in enumerate(chunks):
                try:
                    vector = await embedding_service.embed_text(chunk)
                    validate_vector_dimension(vector, expected_dimension)
                    await vector_repository.upsert_vector(
                        collection_name=KNOWLEDGE,
                        point_id=knowledge_point_id(document.id, chunk_index),
                        vector=vector,
                        payload=build_knowledge_payload(
                            document_id=document.id,
                            chunk_index=chunk_index,
                            category=category,
                            title=document.title,
                        ),
                    )
                except Exception as exc:
                    failed_chunks += 1
                    stats.vectors_failed += 1
                    logger.error(
                        "Failed to index knowledge document %s chunk %d: %s",
                        document.id,
                        chunk_index,
                        exc,
                    )
                else:
                    stats.vectors_written += 1

            if failed_chunks:
                stats.records_failed += 1
                stats.failures.append(str(document.id))
            else:
                stats.records_processed += 1

        logger.info(
            "[%s] batch %d: source=%d processed=%d skipped=%d failed=%d written=%d",
            KNOWLEDGE,
            batch_number,
            stats.source_records,
            stats.records_processed,
            stats.records_skipped,
            stats.records_failed,
            stats.vectors_written,
        )
    return stats


async def run_reindex(
    collections: Sequence[str],
    *,
    execute: bool,
    batch_size: int = DEFAULT_BATCH_SIZE,
    session_factory: Any = async_session_factory,
    vector_repository: QdrantVectorRepository | None = None,
    embedding_service: EmbeddingService | None = None,
) -> list[CollectionStats]:
    """Run preflight, then reindex selected collections in a fixed order."""
    selected: list[str] = []
    requested = list(collections)
    if "all" in requested:
        requested = list(ALL_COLLECTIONS)
    for name in requested:
        if name not in ALL_COLLECTIONS:
            raise ReindexError(f"Unknown collection: {name}")
        if name not in selected:
            selected.append(name)

    owns_repository = vector_repository is None
    repository = vector_repository or QdrantVectorRepository()
    embedding = embedding_service or EmbeddingService(
        SentenceTransformerEmbeddingProvider()
    )

    try:
        stats_by_name = await preflight_collections(repository, selected)
        logger.info(
            "Mode: %s | collections: %s",
            "EXECUTE" if execute else "DRY RUN",
            ", ".join(selected),
        )

        async with session_factory() as session:
            matching_service = AIMatchingService(
                embedding_service=embedding,
                vector_repository=repository,
            )
            job_service = JobService(
                session=session,
                embedding_service=embedding,
                vector_repository=repository,
            )

            for name in selected:
                stats = stats_by_name[name]
                if name == RESUMES:
                    await reindex_resumes(
                        session,
                        stats,
                        execute=execute,
                        batch_size=batch_size,
                        matching_service=matching_service,
                    )
                elif name == JOBS:
                    await reindex_jobs(
                        session,
                        stats,
                        execute=execute,
                        batch_size=batch_size,
                        job_service=job_service,
                    )
                else:
                    await reindex_knowledge(
                        session,
                        stats,
                        execute=execute,
                        batch_size=batch_size,
                        embedding_service=embedding,
                        vector_repository=repository,
                    )
    finally:
        if owns_repository:
            try:
                await repository.client.close()
            except Exception:
                logger.debug("Could not close Qdrant client cleanly.", exc_info=True)

    results = [stats_by_name[name] for name in selected]
    logger.info("Reindex summary (%s):", "EXECUTE" if execute else "DRY RUN")
    for stats in results:
        logger.info(
            "[%s] source=%d processed=%d skipped=%d failed=%d "
            "vectors_planned=%d written=%d failed=%d existing=%s dimension=%s",
            stats.collection,
            stats.source_records,
            stats.records_processed,
            stats.records_skipped,
            stats.records_failed,
            stats.vectors_planned,
            stats.vectors_written,
            stats.vectors_failed,
            stats.existing_points,
            stats.collection_dimension,
        )
        for failure in stats.failures:
            logger.info("  failed: %s", failure)

    if not execute:
        logger.info(
            "DRY RUN completed. No embeddings were generated and no Qdrant "
            "points were written, updated or deleted."
        )
    return results


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild Qdrant vectors from SQL Server data using the application's "
            "existing embedding and indexing pipelines."
        )
    )
    parser.add_argument(
        "--collection",
        nargs="+",
        choices=(*ALL_COLLECTIONS, "all"),
        default=["all"],
        help="Collections to reindex. Default: all.",
    )
    parser.add_argument(
        "--batch-size",
        type=_positive_int,
        default=DEFAULT_BATCH_SIZE,
        help=f"SQL batch size (default: {DEFAULT_BATCH_SIZE}).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Read-only planning mode (the default).",
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="Write embeddings/upserts. Without this flag nothing is written.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Logging verbosity (default: INFO).",
    )
    return parser


async def _run_cli(
    collections: Sequence[str],
    *,
    execute: bool,
    batch_size: int,
) -> list[CollectionStats]:
    try:
        return await run_reindex(
            collections,
            execute=execute,
            batch_size=batch_size,
        )
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    execute = bool(args.execute)
    logger.info("Starting Qdrant reindex (%s)", "EXECUTE" if execute else "DRY RUN")
    try:
        stats = asyncio.run(
            _run_cli(
                args.collection,
                execute=execute,
                batch_size=args.batch_size,
            )
        )
    except ReindexError as exc:
        logger.error("Reindex preflight failed: %s", exc)
        return 2
    except Exception:
        logger.exception("Reindex failed unexpectedly.")
        return 1

    failures = sum(
        stats_item.records_failed + stats_item.vectors_failed
        for stats_item in stats
    )
    if failures:
        logger.error("Reindex completed with %d failure(s).", failures)
        return 1
    logger.info("Reindex completed without failures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
