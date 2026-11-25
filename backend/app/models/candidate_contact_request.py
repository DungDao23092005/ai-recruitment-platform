from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin
from app.domain.enums import ContactRequestStatus
from app.domain.models.base import utc_now

if TYPE_CHECKING:
    from app.models.candidate import CandidateProfile
    from app.models.company import Company
    from app.models.user import User


class CandidateContactRequest(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "candidate_contact_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id"),
        nullable=False,
        index=True,
    )
    requester_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    status: Mapped[ContactRequestStatus] = mapped_column(
        String(50),
        default=ContactRequestStatus.PENDING,
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    company: Mapped[Company] = relationship()
    candidate: Mapped[CandidateProfile] = relationship(
        back_populates="contact_requests"
    )
    requester_user: Mapped[User] = relationship()

    __table_args__ = (
        Index(
            "uq_active_candidate_contact_request",
            "company_id",
            "candidate_id",
            unique=True,
            postgresql_where=sa.text(
                "status IN ('pending', 'accepted') AND is_deleted = false"
            ),
            sqlite_where=sa.text(
                "status IN ('pending', 'accepted') AND is_deleted = 0"
            ),
            mssql_where=sa.text(
                "status IN ('pending', 'accepted') AND is_deleted = 0"
            ),
        ),
    )


class ContactDisclosureAuditLog(Base):
    """Append-only, metadata-only audit log for contact disclosure events.

    Deliberately does not inherit SoftDeleteMixin or TimestampMixin with onupdate,
    and never stores actual email or phone values.
    """

    __tablename__ = "contact_disclosure_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    contact_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_contact_requests.id"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id"),
        nullable=False,
        index=True,
    )
    disclosed_to_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    disclosed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )

    contact_request: Mapped[CandidateContactRequest] = relationship()
    company: Mapped[Company] = relationship()
    candidate: Mapped[CandidateProfile] = relationship()
    disclosed_to_user: Mapped[User] = relationship()
