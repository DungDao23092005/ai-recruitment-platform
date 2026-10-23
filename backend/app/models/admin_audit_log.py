from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, utc_now
from app.domain.enums import AdminAuditAction
from app.models.user import StringEnum

if TYPE_CHECKING:
    from app.models.user import User


class AdminAuditLog(Base):
    """Immutable audit trail for administrator user-management mutations.

    Rows are written in the same transaction as the mutation they describe.
    The table is deliberately append-only: there is no ``updated_at``, no
    soft-delete column, and no update/delete API. ``details`` stores a small,
    sanitized snapshot needed to understand the action; secrets, tokens,
    passwords and original email addresses must never be stored here.
    """

    __tablename__ = "admin_audit_logs"
    __table_args__ = (
        Index("ix_admin_audit_logs_created_at", "created_at"),
        Index(
            "ix_admin_audit_logs_admin_created",
            "admin_id",
            "created_at",
        ),
        Index(
            "ix_admin_audit_logs_target_created",
            "target_user_id",
            "created_at",
        ),
        Index(
            "ix_admin_audit_logs_action_created",
            "action",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    target_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    action: Mapped[AdminAuditAction] = mapped_column(
        StringEnum(AdminAuditAction), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(
        String(500).with_variant(NVARCHAR(500), "mssql"), nullable=True
    )
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    admin: Mapped[User] = relationship(
        foreign_keys=[admin_id],
        lazy="selectin",
    )
    target_user: Mapped[User] = relationship(
        foreign_keys=[target_user_id],
        lazy="selectin",
    )
