import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { AdminUsersPage } from './AdminUsersPage'
import * as adminApi from '@/api/admin'
import type { AdminUser, AdminUserList } from '@/types/admin'

function makeUser(overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    id: 'user-1',
    email: 'candidate@example.com',
    role: 'candidate',
    is_active: true,
    is_deleted: false,
    created_at: '2026-01-10T00:00:00Z',
    updated_at: '2026-01-10T00:00:00Z',
    ...overrides,
  }
}

const candidate = makeUser()
const recruiter = makeUser({
  id: 'user-2',
  email: 'recruiter@example.com',
  role: 'recruiter',
})
const inactive = makeUser({
  id: 'user-3',
  email: 'inactive@example.com',
  role: 'admin',
  is_active: false,
  is_deleted: false,
})
const deleted = makeUser({
  id: 'user-4',
  email: 'deleted@example.com',
  role: 'recruiter',
  is_active: true,
  is_deleted: true,
})

function makeList(
  items: AdminUser[] = [candidate, recruiter, inactive, deleted],
  total = items.length,
): AdminUserList {
  return { items, total, skip: 0, limit: 10 }
}

vi.mock('@/api/admin', () => ({
  getAdminStats: vi.fn(),
  getSystemHealth: vi.fn(),
  getAdminUsers: vi.fn(),
  getAdminUserById: vi.fn(),
  deactivateAdminUser: vi.fn(),
  activateAdminUser: vi.fn(),
}))

const mockedGetAdminUsers = vi.mocked(adminApi.getAdminUsers)
const mockedDeactivateAdminUser = vi.mocked(adminApi.deactivateAdminUser)
const mockedActivateAdminUser = vi.mocked(adminApi.activateAdminUser)

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminUsersPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedGetAdminUsers.mockResolvedValue(makeList())
})

