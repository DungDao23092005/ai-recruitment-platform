import { render, screen, waitFor, within, fireEvent, act } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { AppShell } from './AppShell'
import { AuthProvider } from '@/contexts/AuthContext'
import { WorkspaceProvider } from '@/contexts/WorkspaceContext'
import * as authApi from '@/api/auth'
import * as workspacesApi from '@/api/workspaces'
import { WORKSPACE_STORAGE_KEY } from '@/api/client'
import { USER_ROLE_LABELS } from '@/types/auth'
import type { User, UserRole } from '@/types/auth'
import type { MembershipRole, Workspace } from '@/types/workspace'

const mockUser: User = {
  id: 'user-1',
  email: 'user@example.com',
  role: 'candidate',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

function makeWorkspace(
  role: MembershipRole,
  companyId = 'company-1',
  companyName = 'Acme Corp',
): Workspace {
  return {
    company_id: companyId,
    company_name: companyName,
    company_slug: companyName.toLowerCase().replace(/\s+/g, '-'),
    membership_id: `membership-${companyId}`,
    role,
    is_platform_admin: false,
  }
}

vi.mock('@/api/auth', () => ({
  login: vi.fn(),
  register: vi.fn(),
  getCurrentUser: vi.fn(),
  createCandidateProfile: vi.fn(),
  createRecruiterProfile: vi.fn(),
}))

vi.mock('@/components/common/NotificationBell', () => ({
  NotificationBell: () => null,
}))

vi.mock('@/api/workspaces', () => ({
  getWorkspaces: vi.fn().mockResolvedValue([]),
}))

const mockedGetCurrentUser = vi.mocked(authApi.getCurrentUser)
const mockedGetWorkspaces = vi.mocked(workspacesApi.getWorkspaces)

function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <WorkspaceProvider>
          <Routes>
            <Route element={<AppShell />}>
              <Route path={path} element={<div>App Content</div>} />
            </Route>
          </Routes>
        </WorkspaceProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

function renderShell(
  role: UserRole,
  path: string,
  workspaceRole?: MembershipRole,
) {
  mockedGetCurrentUser.mockResolvedValue({ ...mockUser, role })
  mockedGetWorkspaces.mockResolvedValue(
    workspaceRole ? [makeWorkspace(workspaceRole)] : [],
  )
  localStorage.setItem('ai_recruitment_token', 'token-abc')

  return renderApp(path)
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

async function waitForRoleBadge(role: UserRole) {
  await waitFor(() => {
    expect(
      screen.getAllByText(USER_ROLE_LABELS[role]).length,
    ).toBeGreaterThan(0)
  })
}

function getAppNav() {
  return screen.getByRole('navigation', { name: 'Điều hướng ứng dụng' })
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})

describe('AppShell sidebar', () => {
  it('renders the sidebar with candidate navigation', async () => {
    renderShell('candidate', '/candidate/portal')

    // "Tìm việc AI" only exists in the candidate sidebar, so it proves the
    // authenticated candidate (not the loading fallback) has rendered.
    await waitFor(() => {
      expect(within(getAppNav()).getByText('Tìm việc AI')).toBeInTheDocument()
    })

    const nav = getAppNav()
    expect(within(nav).getByText('Tổng quan')).toBeInTheDocument()
    expect(within(nav).getByText('Lịch phỏng vấn')).toBeInTheDocument()
    expect(within(nav).getByText('Tìm việc AI')).toBeInTheDocument()
    expect(within(nav).getByText('Gợi ý việc làm')).toBeInTheDocument()
    expect(within(nav).getByText('Trợ lý AI')).toBeInTheDocument()
    expect(within(nav).getByText('Upload CV')).toBeInTheDocument()
    expect(within(nav).getByText('Hồ sơ cá nhân')).toBeInTheDocument()
    expect(within(nav).getByText('Gói dịch vụ AI')).toBeInTheDocument()
    expect(
      within(nav).queryByText('Nâng cấp nhà tuyển dụng'),
    ).not.toBeInTheDocument()
    expect(within(nav).queryByText('Quản lý người dùng')).not.toBeInTheDocument()
    expect(screen.getByText('App Content')).toBeInTheDocument()
  })

  it('does not render removed public items in private candidate sidebar', async () => {
    renderShell('candidate', '/candidate/portal')

    await waitFor(() => {
      expect(getAppNav()).toBeInTheDocument()
    })

    const nav = getAppNav()
    expect(within(nav).queryByText('Việc làm công khai')).not.toBeInTheDocument()
    expect(within(nav).queryByText('Sức khỏe hệ thống')).not.toBeInTheDocument()
  })

  it('marks the active route in the sidebar', async () => {
    renderShell('candidate', '/candidate/portal')

    await waitFor(() => {
      expect(screen.getByText('Tổng quan')).toBeInTheDocument()
    })

    expect(screen.getByRole('link', { name: 'Tổng quan' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('renders the sidebar with company admin workspace navigation', async () => {
    renderShell('recruiter', '/recruiter/portal', 'admin')

    await waitFor(() => {
      expect(mockedGetWorkspaces).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(within(getAppNav()).getByText('Công ty')).toBeInTheDocument()
    })

    const nav = getAppNav()
    expect(within(nav).getByText('Tổng quan')).toBeInTheDocument()
    expect(within(nav).getByText('Công ty')).toBeInTheDocument()
    expect(within(nav).getByText('Tin tuyển dụng')).toBeInTheDocument()
    expect(within(nav).getByText('Đăng tin mới')).toBeInTheDocument()
    expect(within(nav).getByText('Phân tích')).toBeInTheDocument()
    expect(within(nav).getByText('Lịch phỏng vấn')).toBeInTheDocument()
    expect(within(nav).getByText('Thành viên')).toBeInTheDocument()
    expect(within(nav).getByText('Gói & Thanh toán')).toBeInTheDocument()
    expect(within(nav).getByText('Tìm ứng viên AI')).toBeInTheDocument()
    expect(within(nav).getByText('Hồ sơ cá nhân')).toBeInTheDocument()
    expect(within(nav).getByText('Trợ lý AI')).toBeInTheDocument()
  })

  it('renders standard recruiter workspace navigation without company settings or member governance', async () => {
    renderShell('recruiter', '/recruiter/portal', 'recruiter')

    await waitFor(() => {
      expect(getAppNav()).toBeInTheDocument()
      expect(mockedGetWorkspaces).toHaveBeenCalled()
    })

    const nav = getAppNav()
    expect(within(nav).getByText('Tổng quan')).toBeInTheDocument()
    expect(within(nav).getByText('Tin tuyển dụng')).toBeInTheDocument()
    expect(within(nav).getByText('Đăng tin mới')).toBeInTheDocument()
    expect(within(nav).getByText('Phân tích')).toBeInTheDocument()
    expect(within(nav).getByText('Lịch phỏng vấn')).toBeInTheDocument()
    expect(within(nav).getByText('Gói & Thanh toán')).toBeInTheDocument()
    expect(within(nav).getByText('Tìm ứng viên AI')).toBeInTheDocument()
    expect(within(nav).getByText('Hồ sơ cá nhân')).toBeInTheDocument()
    expect(within(nav).getByText('Trợ lý AI')).toBeInTheDocument()
    expect(within(nav).queryByText('Công ty')).not.toBeInTheDocument()
    expect(within(nav).queryByText('Thành viên')).not.toBeInTheDocument()
  })

  it('renders interviewer workspace navigation with only assigned interviews, notifications and profile', async () => {
    renderShell('recruiter', '/interviewer/interviews', 'interviewer')

    await waitFor(() => {
      expect(getAppNav()).toBeInTheDocument()
      expect(
        within(getAppNav()).queryByText('Tin tuyển dụng'),
      ).not.toBeInTheDocument()
    })

    const nav = getAppNav()
    expect(within(nav).getByText('Lịch phỏng vấn')).toBeInTheDocument()
    expect(within(nav).getByText('Thông báo')).toBeInTheDocument()
    expect(within(nav).getByText('Hồ sơ cá nhân')).toBeInTheDocument()
    expect(within(nav).queryByText('Công ty')).not.toBeInTheDocument()
    expect(within(nav).queryByText('Tin tuyển dụng')).not.toBeInTheDocument()
    expect(within(nav).queryByText('Phân tích')).not.toBeInTheDocument()
    expect(within(nav).queryByText('Thành viên')).not.toBeInTheDocument()
    expect(within(nav).queryByText('Trợ lý AI')).not.toBeInTheDocument()
  })

  it('renders the sidebar with admin navigation', async () => {
    renderShell('admin', '/admin/dashboard')

    // The sidebar exists synchronously and the admin fallback nav renders even
    // while auth is loading, so wait for the role badge to show the loaded
    // Admin user before asserting role-gated navigation.
    await waitForRoleBadge('admin')

    const nav = getAppNav()
    expect(within(nav).getByText('Tổng quan')).toBeInTheDocument()
    expect(within(nav).getByText('Người dùng')).toBeInTheDocument()
    expect(within(nav).getByText('Công ty')).toBeInTheDocument()
    expect(within(nav).getByText('Tin tuyển dụng')).toBeInTheDocument()
    expect(within(nav).getByText('Gói dịch vụ')).toBeInTheDocument()
    expect(within(nav).getByText('Thuê bao')).toBeInTheDocument()
    expect(within(nav).getByText('Đơn thanh toán')).toBeInTheDocument()
    expect(within(nav).getByText('Hàng đợi email')).toBeInTheDocument()
    expect(within(nav).getByText('Nhật ký quản trị')).toBeInTheDocument()
    expect(within(nav).queryByText('Lịch phỏng vấn')).not.toBeInTheDocument()
    expect(within(nav).queryByText('Tìm ứng viên AI')).not.toBeInTheDocument()
    expect(within(nav).queryByText('Trợ lý AI')).not.toBeInTheDocument()
  })

  it('hides the AI Chat link while authentication is loading', async () => {
    const pendingUser = deferred<User>()
    mockedGetCurrentUser.mockReturnValue(pendingUser.promise)
    mockedGetWorkspaces.mockResolvedValue([])
    localStorage.setItem('ai_recruitment_token', 'token-abc')

    renderApp('/admin/dashboard')

    expect(mockedGetCurrentUser).toHaveBeenCalledTimes(1)
    expect(within(getAppNav()).queryByText('Trợ lý AI')).not.toBeInTheDocument()

    await act(async () => {
      pendingUser.resolve({ ...mockUser, role: 'admin' })
      await pendingUser.promise
    })

    await waitForRoleBadge('admin')

    const nav = getAppNav()
    expect(within(nav).queryByText('Trợ lý AI')).not.toBeInTheDocument()
    expect(within(nav).getByText('Người dùng')).toBeInTheDocument()
    expect(within(nav).getByText('Hàng đợi email')).toBeInTheDocument()
  })

  it('points admin "Người dùng" at /admin/users', async () => {
    renderShell('admin', '/admin/dashboard')

    await waitFor(() => {
      expect(screen.getByText('Tổng quan')).toBeInTheDocument()
    })

    expect(
      screen.getByRole('link', { name: 'Người dùng' }),
    ).toHaveAttribute('href', '/admin/users')
  })

  it('points admin "Công ty" at /admin/companies', async () => {
    renderShell('admin', '/admin/dashboard')

    await waitFor(() => {
      expect(screen.getByText('Tổng quan')).toBeInTheDocument()
    })

    expect(
      screen.getByRole('link', { name: 'Công ty' }),
    ).toHaveAttribute('href', '/admin/companies')
  })

  it('points admin "Đơn thanh toán" at /admin/payment-orders', async () => {
    renderShell('admin', '/admin/dashboard')

    await waitFor(() => {
      expect(screen.getByText('Tổng quan')).toBeInTheDocument()
    })

    expect(
      screen.getByRole('link', { name: 'Đơn thanh toán' }),
    ).toHaveAttribute('href', '/admin/payment-orders')
  })

  it('points candidate "Việc làm" at the private candidate jobs route', async () => {
    renderShell('candidate', '/candidate/portal')

    await waitFor(() => {
      expect(screen.getByText('Tổng quan')).toBeInTheDocument()
    })

    expect(screen.getByRole('link', { name: 'Việc làm' })).toHaveAttribute(
      'href',
      '/candidate/jobs',
    )
  })

  it('points candidate "Đơn ứng tuyển" at /candidate/applications', async () => {
    renderShell('candidate', '/candidate/portal')

    await waitFor(() => {
      expect(screen.getByText('Tổng quan')).toBeInTheDocument()
    })

    expect(
      screen.getByRole('link', { name: 'Đơn ứng tuyển' }),
    ).toHaveAttribute('href', '/candidate/applications')
  })

  it('points candidate "Lịch phỏng vấn" at /candidate/interviews and positions it after "Đơn ứng tuyển"', async () => {
    renderShell('candidate', '/candidate/portal')

    await waitFor(() => {
      expect(screen.getByText('Tổng quan')).toBeInTheDocument()
    })

    const nav = getAppNav()
    const links = within(nav).getAllByRole('link')
    const linkTexts = links.map((l) => l.textContent)
    const appIndex = linkTexts.findIndex((t) => t?.includes('Đơn ứng tuyển'))
    const interviewIndex = linkTexts.findIndex((t) => t?.includes('Lịch phỏng vấn'))
    expect(appIndex).toBeGreaterThan(-1)
    expect(interviewIndex).toBe(appIndex + 1)
    expect(links[interviewIndex]).toHaveAttribute('href', '/candidate/interviews')
  })

  it('opens the mobile drawer with the same sidebar navigation', async () => {
    renderShell('candidate', '/candidate/portal')

    await waitFor(() => {
      expect(getAppNav()).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Mở menu điều hướng' }))

    expect(
      screen.getByRole('button', { name: 'Đóng menu điều hướng' }),
    ).toBeInTheDocument()
    expect(
      screen.getAllByRole('navigation', { name: 'Điều hướng ứng dụng' }),
    ).toHaveLength(2)
  })

  it('closes the mobile drawer when navigating', async () => {
    renderShell('candidate', '/candidate/portal')

    await waitFor(() => {
      expect(getAppNav()).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Mở menu điều hướng' }))
    expect(
      screen.getByRole('button', { name: 'Đóng menu điều hướng' }),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Đóng menu điều hướng' }))
    expect(
      screen.queryByRole('button', { name: 'Đóng menu điều hướng' }),
    ).not.toBeInTheDocument()
  })
})

describe('AppShell workspace switcher visibility', () => {
  const switcherName = 'Chọn công ty làm việc'

  it('does not render the workspace switcher on /admin', async () => {
    renderShell('admin', '/admin', 'admin')

    await waitForRoleBadge('admin')

    expect(
      screen.queryByRole('combobox', { name: switcherName }),
    ).not.toBeInTheDocument()
  })

  it('does not render the workspace switcher on nested /admin routes', async () => {
    renderShell('admin', '/admin/audit', 'admin')

    await waitForRoleBadge('admin')

    expect(
      screen.queryByRole('combobox', { name: switcherName }),
    ).not.toBeInTheDocument()
  })

  it.each(['/recruiter/portal', '/recruiter/jobs', '/recruiter/admin-tools'])(
    'keeps the workspace switcher on %s',
    async (path) => {
      renderShell('recruiter', path, 'recruiter')

      const switcher = await screen.findByRole('combobox', {
        name: switcherName,
      })

      expect(switcher).toBeInTheDocument()
      expect(
        within(switcher).getByRole('option', { name: 'Acme Corp' }),
      ).toBeInTheDocument()
    },
  )

  it('keeps recruiter workspace selection behavior unchanged', async () => {
    mockedGetCurrentUser.mockResolvedValue({ ...mockUser, role: 'recruiter' })
    mockedGetWorkspaces.mockResolvedValue([
      makeWorkspace('recruiter', 'company-1', 'Acme Corp'),
      makeWorkspace('admin', 'company-2', 'Beta Inc'),
    ])
    localStorage.setItem('ai_recruitment_token', 'token-abc')

    renderApp('/recruiter/portal')

    const switcher = await screen.findByRole('combobox', {
      name: switcherName,
    })
    await waitFor(() => expect(switcher).toHaveValue('company-1'))

    fireEvent.change(switcher, { target: { value: 'company-2' } })

    expect(switcher).toHaveValue('company-2')
    expect(localStorage.getItem(WORKSPACE_STORAGE_KEY)).toBe('company-2')
  })
})
