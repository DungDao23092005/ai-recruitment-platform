import { describe, expect, it, vi, beforeEach } from 'vitest'
import axios from 'axios'

import { createVNPayPayment, getPaymentStatus } from './payments'

vi.mock('axios', async (importOriginal) => {
  const actual = await importOriginal<typeof import('axios')>()
  const mockInstance = {
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  }
  return {
    __esModule: true,
    ...actual,
    default: {
      ...actual.default,
      create: vi.fn(() => mockInstance),
    },
  }
})

const mockAxiosInstance = axios.create as ReturnType<typeof vi.fn>
const instance = mockAxiosInstance.mock.results[0].value

beforeEach(() => {
  vi.clearAllMocks()
})

describe('createVNPayPayment', () => {
  it('sends POST to /payments/vnpay/create with plan_id', async () => {
    const planId = 'plan-1'
    instance.post.mockResolvedValueOnce({
      payment_url: 'url',
      internal_order_id: 'order-1',
      payment_order_id: 'pay-1',
      subscription_id: 'sub-1',
    } as any)

    const result = await createVNPayPayment(planId)

    expect(instance.post).toHaveBeenCalledWith('/payments/vnpay/create', { plan_id: planId })
    expect(result.payment_url).toBe('url')
    expect(result.internal_order_id).toBe('order-1')
    expect(result.payment_order_id).toBe('pay-1')
    expect(result.subscription_id).toBe('sub-1')
  })

  it('propagates API error', async () => {
    const message = 'Plan not found'
    instance.post.mockRejectedValueOnce(new Error(message))

    await expect(createVNPayPayment('non-existent-plan')).rejects.toEqual(new Error(message))

    expect(instance.post).toHaveBeenCalledWith('/payments/vnpay/create', { plan_id: 'non-existent-plan' })
  })
})

describe('getPaymentStatus', () => {
  it('sends GET to /payments/vnpay/status/:orderId', async () => {
    const orderId = 'order-1'
    instance.get.mockResolvedValueOnce({
      payment_order: { id: 'pay-1', status: 'success', user_id: 'user-1', plan_id: 'plan-1', amount: 100000, currency: 'VND', provider: 'vnpay', internal_order_id: 'order-1', provider_order_id: null, provider_request_id: null, status: 'success', paid_at: '2024-01-01T00:00:00Z', expired_at: null, created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
      transaction: { id: 'tx-1', payment_order_id: 'pay-1', provider_transaction_id: null, provider_result_code: null, provider_message: null, provider_response_metadata: null, status: 'success', responded_at: '2024-01-01T00:00:00Z', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
      is_successful: true,
      message: 'Payment successful',
    } as any)

    const result = await getPaymentStatus(orderId)

    expect(instance.get).toHaveBeenCalledWith('/payments/vnpay/status/' + orderId)
    expect(result.is_successful).toBe(true)
    expect(result.payment_order.status).toBe('success')
    expect(result.message).toBe('Payment successful')
  })

  it('propagates API error', async () => {
    const message = 'Payment order not found'
    instance.get.mockRejectedValueOnce(new Error(message))

    await expect(getPaymentStatus('non-existent-order')).rejects.toEqual(new Error(message))

    expect(instance.get).toHaveBeenCalledWith('/payments/vnpay/status/' + 'non-existent-order')
  })
})