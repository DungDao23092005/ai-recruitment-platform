import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { RecruiterBillingPage } from './RecruiterBillingPage'
import { useWorkspace } from '@/contexts/WorkspaceContext'
import {
  getCompanySubscription,
  getCompanySubscriptionHistory,
  getCompanyUsages,
} from '@/api/subscriptions'
import { getWorkspaceMembers } from '@/api/workspaces'
import type { Workspace } from '@/types/workspace'
import type { Subscription } from '@/types/subscription'
import type { PaymentOrderRead } from '@/types/payment'

vi.mock('@/contexts/WorkspaceContext', () => ({
  useWorkspace: vi.fn(),
  useOptionalWorkspace: vi.fn(),
}))

vi.mock('@/api/subscriptions', async () => {
  const actual = await import('@/api/subscriptions')
  return {
    ...actual,
    getCompanySubscription: vi.fn(),
    getCompanySubscriptionHistory: vi.fn(),
    getCompanyUsages: vi.fn(),
  }
})

vi.mock('@/api/workspaces', async () => {
  const actual = await import('@/api/workspaces')
  return {
    ...actual,
    getWorkspaceMembers: vi.fn(),
  }
})

const mockedUseWorkspace = vi.mocked(useWorkspace)
const mockedGetCompanySubscription = vi.mocked(getCompanySubscription)
const mockedGetCompanyHistory = vi.mocked(getCompanySubscriptionHistory)
const mockedGetCompanyUsages = vi.mocked(getCompanyUsages)
const mockedGetWorkspaceMembers = vi.mocked(getWorkspaceMembers)

const subscription: Subscription = {
  id: 'sub-1',
  user_id: 'user-1',
  plan_id: 'plan-1',
  status: 'active',
  started_at: '2026-11-01T00:00:00Z',
  expires_at: '2026-12-01T00:00:00Z',
  max_job_posts: 10,
  max_candidate_searches: 20,
  max_ai_features: 5,
  job_posts_used: 3,
  candidate_searches_used: 4,
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

const usageResponse = {
  items: [
    {
      id: 'usage-1',
      subscription_id: 'sub-1',
      user_id: 'user-1',
      user_email: 'recruiter@example.com',
      user_full_name: 'Nguyễn Văn A',
      feature_type: 'job_post' as const,
      feature_label: 'Tin tuyển dụng',
      amount: 1,
      status: 'completed' as const,
      status_label: 'Hoàn tất',
      reference_id: null,
      created_at: '2026-11-10T03:00:00Z',
      finalized_at: '2026-11-10T03:00:01Z',
    },
  ],
  total: 1,
  page: 1,
  page_size: 10,
  total_pages: 1,
}

const paymentOrder: PaymentOrderRead = {
  id: 'order-1',
  user_id: 'user-1',
  plan_id: 'plan-1',
  subscription_id: 'sub-1',
  company_id: 'company-1',
  scope: 'company_recruiting',
  amount: 5000000,
  currency: 'VND',
  provider: 'vnpay',
  internal_order_id: 'ORDER-123',
  provider_order_id: null,
  provider_request_id: null,
  status: 'paid',
  paid_at: '2026-11-01T00:00:00Z',
  expired_at: null,
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
}

function workspace(role: 'admin' | 'recruiter'): Workspace {
  return {
    company_id: 'company-1',
    company_name: 'Công ty Mẫu',
    company_slug: 'cong-ty-mau',
    membership_id: 'membership-1',
    role,
    is_platform_admin: false,
  }
}

function mockWorkspace(role: 'admin' | 'recruiter' | null) {
  const selectedWorkspace = role ? workspace(role) : null
  const value = {
    workspaces: selectedWorkspace ? [selectedWorkspace] : [],
    selectedCompanyId: selectedWorkspace ? selectedWorkspace.company_id : null,
    selectedWorkspace,
    isLoading: false,
    error: null,
    selectWorkspace: vi.fn(),
    refreshWorkspaces: vi.fn(),
  }
  mockedUseWorkspace.mockReturnValue(value as ReturnType<typeof useWorkspace>)
  return value
}

function renderPage() {
  return render(
    <MemoryRouter>
      <RecruiterBillingPage />
    </MemoryRouter>,
  )
}

describe('RecruiterBillingPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockWorkspace('admin')
    mockedGetCompanySubscription.mockResolvedValue(subscription)
    mockedGetCompanyUsages.mockResolvedValue(usageResponse)
    mockedGetCompanyHistory.mockResolvedValue([paymentOrder])
    mockedGetWorkspaceMembers.mockResolvedValue([
      {
        membership_id: 'membership-1',
        user_id: 'user-1',
        email: 'recruiter@example.com',
        full_name: 'Nguyễn Văn A',
        role: 'admin',
        status: 'active',
        joined_at: null,
        revoked_at: null,
      },
    ])
  })

  it('renders plan, usage history and payment history for a Workspace Admin', async () => {
    renderPage()

    expect(await screen.findByText('Gói Doanh nghiệp')).toBeInTheDocument()
    expect(screen.getByText('Đang hoạt động')).toBeInTheDocument()
    expect(screen.getAllByText('Nguyễn Văn A').length).toBeGreaterThan(0)
    expect(screen.getByText('ORDER-123')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /Gia hạn hoặc thay đổi gói/ }),
    ).toHaveAttribute('href', '/plans?audience=company')
  })

  it('keeps Workspace Recruiters read-only', async () => {
    mockWorkspace('recruiter')

    renderPage()

    expect(
      await screen.findByText(
        'Chỉ Quản trị viên công ty (Workspace Admin) mới có quyền mua hoặc thay đổi gói dịch vụ.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('link', { name: /Gia hạn hoặc thay đổi gói/ }),
    ).not.toBeInTheDocument()
    expect(screen.getByText('ORDER-123')).toBeInTheDocument()
  })

  it('forwards the feature filter and resets pagination', async () => {
    renderPage()

    await screen.findByText('Gói Doanh nghiệp')
    fireEvent.change(screen.getByLabelText('Tính năng'), {
      target: { value: 'job_post' },
    })

    await waitFor(() => {
      expect(mockedGetCompanyUsages).toHaveBeenLastCalledWith(
        expect.objectContaining({
          page: 1,
          feature_type: 'job_post',
          page_size: 10,
        }),
      )
    })
  })

  it('paginates usage history', async () => {
    mockedGetCompanyUsages.mockResolvedValue({
      ...usageResponse,
      total: 25,
      total_pages: 3,
    })

    renderPage()

    await screen.findByText('Gói Doanh nghiệp')
    fireEvent.click(screen.getByRole('button', { name: 'Sau' }))

    await waitFor(() => {
      expect(mockedGetCompanyUsages).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2 }),
      )
    })
  })

  it('shows an error state when usage history fails', async () => {
    mockedGetCompanyUsages.mockRejectedValueOnce(new Error('Usage failed'))

    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Usage failed')
    })
  })

  it('shows the empty usage state', async () => {
    mockedGetCompanyUsages.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 10,
      total_pages: 0,
    })

    renderPage()

    expect(
      await screen.findByText('Chưa có lịch sử sử dụng'),
    ).toBeInTheDocument()
  })

  it('shows a no-workspace state without calling company APIs', () => {
    mockWorkspace(null)

    renderPage()

    expect(screen.getByText('Chưa chọn công ty')).toBeInTheDocument()
    expect(mockedGetCompanySubscription).not.toHaveBeenCalled()
    expect(mockedGetCompanyUsages).not.toHaveBeenCalled()
  })
})
