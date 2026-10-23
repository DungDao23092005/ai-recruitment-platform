import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AdminAuditPage } from './AdminAuditPage'
import * as adminApi from '@/api/admin'
import type { AdminAuditLog, AdminAuditLogList } from '@/types/admin'

vi.mock('@/api/admin', () => ({
  getAdminAuditLogs: vi.fn(),
}))

const mockedGetAdminAuditLogs = vi.mocked(adminApi.getAdminAuditLogs)

function makeLog(overrides: Partial<AdminAuditLog> = {}): AdminAuditLog {
  return {
    id: 'audit-1',
    admin_id: 'admin-1',
    admin_email: 'admin@example.com',
    target_user_id: 'user-1',
    target_user_email: 'candidate@example.com',
    action: 'user_lock',
    reason: 'Vi phạm điều khoản',
    details: { was_active: true, target_role: 'candidate' },
    created_at: '2026-10-20T10:30:00Z',
    ...overrides,
  }
}

function makeList(
  items: AdminAuditLog[] = [makeLog()],
  total = items.length,
): AdminAuditLogList {
  return { items, total, skip: 0, limit: 20 }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminAuditPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedGetAdminAuditLogs.mockResolvedValue(makeList())
})

describe('AdminAuditPage', () => {
  it('fetches the newest page with the default filters on mount', async () => {
    renderPage()

    await waitFor(() => {
      expect(mockedGetAdminAuditLogs).toHaveBeenCalledWith({
        skip: 0,
        limit: 20,
        search: undefined,
        action: undefined,
        created_from: undefined,
        created_to: undefined,
      })
    })
  })

  it('renders action, actor, target and reason with semantic labels', async () => {
    mockedGetAdminAuditLogs.mockResolvedValue(
      makeList([
        makeLog(),
        makeLog({
          id: 'audit-2',
          action: 'user_unlock',
          reason: null,
          target_user_email: 'recruiter@example.com',
        }),
        makeLog({ id: 'audit-3', action: 'user_delete' }),
      ]),
    )

    renderPage()

    const table = await screen.findByRole('table', {
      name: 'Bảng nhật ký quản trị',
    })
    expect(within(table).getByText('Khóa tài khoản')).toBeInTheDocument()
    expect(within(table).getByText('Mở khóa tài khoản')).toBeInTheDocument()
    expect(within(table).getByText('Xóa tài khoản')).toBeInTheDocument()
    expect(
      within(table).getAllByText('admin@example.com').length,
    ).toBeGreaterThan(0)
    expect(
      within(table).getAllByText('candidate@example.com').length,
    ).toBeGreaterThan(0)
    expect(
      within(table).getAllByText('Vi phạm điều khoản').length,
    ).toBeGreaterThan(0)
    expect(within(table).getByText('Không có lý do')).toBeInTheDocument()
  })

  it('shows the initial empty state', async () => {
    mockedGetAdminAuditLogs.mockResolvedValue(makeList([], 0))

    renderPage()

    expect(await screen.findByText('Chưa có bản ghi nào')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Các thao tác khóa, mở khóa hoặc xóa tài khoản sẽ xuất hiện tại đây.',
      ),
    ).toBeInTheDocument()
  })

  it('shows a filtered empty state and can clear the filters', async () => {
    mockedGetAdminAuditLogs.mockResolvedValue(makeList([], 0))

    renderPage()
    await waitFor(() => {
      expect(mockedGetAdminAuditLogs).toHaveBeenCalledTimes(1)
    })

    fireEvent.change(screen.getByLabelText('Tìm kiếm'), {
      target: { value: 'nothing' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Tra cứu' }))

    expect(
      await screen.findByText('Không có bản ghi phù hợp'),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Xóa bộ lọc' }))

    await waitFor(() => {
      expect(screen.getByText('Chưa có bản ghi nào')).toBeInTheDocument()
    })
    expect(mockedGetAdminAuditLogs).toHaveBeenLastCalledWith({
      skip: 0,
      limit: 20,
      search: undefined,
      action: undefined,
      created_from: undefined,
      created_to: undefined,
    })
  })

  it('shows an error state with retry', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Server error' } },
    })
    mockedGetAdminAuditLogs
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce(makeList())

    renderPage()

    expect(await screen.findByText('Server error')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(screen.getByText('candidate@example.com')).toBeInTheDocument()
    })
  })

  it('applies search, action and date filters and resets to page one', async () => {
    mockedGetAdminAuditLogs.mockResolvedValue(makeList([], 25))

    renderPage()
    await waitFor(() => {
      expect(mockedGetAdminAuditLogs).toHaveBeenCalledTimes(1)
    })

    fireEvent.change(screen.getByLabelText('Tìm kiếm'), {
      target: { value: '  admin@example.com  ' },
    })
    fireEvent.change(screen.getByLabelText('Hành động'), {
      target: { value: 'user_delete' },
    })
    fireEvent.change(screen.getByLabelText('Từ ngày'), {
      target: { value: '2026-10-01' },
    })
    fireEvent.change(screen.getByLabelText('Đến ngày'), {
      target: { value: '2026-10-31' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Tra cứu' }))

    const expectedFrom = new Date('2026-10-01T00:00:00').toISOString()
    const expectedTo = new Date('2026-10-31T23:59:59.999').toISOString()

    await waitFor(() => {
      expect(mockedGetAdminAuditLogs).toHaveBeenLastCalledWith({
        skip: 0,
        limit: 20,
        search: 'admin@example.com',
        action: 'user_delete',
        created_from: expectedFrom,
        created_to: expectedTo,
      })
    })
    expect(screen.getByText('25 bản ghi phù hợp')).toBeInTheDocument()
  })

  it('rejects a reversed date range without calling the API', async () => {
    renderPage()
    await waitFor(() => {
      expect(mockedGetAdminAuditLogs).toHaveBeenCalledTimes(1)
    })

    fireEvent.change(screen.getByLabelText('Từ ngày'), {
      target: { value: '2026-10-31' },
    })
    fireEvent.change(screen.getByLabelText('Đến ngày'), {
      target: { value: '2026-10-01' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Tra cứu' }))

    expect(
      screen.getByText('Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.'),
    ).toBeInTheDocument()
    expect(mockedGetAdminAuditLogs).toHaveBeenCalledTimes(1)
  })

  it('paginates using the real total', async () => {
    mockedGetAdminAuditLogs.mockResolvedValue(makeList([makeLog()], 25))

    renderPage()

    expect(await screen.findByText('Trang 1 / 2')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Trang sau' }))

    await waitFor(() => {
      expect(mockedGetAdminAuditLogs).toHaveBeenLastCalledWith({
        skip: 20,
        limit: 20,
        search: undefined,
        action: undefined,
        created_from: undefined,
        created_to: undefined,
      })
    })
    expect(screen.getByText('Trang 2 / 2')).toBeInTheDocument()
  })

  it('opens an accessible read-only detail modal', async () => {
    renderPage()

    await screen.findByText('candidate@example.com')
    fireEvent.click(
      screen.getByRole('button', { name: 'Xem chi tiết bản ghi audit-1' }),
    )

    const dialog = screen.getByRole('dialog', {
      name: 'Chi tiết bản ghi nhật ký quản trị',
    })
    expect(dialog).toBeInTheDocument()
    expect(
      within(dialog).getByText(/Bản ghi chỉ đọc/),
    ).toBeInTheDocument()
    expect(
      within(dialog).getAllByText('Khóa tài khoản').length,
    ).toBeGreaterThan(0)
    expect(within(dialog).getByText('Vi phạm điều khoản')).toBeInTheDocument()
    expect(
      within(dialog).getByLabelText('Chi tiết kỹ thuật'),
    ).toHaveTextContent('"was_active": true')
    expect(within(dialog).getByText('admin@example.com')).toBeInTheDocument()

    const closeButtons = within(dialog).getAllByRole('button', { name: 'Đóng' })
    fireEvent.click(closeButtons[closeButtons.length - 1])
    expect(
      screen.queryByRole('dialog', {
        name: 'Chi tiết bản ghi nhật ký quản trị',
      }),
    ).not.toBeInTheDocument()
  })

  it('shows a no-details fallback in the modal', async () => {
    mockedGetAdminAuditLogs.mockResolvedValue(
      makeList([makeLog({ details: null, reason: null })]),
    )

    renderPage()

    await screen.findByText('candidate@example.com')
    fireEvent.click(
      screen.getByRole('button', { name: 'Xem chi tiết bản ghi audit-1' }),
    )

    const dialog = screen.getByRole('dialog', {
      name: 'Chi tiết bản ghi nhật ký quản trị',
    })
    expect(
      within(dialog).getByText('Không có lý do được ghi nhận.'),
    ).toBeInTheDocument()
    expect(
      within(dialog).getByText('Không có dữ liệu bổ sung.'),
    ).toBeInTheDocument()
  })
})
