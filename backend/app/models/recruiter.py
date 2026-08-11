from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin


class RecruiterProfile(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "recruiter_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id"),
        nullable=True,
    )
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    position: Mapped[str | None] = mapped_column(String(100), nullable=True)

    user: Mapped[User] = relationship(back_populates="recruiter_profile")
    company: Mapped[Company | None] = relationship(back_populates="recruiters")
