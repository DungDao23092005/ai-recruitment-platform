from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin


class InterviewAssignment(Base, TimestampMixin, SoftDeleteMixin):
    """Explicit assignment of an interview to a workspace member."""

    __tablename__ = "interview_assignments"
    __table_args__ = (
        Index(
            "uq_interview_assignments_active_interview_user",
            "interview_id",
            "user_id",
            unique=True,
            mssql_where=text("is_deleted = 0"),
        ),
        Index(
            "ix_interview_assignments_user_active",
            "user_id",
            mssql_where=text("is_deleted = 0"),
        ),
        Index(
            "ix_interview_assignments_interview_active",
            "interview_id",
            mssql_where=text("is_deleted = 0"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    interview_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="NO ACTION"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=False,
    )
    assigned_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=False,
    )
