import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CandidateInterviewsPage } from './CandidateInterviewsPage'
import * as interviewsApi from '@/api/interviews'
import type { CandidateScheduledInterview } from '@/types/application'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  )
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

vi.mock('@/api/interviews', () => ({
  listCandidateInterviews: vi.fn(),
  candidateActionInterview: vi.fn(),
}))

const mockedList = vi.mocked(interviewsApi.listCandidateInterviews)
const mockedAction = vi.mocked(interviewsApi.candidateActionInterview)

const futureDate = new Date(Date.now() + 86400000 * 2).toISOString()
const pastDate = new Date(Date.now() - 86400000 * 2).toISOString()

const scheduledInterview: CandidateScheduledInterview = {
  id: 'interview-1',
  application_id: 'app-1',
  scheduled_at: futureDate,
  duration_minutes: 60,
  interview_type: 'technical',
  meeting_url: 'https://meet.google.com/xyz-123',
  location: null,
  candidate_notes: null,
  status: 'scheduled',
  created_at: pastDate,
  updated_at: pastDate,
  job_id: 'job-1',
  job_title: 'Staff Platform Engineer',
  company_name: 'Tech Alpha Corp',
}

const confirmedInterview: CandidateScheduledInterview = {
  id: 'interview-2',
  application_id: 'app-2',
  scheduled_at: futureDate,
  duration_minutes: 45,
  interview_type: 'behavioral',
  meeting_url: null,
  location: 'Tầng 5, Tòa nhà Bitexco',
  candidate_notes: 'Tôi sẽ đến sớm 10 phút.',
  status: 'candidate_confirmed',
  created_at: pastDate,
  updated_at: pastDate,
  job_id: 'job-2',
  job_title: 'Engineering Manager',
  company_name: 'Beta Global Solutions',
}

const declinedInterview: CandidateScheduledInterview = {
  id: 'interview-3',
  application_id: 'app-3',
  scheduled_at: futureDate,
  duration_minutes: 30,
  interview_type: 'hr',
  meeting_url: null,
  location: 'Văn phòng Cầu Giấy',
  candidate_notes: 'Trùng lịch công tác.',
  status: 'candidate_declined',
  created_at: pastDate,
  updated_at: pastDate,
  job_id: 'job-3',
  job_title: 'DevOps Specialist',
  company_name: 'Gamma Cloud Inc',
}

const completedInterview: CandidateScheduledInterview = {
  id: 'interview-4',
  application_id: 'app-4',
  scheduled_at: pastDate,
  duration_minutes: 60,
  interview_type: 'technical',
  meeting_url: 'https://zoom.us/j/123456789',
  location: null,
  candidate_notes: null,
  status: 'completed',
  created_at: pastDate,
  updated_at: pastDate,
  job_id: 'job-4',
  job_title: 'Senior Frontend Dev',
  company_name: 'Delta Software',
}

const cancelledInterview: CandidateScheduledInterview = {
  id: 'interview-5',
  application_id: 'app-5',
  scheduled_at: futureDate,
  duration_minutes: 45,
  interview_type: 'case_study',
  meeting_url: null,
  location: 'Online',
  candidate_notes: null,
  status: 'cancelled',
  created_at: pastDate,
  updated_at: pastDate,
  job_id: 'job-5',
  job_title: 'Product Architect',
  company_name: 'Epsilon Ventures',
}

function renderComponent() {
  return render(
    <MemoryRouter>
      <CandidateInterviewsPage />
    </MemoryRouter>,
  )
}

