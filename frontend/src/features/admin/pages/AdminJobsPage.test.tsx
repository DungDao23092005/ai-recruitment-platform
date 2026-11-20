import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { AdminJobsPage } from './AdminJobsPage'
import { AuthProvider } from '@/contexts/AuthContext'
import * as adminApi from '@/api/admin'
import * as authApi from '@/api/auth'
import * as jobsApi from '@/api/jobs'
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

vi.mock('@/api/jobs', () => ({
  updateMyJobStatus: vi.fn(),
  deleteMyJob: vi.fn(),
}))

const mockedGetAdminJobs = vi.mocked(adminApi.getAdminJobs)
const mockedGetCurrentUser = vi.mocked(authApi.getCurrentUser)
const mockedUpdateMyJobStatus = vi.mocked(jobsApi.updateMyJobStatus)
const mockedDeleteMyJob = vi.mocked(jobsApi.deleteMyJob)

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
          <Route path="/admin/jobs/:id/edit" element={<div data-testid="admin-job-edit-page">Trang sửa tin tuyển dụng</div>} />
          <Route path="/admin/jobs/:id/applicants" element={<div data-testid="admin-job-applicants-page">Trang ứng viên</div>} />
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

  describe('Status Change (MOD-03)', () => {
    it('clicking the status-change button opens the status dialog for the selected job', async () => {
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

      fireEvent.click(screen.getByRole('button', { name: 'Đổi trạng thái Senior Frontend Engineer' }))

      expect(screen.getByRole('heading', { name: 'Đổi trạng thái tin tuyển dụng' })).toBeInTheDocument()
      expect(screen.getByText(/Chọn trạng thái mới cho tin tuyển dụng/)).toBeInTheDocument()
    })

    it('displays only permitted status transitions for the selected job', async () => {
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

      // job-1 status is published -> permitted transition is only 'closed' (Đã đóng)
      fireEvent.click(screen.getByRole('button', { name: 'Đổi trạng thái Senior Frontend Engineer' }))

      expect(screen.getByRole('option', { name: 'Đã đóng' })).toBeInTheDocument()
      expect(screen.queryByRole('option', { name: 'Đã đăng' })).not.toBeInTheDocument()
      expect(screen.queryByRole('option', { name: 'Bản nháp' })).not.toBeInTheDocument()

      // Close dialog
      fireEvent.click(screen.getByRole('button', { name: 'Hủy' }))
      await waitFor(() => {
        expect(screen.queryByRole('heading', { name: 'Đổi trạng thái tin tuyển dụng' })).not.toBeInTheDocument()
      })

      // job-2 status is draft -> permitted transition is only 'published' (Đã đăng)
      fireEvent.click(screen.getByRole('button', { name: 'Đổi trạng thái Backend Developer' }))

      expect(screen.getByRole('option', { name: 'Đã đăng' })).toBeInTheDocument()
      expect(screen.queryByRole('option', { name: 'Đã đóng' })).not.toBeInTheDocument()
      expect(screen.queryByRole('option', { name: 'Bản nháp' })).not.toBeInTheDocument()
    })

    it('disables the status-change button for an expired job with no permitted transitions', async () => {
      const expiredJob = {
        ...mockJobs[0],
        id: 'job-expired',
        title: 'Expired DevOps Role',
        status: 'expired' as const,
      }

      mockedGetAdminJobs.mockResolvedValue({
        items: [expiredJob],
        total: 1,
        skip: 0,
        limit: 10,
      })

      renderAdminJobsPage()

      await waitFor(() => {
        expect(screen.getByText('Expired DevOps Role')).toBeInTheDocument()
      })

      const statusButton = screen.getByRole('button', { name: 'Đổi trạng thái Expired DevOps Role' })
      expect(statusButton).toBeDisabled()
    })

    it('canceling status dialog closes the dialog and does not call updateMyJobStatus', async () => {
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

      fireEvent.click(screen.getByRole('button', { name: 'Đổi trạng thái Senior Frontend Engineer' }))
      expect(screen.getByRole('heading', { name: 'Đổi trạng thái tin tuyển dụng' })).toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: 'Hủy' }))

      await waitFor(() => {
        expect(screen.queryByRole('heading', { name: 'Đổi trạng thái tin tuyển dụng' })).not.toBeInTheDocument()
      })
      expect(mockedUpdateMyJobStatus).not.toHaveBeenCalled()
    })

    it('selecting a permitted status and confirming calls updateMyJobStatus, closes dialog, and reloads job list', async () => {
      mockedGetAdminJobs.mockResolvedValue({
        items: mockJobs,
        total: mockJobs.length,
        skip: 0,
        limit: 10,
      })
      mockedUpdateMyJobStatus.mockResolvedValue({
        ...mockJobs[0],
        status: 'closed',
      } as any)

      renderAdminJobsPage()

      await waitFor(() => {
        expect(screen.getByText('Senior Frontend Engineer')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('button', { name: 'Đổi trạng thái Senior Frontend Engineer' }))

      // Select has 'closed' by default for published job
      const select = screen.getByRole('combobox')
      expect(select).toHaveValue('closed')

      fireEvent.click(screen.getByRole('button', { name: 'Cập nhật' }))

      await waitFor(() => {
        expect(mockedUpdateMyJobStatus).toHaveBeenCalledWith('job-1', 'closed')
      })

      await waitFor(() => {
        expect(screen.queryByRole('heading', { name: 'Đổi trạng thái tin tuyển dụng' })).not.toBeInTheDocument()
      })

      // Reload occurs
      expect(mockedGetAdminJobs).toHaveBeenCalledTimes(2)
    })

    it('displays inline error message when updateMyJobStatus fails', async () => {
      mockedGetAdminJobs.mockResolvedValue({
        items: mockJobs,
        total: mockJobs.length,
        skip: 0,
        limit: 10,
      })
      mockedUpdateMyJobStatus.mockRejectedValue({
        response: {
          status: 400,
          data: { detail: 'Status transition forbidden' },
        },
      })

      renderAdminJobsPage()

      await waitFor(() => {
        expect(screen.getByText('Senior Frontend Engineer')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('button', { name: 'Đổi trạng thái Senior Frontend Engineer' }))
      fireEvent.click(screen.getByRole('button', { name: 'Cập nhật' }))

      await waitFor(() => {
        expect(screen.getByText('Status transition forbidden')).toBeInTheDocument()
      })

      // Dialog stays open
      expect(screen.getByRole('heading', { name: 'Đổi trạng thái tin tuyển dụng' })).toBeInTheDocument()
    })
  })

  describe('Job Deletion (MOD-03)', () => {
    it('clicking delete opens confirmation dialog displaying correct job title', async () => {
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

      fireEvent.click(screen.getByRole('button', { name: 'Xóa tin tuyển dụng Senior Frontend Engineer' }))

      expect(screen.getByRole('heading', { name: 'Xóa tin tuyển dụng' })).toBeInTheDocument()
      expect(screen.getByText(/Bạn có chắc chắn muốn xóa tin tuyển dụng/)).toBeInTheDocument()
      expect(screen.getByText('Xác nhận xóa tin tuyển dụng này?')).toBeInTheDocument()
    })

    it('canceling delete dialog closes dialog and does not call deleteMyJob', async () => {
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

      fireEvent.click(screen.getByRole('button', { name: 'Xóa tin tuyển dụng Senior Frontend Engineer' }))
      expect(screen.getByRole('heading', { name: 'Xóa tin tuyển dụng' })).toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: 'Hủy' }))

      await waitFor(() => {
        expect(screen.queryByRole('heading', { name: 'Xóa tin tuyển dụng' })).not.toBeInTheDocument()
      })

      expect(mockedDeleteMyJob).not.toHaveBeenCalled()
    })

    it('confirming deletion calls deleteMyJob with job id, closes dialog, and reloads job list', async () => {
      mockedGetAdminJobs.mockResolvedValue({
        items: mockJobs,
        total: mockJobs.length,
        skip: 0,
        limit: 10,
      })
      mockedDeleteMyJob.mockResolvedValue(undefined as any)

      renderAdminJobsPage()

      await waitFor(() => {
        expect(screen.getByText('Senior Frontend Engineer')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('button', { name: 'Xóa tin tuyển dụng Senior Frontend Engineer' }))
      fireEvent.click(screen.getByRole('button', { name: 'Xóa' }))

      await waitFor(() => {
        expect(mockedDeleteMyJob).toHaveBeenCalledWith('job-1')
      })

      await waitFor(() => {
        expect(screen.queryByRole('heading', { name: 'Xóa tin tuyển dụng' })).not.toBeInTheDocument()
      })

      // Reload occurs
      expect(mockedGetAdminJobs).toHaveBeenCalledTimes(2)
    })

    it('shows alert error when deleteMyJob fails', async () => {
      const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {})
      mockedGetAdminJobs.mockResolvedValue({
        items: mockJobs,
        total: mockJobs.length,
        skip: 0,
        limit: 10,
      })
      mockedDeleteMyJob.mockRejectedValue({
        response: {
          status: 400,
          data: { detail: 'Cannot delete active job' },
        },
      })

      renderAdminJobsPage()

      await waitFor(() => {
        expect(screen.getByText('Senior Frontend Engineer')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('button', { name: 'Xóa tin tuyển dụng Senior Frontend Engineer' }))
      fireEvent.click(screen.getByRole('button', { name: 'Xóa' }))

      await waitFor(() => {
        expect(alertSpy).toHaveBeenCalledWith('Cannot delete active job')
      })

      alertSpy.mockRestore()
    })
  })

  describe('Admin Navigation (MOD-03)', () => {
    it('edit action navigates to /admin/jobs/:id/edit', async () => {
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

      fireEvent.click(screen.getByRole('button', { name: 'Sửa tin tuyển dụng Senior Frontend Engineer' }))

      await waitFor(() => {
        expect(screen.getByTestId('admin-job-edit-page')).toBeInTheDocument()
      })
    })

    it('applicants action navigates to /admin/jobs/:id/applicants', async () => {
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

      fireEvent.click(screen.getByRole('button', { name: 'Xem ứng viên Senior Frontend Engineer' }))

      await waitFor(() => {
        expect(screen.getByTestId('admin-job-applicants-page')).toBeInTheDocument()
      })
    })
  })
})
