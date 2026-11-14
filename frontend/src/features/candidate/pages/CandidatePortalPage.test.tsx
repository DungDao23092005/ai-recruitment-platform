import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { CandidatePortalPage } from '@/features/candidate/pages/CandidatePortalPage'

vi.mock('@/api/subscriptions', async () => {
  const actual = await import('@/api/subscriptions')
  return {
    ...actual,
    getCandidateEntitlementSummary: vi.fn(),
    getCandidateUsages: vi.fn(),
  }
})

const mockedSummary = (await import('@/api/subscriptions'))
  .getCandidateEntitlementSummary as ReturnType<typeof vi.fn>
const mockedUsages = (await import('@/api/subscriptions'))
  .getCandidateUsages as ReturnType<typeof vi.fn>

const entitlement = {
  effective_tier: 'free' as const,
  effective_subscription: {
    id: 'sub-free',
    plan_id: 'plan-free',
    plan_name: 'Gói Khởi đầu',
    status: 'active' as const,
    is_free: true,
    started_at: '2026-01-01T00:00:00Z',
    expires_at: null,
    current_period_key: '2026-11',
    max_ai_features: 6,
    ai_features_used: 2,
    ai_features_remaining: 4,
    is_projected: false,
  },
  free_subscription: null,
  paid_subscription: null,
  is_paid_exhausted: false,
  is_projected: false,
  next_free_reset_at: '2026-12-01T00:00:00Z',
}

describe('CandidatePortalPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedSummary.mockResolvedValue(entitlement)
    mockedUsages.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 10,
      total_pages: 0,
    })
  })

  it('keeps the portal cards and mounts the AI quota and usage sections', async () => {
    render(
      <MemoryRouter>
        <CandidatePortalPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('Tổng quan ứng viên')).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Tìm việc làm' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Tìm việc AI' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Gợi ý việc làm' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Upload CV' }),
    ).toBeInTheDocument()

    expect(await screen.findByText('Gói dịch vụ AI')).toBeInTheDocument()
    expect(screen.getByText('Gói Khởi đầu')).toBeInTheDocument()
    expect(await screen.findByText('Lịch sử sử dụng AI')).toBeInTheDocument()
    expect(
      await screen.findByText('Chưa có lịch sử sử dụng'),
    ).toBeInTheDocument()
  })
})
