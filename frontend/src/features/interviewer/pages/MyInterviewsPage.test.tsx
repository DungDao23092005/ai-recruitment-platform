import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { MyInterviewsPage } from './MyInterviewsPage'
import * as interviewsApi from '@/api/interviews'
import { useAuth } from '@/contexts/AuthContext'
import type {
  AssignedInterview,
  InterviewEvaluation,
  InterviewerApplication,
} from '@/types/application'

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

vi.mock('@/api/interviews', () => ({
  listMyAssignedInterviews: vi.fn(),
  getInterviewerApplication: vi.fn(),
  listWorkspaceInterviewEvaluations: vi.fn(),
  createWorkspaceInterviewEvaluation: vi.fn(),
  updateWorkspaceInterviewEvaluation: vi.fn(),
  submitWorkspaceInterviewEvaluation: vi.fn(),
  deleteWorkspaceInterviewEvaluation: vi.fn(),
}))

const mockedUseAuth = vi.mocked(useAuth)
const mockedList = vi.mocked(interviewsApi.listMyAssignedInterviews)
const mockedApplication = vi.mocked(interviewsApi.getInterviewerApplication)
const mockedListEvaluations = vi.mocked(
  interviewsApi.listWorkspaceInterviewEvaluations,
)
const mockedCreateEvaluation = vi.mocked(
  interviewsApi.createWorkspaceInterviewEvaluation,
)
const mockedUpdateEvaluation = vi.mocked(
  interviewsApi.updateWorkspaceInterviewEvaluation,
)
const mockedSubmitEvaluation = vi.mocked(
  interviewsApi.submitWorkspaceInterviewEvaluation,
)
const mockedDeleteEvaluation = vi.mocked(
  interviewsApi.deleteWorkspaceInterviewEvaluation,
)

const interview: AssignedInterview = {
  id: 'interview-1',
  application_id: 'application-1',
  scheduled_at: '2026-11-10T09:00:00Z',
  duration_minutes: 60,
  interview_type: 'technical',
  meeting_url: null,
  location: 'Room 3',
  status: 'scheduled',
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
  job_id: 'job-1',
  job_title: 'Backend Engineer',
  company_name: 'Assignment Corp',
  candidate_name: 'Assigned Candidate',
  application_status: 'interviewing',
}

const application: InterviewerApplication = {
  id: 'application-1',
  job_id: 'job-1',
  job_title: 'Backend Engineer',
  company_name: 'Assignment Corp',
  status: 'interviewing',
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
  candidate: {
    id: 'candidate-1',
    full_name: 'Assigned Candidate',
    title: 'Engineer',
    email: null,
    phone: null,
  },
  resume: {
    id: 'resume-1',
    title: 'Primary',
    is_primary: true,
    is_confirmed: true,
    parsed_data: {
      full_name: 'Assigned Candidate',
      email: null,
      phone: null,
      title: 'Engineer',
      summary: 'Backend engineer',
      total_years_experience: 5,
      skills: ['Python', 'FastAPI'],
      experiences: [],
      education: [],
      certifications: [],
      languages: [],
    },
  },
}

const myDraft: InterviewEvaluation = {
  id: 'eval-draft-1',
  interview_id: 'interview-1',
  application_id: 'application-1',
  evaluator_id: 'user-interviewer',
  rating: 4,
  recommendation: 'hire',
  strengths: 'Strong algorithms',
  weaknesses: 'Needs async review',
  notes: 'Good candidate overall',
  status: 'draft',
  submitted_at: null,
  created_at: '2026-11-10T10:00:00Z',
  updated_at: '2026-11-10T10:00:00Z',
}

const mySubmitted: InterviewEvaluation = {
  ...myDraft,
  id: 'eval-submitted-1',
  status: 'submitted',
  submitted_at: '2026-11-10T11:00:00Z',
}

const colleagueEval: InterviewEvaluation = {
  id: 'eval-colleague-1',
  interview_id: 'interview-1',
  application_id: 'application-1',
  evaluator_id: 'colleague-user',
  rating: 5,
  recommendation: 'strong_hire',
  strengths: 'Architecture knowledge',
  weaknesses: '',
  notes: 'Must hire',
  status: 'submitted',
  submitted_at: '2026-11-10T10:30:00Z',
  created_at: '2026-11-10T10:00:00Z',
  updated_at: '2026-11-10T10:30:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedUseAuth.mockReturnValue({
    currentUser: {
      id: 'user-interviewer',
      email: 'interviewer@example.com',
      role: 'interviewer',
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    token: 'token',
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refreshCurrentUser: vi.fn(),
  })
  mockedList.mockResolvedValue([interview])
  mockedApplication.mockResolvedValue(application)
  mockedListEvaluations.mockResolvedValue([])
})

