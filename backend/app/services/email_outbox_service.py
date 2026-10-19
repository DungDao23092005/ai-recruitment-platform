"""Durable transactional outbox for business notification emails.

Business flows (VNPAY receipt, account lock/delete, subscription lifecycle)
call :func:`enqueue_email` inside their own database transaction, so the email
intent commits atomically with the state change that produced it. Delivery is
performed later by ``EmailOutboxWorker``, which claims due rows atomically,
calls the provider outside any transaction, and records the outcome. A process
restart therefore can no longer drop a pending notification.

This module owns the queue mechanics (enqueue, atomic claim, lease recovery,
terminal transitions, admin queries). It never sends email itself.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    EntityNotFoundException,
    InvalidTransitionException,
)
from app.database.base_class import utc_now
from app.domain.enums import OutboxStatus
from app.models.email_outbox import (
    IDEMPOTENCY_KEY_MAX_LENGTH,
    LAST_ERROR_MAX_LENGTH,
    SUBJECT_MAX_LENGTH,
    TO_EMAIL_MAX_LENGTH,
    EmailOutbox,
)

logger = logging.getLogger(__name__)

# The claim query takes an update lock on each candidate row and skips rows that
# another worker already holds. ``READPAST`` + ``UPDLOCK`` is the canonical
# queue pattern; ``READCOMMITTEDLOCK`` is added when the database runs with
# READ_COMMITTED_SNAPSHOT so the read still takes a real lock. Both variants
# were verified against the target SQL Server instance.
_CLAIM_HINTS_READ_COMMITTED = "WITH (UPDLOCK, ROWLOCK, READPAST)"
_CLAIM_HINTS_RCSI = "WITH (UPDLOCK, ROWLOCK, READPAST, READCOMMITTEDLOCK)"

# Resolved once per process from ``sys.databases``; both values are valid across
# configurations, the resolution only selects the tighter hint set.
_resolved_claim_hints: Optional[str] = None


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit]


def reset_claim_hint_cache() -> None:
    """Clear the cached lock-hint resolution (used by tests)."""
    global _resolved_claim_hints
    _resolved_claim_hints = None


async def resolve_claim_lock_hints(session: AsyncSession) -> str:
    """Pick the claim lock hints that match the live isolation configuration.

    READ_COMMITTED_SNAPSHOT (RCSI) turns locking reads into versioned reads, so
    the plain ``UPDLOCK, ROWLOCK, READPAST`` combination is no longer guaranteed
    to serialize claimers; ``READCOMMITTEDLOCK`` forces a locking read again.
    When the setting cannot be read we fall back to the always-safe superset.
    """
    global _resolved_claim_hints
    if _resolved_claim_hints is not None:
        return _resolved_claim_hints

    hints = _CLAIM_HINTS_RCSI
    try:
        result = await session.execute(
            text(
                "SELECT is_read_committed_snapshot_on FROM sys.databases "
                "WHERE name = DB_NAME()"
            )
        )
        rcsi = result.scalar_one_or_none()
        hints = _CLAIM_HINTS_RCSI if rcsi else _CLAIM_HINTS_READ_COMMITTED
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Could not read READ_COMMITTED_SNAPSHOT setting, using safe claim "
            "hints: %s",
            exc,
        )
    _resolved_claim_hints = hints
    return hints


async def enqueue_email(
    session: AsyncSession,
    *,
    event_type: str,
    to_email: Optional[str],
    subject: str,
    html_body: str,
    text_body: str,
    idempotency_key: Optional[str] = None,
    max_attempts: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Optional[EmailOutbox]:
    """Insert an outbox row into the caller's active transaction.

    The caller owns the transaction: this never commits, so the row is visible
    only after the surrounding business change commits. Returns the new row, or
    ``None`` when there is no recipient or the idempotency key was already
    enqueued (a committed duplicate). ``to_email``/``subject``/``idempotency_key``
    are bounded so a hostile or malformed value can never overflow the schema.
    """
    if not to_email:
        logger.warning("Skipping outbox email (%s): no recipient", event_type)
        return None

    normalized_key: Optional[str] = None
    if idempotency_key:
        normalized_key = _truncate(str(idempotency_key), IDEMPOTENCY_KEY_MAX_LENGTH)
        existing = await session.execute(
            select(EmailOutbox.id).where(
                EmailOutbox.idempotency_key == normalized_key
            )
        )
        if existing.scalar_one_or_none() is not None:
            logger.debug(
                "Outbox email (%s) already enqueued for key %s",
                event_type,
                normalized_key,
            )
            return None

    row = EmailOutbox(
        event_type=event_type,
        to_email=_truncate(str(to_email), TO_EMAIL_MAX_LENGTH),
        subject=_truncate(subject, SUBJECT_MAX_LENGTH),
        html_body=html_body,
        text_body=text_body,
        status=OutboxStatus.PENDING.value,
        attempts=0,
        max_attempts=max_attempts or settings.EMAIL_OUTBOX_MAX_ATTEMPTS,
        next_attempt_at=now or utc_now(),
        idempotency_key=normalized_key,
    )
    session.add(row)
    return row


async def recover_stale_leases(
    session: AsyncSession,
    *,
    lease_seconds: int,
    now: Optional[datetime] = None,
) -> int:
    """Return abandoned PROCESSING rows to PENDING and report how many.

    A worker that dies mid-delivery leaves a row stuck in PROCESSING. After the
    lease expires it becomes eligible again, so at-least-once delivery is
    preserved without a separate reaper process.
    """
    moment = now or utc_now()
    cutoff = moment - timedelta(seconds=lease_seconds)
    result = await session.execute(
        text(
            """
            UPDATE email_outbox
            SET status = :pending,
                processing_started_at = NULL,
                updated_at = :now
            WHERE status = :processing
              AND processing_started_at IS NOT NULL
              AND processing_started_at < :cutoff
            """
        ),
        {
            "pending": OutboxStatus.PENDING.value,
            "processing": OutboxStatus.PROCESSING.value,
            "cutoff": cutoff,
            "now": moment,
        },
    )
    return result.rowcount or 0


async def claim_due_messages(
    session: AsyncSession,
    *,
    batch_size: int,
    lock_hints: str,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Atomically claim up to ``batch_size`` due messages and return them.

    ``TOP (n) ... WITH (UPDLOCK, ROWLOCK, READPAST) ... OUTPUT`` is a single
    locking statement: two concurrent workers never observe the same row
    because each holds an update lock on the rows it claims, and READPAST skips
    rows the other worker is holding. The claim is committed by the caller
    *before* the provider is contacted.
    """
    statement = text(
        f"""
        UPDATE TOP (:batch_size) email_outbox {lock_hints}
        SET status = :processing,
            processing_started_at = :now,
            attempts = attempts + 1,
            updated_at = :now
        OUTPUT inserted.id,
               inserted.event_type,
               inserted.to_email,
               inserted.subject,
               inserted.html_body,
               inserted.text_body,
               inserted.attempts,
               inserted.max_attempts
        WHERE status = :pending
          AND next_attempt_at <= :now
        """
    )
    result = await session.execute(
        statement,
        {
            "batch_size": batch_size,
            "processing": OutboxStatus.PROCESSING.value,
            "pending": OutboxStatus.PENDING.value,
            "now": now or utc_now(),
        },
    )
    return [dict(row) for row in result.mappings().all()]


