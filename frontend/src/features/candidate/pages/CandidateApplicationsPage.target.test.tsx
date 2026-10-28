import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CandidateApplicationsPage } from './CandidateApplicationsPage'
import * as applicationsApi from '@/api/applications'
import { getFriendlyErrorMessage } from '@/utils/errors'
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
]

const targetApplication: ApplicationWithJob = {
  id: 'app-4',
  job_id: 'job-4',
  job_title: 'Product Designer',
  company_name: 'Target Corp',
  status: 'offered',
  created_at: '2026-06-01T00:00:00Z',
  updated_at: '2026-06-01T00:00:00Z',
}

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

describe('CandidateApplicationsPage target navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedGetMyApplication.mockReset()
    mockedGetTimeline.mockResolvedValue([])
    Element.prototype.scrollIntoView = scrollIntoViewMock
    scrollIntoViewMock.mockClear()
  })

  it('highlights an application that is already in the initial list', async () => {
    mockedGetMyApplications.mockResolvedValue(mockApplications)

    renderPage('/candidate/applications?id=app-1')

    await waitFor(() => {
      expect(screen.getByText('Backend Developer')).toBeInTheDocument()
      expect(
        document.getElementById('application-app-1'),
      ).toHaveAttribute('data-highlighted', 'true')
    })
    expect(mockedGetMyApplication).not.toHaveBeenCalled()
    expect(scrollIntoViewMock).toHaveBeenCalled()
  })

  it('waits for the initial list before fetching a missing target', async () => {
    let resolveList!: (value: ApplicationWithJob[]) => void
    mockedGetMyApplications.mockReturnValue(
      new Promise((resolve) => {
        resolveList = resolve
      }),
    )
    mockedGetMyApplication.mockResolvedValue(targetApplication)

    renderPage('/candidate/applications?id=app-4')

    await waitFor(() => {
      expect(mockedGetMyApplications).toHaveBeenCalled()
    })
    expect(mockedGetMyApplication).not.toHaveBeenCalled()

    resolveList(mockApplications)

    await waitFor(() => {
      expect(mockedGetMyApplication).toHaveBeenCalledWith('app-4')
    })
  })

  it('fetches, appends and highlights a target outside the initial list', async () => {
    mockedGetMyApplications.mockResolvedValue(mockApplications)
    mockedGetMyApplication.mockResolvedValue(targetApplication)

    renderPage('/candidate/applications?id=app-4')

    await waitFor(() => {
      expect(screen.getByText('Product Designer')).toBeInTheDocument()
      expect(
        document.getElementById('application-app-4'),
      ).toHaveAttribute('data-highlighted', 'true')
    })

    expect(mockedGetMyApplication).toHaveBeenCalledWith('app-4')
    expect(mockedGetMyApplications).toHaveBeenCalledTimes(1)
    expect(document.querySelector('[aria-pressed="true"]')).toHaveTextContent(
      'Tất cả',
    )
  })

  it('keeps the list usable when the target application is not found', async () => {
    const notFoundError = Object.assign(new Error('Not found'), {
      response: { status: 404, data: { detail: 'Application not found' } },
    })
    mockedGetMyApplications.mockResolvedValue(mockApplications)
    mockedGetMyApplication.mockRejectedValue(notFoundError)

    renderPage('/candidate/applications?id=missing')

    await waitFor(() => {
      expect(
        screen.getByText('Đơn ứng tuyển này không tồn tại hoặc đã bị xóa.'),
      ).toBeInTheDocument()
    })
    expect(screen.getByText('Backend Developer')).toBeInTheDocument()
    expect(mockedGetMyApplications).toHaveBeenCalledTimes(1)
  })

  it('shows a generic message for a target request failure', async () => {
    const serverError = Object.assign(new Error('Server error'), {
      response: { status: 500, data: { detail: 'Internal Server Error' } },
    })
    mockedGetMyApplications.mockResolvedValue(mockApplications)
    mockedGetMyApplication.mockRejectedValue(serverError)

    renderPage('/candidate/applications?id=app-4')

    await waitFor(() => {
      expect(
        screen.getByText(getFriendlyErrorMessage(serverError)),
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByText('Đơn ứng tuyển này không tồn tại hoặc đã bị xóa.'),
    ).not.toBeInTheDocument()
    expect(screen.getByText('Backend Developer')).toBeInTheDocument()
  })

  it('ignores a stale target response after the target changes', async () => {
    let resolveFirst!: (value: ApplicationWithJob) => void
    const newTarget: ApplicationWithJob = {
      ...targetApplication,
      id: 'app-5',
      job_title: 'New Target Role',
    }
    mockedGetMyApplications.mockResolvedValue([])
    mockedGetMyApplication.mockImplementation((applicationId) => {
      if (applicationId === 'app-4') {
        return new Promise((resolve) => {
          resolveFirst = resolve
        })
      }
      return Promise.resolve(newTarget)
    })

    renderPage('/candidate/applications?id=app-4', true)

    await waitFor(() => {
      expect(mockedGetMyApplication).toHaveBeenCalledWith('app-4')
    })

    fireEvent.click(screen.getByRole('link', { name: 'Next target' }))

    await waitFor(() => {
      expect(screen.getByText('New Target Role')).toBeInTheDocument()
    })

    resolveFirst(targetApplication)

    await waitFor(() => {
      expect(screen.queryByText('Product Designer')).not.toBeInTheDocument()
    })
  })
})
