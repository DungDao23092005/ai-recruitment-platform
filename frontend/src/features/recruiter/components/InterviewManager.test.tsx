import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { InterviewManager } from './InterviewManager'
import type { Interview } from '@/types/application'

vi.mock('@/api/interviews', () => ({
  scheduleInterview: vi.fn(),
  updateInterview: vi.fn(),
  cancelInterview: vi.fn(),
}))

const mockScheduledInterview: Interview = {
  id: 'interview-1',
  application_id: 'app-1',
  scheduled_at: '2026-08-20T10:00:00Z',
  duration_minutes: 60,
  interview_type: 'technical',
  meeting_url: 'https://meet.google.com/abc',
  location: 'Online',
  notes: 'Technical interview',
  candidate_notes: null,
  status: 'scheduled',
  created_at: '2026-08-18T00:00:00Z',
  updated_at: '2026-08-18T00:00:00Z',
}

const mockConfirmedInterview: Interview = {
  ...mockScheduledInterview,
  id: 'interview-2',
  interview_type: 'behavioral',
  meeting_url: null,
  location: 'Office',
  notes: 'Behavioral interview',
  candidate_notes: 'Looking forward to it',
  status: 'candidate_confirmed',
}

const mockDeclinedInterview: Interview = {
  ...mockScheduledInterview,
  id: 'interview-3',
  interview_type: 'hr',
  meeting_url: null,
  location: 'Online',
  notes: 'HR interview',
  candidate_notes: 'Not interested',
  status: 'candidate_declined',
}

function renderManager(overrides: { initialInterviews?: Interview[] } = {}) {
  return render(
    <MemoryRouter>
      <InterviewManager
        applicationId="app-1"
        jobId="job-1"
        initialInterviews={overrides.initialInterviews || []}
        onInterviewUpdated={vi.fn()}
      />
    </MemoryRouter>,
  )
}

describe('InterviewManager', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders candidate_confirmed interviews with "Đã xác nhận" badge', () => {
    renderManager({ initialInterviews: [mockConfirmedInterview] })

    expect(screen.getByText(/Đã xác nhận/)).toBeInTheDocument()
  })

  it('renders candidate_declined interviews with "Đã từ chối" badge', () => {
    renderManager({ initialInterviews: [mockDeclinedInterview] })

    expect(screen.getByText(/Đã từ chối/)).toBeInTheDocument()
  })

  it('displays candidate_notes for confirmed interviews', () => {
    renderManager({ initialInterviews: [mockConfirmedInterview] })

    expect(screen.getByText(/Phản hồi: Looking forward to it/)).toBeInTheDocument()
  })

  it('displays candidate_notes for declined interviews', () => {
    renderManager({ initialInterviews: [mockDeclinedInterview] })

    expect(screen.getByText(/Lý do: Not interested/)).toBeInTheDocument()
  })

  it('does not show confirmed/declined badges for scheduled interviews', () => {
    renderManager({ initialInterviews: [mockScheduledInterview] })

    expect(screen.queryByText(/Đã xác nhận/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Đã từ chối/)).not.toBeInTheDocument()
  })

  it('shows scheduled interviews in active section', () => {
    renderManager({ initialInterviews: [mockScheduledInterview] })

    expect(screen.getByText(/Phỏng vấn technical/)).toBeInTheDocument()
    expect(screen.getByText(/Online/)).toBeInTheDocument()
  })

  it('shows "Chưa có lịch phỏng vấn nào" when no interviews', () => {
    renderManager({ initialInterviews: [] })

    expect(screen.getByText('Chưa có lịch phỏng vấn nào.')).toBeInTheDocument()
  })

  it('shows "Tạo câu hỏi AI" button', () => {
    renderManager({ initialInterviews: [] })

    expect(screen.getByRole('button', { name: /Tạo câu hỏi AI/i })).toBeInTheDocument()
  })

  it('shows "Lên lịch" button when not editing', () => {
    renderManager({ initialInterviews: [] })

    expect(screen.getByRole('button', { name: /Lên lịch/i })).toBeInTheDocument()
  })
})