import { useEffect } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within, fireEvent, act } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

import { PlansPage } from '@/pages/plans/PlansPage'
import { useAuth } from '@/contexts/AuthContext'
import { usePlans } from '@/features/subscriptions/hooks/usePlans'
import { useMySubscription } from '@/features/subscriptions/hooks/useMySubscription'
import type { UserRole } from '@/types/auth'

// Mock the API modules
vi.mock('@/api/plans', async () => {
  const actual = await import('@/api/plans')
  return {
    ...actual,
    getPlans: vi.fn(),
    getPlan: vi.fn(),
  }
})

vi.mock('@/api/subscriptions', async () => {
  const actual = await import('@/api/subscriptions')
  return {
    ...actual,
    getMySubscription: vi.fn(),
  }
})

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

const mockedGetPlans = (await import('@/api/plans')).getPlans
const mockedGetMySubscription = (await import('@/api/subscriptions')).getMySubscription
const mockedUseAuth = vi.mocked(useAuth)

const loginMock = vi.fn()
const logoutMock = vi.fn()
const refreshCurrentUserMock = vi.fn()

function makeUser(role: UserRole) {
  return {
    id: 'user-1',
    email: 'user@example.com',
    role,
    is_active: true,
    created_at: '2024-01-01',
    updated_at: '2024-01-01',
  }
}

function mockAuth(role: UserRole) {
  mockedUseAuth.mockReturnValue({
    currentUser: makeUser(role),
    token: 'test-token',
    isAuthenticated: true,
    isLoading: false,
    login: loginMock,
    logout: logoutMock,
    refreshCurrentUser: refreshCurrentUserMock,
  } as ReturnType<typeof useAuth>)
}

let checkoutMounts = 0

function CheckoutProbe() {
  useEffect(() => {
    checkoutMounts += 1
  }, [])
  return <div>CHECKOUT PAGE</div>
}

function renderPlans() {
  return render(
    <MemoryRouter initialEntries={['/plans']}>
      <Routes>
        <Route path="/plans" element={<PlansPage />} />
        <Route path="/checkout/:planId" element={<CheckoutProbe />} />
      </Routes>
    </MemoryRouter>,
  )
}

const plans = [
  {
    id: 'plan-1',
    name: 'Gói Standard',
    description: 'Gói đăng tin cơ bản',
    price: 5000000,
    currency: 'VND',
    duration_days: 30,
    max_job_posts: 5,
    max_candidate_searches: 10,
    max_ai_features: 3,
    is_active: true,
    features: ['1 công việc đăng'],
  },
  {
    id: 'plan-2',
    name: 'Gói Nâng cao',
    description: 'Gói đăng tin nâng cao',
    price: 10000000,
    currency: 'VND',
    duration_days: 30,
    max_job_posts: 20,
    max_candidate_searches: 50,
    max_ai_features: 10,
    is_active: true,
    features: ['5 công việc đăng', 'Tiếp cận người dùng kích cỡ'],
  },
]

const subscription = {
  id: 'sub-1',
  user_id: 'user-1',
  plan_id: 'plan-1',
  status: 'active' as const,
  started_at: '2024-01-01',
  expires_at: '2099-01-01',
  plan: {
    id: 'plan-1',
    name: 'Gói Standard',
    description: 'Gói đăng tin cơ bản',
    price: 5000000,
    currency: 'VND',
    duration_days: 30,
    max_job_posts: 5,
    max_candidate_searches: 10,
    max_ai_features: 3,
    features: ['1 công việc đăng'],
  },
}