describe('CandidateInterviewsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading skeleton while fetching data', () => {
    mockedList.mockReturnValue(new Promise(() => {}))
    renderComponent()

    expect(
      screen.getByRole('heading', { name: 'Lịch phỏng vấn' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Theo dõi và quản lý lịch phỏng vấn cho các vị trí bạn đã ứng tuyển.'),
    ).toBeInTheDocument()
  })

  it('renders populated interview cards with details and status labels', async () => {
    mockedList.mockResolvedValue([
      scheduledInterview,
      confirmedInterview,
      declinedInterview,
      completedInterview,
      cancelledInterview,
    ])
    renderComponent()

    await waitFor(() => {
      expect(mockedList).toHaveBeenCalledTimes(1)
    })

    expect(screen.getByText('Staff Platform Engineer')).toBeInTheDocument()
    expect(screen.getByText('Tech Alpha Corp')).toBeInTheDocument()
    expect(screen.getByText('Engineering Manager')).toBeInTheDocument()
    expect(screen.getByText('Beta Global Solutions')).toBeInTheDocument()

    // Vietnamese status labels
    expect(screen.getByText('Chờ bạn xác nhận')).toBeInTheDocument()
    expect(screen.getByText('Bạn đã xác nhận')).toBeInTheDocument()
    expect(screen.getByText('Bạn đã từ chối')).toBeInTheDocument()
    expect(screen.getByText('Đã hoàn thành')).toBeInTheDocument()
    expect(screen.getByText('Đã hủy')).toBeInTheDocument()

    // Meeting link and physical location
    const meetingLinks = screen.getAllByRole('link', { name: /Tham gia trực tuyến/i })
    expect(meetingLinks[0]).toHaveAttribute('href', 'https://meet.google.com/xyz-123')
    expect(screen.getByText('Tầng 5, Tòa nhà Bitexco')).toBeInTheDocument()

    // Candidate notes display
    expect(screen.getByText(/Tôi sẽ đến sớm 10 phút/)).toBeInTheDocument()
  })

  it('renders empty state and provides jobs CTA when no interviews exist', async () => {
    mockedList.mockResolvedValue([])
    renderComponent()

    await waitFor(() => {
      expect(screen.getByText('Chưa có lịch phỏng vấn nào')).toBeInTheDocument()
    })

    const ctaButton = screen.getByRole('button', { name: 'Tìm việc làm ngay' })
    fireEvent.click(ctaButton)
    expect(mockNavigate).toHaveBeenCalledWith('/candidate/jobs')
  })

  it('renders error banner and allows retry when API fails', async () => {
    mockedList.mockRejectedValueOnce(new Error('Network error'))
    renderComponent()

    await waitFor(() => {
      expect(
        screen.getByText(/Không thể kết nối|Network error|Không thể tải/),
      ).toBeInTheDocument()
    })

    mockedList.mockResolvedValueOnce([scheduledInterview])
    const retryButton = screen.getByRole('button', { name: /Thử lại/i })
    fireEvent.click(retryButton)

    await waitFor(() => {
      expect(screen.getByText('Staff Platform Engineer')).toBeInTheDocument()
    })
    expect(mockedList).toHaveBeenCalledTimes(2)
  })

  it('filters interviews by tabs: all, upcoming, past', async () => {
    mockedList.mockResolvedValue([
      scheduledInterview,
      confirmedInterview,
      declinedInterview,
      completedInterview,
      cancelledInterview,
    ])
    renderComponent()

    await waitFor(() => {
      expect(screen.getByText('Staff Platform Engineer')).toBeInTheDocument()
    })

    // "Tất cả" tab is active by default (5 items)
    expect(screen.getByText('DevOps Specialist')).toBeInTheDocument()
    expect(screen.getByText('Senior Frontend Dev')).toBeInTheDocument()

    // Switch to "Sắp tới" tab: only scheduled and confirmed
    const upcomingTab = screen.getByRole('button', { name: /Sắp tới/i })
    fireEvent.click(upcomingTab)

    expect(screen.getByText('Staff Platform Engineer')).toBeInTheDocument()
    expect(screen.getByText('Engineering Manager')).toBeInTheDocument()
    // Cancelled and declined must NEVER appear in upcoming
    expect(screen.queryByText('DevOps Specialist')).not.toBeInTheDocument()
    expect(screen.queryByText('Senior Frontend Dev')).not.toBeInTheDocument()
    expect(screen.queryByText('Product Architect')).not.toBeInTheDocument()

    // Switch to "Đã qua" tab: completed, elapsed, cancelled, declined
    const pastTab = screen.getByRole('button', { name: /Đã qua/i })
    fireEvent.click(pastTab)

    expect(screen.getByText('DevOps Specialist')).toBeInTheDocument()
    expect(screen.getByText('Senior Frontend Dev')).toBeInTheDocument()
    expect(screen.getByText('Product Architect')).toBeInTheDocument()
    expect(screen.queryByText('Staff Platform Engineer')).not.toBeInTheDocument()
  })

  it('handles candidate confirmation action and updates card state', async () => {
    mockedList.mockResolvedValue([scheduledInterview])
    mockedAction.mockResolvedValue({
      ...scheduledInterview,
      status: 'candidate_confirmed',
    })
    renderComponent()

    await waitFor(() => {
      expect(screen.getByText('Staff Platform Engineer')).toBeInTheDocument()
    })

    const confirmButton = screen.getByRole('button', { name: /Xác nhận tham gia/i })
    expect(confirmButton).toBeInTheDocument()

    fireEvent.click(confirmButton)

    await waitFor(() => {
      expect(mockedAction).toHaveBeenCalledWith(
        'app-1',
        'interview-1',
        'confirm',
      )
    })

    await waitFor(() => {
      expect(screen.getByText('Bạn đã xác nhận')).toBeInTheDocument()
    })
    // Action buttons must disappear once confirmed
    expect(screen.queryByRole('button', { name: /Xác nhận tham gia/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Từ chối/i })).not.toBeInTheDocument()
    expect(screen.getByText(/Bạn đã xác nhận tham gia buổi phỏng vấn thành công/i)).toBeInTheDocument()
  })

  it('handles candidate decline modal and updates card state on submission', async () => {
    mockedList.mockResolvedValue([scheduledInterview])
    mockedAction.mockResolvedValue({
      ...scheduledInterview,
      status: 'candidate_declined',
      candidate_notes: 'Lý do bận việc gia đình',
    })
    renderComponent()

    await waitFor(() => {
      expect(screen.getByText('Staff Platform Engineer')).toBeInTheDocument()
    })

    const declineButton = screen.getByRole('button', { name: /Từ chối/i })
    fireEvent.click(declineButton)

    // Decline modal opens
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByLabelText(/Lý do từ chối/i)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/Lý do từ chối/i), {
      target: { value: 'Lý do bận việc gia đình' },
    })

    const confirmDeclineButton = screen.getByRole('button', { name: 'Xác nhận từ chối' })
    fireEvent.click(confirmDeclineButton)

    await waitFor(() => {
      expect(mockedAction).toHaveBeenCalledWith(
        'app-1',
        'interview-1',
        'decline',
        'Lý do bận việc gia đình',
      )
    })

    await waitFor(() => {
      expect(screen.getByText('Bạn đã từ chối')).toBeInTheDocument()
    })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Xác nhận tham gia/i })).not.toBeInTheDocument()
  })
})
