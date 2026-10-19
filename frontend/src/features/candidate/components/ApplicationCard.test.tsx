import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { ApplicationCard } from './ApplicationCard'
import * as applicationsApi from '@/api/applications'
import * as interviewsApi from '@/api/interviews'
import type { ApplicationWithJob, Interview } from '@/types/application'

vi.mock('@/api/applications', () => ({
  applyJob: vi.fn(),
  withdrawApplication: vi.fn(),
  getApplicationsByJob: vi.fn(),
  getMyApplications: vi.fn(),
  getMyApplicationTimeline: vi.fn(),
}))

vi.mock('@/api/interviews', () => ({
  candidateActionInterview: vi.fn(),
}))

const mockedWithdrawApplication = vi.mocked(
  applicationsApi.withdrawApplication,
)

const mockedGetTimeline = vi.mocked(applicationsApi.getMyApplicationTimeline)

const mockedCandidateActionInterview = vi.mocked(
  interviewsApi.candidateActionInterview,
)

const mockInterview: Interview = {
  id: 'interview-1',
  application_id: 'app-1',
  scheduled_at: '2026-08-20T10:00:00Z',
  duration_minutes: 60,
  interview_type: 'technical',
  meeting_url: null,
  location: 'Online',
  notes: 'Technical interview',
  candidate_notes: null,
  status: 'scheduled',
  created_at: '2026-08-18T00:00:00Z',
  updated_at: '2026-08-18T00:00:00Z',
}