describe('AdminUsersPage', () => {
  it('fetches users on mount with default pagination', async () => {
    renderPage()

    await waitFor(() => {
      expect(mockedGetAdminUsers).toHaveBeenCalledWith({
        skip: 0,
        limit: 10,
        search: undefined,
        role: undefined,
      })
    })
  })

  it('renders users with role and status badges', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('candidate@example.com')).toBeInTheDocument()
      expect(screen.getByText('recruiter@example.com')).toBeInTheDocument()
    })
    const table = screen.getByRole('table')
    expect(within(table).getAllByText('Ứng viên').length).toBeGreaterThan(0)
    expect(within(table).getAllByText('Nhà tuyển dụng').length).toBeGreaterThan(0)
    expect(within(table).getAllByText('Quản trị viên').length).toBeGreaterThan(0)
    // candidate, recruiter, deleted = 3 active; inactive = 1 locked
    expect(within(table).getAllByText('Đang hoạt động')).toHaveLength(3)
    expect(within(table).getByText('Đã khóa')).toBeInTheDocument()
  })

  it('renders the empty state when no users match', async () => {
    mockedGetAdminUsers.mockResolvedValue(makeList([], 0))

    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText('Không tìm thấy người dùng'),
      ).toBeInTheDocument()
    })
  })

  it('shows an error state with retry', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Server error' } },
    })
    mockedGetAdminUsers
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce(makeList())

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(screen.getByText('candidate@example.com')).toBeInTheDocument()
    })
  })

  it('searches by email on submit and resets to page one', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('candidate@example.com')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('Tìm theo email'), {
      target: { value: 'acme' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Tìm kiếm' }))

    await waitFor(() => {
      expect(mockedGetAdminUsers).toHaveBeenLastCalledWith({
        skip: 0,
        limit: 10,
        search: 'acme',
        role: undefined,
      })
    })
  })

  it('filters by role and reloads from page one', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('candidate@example.com')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('Lọc theo vai trò'), {
      target: { value: 'recruiter' },
    })

    await waitFor(() => {
      expect(mockedGetAdminUsers).toHaveBeenLastCalledWith({
        skip: 0,
        limit: 10,
        search: undefined,
        role: 'recruiter',
      })
    })
  })

  it('paginates to the next page with the correct skip', async () => {
    const manyUsers = Array.from({ length: 12 }, (_, index) =>
      makeUser({
        id: `user-${index}`,
        email: `user-${index}@example.com`,
      }),
    )
    mockedGetAdminUsers.mockResolvedValue(
      makeList(manyUsers.slice(0, 10), manyUsers.length),
    )

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Trang 1 / 2')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Trang sau' }))

    await waitFor(() => {
      expect(mockedGetAdminUsers).toHaveBeenLastCalledWith({
        skip: 10,
        limit: 10,
        search: undefined,
        role: undefined,
      })
    })
    expect(screen.getByText('Trang 2 / 2')).toBeInTheDocument()
  })

  it('disables the lock action for an inactive account', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('inactive@example.com')).toBeInTheDocument()
    })

    expect(
      screen.getByRole('button', { name: 'Mở khóa tài khoản inactive@example.com' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Khóa tài khoản inactive@example.com' }),
    ).not.toBeInTheDocument()
  })

  it('deactivates a user after confirmation and reloads the list', async () => {
    mockedDeactivateAdminUser.mockResolvedValue(makeUser({ is_active: false, is_deleted: false }))

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('candidate@example.com')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Khóa tài khoản candidate@example.com',
      }),
    )

    // Use within to scope queries to the deactivate dialog
    const deactivateDialog = screen.getByRole('dialog', { name: 'Khóa tài khoản người dùng' })
    expect(deactivateDialog).toBeInTheDocument()
    expect(within(deactivateDialog).getByText(/không thể đăng nhập/i)).toBeInTheDocument()
    expect(within(deactivateDialog).getByText(/vẫn được lưu giữ và không bị xóa/i)).toBeInTheDocument()

    // Fill in the reason field
    fireEvent.change(within(deactivateDialog).getByLabelText('Lý do khóa tài khoản *'), {
      target: { value: 'Test reason' },
    })
    fireEvent.click(within(deactivateDialog).getByRole('button', { name: 'Khóa tài khoản' }))

    await waitFor(() => {
      expect(mockedDeactivateAdminUser).toHaveBeenCalledWith('user-1', { reason: 'Test reason' })
    })

    await waitFor(() => {
      expect(mockedGetAdminUsers).toHaveBeenCalledTimes(2)
    })
  })

  it('shows an error inside the deactivate dialog when deactivation fails', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Server error' } },
    })
    mockedDeactivateAdminUser.mockRejectedValue(error)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('candidate@example.com')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Khóa tài khoản candidate@example.com',
      }),
    )

    const deactivateDialog = screen.getByRole('dialog', { name: 'Khóa tài khoản người dùng' })
    // Fill in the reason field
    fireEvent.change(within(deactivateDialog).getByLabelText('Lý do khóa tài khoản *'), {
      target: { value: 'Test reason' },
    })
    fireEvent.click(within(deactivateDialog).getByRole('button', { name: 'Khóa tài khoản' }))

    await waitFor(() => {
      expect(within(deactivateDialog).getByRole('alert')).toHaveTextContent('Server error')
    })
    expect(deactivateDialog).toBeInTheDocument()
  })

  it('activates a user after confirmation and reloads the list', async () => {
    mockedActivateAdminUser.mockResolvedValue(makeUser({ is_active: true }))

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('inactive@example.com')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Mở khóa tài khoản inactive@example.com',
      }),
    )

    expect(
      screen.getByRole('dialog', { name: 'Mở khóa tài khoản người dùng' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/đăng nhập lại/i),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Mở khóa tài khoản' }))

    await waitFor(() => {
      expect(mockedActivateAdminUser).toHaveBeenCalledWith('user-3')
    })

    await waitFor(() => {
      expect(mockedGetAdminUsers).toHaveBeenCalledTimes(2)
    })
  })

  it('shows an error inside the activate dialog when activation fails', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Server error' } },
    })
    mockedActivateAdminUser.mockRejectedValue(error)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('inactive@example.com')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Mở khóa tài khoản inactive@example.com',
      }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Mở khóa tài khoản' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Server error')
    })
    expect(
      screen.getByRole('dialog', { name: 'Mở khóa tài khoản người dùng' }),
    ).toBeInTheDocument()
  })

  it('closes the deactivate dialog without reloading', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('candidate@example.com')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Khóa tài khoản candidate@example.com',
      }),
    )

    const deactivateDialog = screen.getByRole('dialog', { name: 'Khóa tài khoản người dùng' })
    fireEvent.click(within(deactivateDialog).getByRole('button', { name: 'Hủy' }))

    await waitFor(() => {
      expect(
        screen.queryByRole('dialog', { name: 'Khóa tài khoản người dùng' }),
      ).not.toBeInTheDocument()
    })
    expect(mockedGetAdminUsers).toHaveBeenCalledTimes(1)
  })
})