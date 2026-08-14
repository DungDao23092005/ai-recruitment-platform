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
  },
  {
    id: 'app-2',
    candidate_id: '22222222-2222-2222-2222-222222222222',
    job_id: 'job-1',
    status: 'shortlisted',
    created_at: '2026-01-21T00:00:00Z',
    updated_at: '2026-01-22T00:00:00Z',
  },
]

vi.mock('@/api/jobs', () => ({
  getJobs: vi.fn(),
  getJobById: vi.fn(),
}))

vi.mock('@/api/applications', () => ({
  applyJob: vi.fn(),
  getApplicationsByJob: vi.fn(),
}))

const mockedGetJobById = vi.mocked(jobsApi.getJobById)
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
    mockedGetJobById.mockResolvedValue(mockJob)
    mockedGetApplicationsByJob.mockResolvedValue(mockApplications)

    renderJobApplicantsPage()

    await waitFor(() => {
      expect(mockedGetJobById).toHaveBeenCalledWith('job-1')
      expect(mockedGetApplicationsByJob).toHaveBeenCalledWith('job-1')
    })
  })

  it('shows loading state while fetching', async () => {
    let resolveJob!: (value: Job) => void
    let resolveApps!: (value: Application[]) => void
    mockedGetJobById.mockReturnValue(
      new Promise((r) => {
        resolveJob = r
      }),
    )
    mockedGetApplicationsByJob.mockReturnValue(
      new Promise((r) => {
        resolveApps = r
      }),
    )

    renderJobApplicantsPage()

    await waitFor(() => {
      expect(screen.getByLabelText('Loading')).toBeInTheDocument()
    })

    resolveJob(mockJob)
    resolveApps(mockApplications)
  })

  it('renders the job title and applicants', async () => {
    mockedGetJobById.mockResolvedValue(mockJob)
    mockedGetApplicationsByJob.mockResolvedValue(mockApplications)

    renderJobApplicantsPage()

    await waitFor(() => {
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
      expect(screen.getByText('Candidate 11111111')).toBeInTheDocument()
      expect(screen.getByText('Candidate 22222222')).toBeInTheDocument()
    })
  })

  it('renders candidate statuses', async () => {
    mockedGetJobById.mockResolvedValue(mockJob)
    mockedGetApplicationsByJob.mockResolvedValue(mockApplications)

    renderJobApplicantsPage()

    await waitFor(() => {
      expect(screen.getByText('Applied')).toBeInTheDocument()
      expect(screen.getByText('Shortlisted')).toBeInTheDocument()
    })
  })

  it('opens the status update modal for an applicant', async () => {
    mockedGetJobById.mockResolvedValue(mockJob)
    mockedGetApplicationsByJob.mockResolvedValue(mockApplications)

    renderJobApplicantsPage()

    await waitFor(() => {
      expect(
        screen.getByRole('button', {
          name: /Update status for application app-1/i,
        }),
      ).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', {
        name: /Update status for application app-1/i,
      }),
    )

    expect(
      screen.getByRole('dialog', { name: 'Update application status' }),
    ).toBeInTheDocument()
  })

  it('shows empty state when there are no applicants', async () => {
    mockedGetJobById.mockResolvedValue(mockJob)
    mockedGetApplicationsByJob.mockResolvedValue([])

    renderJobApplicantsPage()

    await waitFor(() => {
      expect(
        screen.getByText('No applicants yet.'),
      ).toBeInTheDocument()
    })
  })

  it('shows an error state when the API fails', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Server error' } },
    })
    mockedGetJobById.mockResolvedValue(mockJob)
    mockedGetApplicationsByJob.mockRejectedValue(error)

    renderJobApplicantsPage()

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument()
    })
  })

  it('shows 404 when job is not found', async () => {
    const error = new Error('Not Found')
    Object.assign(error, { response: { status: 404 } })
    mockedGetJobById.mockRejectedValue(error)

    renderJobApplicantsPage()

    await waitFor(() => {
      expect(screen.getByText('404')).toBeInTheDocument()
      expect(screen.getByText('Job not found')).toBeInTheDocument()
    })
  })
})