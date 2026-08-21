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
}))

vi.mock('@/api/interviews', () => ({
  candidateActionInterview: vi.fn(),
}))

const mockedWithdrawApplication = vi.mocked(
  applicationsApi.withdrawApplication,
)

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
  })

  it('renders job title, company and application date', () => {
    renderCard()

    expect(screen.getByText('Backend Developer')).toBeInTheDocument()
    expect(screen.getByText('Công ty ABC Technology')).toBeInTheDocument()
    expect(screen.getByText(/Ứng tuyển:/)).toBeInTheDocument()
  })

  it('renders the existing status badge', () => {
    renderCard()

    expect(screen.getByText('Đang phỏng vấn')).toBeInTheDocument()
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
          undefined
        )
      })
    })

    it('prompts for reason when Decline clicked', async () => {
      mockedCandidateActionInterview.mockResolvedValue({
        ...mockInterview,
        status: 'candidate_declined',
        candidate_notes: 'Not interested',
      } as never)

      const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('Not interested')

      renderCard()

      fireEvent.click(screen.getByRole('button', { name: /Từ chối/i }))

      await waitFor(() => {
        expect(promptSpy).toHaveBeenCalledWith(expect.stringContaining('lý do'))
      })

      await waitFor(() => {
        expect(mockedCandidateActionInterview).toHaveBeenCalledWith(
          'app-1',
          'interview-1',
          'decline',
          'Not interested'
        )
      })

      promptSpy.mockRestore()
    })

    it('does not send request when decline prompt is cancelled', async () => {
      vi.spyOn(window, 'prompt').mockReturnValue(null)

      renderCard()

      fireEvent.click(screen.getByRole('button', { name: /Từ chối/i }))

      await waitFor(() => {
        expect(mockedCandidateActionInterview).not.toHaveBeenCalled()
      })
    })

    it('does not send request when decline prompt is empty', async () => {
      vi.spyOn(window, 'prompt').mockReturnValue('')

      renderCard()

      fireEvent.click(screen.getByRole('button', { name: /Từ chối/i }))

      await waitFor(() => {
        expect(mockedCandidateActionInterview).not.toHaveBeenCalled()
      })
    })

    it('shows loading state isolated by interview ID when confirming', async () => {
      let resolveConfirm: (value: any) => void
      mockedCandidateActionInterview.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveConfirm = resolve
          }),
      )

      renderCard()

      fireEvent.click(screen.getByRole('button', { name: /Xác nhận/i }))

      // Check loading state is shown for this interview - both buttons show loading since they share interview ID
      expect(screen.getAllByRole('button', { name: /Đang tải/i })).toHaveLength(2)

      resolveConfirm!({
        ...mockInterview,
        status: 'candidate_confirmed',
        candidate_notes: 'Looking forward to it',
      } as never)

      await waitFor(() => {
        expect(screen.queryAllByRole('button', { name: /Đang tải/i })).toHaveLength(0)
      })
    })

    it('shows loading state isolated by interview ID when declining', async () => {
      let resolveDecline: (value: any) => void
      mockedCandidateActionInterview.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveDecline = resolve
          }),
      )

      vi.spyOn(window, 'prompt').mockReturnValue('Not interested')

      renderCard()

      fireEvent.click(screen.getByRole('button', { name: /Từ chối/i }))

      // Check loading state is shown for this interview - both buttons show loading since they share interview ID
      expect(screen.getAllByRole('button', { name: /Đang tải/i })).toHaveLength(2)

      resolveDecline!({
        ...mockInterview,
        status: 'candidate_declined',
        candidate_notes: 'Not interested',
      } as never)

      await waitFor(() => {
        expect(screen.queryAllByRole('button', { name: /Đang tải/i })).toHaveLength(0)
      })
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

    it('shows error state isolated by interview ID when decline fails', async () => {
      mockedCandidateActionInterview.mockRejectedValue({
        response: { status: 400, data: { detail: 'Không thể từ chối' } },
      })
      vi.spyOn(window, 'prompt').mockReturnValue('Not interested')

      renderCard()

      fireEvent.click(screen.getByRole('button', { name: /Từ chối/i }))

      await waitFor(() => {
        expect(screen.getByText(/Không thể từ chối/i)).toBeInTheDocument()
      })
    })

    it('hides Confirm/Decline buttons after successful confirm', async () => {
      mockedCandidateActionInterview.mockResolvedValue({
        ...mockInterview,
        status: 'candidate_confirmed',
        candidate_notes: 'Looking forward to it',
      } as never)

      renderCard()

      fireEvent.click(screen.getByRole('button', { name: /Xác nhận/i }))

      await waitFor(() => {
        expect(screen.queryByRole('button', { name: /Xác nhận/i })).not.toBeInTheDocument()
        expect(screen.queryByRole('button', { name: /Từ chối/i })).not.toBeInTheDocument()
      })
    })

    it('hides Confirm/Decline buttons after successful decline', async () => {
      mockedCandidateActionInterview.mockResolvedValue({
        ...mockInterview,
        status: 'candidate_declined',
        candidate_notes: 'Not interested',
      } as never)

      vi.spyOn(window, 'prompt').mockReturnValue('Not interested')

      renderCard()

      fireEvent.click(screen.getByRole('button', { name: /Từ chối/i }))

      await waitFor(() => {
        expect(screen.queryByRole('button', { name: /Xác nhận/i })).not.toBeInTheDocument()
        expect(screen.queryByRole('button', { name: /Từ chối/i })).not.toBeInTheDocument()
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

    it('displays candidate_notes when available for confirmed interview', () => {
      renderCard({
        interviews: [mockConfirmedInterview],
      })

      expect(screen.getByText(/Phản hồi: Looking forward to it/)).toBeInTheDocument()
    })

    it('displays candidate_notes when available for declined interview', () => {
      renderCard({
        interviews: [mockDeclinedInterview],
      })

      expect(screen.getByText(/Lý do: Not interested/)).toBeInTheDocument()
    })
  })
})