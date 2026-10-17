import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { AuthProvider } from '@/contexts/AuthContext'
import { PaymentResultPage } from '@/pages/plans/PaymentResultPage'
import * as paymentsApi from '@/api/payments'
import type { PaymentStatusResponse } from '@/types/payment'

const mockedGetPaymentStatus = vi.mocked(paymentsApi.getPaymentStatus)
const mockedRefreshCurrentUser = vi.fn()

const POLL_INTERVAL_MS = 3000

let mockCurrentUser: { role: string } | null = null

vi.mock('@/api/payments', () => ({
  getPaymentStatus: vi.fn(),
}))

vi.mock('@/api/auth', () => ({
  getCurrentUser: vi.fn(),
  login: vi.fn(),
  register: vi.fn(),
  createCandidateProfile: vi.fn(),
  createRecruiterProfile: vi.fn(),
  logout: vi.fn(),
}))

vi.mock('@/contexts/AuthContext', async () => {
  const actual = await import('@/contexts/AuthContext')
  return {
    ...actual,
    useAuth: () => ({
      currentUser: mockCurrentUser,
      token: null,
      isAuthenticated: !!mockCurrentUser,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      refreshCurrentUser: mockedRefreshCurrentUser,
    }),
  }
})

function setMockCurrentUser(role: string | null) {
  mockCurrentUser = role ? { role } : null
}

function paidResponse(): PaymentStatusResponse {
  return {
    is_successful: true,
    is_activated: true,
    subscription_status: 'active',
    plan_name: 'Gói Chuyên Nghiệp',
    message: 'Payment successful',
    payment_order: { status: 'paid' } as unknown as PaymentStatusResponse['payment_order'],
    transaction: null,
  }
}

function paidNotActivatedResponse(): PaymentStatusResponse {
  return {
    is_successful: true,
    is_activated: false,
    subscription_status: 'pending',
    plan_name: 'Gói Chuyên Nghiệp',
    message: 'Payment received; subscription activation requires reconciliation',
    payment_order: { status: 'paid' } as unknown as PaymentStatusResponse['payment_order'],
    transaction: null,
  }
}

function pendingResponse(): PaymentStatusResponse {
  return {
    is_successful: false,
    is_activated: false,
    subscription_status: 'pending',
    plan_name: null,
    message: 'Payment pending or failed',
    payment_order: { status: 'pending' } as unknown as PaymentStatusResponse['payment_order'],
    transaction: null,
  }
}

function failedResponse(): PaymentStatusResponse {
  return {
    is_successful: false,
    is_activated: false,
    subscription_status: 'pending',
    plan_name: null,
    message: 'Giao dịch không thành công',
    payment_order: { status: 'failed' } as unknown as PaymentStatusResponse['payment_order'],
    transaction: null,
  }
}

function renderWithUrl(url: string) {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[url]}>
        <PaymentResultPage />
      </MemoryRouter>
    </AuthProvider>,
  )
}

