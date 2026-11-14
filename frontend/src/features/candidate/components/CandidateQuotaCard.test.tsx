import type { ComponentProps } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { CandidateQuotaCard } from '@/features/candidate/components/CandidateQuotaCard'
import type {
  CandidateEntitlementSnapshot,
  CandidateEntitlementSummary,
} from '@/types/subscription'

const FREE_PRESERVED_MESSAGE =
  'Gói miễn phí được bảo lưu và sẽ tự động tiếp tục khi gói trả phí hết hạn.'

function snapshot(
  overrides: Partial<CandidateEntitlementSnapshot> = {},
): CandidateEntitlementSnapshot {
  return {
    id: 'sub-1',
    plan_id: 'plan-free',
    plan_name: 'Gói Khởi đầu',
    status: 'active',
    is_free: true,
    started_at: '2026-01-01T00:00:00Z',
    expires_at: null,
    current_period_key: '2026-11',
    max_ai_features: 6,
    ai_features_used: 2,
    ai_features_remaining: 4,
    is_projected: false,
    ...overrides,
  }
}

function summary(
  overrides: Partial<CandidateEntitlementSummary> = {},
): CandidateEntitlementSummary {
  const free = snapshot()
  return {
    effective_tier: 'free',
    effective_subscription: free,
    free_subscription: free,
    paid_subscription: null,
    is_paid_exhausted: false,
    is_projected: false,
    next_free_reset_at: '2026-12-01T00:00:00Z',
    ...overrides,
  }
}

function renderCard(
  entitlement: CandidateEntitlementSummary | null,
  props: Partial<ComponentProps<typeof CandidateQuotaCard>> = {},
) {
  return render(
    <MemoryRouter>
      <CandidateQuotaCard entitlement={entitlement} {...props} />
    </MemoryRouter>,
  )
}

describe('CandidateQuotaCard', () => {
  it('renders the free quota and monthly reset label', () => {
    renderCard(summary())

    expect(screen.getByText('Gói miễn phí')).toBeInTheDocument()
    expect(screen.getByText('Gói Khởi đầu')).toBeInTheDocument()
    expect(screen.getByText('Lượt AI đã sử dụng')).toBeInTheDocument()
    expect(screen.getByText('Lượt AI còn lại')).toBeInTheDocument()
    expect(
      screen.getByText('Làm mới vào ngày 01 hằng tháng'),
    ).toBeInTheDocument()
    expect(screen.getByText('2/6')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /Nâng cấp gói AI/i }),
    ).toHaveAttribute('href', '/plans')
  })

  it('renders the paid entitlement and preserves the free message', () => {
    const paid = snapshot({
      id: 'sub-paid',
      plan_id: 'plan-paid',
      plan_name: 'Gói AI Pro',
      is_free: false,
      max_ai_features: 25,
      ai_features_used: 4,
      ai_features_remaining: 21,
      expires_at: '2026-12-01T00:00:00Z',
    })
    renderCard(
      summary({
        effective_tier: 'paid',
        effective_subscription: paid,
        paid_subscription: paid,
        free_subscription: snapshot(),
      }),
    )

    expect(screen.getByText('Gói trả phí')).toBeInTheDocument()
    expect(screen.getByText('Gói AI Pro')).toBeInTheDocument()
    expect(screen.getByText('4/25')).toBeInTheDocument()
    expect(screen.getByText(FREE_PRESERVED_MESSAGE)).toBeInTheDocument()
  })

  it('shows the exhausted paid state without falling back to free', () => {
    const paid = snapshot({
      id: 'sub-paid',
      plan_id: 'plan-paid',
      plan_name: 'Gói AI Pro',
      is_free: false,
      max_ai_features: 25,
      ai_features_used: 25,
      ai_features_remaining: 0,
    })
    renderCard(
      summary({
        effective_tier: 'paid',
        effective_subscription: paid,
        paid_subscription: paid,
        is_paid_exhausted: true,
      }),
    )

    expect(screen.getByText('Gói trả phí')).toBeInTheDocument()
    expect(
      screen.getByText(/Bạn đã dùng hết lượt AI của gói hiện tại/),
    ).toBeInTheDocument()
    expect(screen.queryByText('Gói miễn phí')).not.toBeInTheDocument()
  })

  it('renders a projected free snapshot as refreshed in memory', () => {
    const projected = snapshot({
      ai_features_used: 0,
      ai_features_remaining: 6,
      is_projected: true,
    })
    renderCard(
      summary({
        effective_subscription: projected,
        free_subscription: projected,
        is_projected: true,
      }),
    )

    expect(screen.getByText('0/6')).toBeInTheDocument()
    expect(
      screen.getByText(/Hạn mức đã được làm mới cho tháng này/),
    ).toBeInTheDocument()
  })

  it('renders loading and error states', () => {
    const { rerender } = renderCard(null, { isLoading: true })
    expect(screen.getByTestId('candidate-quota-loading')).toBeInTheDocument()

    const retry = vi.fn()
    rerender(
      <MemoryRouter>
        <CandidateQuotaCard
          entitlement={null}
          error="Không tải được quyền lợi AI"
          onRetry={retry}
        />
      </MemoryRouter>,
    )
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Không tải được quyền lợi AI',
    )
  })

  it('renders an empty state without an entitlement', () => {
    renderCard(null)
    expect(screen.getByText('Chưa có thông tin gói AI')).toBeInTheDocument()
  })
})
