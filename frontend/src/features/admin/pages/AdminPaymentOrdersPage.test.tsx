import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { AdminPaymentOrdersPage } from '@/features/admin/pages/AdminPaymentOrdersPage'
import { getAdminPaymentOrders } from '@/api/admin'
import type {
  AdminPaymentOrder,
  AdminPaymentOrderList,
} from '@/types/admin'

vi.mock('@/api/admin')

function makeOrder(overrides: Partial<AdminPaymentOrder> = {}): AdminPaymentOrder {
  return {
    id: 'order-1',
    user_id: 'user-1',
    user_email: 'buyer@example.com',
    user_full_name: 'Nguyễn Văn A',
    company_id: null,
    company_name: null,
    plan_id: 'plan-1',
    plan_name: 'Gói ứng viên',
    plan_audience: 'candidate',
    subscription_id: null,
    scope: 'candidate_personal',
    amount: 199000,
    currency: 'VND',
    provider: 'vnpay',
    internal_order_id: 'ORD-20261113-001',
    status: 'paid',
    paid_at: '2026-11-13T03:00:00Z',
    expired_at: null,
    created_at: '2026-11-13T02:55:00Z',
    ...overrides,
  }
}

function makeResponse(
  items: AdminPaymentOrder[],
  total = items.length,
): AdminPaymentOrderList {
  return { items, total, skip: 0, limit: 10 }
}

describe('AdminPaymentOrdersPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the page header and required order columns', async () => {
    vi.mocked(getAdminPaymentOrders).mockResolvedValue(
      makeResponse([makeOrder()]),
    )

    render(<AdminPaymentOrdersPage />)

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Đơn thanh toán', level: 1 }),
      ).toBeInTheDocument()
      expect(screen.getByText('ORD-20261113-001')).toBeInTheDocument()
    })

    for (const column of [
      'Mã đơn hàng',
      'Người mua',
      'Gói dịch vụ',
      'Phạm vi',
      'Số tiền',
      'Cổng thanh toán',
      'Trạng thái',
      'Ngày tạo',
      'Ngày thanh toán',
    ]) {
      expect(screen.getByRole('columnheader', { name: column })).toBeInTheDocument()
    }
    expect(screen.getByText('Nguyễn Văn A')).toBeInTheDocument()
    expect(screen.getByText('buyer@example.com')).toBeInTheDocument()
    expect(screen.getByText(/199\.000/)).toBeInTheDocument()
    expect(screen.getByText('VNPAY')).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(table).getByText('Đã thanh toán')).toBeInTheDocument()
    expect(within(table).getAllByText('Ứng viên')).toHaveLength(2)
  })

  it('submits a trimmed search and resets to the first page', async () => {
    vi.mocked(getAdminPaymentOrders).mockResolvedValue(
      makeResponse([makeOrder()], 25),
    )

    render(<AdminPaymentOrdersPage />)

    await waitFor(() => {
      expect(screen.getByText('Trang 1 / 3')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Trang sau' }))
    await waitFor(() => {
      expect(getAdminPaymentOrders).toHaveBeenLastCalledWith(
        expect.objectContaining({ skip: 10 }),
      )
    })

    fireEvent.change(screen.getByLabelText('Tìm theo mã đơn hoặc email'), {
      target: { value: '  buyer@example.com  ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Tìm kiếm' }))

    await waitFor(() => {
      expect(getAdminPaymentOrders).toHaveBeenLastCalledWith(
        expect.objectContaining({ skip: 0, search: 'buyer@example.com' }),
      )
    })
  })

  it('sends status and scope filters', async () => {
    vi.mocked(getAdminPaymentOrders).mockResolvedValue(
      makeResponse([makeOrder()]),
    )

    render(<AdminPaymentOrdersPage />)

    await waitFor(() => {
      expect(getAdminPaymentOrders).toHaveBeenCalled()
    })

    fireEvent.change(screen.getByLabelText('Lọc theo trạng thái'), {
      target: { value: 'paid' },
    })
    await waitFor(() => {
      expect(getAdminPaymentOrders).toHaveBeenLastCalledWith(
        expect.objectContaining({ skip: 0, status: 'paid' }),
      )
    })

    fireEvent.change(screen.getByLabelText('Lọc theo phạm vi'), {
      target: { value: 'company_recruiting' },
    })
    await waitFor(() => {
      expect(getAdminPaymentOrders).toHaveBeenLastCalledWith(
        expect.objectContaining({
          skip: 0,
          status: 'paid',
          scope: 'company_recruiting',
        }),
      )
    })
  })

  it('renders the empty state', async () => {
    vi.mocked(getAdminPaymentOrders).mockResolvedValue(makeResponse([]))

    render(<AdminPaymentOrdersPage />)

    await waitFor(() => {
      expect(
        screen.getByText('Không tìm thấy đơn thanh toán'),
      ).toBeInTheDocument()
      expect(
        screen.getByText('Chưa có đơn thanh toán nào trên nền tảng.'),
      ).toBeInTheDocument()
    })
  })

  it('renders an error banner when the request fails', async () => {
    vi.mocked(getAdminPaymentOrders).mockRejectedValue(new Error('boom'))

    render(<AdminPaymentOrdersPage />)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    expect(
      within(screen.getByRole('alert')).getByText(/không thể kết nối/i),
    ).toBeInTheDocument()
  })
})
