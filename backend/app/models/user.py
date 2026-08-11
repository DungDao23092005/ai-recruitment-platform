from __future__ import annotations

import uuid
from enum import Enum

from sqlalchemy import Boolean, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin
from app.domain.enums import UserRole


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
