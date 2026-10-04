import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { PlansPage } from '@/pages/plans/PlansPage'
import { usePlans } from '@/features/subscriptions/hooks/usePlans'
import { useMySubscription } from '@/features/subscriptions/hooks/useMySubscription'

// Mock the API modules
vi.mock('@/api/plans', async () => {
  const actual = await import('@/api/plans')
  return {
    ...actual,
    getPlans: vi.fn(),
  }
})

vi.mock('@/api/subscriptions', async () => {
  const actual = await import('@/api/subscriptions')
  return {
    ...actual,
    getMySubscription: vi.fn(),
  }
})

const mockedGetPlans = (await import('@/api/plans')).getPlans
const mockedGetMySubscription = (await import('@/api/subscriptions')).getMySubscription

const plans = [
  {
    id: 'plan-1',
    name: 'Gói Standard',
    description: 'Gói đăng tin cơ bản',
    price: 5000000,
    currency: 'VND',
    duration_days: 30,
    max_job_posts: 5,
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
    is_active: true,
    features: ['5 công việc đăng', 'Tiếp cận người dùng kích cỡ'],
  },
]

const subscription = {
  id: 'sub-1',
  user_id: 'user-1',
  plan_id: 'plan-1',
  status: 'active' as const,
  start_date: '2024-01-01',
  end_date: '2025-01-01',
  plan: {
    id: 'plan-1',
    name: 'Gói Standard',
    description: 'Gói đăng tin cơ bản',
    price: 5000000,
    currency: 'VND',
    duration_days: 30,
    max_job_posts: 5,
    features: ['1 công việc đăng'],
  },
}

describe('PlansPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows loading UI while fetching data', async () => {
    mockedGetPlans.mockResolvedValueOnce([] as any)
    mockedGetMySubscription.mockResolvedValueOnce(subscription as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    const loadingDiv = screen.getByText('Đang tải gói...')
    expect(loadingDiv).toBeInTheDocument()
  })

  it('shows current subscription when present', async () => {
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockResolvedValueOnce(subscription as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getByText('Tạo lại')).toBeInTheDocument())
  })

  it('renders multiple plan cards', async () => {
    mockedGetPlans.mockResolvedValueOnce(plans as any)
    mockedGetMySubscription.mockResolvedValueOnce(subscription as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(2))
  })

  it('shows empty state when no plans', async () => {
    mockedGetPlans.mockResolvedValueOnce([] as any)
    mockedGetMySubscription.mockResolvedValueOnce(subscription as any)

    render(
      <MemoryRouter initialEntries={['/plans']}>
        <PlansPage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getByText('Không có gói lên kế hoạch')).toBeInTheDocument())
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
})