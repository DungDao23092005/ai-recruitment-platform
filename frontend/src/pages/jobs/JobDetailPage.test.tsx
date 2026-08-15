import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { JobDetailPage } from './JobDetailPage'
import { AuthProvider } from '@/contexts/AuthContext'
import * as jobsApi from '@/api/jobs'
import * as applicationsApi from '@/api/applications'
import * as authApi from '@/api/auth'
import type { Job } from '@/types/job'
import type { User } from '@/types/auth'

const mockJob: Job = {
  id: 'job-1',
  company_id: '00000000-0000-0000-0000-000000000001',
  title: 'Senior Frontend Engineer',
  description: 'Build modern web applications.',
  status: 'published',
  job_type: 'full_time',
  workplace_type: 'remote',
  location: 'Ho Chi Minh City',
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-01-15T00:00:00Z',
}

const candidateUser: User = {
  id: 'user-1',
  email: 'candidate@example.com',
  role: 'candidate',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const recruiterUser: User = {
  ...candidateUser,
  id: 'user-2',
  email: 'recruiter@example.com',
  role: 'recruiter',
}

vi.mock('@/api/jobs', () => ({
  getJobs: vi.fn(),
  getJobById: vi.fn(),
}))

vi.mock('@/api/applications', () => ({
  applyJob: vi.fn(),
}))

vi.mock('@/api/auth', () => ({
  login: vi.fn(),
  getCurrentUser: vi.fn(),
  register: vi.fn(),
  createCandidateProfile: vi.fn(),
  createRecruiterProfile: vi.fn(),
}))

const mockedGetJobById = vi.mocked(jobsApi.getJobById)
const mockedApplyJob = vi.mocked(applicationsApi.applyJob)

function renderJobDetailPage(user: User | null = candidateUser) {
  vi.mocked(authApi.getCurrentUser).mockResolvedValue(user as User)
  if (user) {
    localStorage.setItem('ai_recruitment_token', 'token-abc')
  }

  return render(
    <MemoryRouter initialEntries={['/jobs/job-1']}>
      <AuthProvider>
        <Routes>
          <Route path="/jobs/:id" element={<JobDetailPage />} />
          <Route path="/login" element={<div>Login Page</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})

describe('JobDetailPage', () => {
  it('renders job information after loading', async () => {
    mockedGetJobById.mockResolvedValue(mockJob)

    renderJobDetailPage()

    await waitFor(() => {
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
    })
    expect(screen.getByText('Ho Chi Minh City')).toBeInTheDocument()
    expect(screen.getByText('Toàn thời gian')).toBeInTheDocument()
    expect(screen.getByText('Từ xa')).toBeInTheDocument()
  })

  it('shows loading state while fetching', async () => {
    let resolve!: (value: Job) => void
    mockedGetJobById.mockReturnValue(
      new Promise((r) => {
        resolve = r
      }),
    )

    const { container } = renderJobDetailPage()

    await waitFor(() => {
      expect(container.querySelector('.animate-pulse')).not.toBeNull()
    })

    resolve(mockJob)
  })

  it('shows 404 state when job not found', async () => {
    const error = new Error('Not Found')
    Object.assign(error, { response: { status: 404 } })
    mockedGetJobById.mockRejectedValue(error)

    renderJobDetailPage()

    await waitFor(() => {
      expect(screen.getByText('404')).toBeInTheDocument()
      expect(screen.getByText('Không tìm thấy công việc')).toBeInTheDocument()
    })
  })

  it('opens apply modal for a candidate', async () => {
    mockedGetJobById.mockResolvedValue(mockJob)

    renderJobDetailPage()

    await waitFor(() => {
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Ứng tuyển ngay/i }))

    await waitFor(() => {
      expect(
        screen.getByRole('dialog', { name: 'Xác nhận ứng tuyển' }),
      ).toBeInTheDocument()
    })
  })

  it('shows success message after applying', async () => {
    mockedGetJobById.mockResolvedValue(mockJob)
    mockedApplyJob.mockResolvedValue({
      id: 'app-1',
      candidate_id: 'user-1',
      job_id: 'job-1',
      status: 'applied',
      created_at: '2026-01-20T00:00:00Z',
      updated_at: '2026-01-20T00:00:00Z',
    })

    renderJobDetailPage()

    await waitFor(() => {
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Ứng tuyển ngay/i }))
    await waitFor(() => {
      expect(
        screen.getByRole('dialog', { name: 'Xác nhận ứng tuyển' }),
      ).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: 'Xác nhận ứng tuyển' }),
    )

    await waitFor(() => {
      expect(mockedApplyJob).toHaveBeenCalledWith('job-1')
      expect(screen.getByText('Đã nộp đơn thành công')).toBeInTheDocument()
    })
  })

  it('shows duplicate application message on 400', async () => {
    mockedGetJobById.mockResolvedValue(mockJob)
    const error = new Error('already applied')
    Object.assign(error, {
      response: {
        status: 400,
        data: { detail: 'You have already applied for this job' },
      },
    })
    mockedApplyJob.mockRejectedValue(error)

    renderJobDetailPage()

    await waitFor(() => {
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Ứng tuyển ngay/i }))
    await waitFor(() => {
      expect(
        screen.getByRole('dialog', { name: 'Xác nhận ứng tuyển' }),
      ).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: 'Xác nhận ứng tuyển' }),
    )

    await waitFor(() => {
      expect(
        screen.getByText('Bạn đã nộp đơn cho công việc này.'),
      ).toBeInTheDocument()
    })
  })

  it('redirects to login when unauthenticated user clicks apply', async () => {
    mockedGetJobById.mockResolvedValue(mockJob)

    renderJobDetailPage(null)

    await waitFor(() => {
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Ứng tuyển ngay/i }))

    await waitFor(() => {
      expect(screen.getByText('Login Page')).toBeInTheDocument()
    })
  })

  it('disables apply button for recruiter', async () => {
    mockedGetJobById.mockResolvedValue(mockJob)

    renderJobDetailPage(recruiterUser)

    await waitFor(() => {
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
    })

    const applyButton = screen.getByRole('button', { name: /Ứng tuyển ngay/i })
    expect(applyButton).toBeDisabled()
    expect(
      screen.getByText('Chỉ ứng viên mới có thể ứng tuyển.'),
    ).toBeInTheDocument()
  })
})