import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { ApplicationCard } from './ApplicationCard'
import * as applicationsApi from '@/api/applications'
import type { ApplicationWithJob } from '@/types/application'

vi.mock('@/api/applications', () => ({
  applyJob: vi.fn(),
  withdrawApplication: vi.fn(),
  getApplicationsByJob: vi.fn(),
  getMyApplications: vi.fn(),
}))

const mockedWithdrawApplication = vi.mocked(
  applicationsApi.withdrawApplication,
)

const mockApplication: ApplicationWithJob = {
  id: 'app-1',
  job_id: 'job-1',
  job_title: 'Backend Developer',
  company_name: 'ABC Technology',
  status: 'applied',
  created_at: '2026-08-18T00:00:00Z',
  updated_at: '2026-08-18T00:00:00Z',
}

function renderCard(overrides: Partial<ApplicationWithJob> = {}) {
  return render(
    <MemoryRouter>
      <ApplicationCard
        application={{ ...mockApplication, ...overrides }}
        onWithdrawn={vi.fn()}
      />
    </MemoryRouter>,
  )
}

describe('ApplicationCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders job title, company and application date', () => {
    renderCard()

    expect(screen.getByText('Backend Developer')).toBeInTheDocument()
    expect(screen.getByText('Công ty ABC Technology')).toBeInTheDocument()
    expect(screen.getByText(/Ứng tuyển:/)).toBeInTheDocument()
  })

  it('renders the existing status badge', () => {
    renderCard()

    expect(screen.getByText('Đã nộp')).toBeInTheDocument()
  })

  it('links to the candidate job detail route', () => {
    renderCard()

    const link = screen.getByRole('link', { name: /Xem việc làm/i })
    expect(link).toHaveAttribute('href', '/candidate/jobs/job-1')
  })

  it.each(['applied', 'under_review', 'shortlisted', 'interviewing'])(
    'shows the withdraw button for %s',
    (status) => {
      renderCard({ status: status as ApplicationWithJob['status'] })

      expect(screen.getByRole('button', { name: /Rút đơn/i })).toBeInTheDocument()
    },
  )

  it.each(['accepted', 'rejected', 'withdrawn'])(
    'hides the withdraw button for %s',
    (status) => {
      renderCard({ status: status as ApplicationWithJob['status'] })

      expect(
        screen.queryByRole('button', { name: /Rút đơn/i }),
      ).not.toBeInTheDocument()
    },
  )

  it('withdraws and notifies the parent on success', async () => {
    mockedWithdrawApplication.mockResolvedValue({
      id: 'app-1',
      candidate_id: 'candidate-1',
      job_id: 'job-1',
      status: 'withdrawn',
      created_at: '2026-08-18T00:00:00Z',
      updated_at: '2026-08-18T00:00:00Z',
      candidate: null,
    } as never)
    const onWithdrawn = vi.fn()
    render(
      <MemoryRouter>
        <ApplicationCard application={mockApplication} onWithdrawn={onWithdrawn} />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: /Rút đơn/i }))

    await waitFor(() => {
      expect(mockedWithdrawApplication).toHaveBeenCalledWith('app-1')
      expect(onWithdrawn).toHaveBeenCalledWith('app-1')
    })
  })

  it('shows an error when withdraw fails', async () => {
    mockedWithdrawApplication.mockRejectedValue(new Error('boom'))
    const onWithdrawn = vi.fn()

    render(
      <MemoryRouter>
        <ApplicationCard application={mockApplication} onWithdrawn={onWithdrawn} />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: /Rút đơn/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    expect(onWithdrawn).not.toHaveBeenCalled()
  })
})