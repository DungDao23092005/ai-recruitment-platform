import { render, screen, waitFor, within, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { AppShell } from './AppShell'
import { AuthProvider } from '@/contexts/AuthContext'
import * as authApi from '@/api/auth'
import type { User, UserRole } from '@/types/auth'

const mockUser: User = {
  id: 'user-1',
  email: 'user@example.com',
  role: 'candidate',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

vi.mock('@/api/auth', () => ({
  login: vi.fn(),
  register: vi.fn(),
  getCurrentUser: vi.fn(),
  createCandidateProfile: vi.fn(),
  createRecruiterProfile: vi.fn(),
}))

const mockedGetCurrentUser = vi.mocked(authApi.getCurrentUser)

function renderShell(role: UserRole, path: string) {
  mockedGetCurrentUser.mockResolvedValue({ ...mockUser, role })
  localStorage.setItem('ai_recruitment_token', 'token-abc')

  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route path={path} element={<div>App Content</div>} />
          </Route>
        </Routes>
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
    expect(screen.getByText('App Content')).toBeInTheDocument()
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

  it('renders the sidebar with recruiter navigation', async () => {
    renderShell('recruiter', '/recruiter/portal')

    await waitFor(() => {
      expect(getAppNav()).toBeInTheDocument()
    })

    const nav = getAppNav()
    expect(within(nav).getByText('Tổng quan')).toBeInTheDocument()
    expect(within(nav).getByText('Công ty')).toBeInTheDocument()
    expect(within(nav).getByText('Tin tuyển dụng')).toBeInTheDocument()
    expect(within(nav).getByText('Đăng tin mới')).toBeInTheDocument()
    expect(within(nav).getByText('Tìm ứng viên AI')).toBeInTheDocument()
    expect(within(nav).getByText('Hồ sơ cá nhân')).toBeInTheDocument()
  })

  it('renders the sidebar with admin navigation', async () => {
    renderShell('admin', '/admin/dashboard')

    await waitFor(() => {
      expect(getAppNav()).toBeInTheDocument()
    })

    const nav = getAppNav()
    expect(within(nav).getByText('Tổng quan')).toBeInTheDocument()
    expect(within(nav).getByText('Quản lý tuyển dụng')).toBeInTheDocument()
    expect(within(nav).getByText('Tin tuyển dụng')).toBeInTheDocument()
    expect(within(nav).getByText('Tìm ứng viên AI')).toBeInTheDocument()
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

  it('keeps "Việc làm công khai" pointing at the public /jobs route', async () => {
    renderShell('candidate', '/candidate/portal')

    await waitFor(() => {
      expect(screen.getByText('Tổng quan')).toBeInTheDocument()
    })

    expect(
      screen.getByRole('link', { name: 'Việc làm công khai' }),
    ).toHaveAttribute('href', '/jobs')
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