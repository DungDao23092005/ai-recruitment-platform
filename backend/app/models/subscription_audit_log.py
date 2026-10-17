from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Uuid
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, TimestampMixin
from app.domain.enums import SubscriptionAuditAction
from app.models.user import StringEnum

if TYPE_CHECKING:
    from app.models.user import User


class SubscriptionAuditLog(Base, TimestampMixin):
    """Append-only audit trail for administrator subscription mutations.

    Every admin action that provisions, changes the plan of, or revokes a
    subscription writes one of these rows in the SAME transaction as the
    mutation it describes, so the audit trail can never disagree with the
    subscription state. The table is deliberately append-only: there is no
    soft-delete column and no update/delete API.
    """

    __tablename__ = "subscription_audit_logs"
    __table_args__ = (
        Index(
            "ix_subscription_audit_logs_subscription",
            "subscription_id",
            "created_at",
        ),
        Index("ix_subscription_audit_logs_user", "user_id", "created_at"),
        Index("ix_subscription_audit_logs_admin", "admin_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=False
    )
    action: Mapped[SubscriptionAuditAction] = mapped_column(
        StringEnum(SubscriptionAuditAction), nullable=False
    )
    old_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recruitment_plans.id"), nullable=True
    )
    new_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recruitment_plans.id"), nullable=True
    )
    reason: Mapped[str] = mapped_column(
        String(500).with_variant(NVARCHAR(500), "mssql"), nullable=False
    )

    admin: Mapped[User] = relationship(
        foreign_keys=[admin_id],
        lazy="selectin",
    )
    user: Mapped[User] = relationship(
        foreign_keys=[user_id],
        lazy="selectin",
    )
