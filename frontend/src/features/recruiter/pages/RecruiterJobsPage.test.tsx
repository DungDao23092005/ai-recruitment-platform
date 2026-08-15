import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { RecruiterJobsPage } from './RecruiterJobsPage'
import { getJobs, getMyJobs } from '@/api/jobs'
import type { Job } from '@/types/job'

const mockDraftJob: Job = {
  id: 'job-draft-1',
  company_id: 'company-1',
  company_name: null,
  title: 'Senior Frontend Engineer',
  description: 'Build modern web applications with React.',
  status: 'draft',
  job_type: 'full_time',
  workplace_type: 'remote',
  location: 'Ho Chi Minh City',
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-01-15T00:00:00Z',
}

const mockPublishedJob: Job = {
  id: 'job-published-1',
  company_id: 'company-1',
  company_name: null,
  title: 'Backend Engineer',
  description: 'Build robust APIs.',
  status: 'published',
  job_type: 'full_time',
  workplace_type: 'on_site',
  location: 'Ha Noi',
  created_at: '2026-02-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
}

vi.mock('@/api/jobs', () => ({
  getMyJobs: vi.fn(),
  getJobs: vi.fn(),
}))

const mockedGetMyJobs = vi.mocked(getMyJobs)
const mockedGetJobs = vi.mocked(getJobs)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('RecruiterJobsPage', () => {
  it('calls getMyJobs() on mount', async () => {
    mockedGetMyJobs.mockResolvedValue([])

    render(
      <MemoryRouter>
        <RecruiterJobsPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(mockedGetMyJobs).toHaveBeenCalledWith({ skip: 0, limit: 50 })
    })
  })

  it('renders draft jobs', async () => {
    mockedGetMyJobs.mockResolvedValue([mockDraftJob])

    render(
      <MemoryRouter>
        <RecruiterJobsPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Senior Frontend Engineer')).toBeInTheDocument()
      expect(screen.getByText('Bản nháp')).toBeInTheDocument()
    })
  })

  it('renders published jobs', async () => {
    mockedGetMyJobs.mockResolvedValue([mockPublishedJob])

    render(
      <MemoryRouter>
        <RecruiterJobsPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Backend Engineer')).toBeInTheDocument()
      expect(screen.getByText('Đã đăng')).toBeInTheDocument()
    })
  })

  it('renders multiple jobs', async () => {
    mockedGetMyJobs.mockResolvedValue([mockDraftJob, mockPublishedJob])

    render(
      <MemoryRouter>
        <RecruiterJobsPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Senior Frontend Engineer')).toBeInTheDocument()
      expect(screen.getByText('Backend Engineer')).toBeInTheDocument()
    })
  })

  it('shows the Vietnamese empty state when there are no jobs', async () => {
    mockedGetMyJobs.mockResolvedValue([])

    render(
      <MemoryRouter>
        <RecruiterJobsPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Chưa có tin tuyển dụng')).toBeInTheDocument()
      expect(
        screen.getByText(
          'Tạo tin tuyển dụng đầu tiên của bạn để bắt đầu nhận hồ sơ ứng viên.',
        ),
      ).toBeInTheDocument()
    })
  })

  it('shows a friendly error when loading fails', async () => {
    const error = new Error('Network Error')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Không thể tải tin tuyển dụng.' } },
    })
    mockedGetMyJobs.mockRejectedValueOnce(error)

    render(
      <MemoryRouter>
        <RecruiterJobsPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Không thể tải tin tuyển dụng.',
      )
    })
  })

  it('retries loading when the retry button is clicked', async () => {
    const error = new Error('Network Error')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Không thể tải tin tuyển dụng.' } },
    })
    mockedGetMyJobs.mockRejectedValueOnce(error)

    render(
      <MemoryRouter>
        <RecruiterJobsPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    mockedGetMyJobs.mockResolvedValueOnce([mockPublishedJob])
    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(mockedGetMyJobs).toHaveBeenCalledTimes(2)
      expect(screen.getByText('Backend Engineer')).toBeInTheDocument()
    })
  })

  it('does not use the public getJobs() API', async () => {
    mockedGetMyJobs.mockResolvedValue([mockPublishedJob])

    render(
      <MemoryRouter>
        <RecruiterJobsPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Backend Engineer')).toBeInTheDocument()
    })
    expect(mockedGetJobs).not.toHaveBeenCalled()
  })
})