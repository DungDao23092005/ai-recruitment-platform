import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { RecruiterPortalPage } from './RecruiterPortalPage'
import { getRecruiterMetrics } from '@/api/metrics'
import type { RecruiterMetrics } from '@/types/metrics'
import { isAxiosError } from 'axios'

const mockSuccessMetrics: RecruiterMetrics = {
  total_jobs: 5,
  total_applications: 12,
  jobs_by_status: [
    { status: 'published', count: 3 },
    { status: 'draft', count: 2 },
  ],
  applications_by_status: [
    { status: 'applied', count: 5 },
    { status: 'under_review', count: 3 },
    { status: 'shortlisted', count: 2 },
    { status: 'interviewing', count: 1 },
    { status: 'accepted', count: 1 },
    { status: 'rejected', count: 0 },
    { status: 'withdrawn', count: 0 },
  ],
}

const mockEmptyMetrics: RecruiterMetrics = {
  total_jobs: 0,
  total_applications: 0,
  jobs_by_status: [],
  applications_by_status: [],
}

vi.mock('@/api/metrics', () => ({
  getRecruiterMetrics: vi.fn(),
}))

const mockedGetRecruiterMetrics = vi.mocked(getRecruiterMetrics)

beforeEach(() => {
  vi.clearAllMocks()
})

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

function createAxiosError(status: number, message = 'Request failed') {
  const error = new Error(message)
  Object.assign(error, {
    isAxiosError: true,
    response: { status, data: { detail: message } },
    config: {},
  })
  return error
}

describe('RecruiterPortalPage', () => {
  it('NO COMPANY — 404: shows no-company empty state', async () => {
    const error = createAxiosError(404, 'Not Found')
    mockedGetRecruiterMetrics.mockRejectedValueOnce(error)

    renderWithRouter(<RecruiterPortalPage />)

    await waitFor(() => {
      expect(screen.getByText('Chưa có công ty')).toBeInTheDocument()
    })

    expect(screen.getByText('Hãy tạo công ty để bắt đầu tuyển dụng.')).toBeInTheDocument()

    const createCompanyButton = screen.getByRole('button', { name: /Tạo công ty/i })
    expect(createCompanyButton).toBeInTheDocument()
    expect(createCompanyButton.closest('a')).toHaveAttribute('href', '/recruiter/company')

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText('Request failed with status code 404')).not.toBeInTheDocument()
  })

  it('EMPTY JOBS — 200 + zero jobs: shows empty jobs state', async () => {
    mockedGetRecruiterMetrics.mockResolvedValueOnce(mockEmptyMetrics)

    renderWithRouter(<RecruiterPortalPage />)

    await waitFor(() => {
      expect(screen.getByText('Chưa có tin tuyển dụng')).toBeInTheDocument()
    })

    expect(screen.getByText('Hãy tạo tin tuyển dụng đầu tiên.')).toBeInTheDocument()

    const createJobButton = screen.getByRole('button', { name: /Tạo tin tuyển dụng/i })
    expect(createJobButton).toBeInTheDocument()
    expect(createJobButton.closest('a')).toHaveAttribute('href', '/recruiter/jobs/new')

    expect(screen.queryByText('Tổng tin tuyển dụng')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('SUCCESS — jobs exist: renders dashboard with metrics', async () => {
    mockedGetRecruiterMetrics.mockResolvedValueOnce(mockSuccessMetrics)

    renderWithRouter(<RecruiterPortalPage />)

    await waitFor(() => {
      expect(screen.getByText('Tổng tin tuyển dụng')).toBeInTheDocument()
      // The metric card shows "5" for total_jobs
      expect(screen.getByText('Tổng tin tuyển dụng').closest('div')?.querySelector('p.font-display')).toHaveTextContent('5')
    })

    expect(screen.getByText('Đang tuyển')).toBeInTheDocument()
    expect(screen.getByText('Tổng ứng tuyển')).toBeInTheDocument()
    // The metric card shows "12" for total_applications
    expect(screen.getByText('Tổng ứng tuyển').closest('div')?.querySelector('p.font-display')).toHaveTextContent('12')

    expect(screen.getByText('Tin tuyển dụng theo trạng thái')).toBeInTheDocument()
    expect(screen.getByText('published')).toBeInTheDocument()
    expect(screen.getByText('draft')).toBeInTheDocument()

    expect(screen.getByText('Quy trình ứng tuyển')).toBeInTheDocument()
    expect(screen.getByText('Thao tác nhanh')).toBeInTheDocument()
  })

  it('FATAL ERROR — 500: shows ErrorBanner with retry', async () => {
    const error = createAxiosError(500, 'Internal Server Error')
    mockedGetRecruiterMetrics.mockRejectedValueOnce(error)

    renderWithRouter(<RecruiterPortalPage />)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
      expect(screen.getByRole('alert')).toHaveTextContent('Internal Server Error')
    })

    const retryButton = screen.getByRole('button', { name: /Thử lại/i })
    expect(retryButton).toBeInTheDocument()

    expect(screen.queryByText('Chưa có công ty')).not.toBeInTheDocument()
  })

  it('NETWORK ERROR — non-HTTP error: shows ErrorBanner', async () => {
    const error = new Error('Network Error')
    mockedGetRecruiterMetrics.mockRejectedValueOnce(error)

    renderWithRouter(<RecruiterPortalPage />)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
      expect(screen.getByRole('alert')).toHaveTextContent('Network Error')
    })

    expect(screen.queryByText('Chưa có công ty')).not.toBeInTheDocument()
  })

  it('403 FORBIDDEN: shows ErrorBanner, not no-company state', async () => {
    const error = createAxiosError(403, 'Forbidden')
    mockedGetRecruiterMetrics.mockRejectedValueOnce(error)

    renderWithRouter(<RecruiterPortalPage />)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    expect(screen.queryByText('Chưa có công ty')).not.toBeInTheDocument()
  })

  it('401 UNAUTHORIZED: shows ErrorBanner, not no-company state', async () => {
    const error = createAxiosError(401, 'Unauthorized')
    mockedGetRecruiterMetrics.mockRejectedValueOnce(error)

    renderWithRouter(<RecruiterPortalPage />)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    expect(screen.queryByText('Chưa có công ty')).not.toBeInTheDocument()
  })
})