import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { InterviewManager } from './InterviewManager'
import type { Interview, InterviewAssignment } from '@/types/application'
import type { WorkspaceMember } from '@/types/workspace'
import * as interviewsApi from '@/api/interviews'
import * as workspacesApi from '@/api/workspaces'

vi.mock('@/api/interviews', () => ({
  scheduleInterview: vi.fn(),
  updateInterview: vi.fn(),
  cancelInterview: vi.fn(),
  listInterviewAssignments: vi.fn(),
  assignInterview: vi.fn(),
  unassignInterview: vi.fn(),
}))

vi.mock('@/api/workspaces', () => ({
  getWorkspaceMembers: vi.fn(),
}))

const mockedListAssignments = vi.mocked(interviewsApi.listInterviewAssignments)
const mockedAssignInterview = vi.mocked(interviewsApi.assignInterview)
const mockedUnassignInterview = vi.mocked(interviewsApi.unassignInterview)
const mockedGetWorkspaceMembers = vi.mocked(workspacesApi.getWorkspaceMembers)

const mockMember1: WorkspaceMember = {
  membership_id: 'membership-1',
  user_id: 'user-1',
  email: 'alice@example.com',
  full_name: 'Alice Admin',
  role: 'admin',
  status: 'active',
  joined_at: '2026-01-01T00:00:00Z',
  revoked_at: null,
}

const mockMember2: WorkspaceMember = {
  membership_id: 'membership-2',
  user_id: 'user-2',
  email: 'bob@example.com',
  full_name: 'Bob Interviewer',
  role: 'interviewer',
  status: 'active',
  joined_at: '2026-01-01T00:00:00Z',
  revoked_at: null,
}

