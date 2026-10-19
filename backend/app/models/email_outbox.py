from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, Uuid, text
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base_class import Base, TimestampMixin, utc_now
from app.domain.enums import OutboxStatus

# Bounds keep every column within a predictable, indexable size. Bodies are the
# only unbounded columns because transactional email templates are free-form.
SUBJECT_MAX_LENGTH = 500
TO_EMAIL_MAX_LENGTH = 320
IDEMPOTENCY_KEY_MAX_LENGTH = 255
LAST_ERROR_MAX_LENGTH = 1000


class EmailOutbox(Base, TimestampMixin):
    """Durable SQL Server transactional outbox for business notification emails.

    A message is inserted in the *same* transaction as the business change that
    produced it (payment activation, account lock/delete, subscription
    lifecycle). Delivery is performed asynchronously by ``EmailOutboxWorker``,
    which claims rows atomically and retries with backoff, so a process restart
    can no longer silently drop a notification.

    ``idempotency_key`` is an optional business key (for example the verified
    VNPAY order reference). A filtered unique index makes a duplicate enqueue a
    no-op rather than a second delivery.
    """

    __tablename__ = "email_outbox"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    to_email: Mapped[str] = mapped_column(
        String(TO_EMAIL_MAX_LENGTH).with_variant(
            NVARCHAR(TO_EMAIL_MAX_LENGTH), "mssql"
        ),
        nullable=False,
    )
    subject: Mapped[str] = mapped_column(
        String(SUBJECT_MAX_LENGTH).with_variant(NVARCHAR(SUBJECT_MAX_LENGTH), "mssql"),
        nullable=False,
    )
    html_body: Mapped[str] = mapped_column(
        Text().with_variant(NVARCHAR, "mssql"), nullable=False
    )
    text_body: Mapped[str] = mapped_column(
        Text().with_variant(NVARCHAR, "mssql"), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=OutboxStatus.PENDING.value
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(
        NVARCHAR(LAST_ERROR_MAX_LENGTH), nullable=True
    )

    idempotency_key: Mapped[str | None] = mapped_column(
        String(IDEMPOTENCY_KEY_MAX_LENGTH).with_variant(
            NVARCHAR(IDEMPOTENCY_KEY_MAX_LENGTH), "mssql"
        ),
        nullable=True,
    )

    __table_args__ = (
        # Drives the worker claim query: the next due PENDING message.
        Index(
            "ix_email_outbox_status_next_attempt",
            "status",
            "next_attempt_at",
        ),
        # Drives stale-lease recovery of abandoned PROCESSING rows.
        Index(
            "ix_email_outbox_status_processing_started",
            "status",
            "processing_started_at",
        ),
        # Filtered unique index: enforces idempotency, ignores NULL keys.
        Index(
            "uq_email_outbox_idempotency_key",
            "idempotency_key",
            unique=True,
            mssql_where=text("idempotency_key IS NOT NULL"),
        ),
    )
