from __future__ import annotations

import uuid

from sqlalchemy import Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin
from app.domain.enums import CompanySize
from app.models.user import StringEnum


class Company(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "companies"
    __table_args__ = (
        Index("uq_companies_slug", "slug", unique=True, mssql_where=text("is_deleted = 0")),
        Index(
            "uq_companies_tax_code",
            "tax_code",
            unique=True,
            mssql_where=text("is_deleted = 0"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    tax_code: Mapped[str] = mapped_column(String(50), nullable=False)
    size: Mapped[CompanySize] = mapped_column(StringEnum(CompanySize), nullable=False)

    recruiters: Mapped[list[RecruiterProfile]] = relationship(
        back_populates="company",
    )
    jobs: Mapped[list[Job]] = relationship(
        back_populates="company",
    )
