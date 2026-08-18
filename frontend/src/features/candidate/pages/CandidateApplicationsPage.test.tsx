import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { CandidateApplicationsPage } from './CandidateApplicationsPage'
import * as applicationsApi from '@/api/applications'
import type { ApplicationWithJob } from '@/types/application'

vi.mock('@/api/applications', () => ({
  applyJob: vi.fn(),
  withdrawApplication: vi.fn(),
  getApplicationsByJob: vi.fn(),
  getMyApplications: vi.fn(),
}))

const mockedGetMyApplications = vi.mocked(applicationsApi.getMyApplications)
const mockedWithdrawApplication = vi.mocked(
  applicationsApi.withdrawApplication,
)

const mockApplications: ApplicationWithJob[] = [
  {
    id: 'app-1',
    job_id: 'job-1',
    job_title: 'Backend Developer',
    company_name: 'ABC Technology',
    status: 'applied',
    created_at: '2026-08-18T00:00:00Z',
    updated_at: '2026-08-18T00:00:00Z',
  },
  {
    id: 'app-2',
    job_id: 'job-2',
    job_title: 'Frontend Engineer',
    company_name: 'XYZ Corp',
    status: 'under_review',
    created_at: '2026-08-10T00:00:00Z',
    updated_at: '2026-08-10T00:00:00Z',
  },
]

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/candidate/applications']}>
      <Routes>
        <Route
          path="/candidate/applications"
          element={<CandidateApplicationsPage />}
        />
        <Route path="/candidate/jobs" element={<div>Jobs Page</div>} />
        <Route path="/candidate/jobs/:id" element={<div>Job Detail</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('CandidateApplicationsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls getMyApplications on mount', async () => {
    mockedGetMyApplications.mockResolvedValue([])

    renderPage()

    await waitFor(() => {
      expect(mockedGetMyApplications).toHaveBeenCalledWith({
        skip: 0,
        limit: 10,
      })
    })
  })

  it('shows the loading state while fetching', async () => {
    let resolve!: (value: ApplicationWithJob[]) => void
    mockedGetMyApplications.mockReturnValue(
      new Promise((r) => {
        resolve = r
      }),
    )

    const { container } = renderPage()

    await waitFor(() => {
      expect(container.querySelector('.animate-pulse')).not.toBeNull()
    })

    resolve([])
  })

  it('renders application cards on success', async () => {
    mockedGetMyApplications.mockResolvedValue(mockApplications)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Backend Developer')).toBeInTheDocument()
      expect(screen.getByText('Frontend Engineer')).toBeInTheDocument()
    })
    expect(screen.getByText('Đã nộp')).toBeInTheDocument()
    expect(screen.getByText('Đang xem xét')).toBeInTheDocument()
  })

  it('links each application to /candidate/jobs/:id', async () => {
    mockedGetMyApplications.mockResolvedValue(mockApplications)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Backend Developer')).toBeInTheDocument()
    })

    const links = screen.getAllByRole('link', { name: /Xem việc làm/i })
    expect(links[0]).toHaveAttribute('href', '/candidate/jobs/job-1')
    expect(links[1]).toHaveAttribute('href', '/candidate/jobs/job-2')
  })

  it('shows the empty state with a CTA to the candidate jobs route', async () => {
    mockedGetMyApplications.mockResolvedValue([])

    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText('Bạn chưa có đơn ứng tuyển'),
      ).toBeInTheDocument()
    })

    const link = screen.getByRole('link', { name: /Khám phá việc làm/i })
    expect(link).toHaveAttribute('href', '/candidate/jobs')
  })

  it('shows a friendly error and retries', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Server error' } },
    })
    mockedGetMyApplications
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce(mockApplications)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(screen.getByText('Backend Developer')).toBeInTheDocument()
    })
  })

  it('updates the status badge to withdrawn after withdrawing', async () => {
    mockedGetMyApplications.mockResolvedValue(mockApplications)
    mockedWithdrawApplication.mockResolvedValue({
      id: 'app-1',
      candidate_id: 'candidate-1',
      job_id: 'job-1',
      status: 'withdrawn',
      created_at: '2026-08-18T00:00:00Z',
      updated_at: '2026-08-18T00:00:00Z',
      candidate: null,
    } as never)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Backend Developer')).toBeInTheDocument()
    })

    fireEvent.click(screen.getAllByRole('button', { name: /Rút đơn/i })[0])

    await waitFor(() => {
      expect(mockedWithdrawApplication).toHaveBeenCalledWith('app-1')
      expect(screen.getByText('Đã rút')).toBeInTheDocument()
    })
    const remainingWithdrawButtons = screen.getAllByRole('button', {
      name: /Rút đơn/i,
    })
    expect(remainingWithdrawButtons).toHaveLength(1)
  })
})