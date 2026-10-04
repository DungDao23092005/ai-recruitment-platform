from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class VNPayCreatePaymentRequest(BaseModel):
    """Request to create a VNPAY payment for a recruitment plan."""

    plan_id: uuid.UUID


class VNPayCreatePaymentResponse(BaseModel):
    """Response containing VNPAY payment URL."""

    payment_url: str
    internal_order_id: str
    payment_order_id: uuid.UUID
    subscription_id: uuid.UUID


class VNPayIPNParams(BaseModel):
    """VNPAY IPN callback parameters."""

    vnp_Version: Optional[str] = None
    vnp_Command: Optional[str] = None
    vnp_TmnCode: Optional[str] = None
    vnp_Amount: Optional[str] = None
    vnp_CurrCode: Optional[str] = None
    vnp_TxnRef: Optional[str] = None
    vnp_OrderInfo: Optional[str] = None
    vnp_OrderType: Optional[str] = None
    vnp_TransactionNo: Optional[str] = None
    vnp_TransactionStatus: Optional[str] = None
    vnp_ResponseCode: Optional[str] = None
    vnp_PayDate: Optional[str] = None
    vnp_CardType: Optional[str] = None
    vnp_BankCode: Optional[str] = None
    vnp_BankTranNo: Optional[str] = None
    vnp_SecureHash: Optional[str] = None
    vnp_SecureHashType: Optional[str] = None


class VNPayReturnParams(BaseModel):
    """VNPAY Return URL callback parameters."""

    vnp_Version: Optional[str] = None
    vnp_Command: Optional[str] = None
    vnp_TmnCode: Optional[str] = None
    vnp_Amount: Optional[str] = None
    vnp_CurrCode: Optional[str] = None
    vnp_TxnRef: Optional[str] = None
    vnp_OrderInfo: Optional[str] = None
    vnp_OrderType: Optional[str] = None
    vnp_TransactionNo: Optional[str] = None
    vnp_TransactionStatus: Optional[str] = None
    vnp_ResponseCode: Optional[str] = None
    vnp_PayDate: Optional[str] = None
    vnp_CardType: Optional[str] = None
    vnp_BankCode: Optional[str] = None
    vnp_BankTranNo: Optional[str] = None
    vnp_SecureHash: Optional[str] = None
    vnp_SecureHashType: Optional[str] = None


class PaymentOrderRead(BaseModel):
    """Payment order read model."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    plan_id: uuid.UUID
    subscription_id: Optional[uuid.UUID]
    amount: int
    currency: str
    provider: str
    internal_order_id: str
    provider_order_id: Optional[str]
    provider_request_id: Optional[str]
    status: str
    paid_at: Optional[datetime]
    expired_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class PaymentTransactionRead(BaseModel):
    """Payment transaction read model."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    payment_order_id: uuid.UUID
    provider_transaction_id: Optional[str]
    provider_result_code: Optional[str]
    provider_message: Optional[str]
    provider_response_metadata: Optional[str]
    status: str
    responded_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class PaymentStatusResponse(BaseModel):
    """Payment status response."""

    payment_order: PaymentOrderRead
    transaction: Optional[PaymentTransactionRead] = None
    is_successful: bool
    message: str