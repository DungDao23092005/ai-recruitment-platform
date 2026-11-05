from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, text
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin
from app.domain.enums import InvitationStatus, MembershipRole
from app.models.user import StringEnum

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.user import User


class CompanyInvitation(Base, TimestampMixin, SoftDeleteMixin):
    """Single-use invitation to join a company workspace."""

    __tablename__ = "company_invitations"
    __table_args__ = (
        Index(
            "uq_company_invitations_pending_company_email",
            "company_id",
            "email",
            unique=True,
            mssql_where=text("status = 'pending' AND is_deleted = 0"),
        ),
        Index(
            "uq_company_invitations_token_hash",
            "token_hash",
            unique=True,
        ),
        Index(
            "ix_company_invitations_company_status",
            "company_id",
            "status",
        ),
        Index(
            "ix_company_invitations_email_status",
            "email",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="NO ACTION"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(
        String(320).with_variant(NVARCHAR(320), "mssql"),
        nullable=False,
    )
    role: Mapped[MembershipRole] = mapped_column(
        StringEnum(MembershipRole),
        nullable=False,
        default=MembershipRole.RECRUITER,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[InvitationStatus] = mapped_column(
        StringEnum(InvitationStatus),
        nullable=False,
        default=InvitationStatus.PENDING,
    )
    invited_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    company: Mapped[Company] = relationship(
        "Company",
        back_populates="invitations",
        foreign_keys=[company_id],
    )
    invited_by: Mapped[User] = relationship(
        "User",
        foreign_keys=[invited_by_id],
    )
