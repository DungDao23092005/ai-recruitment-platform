import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { CandidateApplicationsPage } from './CandidateApplicationsPage'
import * as applicationsApi from '@/api/applications'
import type { ApplicationWithJob } from '@/types/application'

vi.mock('@/api/applications', () => ({
  applyJob: vi.fn(),
  withdrawApplication: vi.fn(),
  getApplicationsByJob: vi.fn(),
  getMyApplications: vi.fn(),
  getMyApplication: vi.fn(),
  getMyApplicationTimeline: vi.fn(),
}))

const mockedGetMyApplications = vi.mocked(applicationsApi.getMyApplications)
const mockedGetMyApplication = vi.mocked(applicationsApi.getMyApplication)
const mockedWithdrawApplication = vi.mocked(
  applicationsApi.withdrawApplication,
)
const mockedGetTimeline = vi.mocked(applicationsApi.getMyApplicationTimeline)
const scrollIntoViewMock = vi.fn()

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
  {
    id: 'app-3',
    job_id: 'job-3',
    job_title: 'Data Analyst',
    company_name: 'ABC Technology',
    status: 'accepted',
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
  },
]

function renderPage(
  initialEntry = '/candidate/applications',
  withTargetLink = false,
) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/candidate/applications"
          element={
            <>
              <CandidateApplicationsPage />
              {withTargetLink ? (
                <Link to="/candidate/applications?id=app-5">
                  Next target
                </Link>
              ) : null}
            </>
          }
        />
        <Route path="/candidate/jobs" element={<div>Jobs Page</div>} />
        <Route path="/candidate/jobs/:id" element={<div>Job Detail</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

async function renderWithData() {
  mockedGetMyApplications.mockResolvedValue(mockApplications)
  renderPage()
  await screen.findByText('Backend Developer')
}

describe('CandidateApplicationsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedGetMyApplication.mockReset()
    mockedGetTimeline.mockResolvedValue([])
    Element.prototype.scrollIntoView = scrollIntoViewMock
    scrollIntoViewMock.mockClear()
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
    await renderWithData()

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

  it('filters applications by status', async () => {
    await renderWithData()

    expect(screen.getByText('Data Analyst')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Đang xử lý/i }))

    expect(screen.getByText('Backend Developer')).toBeInTheDocument()
    expect(screen.getByText('Frontend Engineer')).toBeInTheDocument()
    expect(screen.queryByText('Data Analyst')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Đã kết thúc/i }))

    expect(screen.getByText('Data Analyst')).toBeInTheDocument()
    expect(screen.queryByText('Backend Developer')).not.toBeInTheDocument()
  })

  it('searches by job title and company name', async () => {
    await renderWithData()

    fireEvent.change(
      screen.getByRole('searchbox', {
        name: /Tìm kiếm đơn ứng tuyển/i,
      }),
      { target: { value: 'xyz' } },
    )

    expect(screen.getByText('Frontend Engineer')).toBeInTheDocument()
    expect(screen.queryByText('Backend Developer')).not.toBeInTheDocument()

    fireEvent.change(
      screen.getByRole('searchbox', {
        name: /Tìm kiếm đơn ứng tuyển/i,
      }),
      { target: { value: 'abc technology' } },
    )

    expect(screen.getByText('Backend Developer')).toBeInTheDocument()
    expect(screen.getByText('Data Analyst')).toBeInTheDocument()
    expect(screen.queryByText('Frontend Engineer')).not.toBeInTheDocument()
  })

  it('distinguishes a no-match state from a genuinely empty list', async () => {
    await renderWithData()

    fireEvent.change(
      screen.getByRole('searchbox', {
        name: /Tìm kiếm đơn ứng tuyển/i,
      }),
      { target: { value: 'no-such-role' } },
    )

    expect(
      screen.getByText('Không tìm thấy đơn ứng tuyển phù hợp'),
    ).toBeInTheDocument()
    expect(
      screen.queryByText('Bạn chưa có đơn ứng tuyển'),
    ).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Xóa bộ lọc/i }))

    expect(screen.getByText('Backend Developer')).toBeInTheDocument()
    expect(screen.getByText('Data Analyst')).toBeInTheDocument()
  })

  it('refreshes and shows the withdrawn status after withdrawing', async () => {
    mockedGetMyApplications
      .mockResolvedValueOnce(mockApplications)
      .mockResolvedValueOnce([
        { ...mockApplications[0], status: 'withdrawn' },
        mockApplications[1],
        mockApplications[2],
      ])
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
    fireEvent.click(screen.getByRole('button', { name: /Xác nhận rút đơn/i }))

    await waitFor(() => {
      expect(mockedWithdrawApplication).toHaveBeenCalledWith('app-1')
      expect(mockedGetMyApplications).toHaveBeenCalledTimes(2)
      expect(screen.getByText('Đã rút')).toBeInTheDocument()
    })
  })
})
