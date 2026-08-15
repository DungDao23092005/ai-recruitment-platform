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
      screen.getByText('Ứng viên 11111111'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Ứng viên 22222222'),
    ).toBeInTheDocument()
  })

  it('renders a status badge for each applicant', () => {
    render(<ApplicantList applications={mockApplications} />)

    expect(screen.getByText('Đã nộp')).toBeInTheDocument()
    expect(screen.getByText('Lọt vòng ngắn')).toBeInTheDocument()
  })

  it('renders submitted time when available', () => {
    render(<ApplicantList applications={mockApplications} />)

    const submittedDates = screen.getAllByText(/20 thg 1, 2026|21 thg 1, 2026/)
    expect(submittedDates.length).toBeGreaterThan(0)
  })

  it('renders without crashing when there are no applicants', () => {
    const { container } = render(<ApplicantList applications={[]} />)

    expect(container.firstChild).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('opens the status update modal for an applicant', () => {
    render(<ApplicantList applications={mockApplications} />)

    fireEvent.click(
      screen.getByRole('button', {
        name: /Cập nhật trạng thái cho đơn ứng tuyển app-1/i,
      }),
    )

    expect(
      screen.getByRole('dialog', { name: 'Cập nhật trạng thái đơn ứng tuyển' }),
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
        name: /Cập nhật trạng thái cho đơn ứng tuyển app-1/i,
      }),
    )

    const statusSelect = screen.getByLabelText('Trạng thái')
    fireEvent.change(statusSelect, { target: { value: 'under_review' } })

    fireEvent.click(screen.getByRole('button', { name: /Lưu trạng thái/i }))

    await waitFor(() => {
      expect(mockedPatch).toHaveBeenCalledWith('/applications/app-1/status', {
        status: 'under_review',
      })
      expect(onStatusChange).toHaveBeenCalledWith(updated)
    })
  })
})