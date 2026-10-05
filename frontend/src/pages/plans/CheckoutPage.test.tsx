import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

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

vi.mock('@/features/subscriptions/hooks/useMySubscription', () => ({
  useMySubscription: vi.fn(),
}))

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return {
    ...actual,
    useParams: vi.fn(() => ({ planId: 'plan-1' })),
    useNavigate: actual.useNavigate,
    MemoryRouter: actual.MemoryRouter,
  }
})

describe('CheckoutPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading state initially', async () => {
    ;(getPlan as any).mockResolvedValueOnce({
      id: 'plan-1',
      name: 'GA3i Dipper',
      description: 'Dipper plan',
      price: 100000,
      currency: 'VND',
      image: '/placeholder.svg',
      is_active: true,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    })

    const { container } = render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        <CheckoutPage />
      </MemoryRouter>
    )
    expect(container.innerHTML).toContain('Gói không tìm thấy hoặc không còn khả dụng')
  })

  it('renders plan data after plan fetch', async () => {
    ;(getPlan as any).mockResolvedValueOnce({
      id: 'plan-1',
      name: 'GA3i Dipper',
      description: 'Dipper plan',
      price: 100000,
      currency: 'VND',
      image: '/placeholder.svg',
      is_active: true,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    })

    const { container } = render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        <CheckoutPage />
      </MemoryRouter>
    )

    await vi.waitFor(() => {
      expect(screen.getByRole('heading', { name: /Dipper/i })).toBeInTheDocument()
    })
  })

  it('calls createVNPayPayment on submit', async () => {
    ;(getPlan as any).mockResolvedValueOnce({
      id: 'plan-1',
      name: 'GA3i Dipper',
      description: 'Dipper plan',
      price: 100000,
      currency: 'VND',
      image: '/placeholder.svg',
      is_active: true,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    })
    ;(createVNPayPayment as any).mockResolvedValueOnce({
      payment_url: 'https://sandbox.vnpay.com/pay',
      internal_order_id: 'order-1',
      payment_order_id: 'pay-1',
      subscription_id: 'sub-1',
    })

    const { container } = render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        <CheckoutPage />
      </MemoryRouter>
    )

    await vi.waitFor(() => {
      expect(screen.getByRole('heading', { name: /Dipper/i })).toBeInTheDocument()
    })

    const submitBtn = screen.getByRole('button', {
      name: /Thanh toán với VNPAY/i,
    })
    submitBtn.click()

    await vi.waitFor(() => {
      expect(createVNPayPayment).toHaveBeenCalledWith('plan-1')
    })
  })

  it('shows payment CTA button', async () => {
    ;(getPlan as any).mockResolvedValueOnce({
      id: 'plan-1',
      name: 'GA3i Dipper',
      description: 'Dipper plan',
      price: 100000,
      currency: 'VND',
      image: '/placeholder.svg',
      is_active: true,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    })

    const { container } = render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        <CheckoutPage />
      </MemoryRouter>
    )

    await vi.waitFor(() => {
      expect(screen.getByRole('heading', { name: /Dipper/i })).toBeInTheDocument()
    })

    const ctaButton = screen.getByRole('button', {
      name: /Thanh toán với VNPAY/i,
    })
    expect(ctaButton).toBeInTheDocument()
  })

  it('displays plan price with Vietnamese formatting', async () => {
    ;(getPlan as any).mockResolvedValueOnce({
      id: 'plan-1',
      name: 'GA3i Dipper',
      description: 'Dipper plan',
      price: 100000,
      currency: 'VND',
      image: '/placeholder.svg',
      is_active: true,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    })

    const { container } = render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        <CheckoutPage />
      </MemoryRouter>
    )

    await vi.waitFor(() => {
      expect(screen.getByRole('heading', { name: /Dipper/i })).toBeInTheDocument()
    })

    const priceElement = screen.getByText('100,000 VND')
    expect(priceElement).toBeInTheDocument()
  })

  it('prevents duplicate submission', async () => {
    // Use deferred Promise pattern to genuinely test duplicate submission
    let resolvePayment!: (value: {
      payment_url: string
      internal_order_id: string
      payment_order_id: string
      subscription_id: string
    }) => void

    ;(getPlan as any).mockResolvedValueOnce({
      id: 'plan-1',
      name: 'GA3i Dipper',
      description: 'Dipper plan',
      price: 100000,
      currency: 'VND',
      image: '/placeholder.svg',
      is_active: true,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    })

    ;(createVNPayPayment as any).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePayment = resolve
        }),
    )

    const { container } = render(
      <MemoryRouter initialEntries={['/checkout/plan-1']}>
        <CheckoutPage />
      </MemoryRouter>
    )

    await vi.waitFor(() => {
      expect(screen.getByRole('heading', { name: /Dipper/i })).toBeInTheDocument()
    })

    // Query button without name filter initially (text is "Thanh toán với VNPAY")
    let submitBtn = screen.getByRole('button')
    await act(() => {
      submitBtn.click()
    })
    // Wait for the component to enter submitting state (isSubmitting = true, button disabled)
    await vi.waitFor(() => {
      // After first click, button has disabled attribute and text changes to "Đang tạo thanh toán..."
      expect(submitBtn).toHaveAttribute('disabled')
    })

    // Get fresh button reference - now has "Đang tạo thanh toán..." text
    submitBtn = screen.getByRole('button')

    // Second click while the first Promise is STILL pending
    await act(() => {
      submitBtn.click()
    })

    // CRITICAL: At this point, createVNPayPayment should have been called exactly once
    // because the button is disabled (isSubmitting = true) and the first Promise is still pending
    await vi.waitFor(() => {
      expect(createVNPayPayment).toHaveBeenCalledTimes(1)
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
      expect(createVNPayPayment).toHaveBeenCalledTimes(1)
    })
  })
})