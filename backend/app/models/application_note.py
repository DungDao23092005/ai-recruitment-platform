from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Uuid
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin

# Recruiter notes are free-form but bounded so the column stays indexable and
# predictable. Unicode is stored as NVARCHAR on SQL Server.
CONTENT_MAX_LENGTH = 2000


class ApplicationNote(Base, TimestampMixin, SoftDeleteMixin):
    """A recruiter-authored internal note attached to an application.

    Notes are always scoped to a single application and author; they are
    soft-deleted so the audit trail of who wrote what is never destroyed.
    """

    __tablename__ = "application_notes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id"),
        nullable=False,
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        String(CONTENT_MAX_LENGTH).with_variant(
            NVARCHAR(CONTENT_MAX_LENGTH), "mssql"
        ),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_application_notes_application_id", "application_id"),
    )
