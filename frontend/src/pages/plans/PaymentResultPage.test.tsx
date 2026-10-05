import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Mock the API modules
vi.mock('@/api/payments', async () => {
  const actual = await import('@/api/payments')
  return {
    ...actual,
    getPaymentStatus: vi.fn(),
  }
})

import { PaymentResultPage } from '@/pages/plans/PaymentResultPage'

const mockedGetPaymentStatus = (await import('@/api/payments')).getPaymentStatus

let getPaymentStatusCallCount = 0

describe('PaymentResultPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getPaymentStatusCallCount = 0
  })

  it('handles missing order_id safely', () => {
    render(
      <MemoryRouter initialEntries={['/payment-result']}>
        <PaymentResultPage />
      </MemoryRouter>
    )

    const alert = screen.getByText('Thiếu order_id')
    expect(alert).toBeInTheDocument()
  })

  it('shows Success UI when backend returns successful state', async () => {
    mockedGetPaymentStatus.mockResolvedValueOnce({
      payment_order: { id: 'pay-1', status: 'success' },
      is_successful: true,
      message: 'Payment successful',
    })

    render(
      <MemoryRouter initialEntries={['/payment-result?order_id=order-1']}>
        <PaymentResultPage />
      </MemoryRouter>
    )

    await vi.waitFor(() => expect(screen.getByText('Thanh toán thành công')).toBeInTheDocument())
    const goBackButton = screen.getByText('Quay lại gói dịch vụ')
    expect(goBackButton).toBeInTheDocument()
  })

  it('shows Failure UI when backend returns failed state', async () => {
    mockedGetPaymentStatus.mockResolvedValueOnce({
      payment_order: { id: 'pay-1', status: 'failed' },
      is_successful: false,
      message: 'Payment failed',
    })

    render(
      <MemoryRouter initialEntries={['/payment-result?order_id=order-1']}>
        <PaymentResultPage />
      </MemoryRouter>
    )

    await vi.waitFor(() => expect(screen.getByText('Thanh toán thất bại')).toBeInTheDocument())
    const goBackButton = screen.getByText('Quay lại gói dịch vụ')
    expect(goBackButton).toBeInTheDocument()
  })

  it('starts polling when first backend response has pending status', async () => {
    mockedGetPaymentStatus.mockImplementation(() => {
      getPaymentStatusCallCount++
      if (getPaymentStatusCallCount === 1) {
        return Promise.resolve({
          payment_order: { id: 'pay-1', status: 'pending' },
          is_successful: null,
          message: 'Payment pending',
        })
      }
      return Promise.resolve({
        payment_order: { id: 'pay-1', status: 'success' },
        is_successful: true,
        message: 'Payment successful',
      })
    })

    const { unmount } = render(
      <MemoryRouter initialEntries={['/payment-result?order_id=order-1']}>
        <PaymentResultPage />
      </MemoryRouter>
    )

    // Wait for initial load and pending state
    await vi.waitFor(() => expect(screen.getByText('Đang kiểm tra trạng thái thanh toán...')).toBeInTheDocument())

    // Wait for the 3-second polling cycle to complete
    await new Promise(resolve => setTimeout(resolve, 3100))

    // Check for success state after polling
    const successDiv = screen.getByText('Thanh toán thành công')
    expect(successDiv).toBeInTheDocument()

    unmount()
  })

  it('stops polling after maximum retries', async () => {
    getPaymentStatusCallCount = 0
    mockedGetPaymentStatus.mockImplementation(() => {
      getPaymentStatusCallCount++
      if (getPaymentStatusCallCount <= 5) {
        return Promise.resolve({
          payment_order: { id: 'pay-1', status: 'pending' },
          is_successful: null,
          message: 'Payment pending',
        })
      }
      return Promise.resolve({
        payment_order: { id: 'pay-1', status: 'success' },
        is_successful: true,
        message: 'Payment successful',
      })
    })

    const { unmount } = render(
      <MemoryRouter initialEntries={['/payment-result?order_id=order-1']}>
        <PaymentResultPage />
      </MemoryRouter>
    )

    // Wait for initial load and pending state
    await vi.waitFor(() => expect(screen.getByText('Đang kiểm tra trạng thái thanh toán...')).toBeInTheDocument())

    // Wait for 5 retries * 3 seconds + buffer
    await new Promise(resolve => setTimeout(resolve, 3000 * 5 + 200))

    // After 5 retries, polling should stop - mock should have been called 6 times (5 pending + 1 success)
    expect(getPaymentStatusCallCount).toBe(6)

    unmount()
  }, { timeout: 20000 })

  it('shows Failure UI after pending state', async () => {
    mockedGetPaymentStatus.mockImplementation(() => {
      getPaymentStatusCallCount++
      if (getPaymentStatusCallCount === 1) {
        return Promise.resolve({
          payment_order: { id: 'pay-1', status: 'pending' },
          is_successful: null,
          message: 'Payment pending',
        })
      }
      return Promise.resolve({
        payment_order: { id: 'pay-1', status: 'failed' },
        is_successful: false,
        message: 'Payment failed',
      })
    })

    render(
      <MemoryRouter initialEntries={['/payment-result?order_id=order-1']}>
        <PaymentResultPage />
      </MemoryRouter>
    )

    await vi.waitFor(() => expect(screen.getByText('Thanh toán thất bại')).toBeInTheDocument())
  })
})