import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, act, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

import { getPlan } from '@/api/plans'
import { createVNPayPayment } from '@/api/payments'

import { CheckoutPage } from '@/pages/plans/CheckoutPage'

vi.mock('@/api/plans', () => ({
  getPlans: vi.fn(),
  getPlan: vi.fn(),
}))

vi.mock('@/api/payments', () => ({
  createVNPayPayment: vi.fn(),
  getPaymentStatus: vi.fn(),
}))

const mockedGetPlan = (await import('@/api/plans')).getPlan
const mockedCreateVNPayPayment = (await import('@/api/payments')).createVNPayPayment

const testRoutes = (
  <Routes>
    <Route path="/checkout/:planId" element={<CheckoutPage />} />
  </Routes>
)

describe('CheckoutPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const mockPlanData = {
    id: 'plan-1',
    name: 'Gói Standard',
    description: 'Gói đăng tin cơ bản',
    price: 5000000,
    currency: 'VND',
    duration_days: 30,
    max_job_posts: 5,
    max_candidate_searches: 10,
    max_ai_features: 3,
    features: ['1 công việc đăng', 'Hỗ trợ 24/7'],
    is_active: true,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  }

  it('renders loading skeleton initially', async () => {
    ;(mockedGetPlan as any).mockResolvedValueOnce(mockPlanData)

    render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        {testRoutes}
      </MemoryRouter>
    )

    // Check for skeleton loading - uses animate-pulse class
    expect(screen.getByTestId('skeleton')).toBeInTheDocument()
  })

  it('renders plan data after plan fetch', async () => {
    ;(mockedGetPlan as any).mockResolvedValueOnce(mockPlanData)

    render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        {testRoutes}
      </MemoryRouter>
    )

    await waitFor(() => {
      // Scope to main content area - the h2 heading
      const heading = screen.getByRole('heading', { name: 'Gói Standard', level: 2 })
      expect(heading).toBeInTheDocument()
    })
  })

  it('renders plan price with Vietnamese formatting', async () => {
    ;(mockedGetPlan as any).mockResolvedValueOnce(mockPlanData)

    render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        {testRoutes}
      </MemoryRouter>
    )

    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: 'Gói Standard', level: 2 })
      expect(heading).toBeInTheDocument()
    })

    // Price appears in main content area (plan info card) - scope to the first occurrence
    const priceElements = screen.getAllByText('5.000.000 ₫')
    expect(priceElements.length).toBeGreaterThanOrEqual(1)
  })

  it('renders plan duration', async () => {
    ;(mockedGetPlan as any).mockResolvedValueOnce(mockPlanData)

    render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        {testRoutes}
      </MemoryRouter>
    )

    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: 'Gói Standard', level: 2 })
      expect(heading).toBeInTheDocument()
    })

    // Duration appears in the price section next to price - formatDuration(30) returns "1 tháng"
    const durationElements = screen.getAllByText(/1 tháng/)
    expect(durationElements.length).toBeGreaterThanOrEqual(1)
  })

  it('renders max job posts', async () => {
    ;(mockedGetPlan as any).mockResolvedValueOnce(mockPlanData)

    render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        {testRoutes}
      </MemoryRouter>
    )

    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: 'Gói Standard', level: 2 })
      expect(heading).toBeInTheDocument()
    })

    // Check in the main content area (plan info card)
    const jobPostsElements = screen.getAllByText('5 bài')
    expect(jobPostsElements.length).toBeGreaterThanOrEqual(1)
  })

  it('renders candidate searches quota when available', async () => {
    ;(mockedGetPlan as any).mockResolvedValueOnce(mockPlanData)

    render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        {testRoutes}
      </MemoryRouter>
    )

    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: 'Gói Standard', level: 2 })
      expect(heading).toBeInTheDocument()
    })

    const searchElements = screen.getAllByText('10 lần')
    expect(searchElements.length).toBeGreaterThanOrEqual(1)
  })

  it('renders AI features quota when available', async () => {
    ;(mockedGetPlan as any).mockResolvedValueOnce(mockPlanData)

    render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        {testRoutes}
      </MemoryRouter>
    )

    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: 'Gói Standard', level: 2 })
      expect(heading).toBeInTheDocument()
    })

    const aiElements = screen.getAllByText('3 lần')
    expect(aiElements.length).toBeGreaterThanOrEqual(1)
  })

  it('shows back button to return to plans', async () => {
    ;(mockedGetPlan as any).mockResolvedValueOnce(mockPlanData)

    render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        {testRoutes}
      </MemoryRouter>
    )

    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: 'Gói Standard', level: 2 })
      expect(heading).toBeInTheDocument()
    })

    const backButton = screen.getByRole('button', { name: /Quay lại danh sách gói/i })
    expect(backButton).toBeInTheDocument()
  })

  it('shows payment CTA button', async () => {
    ;(mockedGetPlan as any).mockResolvedValueOnce(mockPlanData)

    render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        {testRoutes}
      </MemoryRouter>
    )

    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: 'Gói Standard', level: 2 })
      expect(heading).toBeInTheDocument()
    })

    const ctaButton = screen.getByRole('button', { name: /Thanh toán với VNPAY/i })
    expect(ctaButton).toBeInTheDocument()
  })

  it('calls createVNPayPayment on submit', async () => {
    ;(mockedGetPlan as any).mockResolvedValueOnce(mockPlanData)
    ;(mockedCreateVNPayPayment as any).mockResolvedValueOnce({
      payment_url: 'https://sandbox.vnpay.com/pay',
      internal_order_id: 'order-1',
      payment_order_id: 'pay-1',
      subscription_id: 'sub-1',
    })

    render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        {testRoutes}
      </MemoryRouter>
    )

    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: 'Gói Standard', level: 2 })
      expect(heading).toBeInTheDocument()
    })

    const submitBtn = screen.getByRole('button', { name: /Thanh toán với VNPAY/i })
    submitBtn.click()

    await vi.waitFor(() => {
      expect(mockedCreateVNPayPayment).toHaveBeenCalledWith('plan-1')
    })
  })

  it('prevents duplicate submission', async () => {
    let resolvePayment!: (value: {
      payment_url: string
      internal_order_id: string
      payment_order_id: string
      subscription_id: string
    }) => void

    ;(mockedGetPlan as any).mockResolvedValueOnce(mockPlanData)

    ;(mockedCreateVNPayPayment as any).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePayment = resolve
        }),
    )

    render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        {testRoutes}
      </MemoryRouter>
    )

    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: 'Gói Standard', level: 2 })
      expect(heading).toBeInTheDocument()
    })

    // Query button - use specific name to avoid multiple matches
    let submitBtn = screen.getByRole('button', { name: /Thanh toán với VNPAY/i })
    await act(() => {
      submitBtn.click()
    })

    // Wait for the component to enter submitting state
    await vi.waitFor(() => {
      expect(submitBtn).toHaveAttribute('disabled')
    })

    // Get fresh button reference - now has "Đang tạo thanh toán..." text
    submitBtn = screen.getByRole('button', { name: /Đang tạo thanh toán/i })

    // Second click while the first Promise is STILL pending
    await act(() => {
      submitBtn.click()
    })

    // CRITICAL: At this point, createVNPayPayment should have been called exactly once
    await vi.waitFor(() => {
      expect(mockedCreateVNPayPayment).toHaveBeenCalledTimes(1)
    })

    // Resolve the deferred Promise to cleanly complete the async flow
    resolvePayment!({
      payment_url: 'https://sandbox.vnpay.com/pay',
      internal_order_id: 'order-1',
      payment_order_id: 'pay-1',
      subscription_id: 'sub-1',
    })

    // Wait for the async operation to settle
    await vi.waitFor(() => {
      expect(mockedCreateVNPayPayment).toHaveBeenCalledTimes(1)
    })
  })

  it('shows error message when payment fails with 409', async () => {
    ;(mockedGetPlan as any).mockResolvedValueOnce(mockPlanData)
    ;(mockedCreateVNPayPayment as any).mockRejectedValueOnce({
      response: {
        status: 409,
        message: 'Bạn đang có gói đăng tin đang hoạt động.',
      },
    })

    render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        {testRoutes}
      </MemoryRouter>
    )

    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: 'Gói Standard', level: 2 })
      expect(heading).toBeInTheDocument()
    })

    const submitBtn = screen.getByRole('button', { name: /Thanh toán với VNPAY/i })
    submitBtn.click()

    await vi.waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    // Check for the specific error message
    expect(screen.getByText(/đang có gói đăng tin đang hoạt động/i)).toBeInTheDocument()
  })

  it('prefers the server-provided detail when a 409 is returned', async () => {
    ;(mockedGetPlan as any).mockResolvedValueOnce(mockPlanData)
    ;(mockedCreateVNPayPayment as any).mockRejectedValueOnce({
      response: {
        status: 409,
        data: { detail: 'Bạn chỉ có thể nâng cấp lên gói có giá cao hơn gói hiện tại đang hoạt động.' },
      },
    })

    render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        {testRoutes}
      </MemoryRouter>
    )

    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: 'Gói Standard', level: 2 })
      expect(heading).toBeInTheDocument()
    })

    screen.getByRole('button', { name: /Thanh toán với VNPAY/i }).click()

    await vi.waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    expect(screen.getByText(/chỉ có thể nâng cấp lên gói có giá cao hơn/i)).toBeInTheDocument()
  })

  it('shows error message when plan fetch fails', async () => {
    ;(mockedGetPlan as any).mockRejectedValueOnce(new Error('Failed to load plan'))

    render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        {testRoutes}
      </MemoryRouter>
    )

    await vi.waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    expect(screen.getByText(/Không thể tải thông tin gói/i)).toBeInTheDocument()
  })

  it('shows plan features in checkout', async () => {
    ;(mockedGetPlan as any).mockResolvedValueOnce(mockPlanData)

    render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        {testRoutes}
      </MemoryRouter>
    )

    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: 'Gói Standard', level: 2 })
      expect(heading).toBeInTheDocument()
    })

    // Features are in main content area
    expect(screen.getByText('1 công việc đăng')).toBeInTheDocument()
    expect(screen.getByText('Hỗ trợ 24/7')).toBeInTheDocument()
  })

  it('displays order summary with correct total', async () => {
    ;(mockedGetPlan as any).mockResolvedValueOnce(mockPlanData)

    render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        {testRoutes}
      </MemoryRouter>
    )

    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: 'Gói Standard', level: 2 })
      expect(heading).toBeInTheDocument()
    })

    // Check order summary in sidebar
    expect(screen.getByText('Tóm tắt đơn hàng')).toBeInTheDocument()
    expect(screen.getByText('Tổng thanh toán')).toBeInTheDocument()
    // Price in order summary - scope to sidebar
    const sidebar = screen.getByText('Tóm tắt đơn hàng').closest('div')
    const sidebarSection = within(sidebar!)
    const priceElements = sidebarSection.getAllByText('5.000.000 ₫')
    expect(priceElements.length).toBeGreaterThanOrEqual(1)
  })

  it('shows VNPAY security notice', async () => {
    ;(mockedGetPlan as any).mockResolvedValueOnce(mockPlanData)

    render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        {testRoutes}
      </MemoryRouter>
    )

    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: 'Gói Standard', level: 2 })
      expect(heading).toBeInTheDocument()
    })

    expect(screen.getByText('Giao dịch được xử lý và bảo mật qua cổng thanh toán VNPAY.')).toBeInTheDocument()
  })
})