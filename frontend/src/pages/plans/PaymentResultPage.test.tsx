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

function makeOrder(overrides: Partial<PaymentStatusResponse['payment_order']> = {}) {
  return {
    id: 'po-1',
    user_id: 'user-1',
    plan_id: 'plan-1',
    subscription_id: 'sub-1',
    amount: 299000,
    currency: 'VND',
    provider: 'vnpay',
    internal_order_id: 'VNPAY_ORDER_123',
    provider_order_id: null,
    provider_request_id: null,
    status: 'paid',
    paid_at: '2026-01-15T03:30:00Z',
    expired_at: null,
    created_at: '2026-01-15T03:00:00Z',
    updated_at: '2026-01-15T03:30:00Z',
    ...overrides,
  } as PaymentStatusResponse['payment_order']
}

function makeTransaction(
  overrides: Partial<NonNullable<PaymentStatusResponse['transaction']>> = {},
) {
  return {
    id: 'tx-1',
    payment_order_id: 'po-1',
    provider_transaction_id: 'VNP_TXN_987654',
    provider_result_code: '00',
    provider_message: 'Success',
    provider_response_metadata: null,
    status: 'success',
    responded_at: '2026-01-15T03:30:00Z',
    created_at: '2026-01-15T03:30:00Z',
    updated_at: '2026-01-15T03:30:00Z',
    ...overrides,
  } as NonNullable<PaymentStatusResponse['transaction']>
}

function paidResponse(
  overrides: Partial<PaymentStatusResponse> = {},
): PaymentStatusResponse {
  return {
    is_successful: true,
    is_activated: true,
    subscription_status: 'active',
    plan_name: 'Gói Chuyên Nghiệp',
    subscription_expires_at: '2026-02-14T03:30:00Z',
    message: 'Payment successful',
    payment_order: makeOrder(),
    transaction: makeTransaction(),
    ...overrides,
  }
}

function paidNotActivatedResponse(): PaymentStatusResponse {
  return {
    is_successful: true,
    is_activated: false,
    subscription_status: 'pending',
    plan_name: 'Gói Chuyên Nghiệp',
    subscription_expires_at: null,
    message: 'Payment received; subscription activation requires reconciliation',
    payment_order: makeOrder(),
    transaction: makeTransaction(),
  }
}

function pendingResponse(): PaymentStatusResponse {
  return {
    is_successful: false,
    is_activated: false,
    subscription_status: 'pending',
    plan_name: null,
    subscription_expires_at: null,
    message: 'Payment pending or failed',
    payment_order: makeOrder({ status: 'pending', paid_at: null }),
    transaction: null,
  }
}

function failedResponse(): PaymentStatusResponse {
  return {
    is_successful: false,
    is_activated: false,
    subscription_status: 'pending',
    plan_name: null,
    subscription_expires_at: null,
    message: 'Giao dịch không thành công',
    payment_order: makeOrder({ status: 'failed', paid_at: null }),
    transaction: makeTransaction({ provider_transaction_id: null }),
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

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedGetPaymentStatus.mockReset()
  mockedRefreshCurrentUser.mockReset()
  mockedRefreshCurrentUser.mockResolvedValue(undefined)
  mockCurrentUser = null
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

  it('falls back to vnp_TxnRef when order_id is absent (direct VNPAY return)', async () => {
    mockedGetPaymentStatus.mockResolvedValue(paidResponse())
    renderPaymentPage('TXN-42', 'vnp_TxnRef')
    await waitFor(() => expect(screen.getByText('Thanh toán thành công')).toBeInTheDocument())
    expect(mockedGetPaymentStatus).toHaveBeenCalledWith('TXN-42')
  })

  it('shows a receipt skeleton with a live status region while verifying', () => {
    mockedGetPaymentStatus.mockReturnValue(new Promise(() => {}))
    renderPaymentPage()
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByText('Đang xác minh giao dịch với VNPAY...')).toBeInTheDocument()
  })
})

