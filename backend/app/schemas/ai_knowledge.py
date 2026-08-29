from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


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


class KnowledgeDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    category: KnowledgeCategory
    visibility: KnowledgeVisibility
    status: KnowledgeStatus
    language: str
    content: str
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentListResponse(BaseModel):
    items: list[KnowledgeDocumentRead]
    total: int
    skip: int
    limit: int


class KnowledgeDocumentCreate(BaseModel):
    title: str
    category: KnowledgeCategory
    content: str
    visibility: KnowledgeVisibility = KnowledgeVisibility.PUBLIC
    status: KnowledgeStatus = KnowledgeStatus.DRAFT
    language: str = "vi"


class KnowledgeDocumentUpdate(BaseModel):
    title: str | None = None
    category: KnowledgeCategory | None = None
    content: str | None = None
    visibility: KnowledgeVisibility | None = None
    status: KnowledgeStatus | None = None
    language: str | None = None