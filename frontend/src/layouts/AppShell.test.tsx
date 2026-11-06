import { render, screen, waitFor, within, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { AppShell } from './AppShell'
import { AuthProvider } from '@/contexts/AuthContext'
import { WorkspaceProvider } from '@/contexts/WorkspaceContext'
import * as authApi from '@/api/auth'
import * as workspacesApi from '@/api/workspaces'
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

function makeWorkspace(role: MembershipRole): Workspace {
  return {
    company_id: 'company-1',
    company_name: 'Acme Corp',
    company_slug: 'acme-corp',
    membership_id: 'membership-1',
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

    await waitFor(() => {
      expect(getAppNav()).toBeInTheDocument()
    })

    const nav = getAppNav()
    expect(within(nav).getByText('Tổng quan')).toBeInTheDocument()
    expect(within(nav).getByText('Tìm việc AI')).toBeInTheDocument()
    expect(within(nav).getByText('Gợi ý việc làm')).toBeInTheDocument()
    expect(within(nav).getByText('Trợ lý AI')).toBeInTheDocument()
    expect(within(nav).getByText('Upload CV')).toBeInTheDocument()
    expect(within(nav).getByText('Hồ sơ cá nhân')).toBeInTheDocument()
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
      expect(getAppNav()).toBeInTheDocument()
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
    expect(within(nav).getByText('Tìm ứng viên AI')).toBeInTheDocument()
    expect(within(nav).getByText('Hồ sơ cá nhân')).toBeInTheDocument()
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
    expect(within(nav).getByText('Tìm ứng viên AI')).toBeInTheDocument()
    expect(within(nav).getByText('Hồ sơ cá nhân')).toBeInTheDocument()
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
  })

  it('renders the sidebar with admin navigation', async () => {
    renderShell('admin', '/admin/dashboard')

    await waitFor(() => {
      expect(getAppNav()).toBeInTheDocument()
    })

    const nav = getAppNav()
    expect(within(nav).getByText('Tổng quan')).toBeInTheDocument()
    expect(within(nav).getByText('Quản lý người dùng')).toBeInTheDocument()
    expect(within(nav).getByText('Quản lý công ty')).toBeInTheDocument()
    expect(within(nav).getByText('Quản lý tuyển dụng')).toBeInTheDocument()
    expect(within(nav).getByText('Tin tuyển dụng')).toBeInTheDocument()
    expect(within(nav).getByText('Tìm ứng viên AI')).toBeInTheDocument()
  })

  it('points admin "Quản lý người dùng" at /admin/users', async () => {
    renderShell('admin', '/admin/dashboard')

    await waitFor(() => {
      expect(screen.getByText('Tổng quan')).toBeInTheDocument()
    })

    expect(
      screen.getByRole('link', { name: 'Quản lý người dùng' }),
    ).toHaveAttribute('href', '/admin/users')
  })

  it('points admin "Quản lý công ty" at /admin/companies', async () => {
    renderShell('admin', '/admin/dashboard')

    await waitFor(() => {
      expect(screen.getByText('Tổng quan')).toBeInTheDocument()
    })

    expect(
      screen.getByRole('link', { name: 'Quản lý công ty' }),
    ).toHaveAttribute('href', '/admin/companies')
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