describe('PaymentResultPage - success and active subscription (A)', () => {
  it('renders the full verified receipt without the hardcoded upgrade claim', async () => {
    setMockCurrentUser('recruiter')
    mockedGetPaymentStatus.mockResolvedValue(paidResponse())
    renderPaymentPage()

    await waitFor(() => expect(screen.getByText('Thanh toán thành công')).toBeInTheDocument())

    expect(screen.getByText(/Gói "Gói Chuyên Nghiệp" đã được kích hoạt thành công/)).toBeInTheDocument()
    expect(screen.getByText(/299\.000/)).toBeInTheDocument()
    expect(screen.getByText('VNPAY_ORDER_123')).toBeInTheDocument()
    expect(screen.getByText('VNP_TXN_987654')).toBeInTheDocument()
    expect(screen.getByText('10:30 15/01/2026')).toBeInTheDocument()
    expect(screen.getByText('14/02/2026')).toBeInTheDocument()
    expect(
      screen.queryByText('Bạn đã được nâng cấp lên Nhà tuyển dụng thành công'),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Bắt đầu tuyển dụng' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Quay lại gói dịch vụ' })).toBeInTheDocument()
  })

  it('refreshes auth exactly once for a paid and activated order', async () => {
    mockedGetPaymentStatus.mockResolvedValue(paidResponse())
    renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Thanh toán thành công')).toBeInTheDocument())
    expect(mockedRefreshCurrentUser).toHaveBeenCalledTimes(1)
  })

  it('hides the expiry row when the backend does not confirm an entitlement period', async () => {
    setMockCurrentUser('recruiter')
    mockedGetPaymentStatus.mockResolvedValue(
      paidResponse({ subscription_expires_at: null }),
    )
    renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Thanh toán thành công')).toBeInTheDocument())
    expect(screen.queryByText('Hiệu lực đến')).not.toBeInTheDocument()
  })

  it('exposes the terminal state via a heading for assistive tech', async () => {
    mockedGetPaymentStatus.mockResolvedValue(paidResponse())
    renderPaymentPage()
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { level: 1, name: 'Thanh toán thành công' }),
      ).toBeInTheDocument(),
    )
  })
})

describe('PaymentResultPage - paid but not activated (B)', () => {
  it('shows the reconciliation-pending state with receipt details and no duplicate payment', async () => {
    setMockCurrentUser('recruiter')
    mockedGetPaymentStatus.mockResolvedValue(paidNotActivatedResponse())
    renderPaymentPage()

    await waitFor(() =>
      expect(screen.getByText('Đã nhận thanh toán, đang kích hoạt gói')).toBeInTheDocument(),
    )
    expect(screen.getByText(/không thanh toán lại/)).toBeInTheDocument()
    expect(screen.getByText('VNPAY_ORDER_123')).toBeInTheDocument()
    expect(screen.getByText(/299\.000/)).toBeInTheDocument()
    expect(screen.queryByText('Thanh toán thành công')).not.toBeInTheDocument()
    expect(screen.queryByText('Bắt đầu tuyển dụng')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Kiểm tra lại' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Quay lại gói dịch vụ' })).toBeInTheDocument()
    expect(mockedRefreshCurrentUser).not.toHaveBeenCalled()
  })

  it('re-checks status when the user clicks "Kiểm tra lại"', async () => {
    mockedGetPaymentStatus.mockResolvedValueOnce(paidNotActivatedResponse())
    renderPaymentPage()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Kiểm tra lại' })).toBeInTheDocument(),
    )

    mockedGetPaymentStatus.mockResolvedValue(paidResponse())
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra lại' }))

    await waitFor(() => expect(screen.getByText('Thanh toán thành công')).toBeInTheDocument())
  })
})

