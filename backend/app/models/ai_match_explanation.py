from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base_class import Base, TimestampMixin


class AIMatchExplanationIdempotency(Base, TimestampMixin):
    """Durable, user-scoped idempotency tombstone for AI match refreshes.

    Rows are never deleted by the application. ``ON DELETE NO ACTION`` on both
    foreign keys deliberately makes hard-deleting a user or application fail
    while a tombstone exists; soft deletes are unaffected.
    """

    __tablename__ = "ai_match_explanation_idempotency"
    __table_args__ = (
        Index(
            "uq_match_idempotency_user_key",
            "user_id",
            "key_hash",
            unique=True,
        ),
        Index("ix_match_idempotency_app", "application_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="NO ACTION"), nullable=False
    )
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="NO ACTION"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    owner_token: Mapped[str] = mapped_column(String(36), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    response_payload: Mapped[str | None] = mapped_column(
        Text().with_variant(NVARCHAR, "mssql"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AIMatchExplanationApplicationLease(Base, TimestampMixin):
    """Authoritative SQL mutual-exclusion lease for one application refresh."""

    __tablename__ = "ai_match_explanation_application_leases"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        primary_key=True,
    )
    owner_token: Mapped[str] = mapped_column(String(36), nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    lease_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
