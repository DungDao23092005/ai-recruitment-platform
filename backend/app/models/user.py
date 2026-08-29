from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin
from app.domain.enums import UserRole
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.notification import Notification
    from app.models.password_reset_otp import PasswordResetOTP


class StringEnum(TypeDecorator):
    """Maps a domain (str, Enum) member to its lowercase string value."""

    impl = String
    cache_ok = True

    def __init__(self, enum_class: type[Enum]) -> None:
        super().__init__(length=50)
        self.enum_class = enum_class

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return value.value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return self.enum_class(value)

    def _coerce_compared_value(self, op, value):
        return self.impl.coerce_compared_value(op, value)


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_email", "email", unique=True, mssql_where=text("is_deleted = 0")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(StringEnum(UserRole), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_password_reset: Mapped[datetime | None] = mapped_column(nullable=True)
    lock_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    locked_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id"),
        nullable=True,
    )

    candidate_profile: Mapped[CandidateProfile | None] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    recruiter_profile: Mapped[RecruiterProfile | None] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    password_reset_otps: Mapped[list["PasswordResetOTP"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    locked_by_user: Mapped["User | None"] = relationship(
        back_populates="locked_users",
        remote_side=[id],
    )
    locked_users: Mapped[list["User"]] = relationship(
        back_populates="locked_by_user",
    )
