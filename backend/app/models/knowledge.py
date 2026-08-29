from __future__ import annotations

import uuid
from enum import Enum

from sqlalchemy import Enum as SQLEnum, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class KnowledgeCategory(str, Enum):
    CAREER = "career"
    RECRUITMENT = "recruitment"
    TECHNOLOGY = "technology"
    INTERVIEW = "interview"


class KnowledgeVisibility(str, Enum):
    PUBLIC = "public"
    RECRUITER_ONLY = "recruiter_only"
    INTERNAL = "internal"


class KnowledgeStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class KnowledgeDocument(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        Index(
            "ix_knowledge_documents_category_status_visibility",
            "category",
            "status",
            "visibility",
            mssql_where=text("is_deleted = 0"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[KnowledgeCategory] = mapped_column(
        SQLEnum(KnowledgeCategory, values_callable=lambda x: [e.value for e in KnowledgeCategory]),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(nullable=False)
    visibility: Mapped[KnowledgeVisibility] = mapped_column(
        SQLEnum(KnowledgeVisibility, values_callable=lambda x: [e.value for e in KnowledgeVisibility]),
        nullable=False,
        default=KnowledgeVisibility.PUBLIC,
    )
    status: Mapped[KnowledgeStatus] = mapped_column(
        SQLEnum(KnowledgeStatus, values_callable=lambda x: [e.value for e in KnowledgeStatus]),
        nullable=False,
        default=KnowledgeStatus.DRAFT,
    )
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="vi")