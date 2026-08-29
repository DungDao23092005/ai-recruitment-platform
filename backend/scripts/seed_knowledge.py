"""Knowledge Base Seeding Script

This script reads Markdown documents from the knowledge directory,
parses metadata, creates/updates KnowledgeDocument records,
chunks content, generates embeddings, and upserts to Qdrant.

Usage:
    python backend/scripts/seed_knowledge.py [--apply]

Options:
    --apply    Actually apply changes (default is dry-run)
    --help     Show this help message
"""

import argparse
import os
import re
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database.base_class import Base
from app.models.knowledge import KnowledgeDocument, KnowledgeCategory, KnowledgeVisibility, KnowledgeStatus
from app.ai.embeddings.embedding_service import EmbeddingService
from app.ai.embeddings.embedding_service import SentenceTransformerEmbeddingProvider
from app.ai.vector_db.qdrant_client import QdrantVectorRepository
from app.ai.interfaces.base_provider import BaseVectorRepository
from app.core.config import settings


KNOWLEDGE_DIR = Path(__file__).parent.parent / "data" / "knowledge"


def parse_markdown_file(filepath: Path) -> dict[str, Any] | None:
    """Parse a Markdown file with YAML frontmatter.

    Expected format:
    ---
    title: "Document Title"
    category: "career"
    visibility: "public"
    status: "published"
    language: "vi"
    ---
    # Document Title

    Content here...
    """
    content = filepath.read_text(encoding="utf-8")

    # Parse frontmatter
    frontmatter = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1].strip()
            for line in fm_text.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    frontmatter[key.strip()] = value.strip()
            content = parts[2].strip()

    # Extract title from first heading if not in frontmatter
    title = frontmatter.get("title")
    if not title:
        for line in content.split("\n"):
            if line.startswith("# "):
                title = line[2:].strip()
                break

    if not title:
        title = filepath.stem.replace("_", " ").title()

    return {
        "title": title,
        "category": frontmatter.get("category", "technology"),
        "visibility": frontmatter.get("visibility", "public"),
        "status": frontmatter.get("status", "published"),
        "language": frontmatter.get("language", "vi"),
        "content": content,
    }


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += chunk_size - overlap
        if start >= len(text):
            break
    return chunks


async def seed_knowledge(apply: bool = False) -> None:
    """Seed the knowledge base with documents from the knowledge directory."""
    engine = create_async_engine(settings.database_uri, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Initialize services
    embedding_provider = SentenceTransformerEmbeddingProvider()
    embedding_service = EmbeddingService(embedding_provider)
    vector_repo: BaseVectorRepository = QdrantVectorRepository()

    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    knowledge_dir = KNOWLEDGE_DIR
    if not knowledge_dir.exists():
        print(f"Knowledge directory not found: {knowledge_dir}")
        return

    markdown_files = list(knowledge_dir.rglob("*.md"))
    if not markdown_files:
        print("No Markdown files found in knowledge directory")
        return

    print(f"Found {len(markdown_files)} Markdown files")

    async with async_session() as session:
        for filepath in markdown_files:
            print(f"Processing: {filepath.relative_to(knowledge_dir)}")

            parsed = parse_markdown_file(filepath)
            if not parsed:
                print(f"  Skipping: failed to parse")
                continue

            # Validate category
            try:
                category = KnowledgeCategory(parsed["category"].lower())
            except ValueError:
                print(f"  Invalid category: {parsed['category']}, using 'technology'")
                category = KnowledgeCategory.TECHNOLOGY

            # Validate visibility
            try:
                visibility = KnowledgeVisibility(parsed["visibility"].lower())
            except ValueError:
                print(f"  Invalid visibility: {parsed['visibility']}, using 'public'")
                visibility = KnowledgeVisibility.PUBLIC

            # Validate status
            try:
                status = KnowledgeStatus(parsed["status"].lower())
            except ValueError:
                print(f"  Invalid status: {parsed['status']}, using 'published'")
                status = KnowledgeStatus.PUBLISHED

            # Check if document already exists (by title)
            stmt = select(KnowledgeDocument).where(
                KnowledgeDocument.title == parsed["title"],
                KnowledgeDocument.is_deleted == False,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                doc_id = existing.id
                print(f"  Updating existing document: {parsed['title']} ({doc_id})")
                if apply:
                    existing.title = parsed["title"]
                    existing.category = category
                    existing.content = parsed["content"]
                    existing.visibility = visibility
                    existing.status = status
                    existing.language = parsed.get("language", "vi")
                    await session.commit()
            else:
                doc_id = uuid.uuid4()
                print(f"  Creating new document: {parsed['title']} ({doc_id})")
                if apply:
                    doc = KnowledgeDocument(
                        id=doc_id,
                        title=parsed["title"],
                        category=category,
                        content=parsed["content"],
                        visibility=visibility,
                        status=status,
                        language=parsed.get("language", "vi"),
                    )
                    session.add(doc)
                    await session.commit()

            if not apply:
                print("  [DRY RUN] Would create/update document")
                continue

            # Idempotency: Remove existing Qdrant points for this document_id before inserting new chunks
            # This prevents duplicate vectors from accumulating on re-runs
            try:
                await vector_repo.delete_vectors_by_filter(
                    collection_name="knowledge",
                    filter_key="document_id",
                    filter_value=str(doc_id),
                )
                print(f"  Removed existing Qdrant points for document_id: {doc_id}")
            except Exception as e:
                print(f"  Warning: Could not remove existing Qdrant points: {e}")

            # Chunk content and generate embeddings
            chunks = chunk_text(parsed["content"])
            print(f"  Chunked into {len(chunks)} pieces")

            for i, chunk in enumerate(chunks):
                try:
                    embedding = await embedding_service.embed_text(chunk)
                except Exception as e:
                    print(f"  Failed to generate embedding for chunk {i}: {e}")
                    continue

                # Upsert to Qdrant
                point_id = f"{uuid.uuid4()}"
                await vector_repo.upsert_vector(
                    collection_name="knowledge",
                    point_id=point_id,
                    vector=embedding,
                    payload={
                        "document_id": str(doc_id),
                        "chunk_index": i,
                        "category": parsed["category"],
                        "title": parsed["title"],
                    },
                )

            if apply:
                await session.commit()
                print(f"  Successfully processed and indexed")
            else:
                print("  [DRY RUN] Would upsert to Qdrant")

    print("Knowledge seeding completed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Knowledge Base")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run)")
    args = parser.parse_args()

    import asyncio
    asyncio.run(seed_knowledge(apply=args.apply))