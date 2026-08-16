import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { JobApplicantsPage } from './JobApplicantsPage'
import * as jobsApi from '@/api/jobs'
import * as applicationsApi from '@/api/applications'
import type { Application } from '@/types/application'
import type { Job } from '@/types/job'

const mockJob: Job = {
  id: 'job-1',
  company_id: 'company-1',
  company_name: null,
  title: 'Senior Frontend Engineer',
  description: 'Build modern web applications with React.',
  status: 'published',
  job_type: 'full_time',
  workplace_type: 'remote',
  location: 'Ho Chi Minh City',
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-01-15T00:00:00Z',
}

const mockApplications: Application[] = [
  {
    id: 'app-1',
    candidate_id: '11111111-1111-1111-1111-111111111111',
    job_id: 'job-1',
    status: 'applied',
    created_at: '2026-01-20T00:00:00Z',
    updated_at: '2026-01-20T00:00:00Z',
    candidate: null,
  },
  {
    id: 'app-2',
    candidate_id: '22222222-2222-2222-2222-222222222222',
    job_id: 'job-1',
    status: 'shortlisted',
    created_at: '2026-01-21T00:00:00Z',
    updated_at: '2026-01-22T00:00:00Z',
    candidate: null,
  },
]

vi.mock('@/api/jobs', () => ({
  getJobs: vi.fn(),
  getMyJobById: vi.fn(),
}))

vi.mock('@/api/applications', () => ({
  applyJob: vi.fn(),
  getApplicationsByJob: vi.fn(),
}))

const mockedGetMyJobById = vi.mocked(jobsApi.getMyJobById)
const mockedGetApplicationsByJob = vi.mocked(
  applicationsApi.getApplicationsByJob,
)

function renderJobApplicantsPage() {
  return render(
    <MemoryRouter initialEntries={['/recruiter/jobs/job-1/applicants']}>
      <Routes>
        <Route
          path="/recruiter/jobs/:id/applicants"
          element={<JobApplicantsPage />}
        />
        <Route path="/recruiter/jobs" element={<div>Jobs Page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('JobApplicantsPage', () => {
  it('fetches job and applications on mount', async () => {
    mockedGetMyJobById.mockResolvedValue(mockJob)
    mockedGetApplicationsByJob.mockResolvedValue(mockApplications)

    renderJobApplicantsPage()

    await waitFor(() => {
      expect(mockedGetMyJobById).toHaveBeenCalledWith('job-1')
      expect(mockedGetApplicationsByJob).toHaveBeenCalledWith('job-1')
    })
  })

  it('shows loading state while fetching', async () => {
    let resolveJob!: (value: Job) => void
    let resolveApps!: (value: Application[]) => void
    mockedGetMyJobById.mockReturnValue(
      new Promise((r) => {
        resolveJob = r
      }),
    )
    mockedGetApplicationsByJob.mockReturnValue(
      new Promise((r) => {
        resolveApps = r
      }),
    )

    const { container } = renderJobApplicantsPage()

    await waitFor(() => {
      expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
    })

    resolveJob(mockJob)
    resolveApps(mockApplications)
  })

  it('renders the job title and applicants', async () => {
    mockedGetMyJobById.mockResolvedValue(mockJob)
    mockedGetApplicationsByJob.mockResolvedValue(mockApplications)

    renderJobApplicantsPage()

    await waitFor(() => {
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
      expect(screen.getByText('Ứng viên 11111111')).toBeInTheDocument()
      expect(screen.getByText('Ứng viên 22222222')).toBeInTheDocument()
    })
  })

  it('renders candidate statuses', async () => {
    mockedGetMyJobById.mockResolvedValue(mockJob)
    mockedGetApplicationsByJob.mockResolvedValue(mockApplications)

    renderJobApplicantsPage()

    await waitFor(() => {
      expect(screen.getByText('Đã nộp')).toBeInTheDocument()
      expect(screen.getByText('Lọt vòng ngắn')).toBeInTheDocument()
    })
  })

  it('opens the status update modal for an applicant', async () => {
    mockedGetMyJobById.mockResolvedValue(mockJob)
    mockedGetApplicationsByJob.mockResolvedValue(mockApplications)

    renderJobApplicantsPage()

    await waitFor(() => {
      expect(
        screen.getByRole('button', {
          name: /Cập nhật trạng thái cho đơn ứng tuyển app-1/i,
        }),
      ).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', {
        name: /Cập nhật trạng thái cho đơn ứng tuyển app-1/i,
      }),
    )

    expect(
      screen.getByRole('dialog', { name: 'Cập nhật trạng thái đơn ứng tuyển' }),
    ).toBeInTheDocument()
  })

  it('shows empty state when there are no applicants', async () => {
    mockedGetMyJobById.mockResolvedValue(mockJob)
    mockedGetApplicationsByJob.mockResolvedValue([])

    renderJobApplicantsPage()

    await waitFor(() => {
      expect(
        screen.getByText('Chưa có ứng viên'),
      ).toBeInTheDocument()
    })
  })

  it('shows an error state when the API fails', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Server error' } },
    })
    mockedGetMyJobById.mockResolvedValue(mockJob)
    mockedGetApplicationsByJob.mockRejectedValue(error)

    renderJobApplicantsPage()

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument()
    })
  })

it('shows 404 when job is not found', async () => {
    const error = new Error('Not Found')
    Object.assign(error, { response: { status: 404 } })
    mockedGetMyJobById.mockRejectedValue(error)

    renderJobApplicantsPage()

    await waitFor(() => {
      expect(screen.getByText('404')).toBeInTheDocument()
      expect(screen.getByText('Không tìm thấy tin tuyển dụng')).toBeInTheDocument()
    })
  })

  it('renders own draft job', async () => {
    const draftJob: Job = { ...mockJob, status: 'draft' }
    mockedGetMyJobById.mockResolvedValue(draftJob)
    mockedGetApplicationsByJob.mockResolvedValue([])

    renderJobApplicantsPage()

    await waitFor(() => {
      expect(mockedGetMyJobById).toHaveBeenCalledWith('job-1')
      expect(screen.getByText('Senior Frontend Engineer')).toBeInTheDocument()
      expect(screen.getByText('Bản nháp')).toBeInTheDocument()
    })
  })

  it('retries the request after a failure', async () => {
    const error = new Error('Server Error')
    Object.assign(error, { response: { status: 500 } })
    mockedGetMyJobById.mockRejectedValueOnce(error).mockResolvedValueOnce(mockJob)
    mockedGetApplicationsByJob.mockResolvedValue(mockApplications)

    renderJobApplicantsPage()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Thử lại/i })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

await waitFor(() => {
      expect(mockedGetMyJobById).toHaveBeenCalledTimes(2)
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
    })
  })
})
