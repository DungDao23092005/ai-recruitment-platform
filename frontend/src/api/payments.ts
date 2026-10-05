import apiClient from '@/api/client'
import type { VNPayCreatePaymentRequest, VNPayCreatePaymentResponse, PaymentStatusResponse } from '@/types/payment'

export async function createVNPayPayment(planId: string): Promise<VNPayCreatePaymentResponse> {
  return apiClient.post<VNPayCreatePaymentRequest, VNPayCreatePaymentResponse>('/payments/vnpay/create', { plan_id: planId })
}

export async function getPaymentStatus(internalOrderId: string): Promise<PaymentStatusResponse> {
  return apiClient.get<PaymentStatusResponse, PaymentStatusResponse>(`/payments/vnpay/status/${internalOrderId}`)
}