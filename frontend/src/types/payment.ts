export interface VNPayCreatePaymentRequest {
  plan_id: string
}

export interface VNPayCreatePaymentResponse {
  payment_url: string
  internal_order_id: string
  payment_order_id: string
  subscription_id: string
}

export interface PaymentOrderRead {
  id: string
  user_id: string
  plan_id: string
  subscription_id: string | null
  amount: number
  currency: string
  provider: string
  internal_order_id: string
  provider_order_id: string | null
  provider_request_id: string | null
  status: string
  paid_at: string | null
  expired_at: string | null
  created_at: string
  updated_at: string
}

export interface PaymentTransactionRead {
  id: string
  payment_order_id: string
  provider_transaction_id: string | null
  provider_result_code: string | null
  provider_message: string | null
  provider_response_metadata: string | null
  status: string
  responded_at: string | null
  created_at: string
  updated_at: string
}

export interface PaymentStatusResponse {
  payment_order: PaymentOrderRead
  transaction: PaymentTransactionRead | null
  is_successful: boolean
  message: string
}