from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Uuid
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.candidate_contact_request import CandidateContactRequest
    from app.models.resume import Resume
    from app.models.user import User


class CandidateProfile(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "candidate_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
    )
    full_name: Mapped[str | None] = mapped_column(
        String(255).with_variant(NVARCHAR(255), "mssql"), nullable=True
    )
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_searchable: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="candidate_profile")
    resumes: Mapped[list[Resume]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    applications: Mapped[list[Application]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    contact_requests: Mapped[list[CandidateContactRequest]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