const mockAssignment1: InterviewAssignment = {
  id: 'assign-1',
  interview_id: 'interview-1',
  user_id: 'user-1',
  assigned_by_id: 'admin-1',
  created_at: '2026-08-19T00:00:00Z',
  updated_at: '2026-08-19T00:00:00Z',
  user: mockMember1,
}

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
    mockedListAssignments.mockResolvedValue([])
    mockedGetWorkspaceMembers.mockResolvedValue([])
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

  describe('Terminal status behavior', () => {
    const terminalStatuses = ['accepted', 'rejected', 'withdrawn'] as const
    const validStatuses = ['applied', 'under_review', 'shortlisted', 'interviewing'] as const

    terminalStatuses.forEach(status => {
      it(`hides "Lên lịch" button when status is ${status}`, () => {
        renderManager({ initialInterviews: [] }, { applicationStatus: status })

        expect(screen.queryByRole('button', { name: /Lên lịch/i })).not.toBeInTheDocument()
      })

      it(`shows disabled "Tạo câu hỏi AI" button when status is ${status}`, () => {
        renderManager({ initialInterviews: [] }, { applicationStatus: status })

        const aiButton = screen.getByRole('button', { name: /Tạo câu hỏi AI/i })
        expect(aiButton).toBeInTheDocument()
        expect(aiButton).toBeDisabled()
      })

      it(`shows warning message when status is ${status}`, () => {
        renderManager({ initialInterviews: [] }, { applicationStatus: status })

        expect(screen.getByText('Không thể tạo lịch phỏng vấn hoặc tạo câu hỏi AI vì hồ sơ ứng viên đang ở trạng thái đã đóng.')).toBeInTheDocument()
      })
    })

    validStatuses.forEach(status => {
      it(`shows "Lên lịch" button when status is ${status}`, () => {
        renderManager({ initialInterviews: [] }, { applicationStatus: status })

        expect(screen.getByRole('button', { name: /Lên lịch/i })).toBeInTheDocument()
      })

      it(`shows enabled "Tạo câu hỏi AI" button when status is ${status}`, () => {
        renderManager({ initialInterviews: [] }, { applicationStatus: status })

        const aiButton = screen.getByRole('button', { name: /Tạo câu hỏi AI/i })
        expect(aiButton).toBeInTheDocument()
        expect(aiButton).not.toBeDisabled()
      })

      it(`does not show warning message when status is ${status}`, () => {
        renderManager({ initialInterviews: [] }, { applicationStatus: status })

        expect(screen.queryByText('Không thể tạo lịch phỏng vấn hoặc tạo câu hỏi AI vì hồ sơ ứng viên đang ở trạng thái đã đóng.')).not.toBeInTheDocument()
      })
    })

    it('shows "Đã đóng" badge when status is terminal', () => {
      renderManager({ initialInterviews: [] }, { applicationStatus: 'withdrawn' })
      expect(screen.getByText('Đã đóng')).toBeInTheDocument()
    })

    it('shows warning message when in terminal status and editing form', () => {
      renderManager({ initialInterviews: [] }, { applicationStatus: 'withdrawn' })

      const button = screen.getByRole('button', { name: /Tạo câu hỏi AI/i })
      expect(button).toBeDisabled()
    })
  })

  describe('Interview Assignments', () => {
    it('shows empty state when no interviewers assigned', async () => {
      mockedListAssignments.mockResolvedValue([])
      renderManager({ initialInterviews: [mockScheduledInterview] })

      await waitFor(() => {
        expect(screen.getByText('Chưa có người phỏng vấn nào được phân công.')).toBeInTheDocument()
      })
    })

    it('renders assigned participants with name, email and role', async () => {
      mockedListAssignments.mockResolvedValue([mockAssignment1])
      mockedGetWorkspaceMembers.mockResolvedValue([mockMember1, mockMember2])

      renderManager({ initialInterviews: [mockScheduledInterview] })

      await waitFor(() => {
        expect(screen.getByText('Alice Admin')).toBeInTheDocument()
      })
      expect(screen.getByText('(alice@example.com)')).toBeInTheDocument()
      expect(screen.getByText('Quản trị viên')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Hủy phân công/ })).toBeInTheDocument()
    })

    it('filters out already assigned members from the assignment dropdown', async () => {
      mockedListAssignments.mockResolvedValue([mockAssignment1])
      mockedGetWorkspaceMembers.mockResolvedValue([mockMember1, mockMember2])

      renderManager({ initialInterviews: [mockScheduledInterview] })

      await waitFor(() => {
        expect(screen.getByText('Alice Admin')).toBeInTheDocument()
      })

      // The select dropdown should only contain mockMember2 (Bob), not mockMember1 (Alice)
      const select = screen.getByRole('combobox')
      const options = Array.from(select.querySelectorAll('option')).map((o) => o.textContent)
      expect(options).toContain('-- Chọn thành viên để phân công --')
      expect(options.some((text) => text?.includes('Bob Interviewer'))).toBe(true)
      expect(options.some((text) => text?.includes('Alice Admin'))).toBe(false)
    })

    it('calls assignInterview when assigning a member', async () => {
      mockedListAssignments.mockResolvedValue([])
      mockedGetWorkspaceMembers.mockResolvedValue([mockMember2])
      mockedAssignInterview.mockResolvedValue({
        id: 'assign-2',
        interview_id: 'interview-1',
        user_id: 'user-2',
        assigned_by_id: 'admin-1',
        created_at: '2026-08-19T00:00:00Z',
        updated_at: '2026-08-19T00:00:00Z',
        user: mockMember2,
      })

      renderManager({ initialInterviews: [mockScheduledInterview] })

      await waitFor(() => {
        expect(screen.getByText('Chưa có người phỏng vấn nào được phân công.')).toBeInTheDocument()
      })

      const select = screen.getByRole('combobox')
      fireEvent.change(select, { target: { value: 'user-2' } })

      const assignButton = screen.getByRole('button', { name: 'Phân công' })
      expect(assignButton).not.toBeDisabled()
      fireEvent.click(assignButton)

      await waitFor(() => {
        expect(mockedAssignInterview).toHaveBeenCalledWith('interview-1', 'user-2')
      })
      expect(await screen.findByText('Bob Interviewer')).toBeInTheDocument()
    })

    it('calls unassignInterview when unassigning a participant', async () => {
      const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
      mockedListAssignments.mockResolvedValue([mockAssignment1])
      mockedGetWorkspaceMembers.mockResolvedValue([mockMember1])
      mockedUnassignInterview.mockResolvedValue(undefined as unknown as void)

      renderManager({ initialInterviews: [mockScheduledInterview] })

      await waitFor(() => {
        expect(screen.getByText('Alice Admin')).toBeInTheDocument()
      })

      const unassignButton = screen.getByRole('button', { name: /Hủy phân công/ })
      fireEvent.click(unassignButton)

      await waitFor(() => {
        expect(mockedUnassignInterview).toHaveBeenCalledWith('interview-1', 'assign-1')
      })
      expect(screen.queryByText('Alice Admin')).not.toBeInTheDocument()
      expect(screen.getByText('Chưa có người phỏng vấn nào được phân công.')).toBeInTheDocument()
      confirmSpy.mockRestore()
    })
  })

  function renderManager(overrides: { initialInterviews?: Interview[] } = {}, options: { applicationStatus?: string } = {}) {
    return render(
      <MemoryRouter>
        <InterviewManager
          applicationId="app-1"
          jobId="job-1"
          initialInterviews={overrides.initialInterviews || []}
          onInterviewUpdated={vi.fn()}
          applicationStatus={options.applicationStatus}
        />
      </MemoryRouter>,
    )
  }
})
