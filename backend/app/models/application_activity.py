from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base_class import Base, utc_now

ACTION_TYPE_MAX_LENGTH = 50
STATUS_MAX_LENGTH = 50
NOTE_MAX_LENGTH = 1000


class ApplicationActivity(Base):
    """Append-only audit trail of everything that happens to an application.

    Rows are immutable: there is deliberately no ``updated_at`` and no soft
    delete, so history can never be rewritten or hidden. ``metadata_json``
    stores optional free-form context as Unicode JSON text.
    """

    __tablename__ = "application_activities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id"),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(
        String(ACTION_TYPE_MAX_LENGTH).with_variant(
            NVARCHAR(ACTION_TYPE_MAX_LENGTH), "mssql"
        ),
        nullable=False,
    )
    from_status: Mapped[str | None] = mapped_column(
        String(STATUS_MAX_LENGTH).with_variant(
            NVARCHAR(STATUS_MAX_LENGTH), "mssql"
        ),
        nullable=True,
    )
    to_status: Mapped[str | None] = mapped_column(
        String(STATUS_MAX_LENGTH).with_variant(
            NVARCHAR(STATUS_MAX_LENGTH), "mssql"
        ),
        nullable=True,
    )
    note: Mapped[str | None] = mapped_column(
        String(NOTE_MAX_LENGTH).with_variant(NVARCHAR(NOTE_MAX_LENGTH), "mssql"),
        nullable=True,
    )
    metadata_json: Mapped[str | None] = mapped_column(
        Text().with_variant(NVARCHAR, "mssql"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_application_activities_application_id", "application_id"),
    )
