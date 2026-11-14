import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { CompanySubscriptionCard } from './CompanySubscriptionCard'
import type { Subscription } from '@/types/subscription'

const baseSubscription: Subscription = {
  id: 'sub-1',
  user_id: 'user-1',
  plan_id: 'plan-1',
  status: 'active',
  started_at: '2026-11-01T00:00:00Z',
  expires_at: '2026-12-01T00:00:00Z',
  max_job_posts: 10,
  max_candidate_searches: 20,
  max_ai_features: 5,
  job_posts_used: 4,
  candidate_searches_used: 20,
  ai_features_used: 1,
  plan: {
    id: 'plan-1',
    name: 'Gói Doanh nghiệp',
    description: 'Gói cho công ty',
    price: 5000000,
    currency: 'VND',
    duration_days: 30,
    max_job_posts: 10,
    max_candidate_searches: 20,
    max_ai_features: 5,
    is_active: true,
  },
}

function renderCard(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('CompanySubscriptionCard', () => {
  it('renders the plan, status and remaining quotas', () => {
    renderCard(<CompanySubscriptionCard subscription={baseSubscription} />)

    expect(screen.getByText('Gói Doanh nghiệp')).toBeInTheDocument()
    expect(screen.getByText('Đang hoạt động')).toBeInTheDocument()
    expect(screen.getByText('Tin tuyển dụng')).toBeInTheDocument()
    expect(screen.getByText('4 / 10')).toBeInTheDocument()
    expect(screen.getByText('Còn lại 6')).toBeInTheDocument()
    expect(screen.getByText('20 / 20')).toBeInTheDocument()
    expect(screen.getAllByText('Còn lại 0').length).toBeGreaterThan(0)
  })

  it('never shows a negative remaining quota', () => {
    renderCard(
      <CompanySubscriptionCard
        subscription={{
          ...baseSubscription,
          job_posts_used: 15,
          max_job_posts: 10,
        }}
      />,
    )

    expect(screen.getByText('15 / 10')).toBeInTheDocument()
    expect(screen.getAllByText('Còn lại 0').length).toBeGreaterThan(0)
  })

  it('handles missing quota values without fabricating zero usage', () => {
    renderCard(
      <CompanySubscriptionCard
        subscription={{
          ...baseSubscription,
          max_job_posts: undefined,
          job_posts_used: undefined,
        }}
      />,
    )

    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('shows an informational empty state to Workspace Recruiters', () => {
    renderCard(
      <CompanySubscriptionCard subscription={null} isAdmin={false} />,
    )

    expect(screen.getByText('Chưa có gói dịch vụ')).toBeInTheDocument()
    expect(
      screen.getByText('Liên hệ Quản trị viên công ty để chọn gói dịch vụ.'),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /Chọn gói dịch vụ/ }),
    ).not.toBeInTheDocument()
  })

  it('links Workspace Admins to the company plan catalog', () => {
    renderCard(<CompanySubscriptionCard subscription={null} isAdmin />)

    const link = screen.getByRole('link', { name: /Chọn gói dịch vụ/ })
    expect(link).toHaveAttribute('href', '/plans?audience=company')
  })

  it('shows the retry action when loading fails', () => {
    const onRetry = vi.fn()
    renderCard(
      <CompanySubscriptionCard
        subscription={null}
        error="Không thể tải gói dịch vụ"
        onRetry={onRetry}
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Không thể tải gói dịch vụ',
    )
    expect(screen.getByRole('button', { name: /Thử lại/i })).toBeInTheDocument()
  })

  it('shows a skeleton while loading', () => {
    renderCard(
      <CompanySubscriptionCard subscription={null} isLoading />,
    )

    expect(
      screen.getByTestId('company-subscription-loading'),
    ).toBeInTheDocument()
  })
})
