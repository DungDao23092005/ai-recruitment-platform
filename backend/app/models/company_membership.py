from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin
from app.domain.enums import MembershipRole, MembershipStatus
from app.models.user import StringEnum

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.user import User


class CompanyMembership(Base, TimestampMixin, SoftDeleteMixin):
    """Authoritative workspace authorization for a user in a company."""

    __tablename__ = "company_memberships"
    __table_args__ = (
        Index(
            "uq_company_memberships_active_company_user",
            "company_id",
            "user_id",
            unique=True,
            mssql_where=text("status = 'active' AND is_deleted = 0"),
        ),
        Index(
            "ix_company_memberships_user_status",
            "user_id",
            "status",
        ),
        Index(
            "ix_company_memberships_company_status",
            "company_id",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="NO ACTION"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=False,
    )
    role: Mapped[MembershipRole] = mapped_column(
        StringEnum(MembershipRole),
        nullable=False,
        default=MembershipRole.RECRUITER,
    )
    status: Mapped[MembershipStatus] = mapped_column(
        StringEnum(MembershipStatus),
        nullable=False,
        default=MembershipStatus.ACTIVE,
    )
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=True,
    )
    joined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=True,
    )

    company: Mapped[Company] = relationship(
        "Company",
        back_populates="memberships",
        foreign_keys=[company_id],
    )
    user: Mapped[User] = relationship(
        "User",
        back_populates="company_memberships",
        foreign_keys=[user_id],
    )
    invited_by: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[invited_by_id],
    )
    revoked_by: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[revoked_by_id],
    )
