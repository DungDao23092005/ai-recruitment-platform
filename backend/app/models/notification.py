from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text, Uuid, Boolean
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, TimestampMixin, SoftDeleteMixin


class Notification(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(
        String(255).with_variant(NVARCHAR(255), "mssql"), nullable=False
    )
    content: Mapped[str] = mapped_column(
        Text().with_variant(NVARCHAR, "mssql"), nullable=False
    )
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship(back_populates="notifications")