describe('PlansPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    checkoutMounts = 0
    mockAuth('recruiter')
  })

  it('shows loading UI while fetching data', async () => {
    mockedGetPlans.mockResolvedValueOnce([] as any)
    mockedGetMySubscription.mockResolvedValueOnce(subscription as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    // Check for skeleton loading - the page renders 3 skeleton cards
    const skeletons = screen.getAllByTestId('skeleton')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('shows page header with title and description', async () => {
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockResolvedValueOnce(subscription as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getByText('Các gói tuyển dụng')).toBeInTheDocument())
    expect(screen.getByText(/Chọn gói phù hợp để đăng tin tuyển dụng/)).toBeInTheDocument()
  })

  it('shows current subscription when present', async () => {
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockResolvedValueOnce(subscription as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getByText('Đang hoạt động')).toBeInTheDocument())
    // Check subscription card specifically
    const subscriptionCard = screen.getByText('Đang hoạt động').closest('div')
    expect(subscriptionCard).toBeInTheDocument()
  })

  it('shows plan name from the subscription.plan object', async () => {
    const subscriptionWithPlan = {
      ...subscription,
      plan_id: 'plan-premium',
      plan: { ...subscription.plan, id: 'plan-premium', name: 'Gói Premium' },
    }
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockResolvedValueOnce(subscriptionWithPlan as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getByText('Đang hoạt động')).toBeInTheDocument())
    expect(screen.getByText('Gói Premium')).toBeInTheDocument()
    expect(screen.queryByText('Gói không xác định')).not.toBeInTheDocument()
  })

  it('falls back to plan_id lookup when subscription.plan is absent', async () => {
    const subscriptionWithoutPlan = {
      id: 'sub-2',
      user_id: 'user-1',
      plan_id: 'plan-1',
      status: 'active' as const,
      started_at: '2024-01-01',
      expires_at: '2025-01-01',
    }
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockResolvedValueOnce(subscriptionWithoutPlan as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getByText('Đang hoạt động')).toBeInTheDocument())
    // Plan card for plan-1 + subscription card resolved via fallback
    expect(screen.getAllByText('Gói Standard').length).toBe(2)
    expect(screen.queryByText('Gói không xác định')).not.toBeInTheDocument()
  })

  it('shows unknown-plan fallback when plan cannot be resolved', async () => {
    const subscriptionUnknownPlan = {
      id: 'sub-3',
      user_id: 'user-1',
      plan_id: 'plan-missing',
      status: 'active' as const,
      started_at: '2024-01-01',
      expires_at: '2025-01-01',
    }
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockResolvedValueOnce(subscriptionUnknownPlan as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getByText('Gói không xác định')).toBeInTheDocument())
  })

  it('shows active status and expiry for the current subscription', async () => {
    const activeSubscription = { ...subscription, expires_at: '2099-01-01' }
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockResolvedValueOnce(activeSubscription as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getByText('Đang hoạt động')).toBeInTheDocument())
    expect(screen.getByText(/Hết hạn vào/)).toBeInTheDocument()
    expect(screen.getByText(/01\/01\/2099/)).toBeInTheDocument()
  })