async def mark_sent(
    session: AsyncSession,
    *,
    message_id: uuid.UUID,
    now: Optional[datetime] = None,
) -> None:
    """Mark a claimed message as delivered (terminal success)."""
    moment = now or utc_now()
    await session.execute(
        text(
            """
            UPDATE email_outbox
            SET status = :sent,
                sent_at = :now,
                processing_started_at = NULL,
                last_error = NULL,
                updated_at = :now
            WHERE id = :id
            """
        ),
        {"sent": OutboxStatus.SENT.value, "now": moment, "id": message_id},
    )


async def mark_failed_attempt(
    session: AsyncSession,
    *,
    message_id: uuid.UUID,
    attempts: int,
    max_attempts: int,
    error: str,
    next_attempt_at: Optional[datetime],
    now: Optional[datetime] = None,
) -> str:
    """Record a failed delivery; returns the resulting status.

    Below the retry budget the message returns to PENDING with a backoff; at the
    budget it becomes terminal FAILED. ``max_attempts`` is re-read from the row
    so a retried row keeps its own budget.
    """
    moment = now or utc_now()
    exhausted = attempts >= max_attempts
    new_status = OutboxStatus.FAILED.value if exhausted else OutboxStatus.PENDING.value
    await session.execute(
        text(
            """
            UPDATE email_outbox
            SET status = :status,
                processing_started_at = NULL,
                next_attempt_at = :next_attempt_at,
                last_error = :error,
                updated_at = :now
            WHERE id = :id
            """
        ),
        {
            "status": new_status,
            "next_attempt_at": next_attempt_at or moment,
            "error": _truncate(str(error), LAST_ERROR_MAX_LENGTH),
            "now": moment,
            "id": message_id,
        },
    )
    return new_status