describe('PaymentResultPage - failed / cancelled / expired (C)', () => {
  it('shows a safe failure state with a single non-resubmitting CTA', async () => {
    mockedGetPaymentStatus.mockResolvedValue(failedResponse())
    renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Thanh toán thất bại')).toBeInTheDocument())
    expect(screen.getByText('Giao dịch không thành công')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Quay lại gói dịch vụ' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Kiểm tra lại' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Thử lại' })).not.toBeInTheDocument()
    expect(mockedRefreshCurrentUser).not.toHaveBeenCalled()
  })

  it('labels a cancelled order as a failure', async () => {
    mockedGetPaymentStatus.mockResolvedValue(
      failedResponse().payment_order
        ? { ...failedResponse(), payment_order: makeOrder({ status: 'cancelled' }) }
        : failedResponse(),
    )
    renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Thanh toán thất bại')).toBeInTheDocument())
    expect(screen.getByText('Đã hủy')).toBeInTheDocument()
  })
})

describe('PaymentResultPage - bounded polling and pending (D)', () => {
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

  it('stops after bounded attempts and shows a pending panel, never a failure or checkout', async () => {
    vi.useFakeTimers()
    mockedGetPaymentStatus.mockResolvedValue(pendingResponse())

    renderPaymentPage()

    await act(async () => {
      await vi.runAllTimersAsync()
    })

    expect(screen.getByText('Giao dịch đang được xử lý')).toBeInTheDocument()
    expect(screen.queryByText('Thanh toán thất bại')).not.toBeInTheDocument()
    expect(screen.getByText('VNPAY_ORDER_123')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Kiểm tra lại' })).toBeInTheDocument()
    expect(mockedRefreshCurrentUser).not.toHaveBeenCalled()
    expect(mockedGetPaymentStatus.mock.calls.length).toBeGreaterThan(1)
  }, 15000)
})

describe('PaymentResultPage - error and invalid (E)', () => {
  it('never trusts query-string success/message/vnp_ResponseCode', async () => {
    mockedGetPaymentStatus.mockResolvedValue(pendingResponse())
    renderWithUrl(
      '/payment-result?order_id=o1&success=true&message=Paid&vnp_ResponseCode=00',
    )
    await waitFor(() => expect(mockedGetPaymentStatus).toHaveBeenCalledWith('o1'))
    expect(screen.queryByText('Thanh toán thành công')).not.toBeInTheDocument()
  })

  it('shows the invalid state when the backend denies ownership (404)', async () => {
    mockedGetPaymentStatus.mockRejectedValue({ response: { status: 404 } })
    renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Không tìm thấy giao dịch')).toBeInTheDocument())
  })

  it('retries transient errors and then allows a manual retry without inferring failure', async () => {
    vi.useFakeTimers()
    mockedGetPaymentStatus.mockRejectedValue(new Error('Network error'))

    renderPaymentPage()

    await act(async () => {
      await vi.runAllTimersAsync()
    })

    expect(
      screen.getByText('Không thể kiểm tra trạng thái thanh toán'),
    ).toBeInTheDocument()
    expect(screen.queryByText('Thanh toán thất bại')).not.toBeInTheDocument()

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

  it('preserves success when the auth refresh fails', async () => {
    mockedGetPaymentStatus.mockResolvedValue(paidResponse())
    mockedRefreshCurrentUser.mockRejectedValueOnce(new Error('Auth refresh failed'))
    renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Thanh toán thành công')).toBeInTheDocument())
    expect(mockedRefreshCurrentUser).toHaveBeenCalledTimes(1)
  })
})

describe('PaymentResultPage - stale data handling', () => {
  it('clears the previous verified receipt while a retry is in flight', async () => {
    const second = deferred<PaymentStatusResponse>()
    mockedGetPaymentStatus.mockResolvedValueOnce(paidNotActivatedResponse())

    renderPaymentPage()
    await waitFor(() => expect(screen.getByText('VNPAY_ORDER_123')).toBeInTheDocument())

    mockedGetPaymentStatus.mockReturnValueOnce(second.promise)
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra lại' }))

    await waitFor(() =>
      expect(screen.queryByText('VNPAY_ORDER_123')).not.toBeInTheDocument(),
    )
    expect(screen.getByRole('status')).toBeInTheDocument()

    await act(async () => {
      second.resolve(failedResponse())
      await second.promise
    })
  })
})

describe('PaymentResultPage - copy interactions', () => {
  it('copies the internal order reference and reports success', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
    mockedGetPaymentStatus.mockResolvedValue(paidResponse())
    renderPaymentPage()
    await waitFor(() => expect(screen.getByText('VNPAY_ORDER_123')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Sao chép mã đơn hàng' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('VNPAY_ORDER_123'))
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Đã sao chép' }),
      ).toBeInTheDocument(),
    )
  })

  it('copies the provider transaction id and surfaces a clipboard failure', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('denied'))
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
    mockedGetPaymentStatus.mockResolvedValue(paidResponse())
    renderPaymentPage()
    await waitFor(() => expect(screen.getByText('VNP_TXN_987654')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Sao chép mã giao dịch VNPAY' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('VNP_TXN_987654'))
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Không thể sao chép' }),
      ).toBeInTheDocument(),
    )
  })
})

describe('PaymentResultPage - recruiter navigation', () => {
  it('hides the recruiter CTA for non-recruiters on verified success', async () => {
    setMockCurrentUser('candidate')
    mockedGetPaymentStatus.mockResolvedValue(paidResponse())

    renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Thanh toán thành công')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Bắt đầu tuyển dụng' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Quay lại gói dịch vụ' })).toBeInTheDocument()
  })
})
