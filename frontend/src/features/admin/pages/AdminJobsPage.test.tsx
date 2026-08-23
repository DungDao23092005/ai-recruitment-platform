import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { AdminJobsPage } from './AdminJobsPage'
import { AuthProvider } from '@/contexts/AuthContext'
import * as adminApi from '@/api/admin'
import * as authApi from '@/api/auth'
import type { User } from '@/types/auth'

const adminUser: User = {
  id: 'admin-1',
  email: 'admin@example.com',
  role: 'admin',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const candidateUser: User = {
  id: 'candidate-1',
  email: 'candidate@example.com',
  role: 'candidate',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const mockJobs = [
  {
    id: 'job-1',
    company_id: 'company-1',
    company_name: 'TechCorp',
    title: 'Senior Frontend Engineer',
    description: 'Build modern web applications.',
    status: 'published' as const,
    job_type: 'full_time' as const,
    workplace_type: 'remote' as const,
    location: 'Ho Chi Minh City',
    created_at: '2026-01-15T00:00:00Z',
    updated_at: '2026-01-15T00:00:00Z',
  },
  {
    id: 'job-2',
    company_id: 'company-2',
    company_name: 'StartupXYZ',
    title: 'Backend Developer',
    description: 'Build robust APIs.',
    status: 'draft' as const,
    job_type: 'part_time' as const,
    workplace_type: 'on_site' as const,
    location: 'Hanoi',
    created_at: '2026-01-10T00:00:00Z',
    updated_at: '2026-01-10T00:00:00Z',
  },
  {
    id: 'job-3',
    company_id: 'company-3',
    company_name: null,
    title: 'DevOps Engineer',
    description: 'Manage infrastructure.',
    status: 'closed' as const,
    job_type: 'contract' as const,
    workplace_type: 'hybrid' as const,
    location: 'Da Nang',
    created_at: '2026-01-05T00:00:00Z',
    updated_at: '2026-01-05T00:00:00Z',
  },
]

vi.mock('@/api/admin', () => ({
  getAdminJobs: vi.fn(),
}))

vi.mock('@/api/auth', () => ({
  getCurrentUser: vi.fn(),
}))

const mockedGetAdminJobs = vi.mocked(adminApi.getAdminJobs)
const mockedGetCurrentUser = vi.mocked(authApi.getCurrentUser)

function renderAdminJobsPage(user: User | null = adminUser) {
  mockedGetCurrentUser.mockResolvedValue(user)
  if (user) {
    localStorage.setItem('ai_recruitment_token', 'token-abc')
  }

  return render(
    <MemoryRouter initialEntries={['/admin/jobs']}>
      <AuthProvider>
        <Routes>
          <Route path="/admin/jobs" element={<AdminJobsPage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})

describe('AdminJobsPage', () => {
  it('shows loading state initially', async () => {
    let resolve!: (value: { items: typeof mockJobs; total: number; skip: number; limit: number }) => void
    mockedGetAdminJobs.mockReturnValue(
      new Promise((r) => {
        resolve = r
      }),
    )

    renderAdminJobsPage()

    await waitFor(() => {
      expect(screen.getByText('Tin tuyển dụng')).toBeInTheDocument()
    })

    expect(screen.queryByText('Senior Frontend Engineer')).not.toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('renders multiple jobs with company, type, workplace, status, location, and created date', async () => {
    mockedGetAdminJobs.mockResolvedValue({
      items: mockJobs,
      total: mockJobs.length,
      skip: 0,
      limit: 10,
    })

    renderAdminJobsPage()

    await waitFor(() => {
      expect(screen.getByText('Senior Frontend Engineer')).toBeInTheDocument()
    })

    expect(screen.getByText('Backend Developer')).toBeInTheDocument()
    expect(screen.getByText('DevOps Engineer')).toBeInTheDocument()

    expect(screen.getByText('TechCorp')).toBeInTheDocument()
    expect(screen.getByText('StartupXYZ')).toBeInTheDocument()
    expect(screen.getByText('Công ty company-')).toBeInTheDocument()

    expect(screen.getByText('Toàn thời gian')).toBeInTheDocument()
    expect(screen.getByText('Bán thời gian')).toBeInTheDocument()
    expect(screen.getByText('Hợp đồng')).toBeInTheDocument()

    expect(screen.getByText('Từ xa')).toBeInTheDocument()
    expect(screen.getByText('Tại văn phòng')).toBeInTheDocument()
    expect(screen.getByText('Hybrid')).toBeInTheDocument()

    expect(screen.getByText('Đã đăng')).toBeInTheDocument()
    expect(screen.getByText('Bản nháp')).toBeInTheDocument()
    expect(screen.getByText('Đã đóng')).toBeInTheDocument()

    expect(screen.getByText('Ho Chi Minh City')).toBeInTheDocument()
    expect(screen.getByText('Hanoi')).toBeInTheDocument()
    expect(screen.getByText('Da Nang')).toBeInTheDocument()

    expect(screen.getByText('15 thg 1, 2026')).toBeInTheDocument()
    expect(screen.getByText('10 thg 1, 2026')).toBeInTheDocument()
    expect(screen.getByText('5 thg 1, 2026')).toBeInTheDocument()
  })

  it('shows empty state when no jobs', async () => {
    mockedGetAdminJobs.mockResolvedValue({
      items: [],
      total: 0,
      skip: 0,
      limit: 10,
    })

    renderAdminJobsPage()

    await waitFor(() => {
      expect(screen.getByText('Không tìm thấy tin tuyển dụng')).toBeInTheDocument()
    })
    expect(screen.getByText('Chưa có tin tuyển dụng nào trên nền tảng.')).toBeInTheDocument()
  })

  it('shows empty state with search query when filtered', async () => {
    mockedGetAdminJobs.mockResolvedValue({
      items: [],
      total: 0,
      skip: 0,
      limit: 10,
    })

    renderAdminJobsPage()

    await waitFor(() => {
      expect(screen.getByText('Tin tuyển dụng')).toBeInTheDocument()
    })

    const searchInput = screen.getByPlaceholderText('Tìm theo tiêu đề...')
    fireEvent.change(searchInput, { target: { value: 'Nonexistent' } })
    fireEvent.submit(screen.getByRole('form'))

    await waitFor(() => {
      expect(screen.getByText('Không tìm thấy tin tuyển dụng')).toBeInTheDocument()
    })
    expect(screen.getByText('Không có tin tuyển dụng nào khớp với từ khóa hiện tại. Hãy điều chỉnh tìm kiếm để xem thêm kết quả.')).toBeInTheDocument()
  })

  it('shows error state when API fails', async () => {
    mockedGetAdminJobs.mockRejectedValue(new Error('Network error'))

    renderAdminJobsPage()

    await waitFor(() => {
      expect(screen.getByText('Không thể kết nối tới máy chủ. Vui lòng kiểm tra kết nối và thử lại.')).toBeInTheDocument()
    })
    expect(screen.getByText('Thử lại')).toBeInTheDocument()
  })

  it('shows admin jobs page for admin role', async () => {
    mockedGetAdminJobs.mockResolvedValue({
      items: mockJobs,
      total: mockJobs.length,
      skip: 0,
      limit: 10,
    })

    renderAdminJobsPage(adminUser)

    await waitFor(() => {
      expect(screen.getByText('Senior Frontend Engineer')).toBeInTheDocument()
    })
  })

  it('handles pagination', async () => {
    const manyJobs = Array.from({ length: 15 }, (_, i) => ({
      ...mockJobs[0],
      id: `job-${i + 1}`,
      title: `Job ${i + 1}`,
    }))

    mockedGetAdminJobs.mockResolvedValueOnce({
      items: manyJobs.slice(0, 10),
      total: 15,
      skip: 0,
      limit: 10,
    })

    renderAdminJobsPage()

    await waitFor(() => {
      expect(screen.getByText('Job 1')).toBeInTheDocument()
    })

    expect(screen.getByText('Trang 1 / 2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Trang sau' })).not.toBeDisabled()
    expect(screen.getByRole('button', { name: 'Trang trước' })).toBeDisabled()

    mockedGetAdminJobs.mockResolvedValueOnce({
      items: manyJobs.slice(10, 15),
      total: 15,
      skip: 10,
      limit: 10,
    })

    fireEvent.click(screen.getByRole('button', { name: 'Trang sau' }))

    await waitFor(() => {
      expect(screen.getByText('Job 11')).toBeInTheDocument()
    })
    expect(screen.getByText('Trang 2 / 2')).toBeInTheDocument()
  })
})