describe('MyInterviewsPage', () => {
  it('loads assigned interviews and masks direct contact details', async () => {
    render(
      <MemoryRouter>
        <MyInterviewsPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(mockedList).toHaveBeenCalledTimes(1)
    })
    expect(screen.getByText('Backend Engineer')).toBeInTheDocument()
    expect(screen.getAllByText('Assigned Candidate').length).toBeGreaterThan(0)

    await waitFor(() => {
      expect(mockedApplication).toHaveBeenCalledWith('interview-1')
    })
    expect(screen.getByText('Email đã ẩn')).toBeInTheDocument()
    expect(screen.getByText('Số điện thoại đã ẩn')).toBeInTheDocument()
    expect(screen.getByText('Python')).toBeInTheDocument()
  })

  it('shows an empty state when nothing is assigned', async () => {
    mockedList.mockResolvedValue([])

    render(
      <MemoryRouter>
        <MyInterviewsPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(
        screen.getByText('Chưa có buổi phỏng vấn nào'),
      ).toBeInTheDocument()
    })
  })

  describe('Interview Scorecard Evaluation', () => {
    it('allows drafting a new scorecard evaluation', async () => {
      mockedCreateEvaluation.mockResolvedValue(myDraft)

      render(
        <MemoryRouter>
          <MyInterviewsPage />
        </MemoryRouter>,
      )

      await waitFor(() => {
        expect(mockedListEvaluations).toHaveBeenCalledWith('interview-1')
      })

      const ratingSelect = await screen.findByLabelText('Điểm đánh giá')
      fireEvent.change(ratingSelect, {
        target: { value: '4' },
      })
      fireEvent.change(screen.getByLabelText('Đề xuất'), {
        target: { value: 'hire' },
      })
      fireEvent.change(screen.getByLabelText('Điểm mạnh'), {
        target: { value: 'Strong algorithms' },
      })
      fireEvent.click(screen.getByRole('button', { name: 'Lưu nháp' }))

      await waitFor(() => {
        expect(mockedCreateEvaluation).toHaveBeenCalledWith('interview-1', {
          rating: 4,
          recommendation: 'hire',
          strengths: 'Strong algorithms',
          weaknesses: null,
          notes: null,
        })
      })
    })

    it('displays draft status and allows updating and deleting draft', async () => {
      const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
      mockedListEvaluations.mockResolvedValue([myDraft])
      mockedDeleteEvaluation.mockResolvedValue(undefined as unknown as void)

      render(
        <MemoryRouter>
          <MyInterviewsPage />
        </MemoryRouter>,
      )

      await waitFor(() => {
        expect(screen.getByText('Bản nháp')).toBeInTheDocument()
      })
      expect(screen.getByLabelText('Điểm mạnh')).toHaveValue('Strong algorithms')

      const deleteButton = screen.getByRole('button', { name: /Xóa nháp/i })
      fireEvent.click(deleteButton)

      await waitFor(() => {
        expect(mockedDeleteEvaluation).toHaveBeenCalledWith('interview-1', 'eval-draft-1')
      })
      confirmSpy.mockRestore()
    })

    it('submits evaluation and enforces immutability', async () => {
      const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
      mockedListEvaluations
        .mockResolvedValueOnce([myDraft])
        .mockResolvedValue([mySubmitted])
      mockedUpdateEvaluation.mockResolvedValue(myDraft)
      mockedSubmitEvaluation.mockResolvedValue(mySubmitted)

      render(
        <MemoryRouter>
          <MyInterviewsPage />
        </MemoryRouter>,
      )

      await waitFor(() => {
        expect(screen.getByText('Bản nháp')).toBeInTheDocument()
      })

      const submitButton = screen.getByRole('button', { name: /Gửi đánh giá/i })
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(mockedSubmitEvaluation).toHaveBeenCalledWith('interview-1', 'eval-draft-1')
      })

      // After submission, it renders "Đã gửi" and no editable form buttons
      await waitFor(() => {
        expect(screen.getByText('Đã gửi')).toBeInTheDocument()
      })
      expect(screen.queryByRole('button', { name: 'Lưu nháp' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Gửi đánh giá/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Xóa nháp/i })).not.toBeInTheDocument()
      confirmSpy.mockRestore()
    })

    it('renders colleague evaluations once own evaluation is submitted', async () => {
      mockedListEvaluations.mockResolvedValue([mySubmitted, colleagueEval])

      render(
        <MemoryRouter>
          <MyInterviewsPage />
        </MemoryRouter>,
      )

      await waitFor(() => {
        expect(screen.getByText('Đánh giá từ đồng nghiệp (1)')).toBeInTheDocument()
      })
      expect(screen.getByText('Architecture knowledge')).toBeInTheDocument()
      expect(screen.getByText('Must hire')).toBeInTheDocument()
    })
  })
})