def compute_backoff_seconds(attempts: int) -> float:
    """Exponential backoff capped at the configured ceiling.

    ``attempts`` is the number of failed tries so far (1-based after the first
    claim).
    """
    base = settings.EMAIL_OUTBOX_RETRY_BASE_SECONDS
    ceiling = settings.EMAIL_OUTBOX_RETRY_MAX_SECONDS
    return float(min(base * (2 ** max(attempts - 1, 0)), ceiling))


class EmailOutboxService:
    """Read/administrative operations over the outbox (no delivery)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_messages(
        self,
        *,
        skip: int = 0,
        limit: int = 10,
        status: Optional[OutboxStatus] = None,
        event_type: Optional[str] = None,
        search: Optional[str] = None,
    ) -> tuple[list[EmailOutbox], int]:
        """Return a page of outbox rows plus the total matching count."""
        filters = []
        if status is not None:
            filters.append(EmailOutbox.status == status.value)
        if event_type:
            filters.append(EmailOutbox.event_type == event_type)
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    EmailOutbox.to_email.ilike(pattern),
                    EmailOutbox.subject.ilike(pattern),
                )
            )

        query = select(EmailOutbox)
        count_query = select(func.count()).select_from(EmailOutbox)
        for condition in filters:
            query = query.where(condition)
            count_query = count_query.where(condition)

        query = query.order_by(EmailOutbox.created_at.desc()).offset(skip).limit(limit)
        items = list((await self.session.execute(query)).scalars().all())
        total = int((await self.session.execute(count_query)).scalar_one())
        return items, total

    async def get_stats(self) -> dict[str, Any]:
        """Return per-status counts and the age of the oldest PENDING row."""
        rows = await self.session.execute(
            select(EmailOutbox.status, func.count()).group_by(EmailOutbox.status)
        )
        counts = {status.value: 0 for status in OutboxStatus}
        for status_value, count in rows.all():
            counts[str(status_value)] = int(count)

        oldest_pending = await self.session.execute(
            select(func.min(EmailOutbox.created_at)).where(
                EmailOutbox.status == OutboxStatus.PENDING.value
            )
        )
        return {
            "pending": counts[OutboxStatus.PENDING.value],
            "processing": counts[OutboxStatus.PROCESSING.value],
            "sent": counts[OutboxStatus.SENT.value],
            "failed": counts[OutboxStatus.FAILED.value],
            "total": sum(counts.values()),
            "oldest_pending_created_at": oldest_pending.scalar_one_or_none(),
        }

    async def retry_message(self, message_id: uuid.UUID) -> EmailOutbox:
        """Requeue a message that is not currently being processed.

        Refuses only PROCESSING rows, which would risk a duplicate delivery
        racing the in-flight worker. On success the attempt budget is reset so a
        previously exhausted message can be delivered again.
        """
        message = await self.session.get(EmailOutbox, message_id)
        if message is None:
            raise EntityNotFoundException(f"Outbox message {message_id} not found")
        if message.status == OutboxStatus.PROCESSING.value:
            raise InvalidTransitionException(
                "Message is currently being processed and cannot be retried"
            )

        now = utc_now()
        message.status = OutboxStatus.PENDING.value
        message.attempts = 0
        message.next_attempt_at = now
        message.processing_started_at = None
        message.last_error = None
        message.sent_at = None
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def purge_sent(
        self,
        *,
        older_than_days: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> int:
        """Delete delivered messages older than the retention window.

        Only SENT rows are removed: pending/failed work is never discarded by
        retention, so a slow or failing provider can never lose a notification
        to a cleanup job.
        """
        days = (
            older_than_days
            if older_than_days is not None
            else settings.EMAIL_OUTBOX_SENT_RETENTION_DAYS
        )
        moment = now or utc_now()
        cutoff = moment - timedelta(days=days)
        result = await self.session.execute(
            text(
                """
                DELETE FROM email_outbox
                WHERE status = :sent
                  AND sent_at IS NOT NULL
                  AND sent_at < :cutoff
                """
            ),
            {"sent": OutboxStatus.SENT.value, "cutoff": cutoff},
        )
        await self.session.commit()
        return result.rowcount or 0
