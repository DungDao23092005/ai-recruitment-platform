import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  AdminSubscriptionChangePlanModal,
  resolveSubscriptionTargetAudience,
} from './AdminSubscriptionChangePlanModal'
import { getAdminPlans, changeAdminSubscriptionPlan } from '@/api/admin'
import type { AdminPlanRead, AdminSubscriptionListItem } from '@/types/admin'

vi.mock('@/api/admin', () => ({
  getAdminPlans: vi.fn(),
  changeAdminSubscriptionPlan: vi.fn(),
}))

const mockCandidateSub: AdminSubscriptionListItem = {
  id: 'sub-cand-1',
  user_id: 'user-cand-1',
  user_email: 'candidate@example.com',
  user_full_name: 'Nguyen Van A',
  user_role: 'candidate',
  plan_id: 'plan-cand-basic',
  plan_name: 'Gói Ứng Viên Cơ Bản',
  plan_audience: 'candidate',
  scope: 'candidate_personal',
  is_free: false,
  company_id: null,
  company_name: null,
  current_period_key: '2026-01',
  status: 'active',
  effective_status: 'active',
  started_at: '2026-01-01T00:00:00Z',
  expires_at: '2026-02-01T00:00:00Z',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  max_job_posts: 0,
  max_candidate_searches: 0,
  max_ai_features: 10,
  job_posts_used: 0,
  candidate_searches_used: 0,
  ai_features_used: 2,
  total_subscriptions: 1,
  has_multiple_active: false,
  has_unresolved_payment: false,
  is_entitlement_incident: false,
  incident_subscription_id: null,
  incident_internal_order_id: null,
  incident_amount: null,
}

const mockCompanySub: AdminSubscriptionListItem = {
  ...mockCandidateSub,
  id: 'sub-comp-1',
  user_id: 'user-rec-1',
  user_email: 'recruiter@example.com',
  user_full_name: 'Tran Recruiter',
  user_role: 'recruiter',
  plan_id: 'plan-comp-starter',
  plan_name: 'Gói Doanh Nghiệp Khởi Đầu',
  plan_audience: 'company',
  scope: 'company_recruiting',
}

