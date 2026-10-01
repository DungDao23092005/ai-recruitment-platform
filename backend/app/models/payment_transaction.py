from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base_class import Base, SoftDeleteMixin, TimestampMixin
from app.domain.enums import PaymentTransactionStatus
from app.models.user import StringEnum

if TYPE_CHECKING:
    from app.models.payment_order import PaymentOrder


class PaymentTransaction(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "payment_transactions"
    __table_args__ = (
        Index("ix_payment_transactions_provider_transaction_id_unique", "provider_transaction_id", unique=True, mssql_where=text("provider_transaction_id IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    payment_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payment_orders.id"), nullable=False
    )
    provider_transaction_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    provider_result_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_message: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    provider_response_metadata: Mapped[str | None] = mapped_column(
        Text(), nullable=True
    )
    status: Mapped[PaymentTransactionStatus] = mapped_column(
        StringEnum(PaymentTransactionStatus),
        default=PaymentTransactionStatus.PENDING,
        nullable=False,
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    payment_order: Mapped["PaymentOrder"] = relationship(back_populates="transactions")