const mockApplication: ApplicationWithJob = {
  id: 'app-1',
  job_id: 'job-1',
  job_title: 'Backend Developer',
  company_name: 'ABC Technology',
  status: 'interviewing',
  created_at: '2026-08-18T00:00:00Z',
  updated_at: '2026-08-18T00:00:00Z',
  interviews: [mockInterview],
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
    mockedGetTimeline.mockResolvedValue([])
  })

  it('renders job title, company and application date', () => {
    renderCard()

    expect(screen.getByText('Backend Developer')).toBeInTheDocument()
    expect(screen.getByText('Công ty ABC Technology')).toBeInTheDocument()
    expect(screen.getByText(/Ứng tuyển:/)).toBeInTheDocument()
  })

  it('renders the existing status badge and the progress tracker', () => {
    renderCard()

    expect(screen.getByText('Đang phỏng vấn')).toBeInTheDocument()
    expect(
      screen.getByRole('group', { name: 'Tiến trình ứng tuyển' }),
    ).toBeInTheDocument()
  })

  it('links to the candidate job detail route', () => {
    renderCard()

    const link = screen.getByRole('link', { name: /Xem việc làm/i })
    expect(link).toHaveAttribute('href', '/candidate/jobs/job-1')
  })

  it.each(['applied', 'under_review', 'shortlisted', 'interviewing', 'offered'])(
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

  it('opens a confirmation dialog before withdrawing', () => {
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: /Rút đơn/i }))

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(mockedWithdrawApplication).not.toHaveBeenCalled()
  })

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
    fireEvent.click(screen.getByRole('button', { name: /Xác nhận rút đơn/i }))

    await waitFor(() => {
      expect(mockedWithdrawApplication).toHaveBeenCalledWith('app-1')
      expect(onWithdrawn).toHaveBeenCalledWith('app-1')
    })
  })

  it('shows an error when withdraw fails', async () => {
    mockedWithdrawApplication.mockRejectedValue(
      Object.assign(new Error('boom'), {
        response: { status: 500, data: { detail: 'Server error' } },
      }),
    )

    renderCard()

    fireEvent.click(screen.getByRole('button', { name: /Rút đơn/i }))
    fireEvent.click(screen.getByRole('button', { name: /Xác nhận rút đơn/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Server error')
    })
  })

  it('toggles the candidate activity timeline', async () => {
    renderCard()

    expect(
      screen.queryByText('Chưa có hoạt động'),
    ).not.toBeInTheDocument()

    fireEvent.click(
      screen.getByRole('button', { name: /Xem lịch sử hoạt động/i }),
    )

    await waitFor(() => {
      expect(mockedGetTimeline).toHaveBeenCalledWith('app-1', { limit: 20 })
    })
    expect(await screen.findByText('Chưa có hoạt động')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /Ẩn lịch sử hoạt động/i }),
    ).toBeInTheDocument()
  })

  describe('Candidate interview actions', () => {
    const mockConfirmedInterview: Interview = {
      ...mockInterview,
      status: 'candidate_confirmed',
      candidate_notes: 'Looking forward to it',
    }

    const mockDeclinedInterview: Interview = {
      ...mockInterview,
      status: 'candidate_declined',
      candidate_notes: 'Not interested',
    }

    it('renders Confirm and Decline buttons for scheduled interview', () => {
      renderCard()

      expect(screen.getByRole('button', { name: /Xác nhận/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Từ chối/i })).toBeInTheDocument()
    })

    it('calls candidateActionInterview with confirm action when Confirm clicked', async () => {
      mockedCandidateActionInterview.mockResolvedValue({
        ...mockInterview,
        status: 'candidate_confirmed',
        candidate_notes: 'Looking forward to it',
      } as never)

      renderCard()

      fireEvent.click(screen.getByRole('button', { name: /Xác nhận/i }))

      await waitFor(() => {
        expect(mockedCandidateActionInterview).toHaveBeenCalledWith(
          'app-1',
          'interview-1',
          'confirm',
        )
      })
    })

    it('opens a decline dialog and submits the reason', async () => {
      mockedCandidateActionInterview.mockResolvedValue({
        ...mockInterview,
        status: 'candidate_declined',
        candidate_notes: 'Not interested',
      } as never)

      renderCard()

      fireEvent.click(screen.getByRole('button', { name: /Từ chối/i }))
      expect(mockedCandidateActionInterview).not.toHaveBeenCalled()

      fireEvent.change(screen.getByLabelText(/Lý do từ chối/i), {
        target: { value: 'Not interested' },
      })
      fireEvent.click(screen.getByRole('button', { name: /Xác nhận từ chối/i }))

      await waitFor(() => {
        expect(mockedCandidateActionInterview).toHaveBeenCalledWith(
          'app-1',
          'interview-1',
          'decline',
          'Not interested',
        )
      })
    })

    it('does not send a decline request when the reason is empty', async () => {
      renderCard()

      fireEvent.click(screen.getByRole('button', { name: /Từ chối/i }))
      fireEvent.click(screen.getByRole('button', { name: /Xác nhận từ chối/i }))

      expect(
        await screen.findByText(/Vui lòng nhập lý do từ chối/i),
      ).toBeInTheDocument()
      expect(mockedCandidateActionInterview).not.toHaveBeenCalled()
    })

    it('shows loading state isolated by interview ID when confirming', async () => {
      mockedCandidateActionInterview.mockReturnValue(new Promise(() => {}))

      renderCard()

      fireEvent.click(screen.getByRole('button', { name: /Xác nhận/i }))

      expect(screen.getAllByRole('button', { name: /Đang tải/i })).toHaveLength(1)
    })

    it('shows loading state in the decline dialog while submitting', async () => {
      mockedCandidateActionInterview.mockReturnValue(new Promise(() => {}))

      renderCard()

      fireEvent.click(screen.getByRole('button', { name: /Từ chối/i }))
      fireEvent.change(screen.getByLabelText(/Lý do từ chối/i), {
        target: { value: 'Not interested' },
      })
      fireEvent.click(screen.getByRole('button', { name: /Xác nhận từ chối/i }))

      expect(
        await screen.findByRole('button', { name: /Đang gửi/i }),
      ).toBeDisabled()
    })

    it('shows error state isolated by interview ID when confirm fails', async () => {
      mockedCandidateActionInterview.mockRejectedValue({
        response: { status: 400, data: { detail: 'Không thể xác nhận' } },
      })

      renderCard()

      fireEvent.click(screen.getByRole('button', { name: /Xác nhận/i }))

      await waitFor(() => {
        expect(screen.getByText(/Không thể xác nhận/i)).toBeInTheDocument()
      })
    })

    it('shows an error in the decline dialog when decline fails', async () => {
      mockedCandidateActionInterview.mockRejectedValue({
        response: { status: 400, data: { detail: 'Không thể từ chối' } },
      })

      renderCard()

      fireEvent.click(screen.getByRole('button', { name: /Từ chối/i }))
      fireEvent.change(screen.getByLabelText(/Lý do từ chối/i), {
        target: { value: 'Not interested' },
      })
      fireEvent.click(screen.getByRole('button', { name: /Xác nhận từ chối/i }))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('Không thể từ chối')
      })
    })

    it('refreshes the parent after a successful decline', async () => {
      mockedCandidateActionInterview.mockResolvedValue({
        ...mockInterview,
        status: 'candidate_declined',
        candidate_notes: 'Not interested',
      } as never)
      const onUpdated = vi.fn()

      render(
        <MemoryRouter>
          <ApplicationCard application={mockApplication} onUpdated={onUpdated} />
        </MemoryRouter>,
      )

      fireEvent.click(screen.getByRole('button', { name: /Từ chối/i }))
      fireEvent.change(screen.getByLabelText(/Lý do từ chối/i), {
        target: { value: 'Not interested' },
      })
      fireEvent.click(screen.getByRole('button', { name: /Xác nhận từ chối/i }))

      await waitFor(() => {
        expect(onUpdated).toHaveBeenCalled()
      })
    })

    it('renders candidate_confirmed state correctly', () => {
      renderCard({
        interviews: [mockConfirmedInterview],
      })

      expect(screen.getByText(/Đã xác nhận/)).toBeInTheDocument()
      expect(screen.getByText(/Phản hồi: Looking forward to it/)).toBeInTheDocument()
    })

    it('renders candidate_declined state correctly', () => {
      renderCard({
        interviews: [mockDeclinedInterview],
      })

      expect(screen.getByText(/Đã từ chối/)).toBeInTheDocument()
      expect(screen.getByText(/Lý do: Not interested/)).toBeInTheDocument()
    })
  })
})