const candidatePlans: AdminPlanRead[] = [
  {
    id: 'plan-cand-basic',
    name: 'Gói Ứng Viên Cơ Bản',
    description: null,
    price: 0,
    currency: 'VND',
    duration_days: 30,
    max_job_posts: 0,
    max_candidate_searches: 0,
    max_ai_features: 10,
    plan_audience: 'candidate',
    is_free: true,
    display_order: 1,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'plan-cand-pro',
    name: 'Gói Ứng Viên Nâng Cao',
    description: null,
    price: 99000,
    currency: 'VND',
    duration_days: 30,
    max_job_posts: 0,
    max_candidate_searches: 0,
    max_ai_features: 50,
    plan_audience: 'candidate',
    is_free: false,
    display_order: 2,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

const companyPlans: AdminPlanRead[] = [
  {
    id: 'plan-comp-starter',
    name: 'Gói Doanh Nghiệp Khởi Đầu',
    description: null,
    price: 500000,
    currency: 'VND',
    duration_days: 30,
    max_job_posts: 5,
    max_candidate_searches: 20,
    max_ai_features: 15,
    plan_audience: 'company',
    is_free: false,
    display_order: 1,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'plan-comp-pro',
    name: 'Gói Doanh Nghiệp Chuyên Nghiệp',
    description: null,
    price: 1500000,
    currency: 'VND',
    duration_days: 30,
    max_job_posts: 20,
    max_candidate_searches: 100,
    max_ai_features: 50,
    plan_audience: 'company',
    is_free: false,
    display_order: 2,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

describe('resolveSubscriptionTargetAudience', () => {
  it('resolves candidate_personal scope to candidate (Priority 1)', () => {
    expect(
      resolveSubscriptionTargetAudience({
        scope: 'candidate_personal',
        user_role: 'recruiter',
        plan_audience: 'company',
      }),
    ).toBe('candidate')
  })

  it('resolves company_recruiting scope to company (Priority 1)', () => {
    expect(
      resolveSubscriptionTargetAudience({
        scope: 'company_recruiting',
        user_role: 'candidate',
        plan_audience: 'candidate',
      }),
    ).toBe('company')
  })

  it('resolves legacy_recruiter_personal scope to company (Priority 1)', () => {
    expect(
      resolveSubscriptionTargetAudience({
        scope: 'legacy_recruiter_personal',
      }),
    ).toBe('company')
  })

  it('resolves user_role candidate to candidate when scope is null (Priority 2)', () => {
    expect(
      resolveSubscriptionTargetAudience({
        scope: null,
        user_role: 'candidate',
        plan_audience: 'company',
      }),
    ).toBe('candidate')
  })

  it('resolves user_role recruiter to company when scope is null (Priority 2)', () => {
    expect(
      resolveSubscriptionTargetAudience({
        scope: null,
        user_role: 'recruiter',
        plan_audience: 'candidate',
      }),
    ).toBe('company')
  })

  it('resolves current plan_audience candidate when scope and user_role are null (Priority 3)', () => {
    expect(
      resolveSubscriptionTargetAudience({
        scope: null,
        user_role: null,
        plan_audience: 'candidate',
      }),
    ).toBe('candidate')
  })

  it('resolves current plan_audience company when scope and user_role are null (Priority 3)', () => {
    expect(
      resolveSubscriptionTargetAudience({
        scope: null,
        user_role: null,
        plan_audience: 'company',
      }),
    ).toBe('company')
  })

  it('defaults to company when all fields are null or unknown (Priority 4)', () => {
    expect(
      resolveSubscriptionTargetAudience({
        scope: null,
        user_role: null,
        plan_audience: null,
      }),
    ).toBe('company')
  })
})

describe('AdminSubscriptionChangePlanModal', () => {
  const onClose = vi.fn()
  const onSuccess = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('filters plans by candidate audience for candidate subscriptions and excludes current plan', async () => {
    vi.mocked(getAdminPlans).mockResolvedValue({
      items: [...candidatePlans, ...companyPlans],
      total: candidatePlans.length + companyPlans.length,
      skip: 0,
      limit: 100,
    })

    render(
      <AdminSubscriptionChangePlanModal
        subscription={mockCandidateSub}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    )

    await waitFor(() => {
      expect(getAdminPlans).toHaveBeenCalledWith({
        skip: 0,
        limit: 100,
        audience: 'candidate',
      })
    })

    // Wait for plans to load
    await waitFor(() => {
      expect(
        screen.getByRole('option', { name: /Gói Ứng Viên Nâng Cao/i }),
      ).toBeInTheDocument()
    })

    // Current plan (plan-cand-basic) should NOT be in the options
    expect(
      screen.queryByRole('option', { name: /Gói Ứng Viên Cơ Bản/i }),
    ).not.toBeInTheDocument()

    // Company plans should NOT be in the options
    expect(
      screen.queryByRole('option', { name: /Gói Doanh Nghiệp/i }),
    ).not.toBeInTheDocument()
  })

  it('filters plans by company audience for company subscriptions', async () => {
    vi.mocked(getAdminPlans).mockResolvedValue({
      items: [...candidatePlans, ...companyPlans],
      total: candidatePlans.length + companyPlans.length,
      skip: 0,
      limit: 100,
    })

    render(
      <AdminSubscriptionChangePlanModal
        subscription={mockCompanySub}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    )

    await waitFor(() => {
      expect(getAdminPlans).toHaveBeenCalledWith({
        skip: 0,
        limit: 100,
        audience: 'company',
      })
    })

    await waitFor(() => {
      expect(
        screen.getByRole('option', { name: /Gói Doanh Nghiệp Chuyên Nghiệp/i }),
      ).toBeInTheDocument()
    })

    // Current company plan excluded
    expect(
      screen.queryByRole('option', { name: /Gói Doanh Nghiệp Khởi Đầu/i }),
    ).not.toBeInTheDocument()

    // Candidate plans excluded
    expect(
      screen.queryByRole('option', { name: /Gói Ứng Viên/i }),
    ).not.toBeInTheDocument()
  })

  it('resolves legacy_recruiter_personal scope to company audience', async () => {
    const legacySub: AdminSubscriptionListItem = {
      ...mockCompanySub,
      scope: 'legacy_recruiter_personal',
    }

    vi.mocked(getAdminPlans).mockResolvedValue({
      items: companyPlans,
      total: companyPlans.length,
      skip: 0,
      limit: 100,
    })

    render(
      <AdminSubscriptionChangePlanModal
        subscription={legacySub}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    )

    await waitFor(() => {
      expect(getAdminPlans).toHaveBeenCalledWith({
        skip: 0,
        limit: 100,
        audience: 'company',
      })
    })
  })

  it('allows remediation for corrupted candidate subscription with company plan', async () => {
    // Corrupted state: scope is candidate_personal, but current plan is a company plan
    const corruptedSub: AdminSubscriptionListItem = {
      ...mockCandidateSub,
      plan_id: 'plan-comp-starter',
      plan_name: 'Gói Chuyên Nghiệp',
      plan_audience: 'company',
      scope: 'candidate_personal',
    }

    vi.mocked(getAdminPlans).mockResolvedValue({
      items: candidatePlans,
      total: candidatePlans.length,
      skip: 0,
      limit: 100,
    })

    render(
      <AdminSubscriptionChangePlanModal
        subscription={corruptedSub}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    )

    // Expected audience is 'candidate' because scope is 'candidate_personal'
    await waitFor(() => {
      expect(getAdminPlans).toHaveBeenCalledWith({
        skip: 0,
        limit: 100,
        audience: 'candidate',
      })
    })

    // Displays the corrupted current plan name accurately
    expect(screen.getByText('Gói Chuyên Nghiệp')).toBeInTheDocument()

    // Displays candidate plans to allow remediation
    await waitFor(() => {
      expect(
        screen.getByRole('option', { name: /Gói Ứng Viên Cơ Bản/i }),
      ).toBeInTheDocument()
      expect(
        screen.getByRole('option', { name: /Gói Ứng Viên Nâng Cao/i }),
      ).toBeInTheDocument()
    })
  })

  it('displays empty state message and disables submit when no alternative plans are available', async () => {
    // Only current plan exists in API response
    vi.mocked(getAdminPlans).mockResolvedValue({
      items: [candidatePlans[0]],
      total: 1,
      skip: 0,
      limit: 100,
    })

    render(
      <AdminSubscriptionChangePlanModal
        subscription={mockCandidateSub}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    )

    await waitFor(() => {
      expect(
        screen.getByText('Không có gói dịch vụ nào khác khả dụng cho đối tượng này.'),
      ).toBeInTheDocument()
    })

    // Select should be disabled with empty-state placeholder
    const select = screen.getByRole('combobox', { name: /Gói mới/i })
    expect(select).toBeDisabled()
    expect(
      screen.getByRole('option', {
        name: 'Không có gói dịch vụ nào khác khả dụng',
      }),
    ).toBeInTheDocument()

    // Confirm button should be disabled
    const submitBtn = screen.getByRole('button', { name: /Xác nhận đổi gói/i })
    expect(submitBtn).toBeDisabled()
  })

  it('submits plan change with valid target plan and reason', async () => {
    vi.mocked(getAdminPlans).mockResolvedValue({
      items: candidatePlans,
      total: candidatePlans.length,
      skip: 0,
      limit: 100,
    })
    vi.mocked(changeAdminSubscriptionPlan).mockResolvedValue({} as any)

    render(
      <AdminSubscriptionChangePlanModal
        subscription={mockCandidateSub}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    )

    await waitFor(() => {
      expect(
        screen.getByRole('option', { name: /Gói Ứng Viên Nâng Cao/i }),
      ).toBeInTheDocument()
    })

    // Select target plan
    const select = screen.getByRole('combobox', { name: /Gói mới/i })
    fireEvent.change(select, { target: { value: 'plan-cand-pro' } })

    // Enter reason
    const reasonInput = screen.getByLabelText(/Lý do đổi gói/i)
    fireEvent.change(reasonInput, {
      target: { value: 'Nâng cấp gói cho ứng viên theo yêu cầu' },
    })

    // Click submit
    const submitBtn = screen.getByRole('button', { name: /Xác nhận đổi gói/i })
    expect(submitBtn).not.toBeDisabled()
    fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(changeAdminSubscriptionPlan).toHaveBeenCalledWith('sub-cand-1', {
        target_plan_id: 'plan-cand-pro',
        reason: 'Nâng cấp gói cho ứng viên theo yêu cầu',
      })
      expect(onSuccess).toHaveBeenCalled()
      expect(onClose).toHaveBeenCalled()
    })
  })
})
