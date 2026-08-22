from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, TimestampMixin


class PasswordResetOTP(Base, TimestampMixin):
    __tablename__ = "password_reset_otps"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    otp_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    reset_token_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="password_reset_otps")

    __table_args__ = (
        Index("ix_password_reset_otps_email_is_used_expires_at", "email", "is_used", "expires_at"),
    )