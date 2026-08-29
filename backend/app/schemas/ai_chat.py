from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: Literal["user", "assistant"] = Field(
        ..., description="Message author role"
    )
    content: str = Field(
        ..., min_length=1, max_length=4000, description="Message text content"
    )


class ChatSource(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_type: Literal["job", "resume", "knowledge"] = Field(
        ..., description="Type of the retrieved source"
    )
    entity_id: uuid.UUID = Field(
        ..., description="Id of the job, resume, or knowledge vector point"
    )
    title: str = Field(
        ..., description="Human readable title for the source"
    )
    relevance_score: float = Field(
        ..., description="CrossEncoder logit or Qdrant semantic score (unbounded)"
    )
    skills: list[str] = Field(
        default_factory=list, description="Skills stored on the vector point"
    )


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="User chat message",
    )
    history: list[ChatMessage] = Field(
        default_factory=list,
        max_length=10,
        description="Recent conversation history (max 10 messages)",
    )


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    answer: str = Field(
        ..., min_length=1, description="Assistant reply in natural Vietnamese"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score in the answer (0.0 to 1.0)"
    )
    sources: list[ChatSource] = Field(
        default_factory=list,
        description="Retrieved context citations from the vector store",
    )
    suggested_followups: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Suggested follow-up questions",
    )