it('renders multiple plan cards with correct data', async () => {
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockResolvedValueOnce(subscription as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(2))
    // Check plan cards - use getAllByRole for plan cards
    const planCards = screen.getAllByRole('article')
    // First article is subscription card, next two are plan cards
    expect(planCards.length).toBeGreaterThanOrEqual(2)

    // Check plan names appear in plan cards - verify both plan names exist in the document
    const standardElements = screen.getAllByText('Gói Standard')
    const nangCaoElements = screen.getAllByText('Gói Nâng cao')
    expect(standardElements.length).toBeGreaterThanOrEqual(1)
    expect(nangCaoElements.length).toBeGreaterThanOrEqual(1)

    // Check prices - there will be multiple but at least these two
    expect(screen.getByText('5.000.000 ₫')).toBeInTheDocument()
    expect(screen.getByText('10.000.000 ₫')).toBeInTheDocument()
  })

  it('shows plan features and quotas correctly', async () => {
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockResolvedValueOnce(subscription as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    await waitFor(() => {
      const jobPostsElements = screen.getAllByText(/bài đăng tin/)
      expect(jobPostsElements.length).toBeGreaterThanOrEqual(1)
    })
    const searchElements = screen.getAllByText(/tìm kiếm ứng viên/)
    expect(searchElements.length).toBeGreaterThanOrEqual(1)
    const aiElements = screen.getAllByText(/tính năng AI/)
    expect(aiElements.length).toBeGreaterThanOrEqual(1)
  })

  it('shows empty state when no plans', async () => {
    mockedGetPlans.mockResolvedValueOnce([] as any)
    mockedGetMySubscription.mockResolvedValueOnce(subscription as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getByText('Không có gói tuyển dụng')).toBeInTheDocument())
  })

  it('shows error when plans API fails', async () => {
    mockedGetPlans.mockRejectedValueOnce(new Error('Failed to load plans'))
    mockedGetMySubscription.mockResolvedValueOnce(subscription as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
  })

  it('renders select buttons for each plan when there is no current plan', async () => {
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockResolvedValueOnce(null)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    await waitFor(() => {
      const buttons = screen.getAllByText('Chọn gói này')
      expect(buttons.length).toBe(2)
    })
    expect(screen.queryByText('Gói hiện tại của bạn')).not.toBeInTheDocument()
  })

  it('marks the active, unexpired plan as current and disables its CTA', async () => {
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockResolvedValueOnce(subscription as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    const currentButton = await screen.findByText('Gói hiện tại của bạn')
    expect(currentButton).toBeDisabled()
    expect(
      screen.getByLabelText('Gói hiện tại của bạn: Gói Standard'),
    ).toBeInTheDocument()
    // The other plan keeps its normal select CTA.
    expect(screen.getByText('Chọn gói này')).toBeInTheDocument()
  })

  it('keeps other plans selectable and navigates them to checkout', async () => {
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockResolvedValueOnce(subscription as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <Routes>
          <Route path="/plans" element={<PlansPage />} />
          <Route path="/checkout/:planId" element={<div>CHECKOUT PAGE</div>} />
        </Routes>
      </MemoryRouter>
    )

    await screen.findByText('Gói hiện tại của bạn')
    fireEvent.click(screen.getByText('Chọn gói này'))

    await waitFor(() => expect(screen.getByText('CHECKOUT PAGE')).toBeInTheDocument())
  })

  it('does not navigate to checkout when clicking the current plan CTA', async () => {
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockResolvedValueOnce(subscription as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <Routes>
          <Route path="/plans" element={<PlansPage />} />
          <Route path="/checkout/:planId" element={<div>CHECKOUT PAGE</div>} />
        </Routes>
      </MemoryRouter>
    )

    const currentButton = await screen.findByText('Gói hiện tại của bạn')
    fireEvent.click(currentButton)

    expect(screen.queryByText('CHECKOUT PAGE')).not.toBeInTheDocument()
    expect(screen.getByText('Các gói tuyển dụng')).toBeInTheDocument()
  })

  it('does not mark current when the subscription is expired', async () => {
    const expired = { ...subscription, expires_at: '2000-01-01' }
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockResolvedValueOnce(expired as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getAllByText('Chọn gói này').length).toBe(2))
    expect(screen.queryByText('Gói hiện tại của bạn')).not.toBeInTheDocument()
  })

  it('does not mark current when expires_at is invalid', async () => {
    const invalid = { ...subscription, expires_at: 'not-a-real-date' }
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockResolvedValueOnce(invalid as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getAllByText('Chọn gói này').length).toBe(2))
    expect(screen.queryByText('Gói hiện tại của bạn')).not.toBeInTheDocument()
  })

  it.each(['pending', 'cancelled', 'expired'] as const)(
    'does not mark current when status is %s',
    async (status) => {
      const nonActive = { ...subscription, status }
      mockedGetPlans.mockResolvedValueOnce(plans as any)
      mockedGetMySubscription.mockResolvedValueOnce(nonActive as any)

      render(
        <MemoryRouter initialEntries={['/plans']}>
          <PlansPage />
        </MemoryRouter>
      )

      await waitFor(() => expect(screen.getAllByText('Chọn gói này').length).toBe(2))
      expect(screen.queryByText('Gói hiện tại của bạn')).not.toBeInTheDocument()
    },
  )

  it('does not mark current while the subscription is still loading', async () => {
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockReturnValueOnce(new Promise(() => {}))

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getAllByText('Chọn gói này').length).toBe(2))
    expect(screen.queryByText('Gói hiện tại của bạn')).not.toBeInTheDocument()
  })

  it('does not mark current when the subscription request fails', async () => {
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockRejectedValueOnce(new Error('Failed to load subscription'))

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getAllByText('Chọn gói này').length).toBe(2))
    expect(screen.queryByText('Gói hiện tại của bạn')).not.toBeInTheDocument()
  })

  it('treats a null expires_at as not expired', async () => {
    const noExpiry = { ...subscription, expires_at: null }
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockResolvedValueOnce(noExpiry as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    const currentButton = await screen.findByText('Gói hiện tại của bạn')
    expect(currentButton).toBeDisabled()
  })

  it('updates the current plan when a subscription invalidation arrives without a reload', async () => {
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription
      .mockResolvedValueOnce(subscription as any)
      .mockResolvedValueOnce(null)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    const currentButton = await screen.findByText('Gói hiện tại của bạn')
    expect(currentButton).toBeDisabled()

    act(() => {
      window.dispatchEvent(
        new CustomEvent('subscription:changed', {
          detail: { notification_type: 'subscription_revoked', entity_type: 'subscription' },
        }),
      )
    })

    await waitFor(
      () => expect(screen.getAllByText('Chọn gói này').length).toBe(2),
      { timeout: 2000 },
    )
    expect(screen.queryByText('Gói hiện tại của bạn')).not.toBeInTheDocument()
    expect(screen.queryByText('Đang hoạt động')).not.toBeInTheDocument()
    // Pricing for the unaffected plan cards is unchanged.
    expect(screen.getByText('5.000.000 ₫')).toBeInTheDocument()
    expect(screen.getByText('10.000.000 ₫')).toBeInTheDocument()
  })

  it('refreshes the subscription state when the renew button is clicked', async () => {
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription
      .mockResolvedValueOnce(subscription as any)
      .mockResolvedValueOnce(null)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    const renewButton = await screen.findByText('Làm mới trạng thái')
    fireEvent.click(renewButton)

    await waitFor(() => expect(screen.getAllByText('Chọn gói này').length).toBe(2))
    expect(mockedGetMySubscription).toHaveBeenCalledTimes(2)
  })

  describe('candidate recruiter upgrade flow', () => {
    beforeEach(() => {
      mockAuth('candidate')
    })

    async function openModal() {
      mockedGetPlans.mockResolvedValueOnce(plans as any)
      mockedGetMySubscription.mockResolvedValueOnce(null)

      renderPlans()

      fireEvent.click(
        await screen.findByRole('button', { name: 'Chọn gói Gói Standard' }),
      )
      return screen.findByRole('dialog')
    }

    it('opens the transition modal instead of navigating to checkout', async () => {
      const dialog = await openModal()

      expect(dialog).toHaveAccessibleName('Bạn muốn trở thành nhà tuyển dụng?')
      expect(
        within(dialog).getByText('Bạn muốn trở thành nhà tuyển dụng?'),
      ).toBeInTheDocument()
      expect(dialog.contains(document.activeElement)).toBe(true)
      expect(screen.queryByText('CHECKOUT PAGE')).not.toBeInTheDocument()
    })

    it('shows the selected plan name, price, duration, and quotas', async () => {
      const dialog = await openModal()

      expect(within(dialog).getByText('Gói Standard')).toBeInTheDocument()
      expect(within(dialog).getByText('5.000.000 ₫')).toBeInTheDocument()
      expect(within(dialog).getByText('/ 1 tháng')).toBeInTheDocument()
      expect(within(dialog).getByText('Bài đăng tin')).toBeInTheDocument()
      expect(within(dialog).getByText('Tìm kiếm ứng viên')).toBeInTheDocument()
      expect(within(dialog).getByText('Tính năng AI')).toBeInTheDocument()
    })

    it('keeps the acknowledgement unchecked and continue disabled by default', async () => {
      const dialog = await openModal()

      const checkbox = within(dialog).getByRole('checkbox')
      const continueButton = within(dialog).getByRole('button', {
        name: /Tiếp tục tới thanh toán/,
      })

      expect(checkbox).not.toBeChecked()
      expect(continueButton).toBeDisabled()

      fireEvent.click(checkbox)

      expect(checkbox).toBeChecked()
      expect(continueButton).toBeEnabled()
    })

    it('explains the role change, lost candidate features, and retained data', async () => {
      const dialog = await openModal()

      expect(
        within(dialog).getAllByText(/Tài khoản của bạn được chuyển từ/).length,
      ).toBeGreaterThan(0)
      expect(
        within(dialog).getAllByText(/tính năng chỉ dành riêng cho ứng viên/)
          .length,
      ).toBeGreaterThan(0)
      expect(
        within(dialog).getAllByText(/Hồ sơ, CV và lịch sử ứng tuyển/)
          .length,
      ).toBeGreaterThan(0)
      expect(
        within(dialog).getAllByText(/xác minh thanh toán thành công/).length,
      ).toBeGreaterThan(0)
    })

    it('navigates to checkout for the selected plan after acknowledgement', async () => {
      const dialog = await openModal()

      fireEvent.click(within(dialog).getByRole('checkbox'))
      fireEvent.click(
        within(dialog).getByRole('button', {
          name: /Tiếp tục tới thanh toán/,
        }),
      )

      await waitFor(() =>
        expect(screen.getByText('CHECKOUT PAGE')).toBeInTheDocument(),
      )
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(checkoutMounts).toBe(1)
    })

    it('cancels back to the plans page without checking out', async () => {
      const dialog = await openModal()

      fireEvent.click(within(dialog).getByRole('button', { name: 'Hủy' }))

      await waitFor(() =>
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
      )
      expect(screen.queryByText('CHECKOUT PAGE')).not.toBeInTheDocument()
      expect(screen.getByText('Các gói tuyển dụng')).toBeInTheDocument()
    })

    it('closes on Escape without navigating', async () => {
      await openModal()

      fireEvent.keyDown(document, { key: 'Escape' })

      await waitFor(() =>
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
      )
      expect(screen.queryByText('CHECKOUT PAGE')).not.toBeInTheDocument()
    })

    it('does not change the account role when opening or confirming', async () => {
      const dialog = await openModal()

      fireEvent.click(within(dialog).getByRole('checkbox'))
      fireEvent.click(
        within(dialog).getByRole('button', {
          name: /Tiếp tục tới thanh toán/,
        }),
      )

      await waitFor(() =>
        expect(screen.getByText('CHECKOUT PAGE')).toBeInTheDocument(),
      )
      expect(refreshCurrentUserMock).not.toHaveBeenCalled()
      expect(loginMock).not.toHaveBeenCalled()
      expect(logoutMock).not.toHaveBeenCalled()
    })

    it('navigates only once when continue is activated again', async () => {
      const dialog = await openModal()

      fireEvent.click(within(dialog).getByRole('checkbox'))
      const continueButton = within(dialog).getByRole('button', {
        name: /Tiếp tục tới thanh toán/,
      })
      fireEvent.click(continueButton)

      await waitFor(() =>
        expect(screen.getByText('CHECKOUT PAGE')).toBeInTheDocument(),
      )
      fireEvent.click(continueButton)

      expect(checkoutMounts).toBe(1)
    })

    it('does not open the transition modal for the current active plan', async () => {
      mockedGetPlans.mockResolvedValueOnce(plans as any)
      mockedGetMySubscription.mockResolvedValueOnce(subscription as any)

      renderPlans()

      const currentButton = await screen.findByText('Gói hiện tại của bạn')
      fireEvent.click(currentButton)

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(screen.queryByText('CHECKOUT PAGE')).not.toBeInTheDocument()
    })
  })

  describe('recruiter plan selection flow', () => {
    it('skips the candidate transition modal and goes straight to checkout', async () => {
      mockAuth('recruiter')
      mockedGetPlans.mockResolvedValueOnce(plans as any)
      mockedGetMySubscription.mockResolvedValueOnce(null)

      renderPlans()

      fireEvent.click(
        await screen.findByRole('button', { name: 'Chọn gói Gói Standard' }),
      )

      await waitFor(() =>
        expect(screen.getByText('CHECKOUT PAGE')).toBeInTheDocument(),
      )
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })
})
