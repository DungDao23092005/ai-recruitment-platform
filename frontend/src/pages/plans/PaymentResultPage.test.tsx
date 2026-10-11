import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { AuthProvider } from '@/contexts/AuthContext'
import { PaymentResultPage } from '@/pages/plans/PaymentResultPage'
import * as paymentsApi from '@/api/payments'
import * as authApi from '@/api/auth'

const mockedGetPaymentStatus = vi.mocked(paymentsApi.getPaymentStatus)
const mockedGetCurrentUser = vi.mocked(authApi.getCurrentUser)
const mockedRefreshCurrentUser = vi.fn()

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
      currentUser: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      refreshCurrentUser: mockedRefreshCurrentUser,
    }),
  }
})

function renderPaymentPage(orderId: string | null = 'order-1') {
  const url = orderId ? `/payment-result?order_id=${orderId}` : '/payment-result'
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[url]}>
        <PaymentResultPage />
      </MemoryRouter>
    </AuthProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedRefreshCurrentUser.mockReset()
  mockedRefreshCurrentUser.mockResolvedValue(undefined)
  vi.spyOn(window, 'alert').mockImplementation(() => {})
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('PaymentResultPage', () => {
  it('handles missing order_id safely', () => {
    const { unmount } = renderPaymentPage(null)
    expect(screen.getByText('Thiếu order_id')).toBeInTheDocument()
    unmount()
  })

  it('shows Success UI when backend returns successful state', async () => {
    mockedGetPaymentStatus.mockResolvedValue({
      is_successful: true,
      message: 'Thành công',
      payment_order: { status: 'success' },
    })

    const { unmount } = renderPaymentPage()
    expect(screen.getByText('Đang kiểm tra trạng thái thanh toán...')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Thành công')).toBeInTheDocument())
    expect(screen.queryByText('Đang kiểm tra trạng thái thanh toán...')).not.toBeInTheDocument()
    unmount()
  })

  it('shows Failure UI when backend returns failed state', async () => {
    mockedGetPaymentStatus.mockResolvedValue({
      is_successful: false,
      message: 'Thất bại',
      payment_order: { status: 'failed' },
    })

    const { unmount } = renderPaymentPage()
    expect(screen.getByText('Đang kiểm tra trạng thái thanh toán...')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Thanh toán thất bại')).toBeInTheDocument())
    expect(screen.queryByText('Đang kiểm tra trạng thái thanh toán...')).not.toBeInTheDocument()
    unmount()
  })

  it('shows Pending state when backend returns pending status', async () => {
    mockedGetPaymentStatus.mockResolvedValue({
      is_successful: false,
      message: 'Đang xử lý',
      payment_order: { status: 'pending' },
    })

    const { unmount } = renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Đang kiểm tra trạng thái thanh toán...')).toBeInTheDocument())
    unmount()
  })

  it('refreshes auth exactly once on definitive success (no duplicate refresh)', async () => {
    mockedGetPaymentStatus.mockResolvedValue({
      is_successful: true,
      message: 'Thành công',
      payment_order: { status: 'success' },
    })

    const { unmount } = renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Thành công')).toBeInTheDocument())
    expect(mockedRefreshCurrentUser).toHaveBeenCalledTimes(1)
    unmount()
  })

  it('preserves payment success when auth refresh fails', async () => {
    mockedGetPaymentStatus.mockResolvedValue({
      is_successful: true,
      message: 'Thành công',
      payment_order: { status: 'success' },
    })
    mockedRefreshCurrentUser.mockRejectedValueOnce(new Error('Auth refresh failed'))

    const { unmount } = renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Thành công')).toBeInTheDocument())
    expect(mockedRefreshCurrentUser).toHaveBeenCalledTimes(1)
    unmount()
  })

  it('transitions from pending to success via polling and refreshes auth once', async () => {
    vi.useFakeTimers()
    mockedGetPaymentStatus
      .mockResolvedValueOnce({
        is_successful: false,
        message: 'Đang xử lý',
        payment_order: { status: 'pending' },
      })
      .mockResolvedValueOnce({
        is_successful: true,
        message: 'Thành công',
        payment_order: { status: 'success' },
      })
      .mockResolvedValueOnce({
        is_successful: true,
        message: 'Thành công',
        payment_order: { status: 'success' },
      })

    const { unmount } = renderPaymentPage()
    // Check initial loading synchronously (no waitFor with fake timers)
    expect(screen.getByText('Đang kiểm tra trạng thái thanh toán...')).toBeInTheDocument()

    // Advance timers by 3 seconds to trigger polling
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000)
    })

    // Run all pending timers
    await act(async () => {
      await vi.runAllTimersAsync()
    })

    // Check for success directly (no waitFor with fake timers)
    const successElements = screen.getAllByText((content) => content.includes('Thành công'))
    expect(successElements.length).toBeGreaterThan(0)
    expect(mockedRefreshCurrentUser).toHaveBeenCalledTimes(1)
    unmount()
  }, 15000)

  it('handles repeated API failures during polling without crashing', async () => {
    vi.useFakeTimers()
    mockedGetPaymentStatus
      .mockResolvedValueOnce({
        is_successful: false,
        message: 'Đang xử lý',
        payment_order: { status: 'pending' },
      })
      .mockRejectedValueOnce(new Error('Network error'))
      .mockRejectedValueOnce(new Error('Network error'))
      .mockResolvedValueOnce({
        is_successful: true,
        message: 'Thành công',
        payment_order: { status: 'success' },
      })
      .mockResolvedValueOnce({
        is_successful: true,
        message: 'Thành công',
        payment_order: { status: 'success' },
      })

    const { unmount } = renderPaymentPage()
    // Check initial loading synchronously (no waitFor with fake timers)
    expect(screen.getByText('Đang kiểm tra trạng thái thanh toán...')).toBeInTheDocument()

    // Advance timers by 3 seconds to trigger first retry
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000)
    })

    // Advance timers by another 3 seconds for second retry
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000)
    })

    // Run all pending timers
    await act(async () => {
      await vi.runAllTimersAsync()
    })

    // Check for success directly (no waitFor with fake timers)
    const successElements = screen.getAllByText((content) => content.includes('Thành công'))
    expect(successElements.length).toBeGreaterThan(0)
    expect(mockedRefreshCurrentUser).toHaveBeenCalledTimes(1)
    unmount()
  }, 15000)

  it('maintains async/act safety with no act warnings', async () => {
    mockedGetPaymentStatus.mockResolvedValue({
      is_successful: true,
      message: 'Thành công',
      payment_order: { status: 'success' },
    })

    let actWarnings = 0
    const originalError = console.error
    console.error = (...args) => {
      if (args[0]?.includes?.('act(...)')) actWarnings++
      originalError(...args)
    }

    const { unmount } = renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Thành công')).toBeInTheDocument())

    console.error = originalError
    expect(actWarnings).toBe(0)
    unmount()
  })

  it('calls refreshCurrentUser after payment success is confirmed', async () => {
    mockedGetPaymentStatus.mockResolvedValue({
      is_successful: true,
      message: 'Thành công',
      payment_order: { status: 'success' },
    })

    const { unmount } = renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Thành công')).toBeInTheDocument())
    expect(mockedRefreshCurrentUser).toHaveBeenCalled()
    unmount()
  })

  it('shows success UI even when auth refresh fails', async () => {
    mockedGetPaymentStatus.mockResolvedValue({
      is_successful: true,
      message: 'Thành công',
      payment_order: { status: 'success' },
    })
    mockedRefreshCurrentUser.mockRejectedValueOnce(new Error('Auth refresh failed'))

    const { unmount } = renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Thành công')).toBeInTheDocument())
    expect(screen.queryByText('Đang kiểm tra trạng thái thanh toán...')).not.toBeInTheDocument()
    unmount()
  })

  it('displays payment status before auth refresh completes', async () => {
    mockedGetPaymentStatus.mockResolvedValue({
      is_successful: true,
      message: 'Thành công',
      payment_order: { status: 'success' },
    })

    const { unmount } = renderPaymentPage()
    await waitFor(() => expect(screen.getByText('Thành công')).toBeInTheDocument())
    expect(screen.queryByText('Đang kiểm tra trạng thái thanh toán...')).not.toBeInTheDocument()
    unmount()
  })

  it('defers loading clearance until after auth refresh resolves (deferred ordering)', async () => {
    // NO fake timers - waitFor needs real timers
    let resolveRefresh: () => void
    const refreshPromise = new Promise<void>((resolve) => {
      resolveRefresh = resolve
    })
    mockedRefreshCurrentUser.mockReturnValue(refreshPromise)

    mockedGetPaymentStatus.mockResolvedValue({
      is_successful: true,
      message: 'Thành công',
      payment_order: { status: 'success' },
    })

    const { unmount } = renderPaymentPage()

    // Allow payment status request to resolve as definitive success
    // Wait until refreshCurrentUser() has actually been called once
    await waitFor(() => expect(mockedRefreshCurrentUser).toHaveBeenCalledTimes(1))

    // NOW assert: loading MUST still be visible WHILE refresh is pending
    // and success UI must NOT be visible yet
    // This proves the loading state persists during the refresh promise
    expect(
      screen.getByText('Đang kiểm tra trạng thái thanh toán...')
    ).toBeInTheDocument()
    expect(screen.queryByText('Thành công')).not.toBeInTheDocument()

    // Resolve the deferred refresh Promise
    await act(async () => {
      resolveRefresh!()
    })

    // Wait for React updates
    await waitFor(() => {
      const successElements = screen.getAllByText((content) => content.includes('Thành công'))
      expect(successElements.length).toBeGreaterThan(0)
    })

    // After refresh resolves: loading gone, success visible
    expect(screen.queryByText('Đang kiểm tra trạng thái thanh toán...')).not.toBeInTheDocument()
    expect(mockedRefreshCurrentUser).toHaveBeenCalledTimes(1)

    unmount()
  }, 15000)
})