import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { ApplicantList } from './ApplicantList'
import apiClient from '@/api/client'
import type { Application } from '@/types/application'

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

vi.mock('@/api/client', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
    patch: vi.fn(),
  },
}))

const mockedPatch = vi.mocked(apiClient.patch)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ApplicantList', () => {
  it('renders applicant information', () => {
    render(<ApplicantList applications={mockApplications} />)

    expect(
      screen.getByText('Candidate 11111111'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Candidate 22222222'),
    ).toBeInTheDocument()
  })

  it('renders a status badge for each applicant', () => {
    render(<ApplicantList applications={mockApplications} />)

    expect(screen.getByText('Applied')).toBeInTheDocument()
    expect(screen.getByText('Shortlisted')).toBeInTheDocument()
  })

  it('renders submitted time when available', () => {
    render(<ApplicantList applications={mockApplications} />)

    const submittedDates = screen.getAllByText(/Jan 20, 2026|Jan 21, 2026/i)
    expect(submittedDates.length).toBeGreaterThan(0)
  })

  it('shows empty state when there are no applicants', () => {
    render(<ApplicantList applications={[]} />)

    expect(screen.getByText('No applicants yet.')).toBeInTheDocument()
  })

  it('opens the status update modal for an applicant', () => {
    render(<ApplicantList applications={mockApplications} />)

    fireEvent.click(
      screen.getByRole('button', {
        name: /Update status for application app-1/i,
      }),
    )

    expect(
      screen.getByRole('dialog', { name: 'Update application status' }),
    ).toBeInTheDocument()
  })

  it('calls onStatusChange when an application status is updated', async () => {
    const onStatusChange = vi.fn()
    const updated: Application = {
      ...mockApplications[0],
      status: 'under_review',
    }
    mockedPatch.mockResolvedValue(updated as never)

    render(
      <ApplicantList
        applications={mockApplications}
        onStatusChange={onStatusChange}
      />,
    )

    fireEvent.click(
      screen.getByRole('button', {
        name: /Update status for application app-1/i,
      }),
    )

    const statusSelect = screen.getByLabelText('Status')
    fireEvent.change(statusSelect, { target: { value: 'under_review' } })

    fireEvent.click(screen.getByRole('button', { name: /Save status/i }))

    await waitFor(() => {
      expect(mockedPatch).toHaveBeenCalledWith('/applications/app-1/status', {
        status: 'under_review',
      })
      expect(onStatusChange).toHaveBeenCalledWith(updated)
    })
  })
})