function renderPaymentPage(orderId: string | null = 'order-1', param = 'order_id') {
  const url = orderId ? `/payment-result?${param}=${orderId}` : '/payment-result'
  return renderWithUrl(url)
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedGetPaymentStatus.mockReset()
  mockedRefreshCurrentUser.mockReset()
  mockedRefreshCurrentUser.mockResolvedValue(undefined)
  mockCurrentUser = null
  vi.spyOn(window, 'alert').mockImplementation(() => {})
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('PaymentResultPage - order reference resolution', () => {
  it('shows an invalid state and never calls the API when no order reference is present', () => {
    renderPaymentPage(null)
    expect(screen.getByText('Không tìm thấy giao dịch')).toBeInTheDocument()
    expect(mockedGetPaymentStatus).not.toHaveBeenCalled()
  })

  it('resolves the reference from order_id', async () => {
    mockedGetPaymentStatus.mockResolvedValue(paidResponse())
    renderPaymentPage('order-abc', 'order_id')
    await waitFor(() => expect(screen.getByText('Thanh toán thành công')).toBeInTheDocument())
    expect(mockedGetPaymentStatus).toHaveBeenCalledWith('order-abc')
  })

  it('falls back to vnp_TxnRef when order_id is absent', async () => {
    mockedGetPaymentStatus.mockResolvedValue(paidResponse())
    renderPaymentPage('TXN-42', 'vnp_TxnRef')
    await waitFor(() => expect(screen.getByText('Thanh toán thành công')).toBeInTheDocument())
    expect(mockedGetPaymentStatus).toHaveBeenCalledWith('TXN-42')
  })
})

describe('PaymentResultPage - server-verified outcome', () => {
  it('shows success and refreshes auth exactly once for a paid order', async () => {
    mockedGetPaymentStatus.mockResolvedValue(paidResponse())
    renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Thanh toán thành công')).toBeInTheDocument())
    expect(mockedRefreshCurrentUser).toHaveBeenCalledTimes(1)
  })

  it('never trusts query-string success/message/vnp_ResponseCode', async () => {
    mockedGetPaymentStatus.mockResolvedValue(pendingResponse())
    renderWithUrl(
      '/payment-result?order_id=o1&success=true&message=Paid&vnp_ResponseCode=00',
    )
    await waitFor(() => expect(mockedGetPaymentStatus).toHaveBeenCalledWith('o1'))
    expect(screen.queryByText('Thanh toán thành công')).not.toBeInTheDocument()
  })

  it('shows failure UI for a definitive failed order', async () => {
    mockedGetPaymentStatus.mockResolvedValue(failedResponse())
    renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Thanh toán thất bại')).toBeInTheDocument())
    expect(mockedRefreshCurrentUser).not.toHaveBeenCalled()
  })

  it('shows the activation-pending state for a paid but unactivated order', async () => {
    setMockCurrentUser('recruiter')
    mockedGetPaymentStatus.mockResolvedValue(paidNotActivatedResponse())
    renderPaymentPage()
    await waitFor(() =>
      expect(screen.getByText('Đã nhận thanh toán, đang kích hoạt gói')).toBeInTheDocument(),
    )
    expect(screen.queryByText('Thanh toán thành công')).not.toBeInTheDocument()
    expect(
      screen.queryByText('Bạn đã được nâng cấp lên Nhà tuyển dụng thành công'),
    ).not.toBeInTheDocument()
    expect(mockedRefreshCurrentUser).not.toHaveBeenCalled()
  })

  it('preserves success when the auth refresh fails', async () => {
    mockedGetPaymentStatus.mockResolvedValue(paidResponse())
    mockedRefreshCurrentUser.mockRejectedValueOnce(new Error('Auth refresh failed'))
    renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Thanh toán thành công')).toBeInTheDocument())
    expect(mockedRefreshCurrentUser).toHaveBeenCalledTimes(1)
  })

  it('shows the invalid state when the backend denies ownership (404)', async () => {
    mockedGetPaymentStatus.mockRejectedValue({ response: { status: 404 } })
    renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Không tìm thấy giao dịch')).toBeInTheDocument())
  })
})

describe('PaymentResultPage - bounded polling', () => {
  it('polls a pending order then surfaces verified success with a single auth refresh', async () => {
    vi.useFakeTimers()
    mockedGetPaymentStatus
      .mockResolvedValueOnce(pendingResponse())
      .mockResolvedValue(paidResponse())

    renderPaymentPage()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    })
    await act(async () => {
      await vi.runAllTimersAsync()
    })

    expect(screen.getByText('Thanh toán thành công')).toBeInTheDocument()
    expect(mockedRefreshCurrentUser).toHaveBeenCalledTimes(1)
  }, 15000)

  it('stops after bounded attempts and shows a pending panel for a persistently pending order', async () => {
    vi.useFakeTimers()
    mockedGetPaymentStatus.mockResolvedValue(pendingResponse())

    renderPaymentPage()

    await act(async () => {
      await vi.runAllTimersAsync()
    })

    expect(screen.getByText('Giao dịch đang được xử lý')).toBeInTheDocument()
    expect(mockedRefreshCurrentUser).not.toHaveBeenCalled()
    expect(mockedGetPaymentStatus.mock.calls.length).toBeGreaterThan(1)
  }, 15000)

  it('retries transient errors and then allows a manual retry', async () => {
    vi.useFakeTimers()
    mockedGetPaymentStatus.mockRejectedValue(new Error('Network error'))

    renderPaymentPage()

    await act(async () => {
      await vi.runAllTimersAsync()
    })

    expect(
      screen.getByText('Không thể kiểm tra trạng thái thanh toán'),
    ).toBeInTheDocument()

    mockedGetPaymentStatus.mockReset()
    mockedGetPaymentStatus.mockResolvedValue(paidResponse())

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    })
    await act(async () => {
      await vi.runAllTimersAsync()
    })

    expect(screen.getByText('Thanh toán thành công')).toBeInTheDocument()
  }, 15000)
})

describe('PaymentResultPage - recruiter navigation', () => {
  it('shows the recruiter upgrade CTA for a recruiter on verified success', async () => {
    setMockCurrentUser('recruiter')
    mockedGetPaymentStatus.mockResolvedValue(paidResponse())

    renderPaymentPage()
    await waitFor(() =>
      expect(
        screen.getByText('Bạn đã được nâng cấp lên Nhà tuyển dụng thành công'),
      ).toBeInTheDocument(),
    )
    expect(screen.getByRole('button', { name: 'Bắt đầu tuyển dụng' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Quay lại gói dịch vụ' })).toBeInTheDocument()
  })

  it('falls back to the standard success UI for non-recruiters', async () => {
    setMockCurrentUser('candidate')
    mockedGetPaymentStatus.mockResolvedValue(paidResponse())

    renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Thanh toán thành công')).toBeInTheDocument())
    expect(
      screen.queryByText('Bạn đã được nâng cấp lên Nhà tuyển dụng thành công'),
    ).not.toBeInTheDocument()
  })
})
