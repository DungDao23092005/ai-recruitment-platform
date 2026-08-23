import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import {
  MemoryRouter,
  Route,
  Routes,
  useNavigate,
} from 'react-router-dom'
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
  company_name: 'TechNova AI',
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
  getMyApplicationForJob: vi.fn(),
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
const mockedGetMyApplicationForJob = vi.mocked(applicationsApi.getMyApplicationForJob)

const mockApplication = (status: string) => ({
  id: 'app-1',
  candidate_id: 'user-1',
  job_id: 'job-1',
  status,
  created_at: '2026-01-20T00:00:00Z',
  updated_at: '2026-01-20T00:00:00Z',
  job_title: 'Senior Frontend Engineer',
  company_name: 'TechNova AI',
  interviews: [],
})

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
    mockedGetMyApplicationForJob.mockResolvedValue(null)

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

  it('renders the company name', async () => {
    mockedGetJobById.mockResolvedValue(mockJob)
    mockedGetMyApplicationForJob.mockResolvedValue(null)

    renderJobDetailPage()

    await waitFor(() => {
      expect(screen.getByText('Công ty TechNova AI')).toBeInTheDocument()
    })
  })

  it('falls back to company id prefix when company_name is null', async () => {
    mockedGetJobById.mockResolvedValue({ ...mockJob, company_name: null })
    mockedGetMyApplicationForJob.mockResolvedValue(null)

    renderJobDetailPage()

    await waitFor(() => {
      expect(screen.getByText(/Công ty 00000000/)).toBeInTheDocument()
    })
  })

  it('shows loading state while fetching', async () => {
    let resolve!: (value: Job) => void
    mockedGetJobById.mockReturnValue(
      new Promise((r) => {
        resolve = r
      }),
    )
    mockedGetMyApplicationForJob.mockResolvedValue(null)

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
    mockedGetMyApplicationForJob.mockResolvedValue(null)

    renderJobDetailPage()

    await waitFor(() => {
      expect(screen.getByText('404')).toBeInTheDocument()
      expect(screen.getByText('Không tìm thấy công việc')).toBeInTheDocument()
    })
  })

  it('opens apply modal for a candidate', async () => {
    mockedGetJobById.mockResolvedValue(mockJob)
    mockedGetMyApplicationForJob.mockResolvedValue(null)

    renderJobDetailPage()

    await waitFor(() => {
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
    })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Ứng tuyển ngay/i })).toBeInTheDocument()
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
    mockedGetMyApplicationForJob.mockResolvedValue(null)
    mockedApplyJob.mockResolvedValue({
      id: 'app-1',
      candidate_id: 'user-1',
      job_id: 'job-1',
      status: 'applied',
      created_at: '2026-01-20T00:00:00Z',
      updated_at: '2026-01-20T00:00:00Z',
      candidate: null,
    })

    renderJobDetailPage()

    await waitFor(() => {
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
    })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Ứng tuyển ngay/i })).toBeInTheDocument()
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
    mockedGetMyApplicationForJob.mockResolvedValue(null)
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

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Ứng tuyển ngay/i })).toBeInTheDocument()
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
    mockedGetMyApplicationForJob.mockResolvedValue(null)

    renderJobDetailPage(null)

    await waitFor(() => {
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
    })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Ứng tuyển ngay/i })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Ứng tuyển ngay/i }))

    await waitFor(() => {
      expect(screen.getByText('Login Page')).toBeInTheDocument()
    })
  })

  it('disables apply button for recruiter', async () => {
    mockedGetJobById.mockResolvedValue(mockJob)
    mockedGetMyApplicationForJob.mockResolvedValue(null)

    renderJobDetailPage(recruiterUser)

    await waitFor(() => {
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
    })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Ứng tuyển ngay/i })).toBeInTheDocument()
    })

    const applyButton = screen.getByRole('button', { name: /Ứng tuyển ngay/i })
    expect(applyButton).toBeDisabled()
    expect(
      screen.getByText('Chỉ ứng viên mới có thể ứng tuyển.'),
    ).toBeInTheDocument()
  })

  it('reloads data with the new id when navigating /jobs/A → /jobs/B while mounted', async () => {
    const jobB: Job = {
      ...mockJob,
      id: 'job-2',
      title: 'Senior Backend Engineer',
      description: 'Build backend APIs with FastAPI.',
      company_name: 'TechNova Vietnam',
    }
    mockedGetJobById
      .mockResolvedValueOnce(mockJob)
      .mockResolvedValueOnce(jobB)
    mockedGetMyApplicationForJob.mockResolvedValue(null)

    function NavToB() {
      const navigate = useNavigate()
      return (
        <button onClick={() => navigate('/jobs/job-2')}>
          Switch to B
        </button>
      )
    }

    vi.mocked(authApi.getCurrentUser).mockResolvedValue(candidateUser)
    localStorage.setItem('ai_recruitment_token', 'token-abc')

    render(
      <MemoryRouter initialEntries={['/jobs/job-1']}>
        <AuthProvider>
          <Routes>
            <Route path="/jobs/:id" element={<JobDetailPage />} />
            <Route path="/login" element={<div>Login Page</div>} />
          </Routes>
          <NavToB />
        </AuthProvider>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
    })
    expect(mockedGetJobById).toHaveBeenCalledWith('job-1')

    fireEvent.click(screen.getByRole('button', { name: 'Switch to B' }))

    await waitFor(() => {
      expect(mockedGetJobById).toHaveBeenNthCalledWith(2, 'job-2')
      expect(screen.getByText('Senior Backend Engineer')).toBeInTheDocument()
      expect(
        screen.getByText('Build backend APIs with FastAPI.'),
      ).toBeInTheDocument()
      expect(screen.getByText('Công ty TechNova Vietnam')).toBeInTheDocument()
    })
  })

  describe('Application Status Display', () => {
    const statusTestCases = [
      { status: 'applied', expectedLabel: 'Đã ứng tuyển' },
      { status: 'under_review', expectedLabel: 'Đang được xem xét' },
      { status: 'shortlisted', expectedLabel: 'Đã lọt vào danh sách' },
      { status: 'interviewing', expectedLabel: 'Đang phỏng vấn' },
      { status: 'accepted', expectedLabel: 'Đã được chấp nhận' },
      { status: 'rejected', expectedLabel: 'Đã bị từ chối' },
      { status: 'withdrawn', expectedLabel: 'Đã rút đơn' },
    ] as const

    statusTestCases.forEach(({ status, expectedLabel }) => {
      it(`displays "${expectedLabel}" when application status is ${status}`, async () => {
        mockedGetJobById.mockResolvedValue(mockJob)
        mockedGetMyApplicationForJob.mockResolvedValue(mockApplication(status))

        renderJobDetailPage()

        await waitFor(() => {
          expect(screen.getByText('Senior Frontend Engineer')).toBeInTheDocument()
        })

        await waitFor(() => {
          expect(screen.getByText(expectedLabel)).toBeInTheDocument()
        })

        expect(screen.getByText('Bạn đã nộp đơn cho vị trí này.')).toBeInTheDocument()

        expect(screen.queryByRole('button', { name: /Ứng tuyển ngay/i })).not.toBeInTheDocument()
      })
    })

    it('does not allow opening ApplyModal when application exists', async () => {
      mockedGetJobById.mockResolvedValue(mockJob)
      mockedGetMyApplicationForJob.mockResolvedValue(mockApplication('applied'))

      renderJobDetailPage()

      await waitFor(() => {
        expect(screen.getByText('Đã ứng tuyển')).toBeInTheDocument()
      })

      expect(screen.queryByRole('button', { name: /Ứng tuyển ngay/i })).not.toBeInTheDocument()

      expect(screen.queryByRole('dialog', { name: 'Xác nhận ứng tuyển' })).not.toBeInTheDocument()
    })
  })

  describe('Application Status Loading State', () => {
    it('shows loading state while fetching application status', async () => {
      mockedGetJobById.mockResolvedValue(mockJob)

      let resolveApp!: (value: { status: string } | null) => void
      const appPromise = new Promise<{ status: string } | null>((r) => {
        resolveApp = r
      })
      mockedGetMyApplicationForJob.mockReturnValue(appPromise)

      renderJobDetailPage()

      await waitFor(() => {
        expect(screen.getByText('Senior Frontend Engineer')).toBeInTheDocument()
      })

      // During loading, the button should not be visible, loading text should show
      await waitFor(() => {
        expect(screen.getByText('Đang kiểm tra trạng thái đơn ứng tuyển...')).toBeInTheDocument()
      })

      // The apply button should not be visible during loading
      expect(screen.queryByRole('button', { name: /Ứng tuyển ngay/i })).not.toBeInTheDocument()

      resolveApp(mockApplication('applied'))

      await waitFor(() => {
        expect(screen.getByText('Đã ứng tuyển')).toBeInTheDocument()
      })
    })

    it('shows "Ứng tuyển ngay" after loading completes with no application', async () => {
      mockedGetJobById.mockResolvedValue(mockJob)

      let resolveApp!: (value: { status: string } | null) => void
      const appPromise = new Promise<{ status: string } | null>((r) => {
        resolveApp = r
      })
      mockedGetMyApplicationForJob.mockReturnValue(appPromise)

      renderJobDetailPage()

      await waitFor(() => {
        expect(screen.getByText('Senior Frontend Engineer')).toBeInTheDocument()
      })

      // During loading, button should not be visible (or loading text shows)
      // Just verify loading text appears
      await waitFor(() => {
        expect(screen.getByText('Đang kiểm tra trạng thái đơn ứng tuyển...')).toBeInTheDocument()
      })

      resolveApp(null)

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Ứng tuyển ngay/i })).toBeInTheDocument()
      })
    })
  })

  describe('API Error Handling', () => {
    it('falls back to "Ứng tuyển ngay" when application status fetch fails', async () => {
      mockedGetJobById.mockResolvedValue(mockJob)
      mockedGetMyApplicationForJob.mockRejectedValue(new Error('Network error'))

      renderJobDetailPage()

      await waitFor(() => {
        expect(screen.getByText('Senior Frontend Engineer')).toBeInTheDocument()
      })

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Ứng tuyển ngay/i })).toBeInTheDocument()
      })

      expect(screen.queryByText('Đang kiểm tra trạng thái đơn ứng tuyển...')).not.toBeInTheDocument()
    })
  })

  describe('Navigation Stale State Prevention', () => {
    it('clears application status when navigating from job with application to job without', async () => {
      const jobA: Job = { ...mockJob, id: 'job-A', title: 'Job A' }
      const jobB: Job = { ...mockJob, id: 'job-B', title: 'Job B' }

      mockedGetJobById.mockResolvedValueOnce(jobA)
      mockedGetMyApplicationForJob.mockResolvedValueOnce(mockApplication('applied'))

      function NavToB() {
        const navigate = useNavigate()
        return (
          <button onClick={() => navigate('/jobs/job-B')}>
            Go to Job B
          </button>
        )
      }

      vi.mocked(authApi.getCurrentUser).mockResolvedValue(candidateUser)
      localStorage.setItem('ai_recruitment_token', 'token-abc')

      render(
        <MemoryRouter initialEntries={['/jobs/job-A']}>
          <AuthProvider>
            <Routes>
              <Route path="/jobs/:id" element={<JobDetailPage />} />
              <Route path="/login" element={<div>Login Page</div>} />
            </Routes>
            <NavToB />
          </AuthProvider>
        </MemoryRouter>,
      )

      await waitFor(() => {
        expect(screen.getByText('Job A')).toBeInTheDocument()
      })

      await waitFor(() => {
        expect(screen.getByText('Đã ứng tuyển')).toBeInTheDocument()
      })

      mockedGetJobById.mockResolvedValueOnce(jobB)
      mockedGetMyApplicationForJob.mockResolvedValueOnce(null)

      fireEvent.click(screen.getByRole('button', { name: 'Go to Job B' }))

      await waitFor(() => {
        expect(mockedGetJobById).toHaveBeenNthCalledWith(2, 'job-B')
        expect(screen.getByText('Job B')).toBeInTheDocument()
      })

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Ứng tuyển ngay/i })).toBeInTheDocument()
      })

      expect(screen.queryByText('Đã ứng tuyển')).not.toBeInTheDocument()
    })

    it('updates application status when navigating from job without to job with application', async () => {
      const jobA: Job = { ...mockJob, id: 'job-A', title: 'Job A' }
      const jobB: Job = { ...mockJob, id: 'job-B', title: 'Job B' }

      mockedGetJobById.mockResolvedValueOnce(jobA)
      mockedGetMyApplicationForJob.mockResolvedValueOnce(null)

      function NavToB() {
        const navigate = useNavigate()
        return (
          <button onClick={() => navigate('/jobs/job-B')}>
            Go to Job B
          </button>
        )
      }

      vi.mocked(authApi.getCurrentUser).mockResolvedValue(candidateUser)
      localStorage.setItem('ai_recruitment_token', 'token-abc')

      let resolveAppA!: (value: { status: string } | null) => void
      const appPromiseA = new Promise<{ status: string } | null>((r) => {
        resolveAppA = r
      })
      mockedGetMyApplicationForJob.mockReturnValue(appPromiseA)

      render(
        <MemoryRouter initialEntries={['/jobs/job-A']}>
          <AuthProvider>
            <Routes>
              <Route path="/jobs/:id" element={<JobDetailPage />} />
              <Route path="/login" element={<div>Login Page</div>} />
            </Routes>
            <NavToB />
          </AuthProvider>
        </MemoryRouter>,
      )

      await waitFor(() => {
        expect(screen.getByText('Job A')).toBeInTheDocument()
      })

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Ứng tuyển ngay/i })).toBeInTheDocument()
      })

      // Resolve Job A application to null (no application)
      resolveAppA(null)

      mockedGetJobById.mockResolvedValueOnce(jobB)

      let resolveAppB!: (value: { status: string } | null) => void
      const appPromiseB = new Promise<{ status: string } | null>((r) => {
        resolveAppB = r
      })
      mockedGetMyApplicationForJob.mockReturnValue(appPromiseB)

      fireEvent.click(screen.getByRole('button', { name: 'Go to Job B' }))

      await waitFor(() => {
        expect(mockedGetJobById).toHaveBeenNthCalledWith(2, 'job-B')
        expect(screen.getByText('Job B')).toBeInTheDocument()
      })

      // Resolve Job B application to under_review
      resolveAppB(mockApplication('under_review'))

      await waitFor(() => {
        expect(screen.getByText('Đang được xem xét')).toBeInTheDocument()
      })

      expect(screen.queryByRole('button', { name: /Ứng tuyển ngay/i })).not.toBeInTheDocument()
    })
  })
})