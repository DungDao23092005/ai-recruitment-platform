import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { vi } from 'vitest'
import { AdminSubscriptionsPage } from '@/features/admin/pages/AdminSubscriptionsPage'
import {
  getAdminSubscriptions,
  getAdminPlans,
  getAdminSubscription,
  changeAdminSubscriptionPlan,
  revokeAdminSubscription,
} from '@/api/admin'
import type {
  AdminPlanRead,
  AdminSubscriptionDetail,
  AdminSubscriptionList,
} from '@/types/admin'

vi.mock('@/api/admin')

const mockList: AdminSubscriptionList = {
  items: [
    {
      id: 'sub-1',
      user_id: 'user-1',
      user_email: 'buyer@example.com',
      plan_id: 'plan-1',
      plan_name: 'Gói cơ bản',
      status: 'active',
      started_at: '2026-01-01T00:00:00Z',
      expires_at: '2026-02-01T00:00:00Z',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      max_job_posts: 5,
      max_candidate_searches: 10,
      max_ai_features: 3,
      job_posts_used: 1,
      candidate_searches_used: 2,
      ai_features_used: 0,
    },
  ],
  total: 1,
  skip: 0,
  limit: 10,
}

const mockPlans: AdminPlanRead[] = [
  {
    id: 'plan-2',
    name: 'Gói nâng cao',
    description: null,
    price: 299000,
    currency: 'VND',
    duration_days: 60,
    max_job_posts: 20,
    max_candidate_searches: 100,
    max_ai_features: 20,
    display_order: 2,
    is_active: true,
    created_at: '2024-01-02T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  },
]

const mockDetail: AdminSubscriptionDetail = {
  subscription: mockList.items[0],
  history: [
    {
      id: 'sub-1',
      plan_id: 'plan-1',
      status: 'active',
      started_at: '2026-01-01T00:00:00Z',
      expires_at: '2026-02-01T00:00:00Z',
    },
  ],
  audit_logs: [
    {
      id: 'audit-1',
      admin_id: 'admin-1',
      admin_email: 'admin@example.com',
      user_id: 'user-1',
      subscription_id: 'sub-1',
      action: 'change_plan',
      old_plan_id: 'plan-1',
      new_plan_id: 'plan-2',
      reason: 'Khách yêu cầu nâng cấp',
      created_at: '2026-01-05T00:00:00Z',
    },
  ],
}

describe('AdminSubscriptionsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getAdminSubscriptions).mockResolvedValue(mockList)
    vi.mocked(getAdminPlans).mockResolvedValue(mockPlans)
    vi.mocked(getAdminSubscription).mockResolvedValue(mockDetail)
    vi.mocked(changeAdminSubscriptionPlan).mockResolvedValue(mockList.items[0])
    vi.mocked(revokeAdminSubscription).mockResolvedValue({
      ...mockList.items[0],
      status: 'cancelled',
    })
  })

  it('renders header and subscription rows', async () => {
    render(<AdminSubscriptionsPage />)

    expect(screen.getByText('Thuê bao người dùng')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('buyer@example.com')).toBeInTheDocument()
    })
    expect(screen.getByText('Gói cơ bản')).toBeInTheDocument()
    expect(screen.getAllByText('Đang hoạt động').length).toBeGreaterThan(0)
  })

  it('searches by email', async () => {
    render(<AdminSubscriptionsPage />)
    await waitFor(() => {
      expect(screen.getByText('buyer@example.com')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('Tìm theo email người dùng'), {
      target: { value: 'buyer@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /tìm kiếm/i }))

    await waitFor(() => {
      expect(getAdminSubscriptions).toHaveBeenCalledWith(
        expect.objectContaining({ search: 'buyer@example.com' }),
      )
    })
  })

  it('renders API error safely', async () => {
    vi.mocked(getAdminSubscriptions).mockRejectedValueOnce(new Error('boom'))
    render(<AdminSubscriptionsPage />)

    await waitFor(() => {
      expect(
        screen.getByText('Không thể kết nối tới máy chủ. Vui lòng kiểm tra kết nối và thử lại.'),
      ).toBeInTheDocument()
    })
  })

  it('opens change-plan modal and submits a reason', async () => {
    render(<AdminSubscriptionsPage />)
    await waitFor(() => {
      expect(screen.getByText('buyer@example.com')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: /đổi gói cho buyer@example.com/i }),
    )

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Đổi gói thuê bao')).toBeInTheDocument()

    await waitFor(() => {
      expect(
        within(dialog).getByRole('option', { name: /gói nâng cao/i }),
      ).toBeInTheDocument()
    })

    // Reason is required (>= 5 chars) before submitting.
    fireEvent.change(within(dialog).getByLabelText(/gói mới/i), {
      target: { value: 'plan-2' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: /xác nhận đổi gói/i }))
    expect(
      await within(dialog).findByText(/lý do phải có ít nhất 5 ký tự/i),
    ).toBeInTheDocument()
    expect(changeAdminSubscriptionPlan).not.toHaveBeenCalled()

    fireEvent.change(within(dialog).getByLabelText(/lý do đổi gói/i), {
      target: { value: 'Nâng cấp theo yêu cầu khách' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: /xác nhận đổi gói/i }))

    await waitFor(() => {
      expect(changeAdminSubscriptionPlan).toHaveBeenCalledWith('sub-1', {
        target_plan_id: 'plan-2',
        reason: 'Nâng cấp theo yêu cầu khách',
      })
    })
  })

  it('opens revoke modal and requires a valid reason', async () => {
    render(<AdminSubscriptionsPage />)
    await waitFor(() => {
      expect(screen.getByText('buyer@example.com')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: /thu hồi gói của buyer@example.com/i }),
    )
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Thu hồi gói thuê bao')).toBeInTheDocument()

    fireEvent.change(within(dialog).getByLabelText(/lý do thu hồi/i), {
      target: { value: 'abc' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: /xác nhận thu hồi/i }))
    expect(
      await within(dialog).findByText(/lý do phải có ít nhất 5 ký tự/i),
    ).toBeInTheDocument()
    expect(revokeAdminSubscription).not.toHaveBeenCalled()
  })

  it('loads detail with audit trail', async () => {
    render(<AdminSubscriptionsPage />)
    await waitFor(() => {
      expect(screen.getByText('buyer@example.com')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', {
        name: /xem chi tiết thuê bao buyer@example.com/i,
      }),
    )

    await waitFor(() => {
      expect(getAdminSubscription).toHaveBeenCalledWith('sub-1')
    })
    const dialog = await screen.findByRole('dialog')
    expect(
      await within(dialog).findByText('Lịch sử thay đổi (audit trail)'),
    ).toBeInTheDocument()
    expect(
      within(dialog).getByText('Khách yêu cầu nâng cấp'),
    ).toBeInTheDocument()

    // Quota snapshot + usage (P2) is surfaced from the subscription object.
    expect(within(dialog).getByText('Tin tuyển dụng')).toBeInTheDocument()
    expect(within(dialog).getByText('1 / 5')).toBeInTheDocument()
    expect(within(dialog).getByText('Tìm kiếm ứng viên')).toBeInTheDocument()
    expect(within(dialog).getByText('2 / 10')).toBeInTheDocument()
    expect(within(dialog).getByText('Tính năng AI')).toBeInTheDocument()
    expect(within(dialog).getByText('0 / 3')).toBeInTheDocument()
  })
})
