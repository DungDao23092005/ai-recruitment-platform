import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

    it('opens in-app confirmation modal without calling window.confirm or submission API', async () => {
      const confirmSpy = vi.spyOn(window, 'confirm')
      mockedListEvaluations.mockResolvedValue([myDraft])

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

      const dialog = screen.getByRole('dialog', { name: 'Xác nhận gửi đánh giá' })
      expect(dialog).toBeInTheDocument()
      expect(within(dialog).getByText('Xác nhận gửi đánh giá')).toBeInTheDocument()
      expect(
        within(dialog).getByText(
          'Bạn đã hoàn tất đánh giá ứng viên? Vui lòng kiểm tra điểm số, nhận xét và đề xuất tuyển dụng trước khi gửi.',
        ),
      ).toBeInTheDocument()
      expect(
        within(dialog).getByText(
          'Sau khi gửi, phiếu đánh giá sẽ không thể chỉnh sửa hoặc xóa.',
        ),
      ).toBeInTheDocument()
      expect(within(dialog).getByText('4 / 5')).toBeInTheDocument()
      expect(within(dialog).getByText('Nên tuyển')).toBeInTheDocument()

      expect(confirmSpy).not.toHaveBeenCalled()
      expect(mockedSubmitEvaluation).not.toHaveBeenCalled()
      expect(mockedUpdateEvaluation).not.toHaveBeenCalled()
      expect(mockedCreateEvaluation).not.toHaveBeenCalled()

      confirmSpy.mockRestore()
    })

    it('shows fallback text when no recommendation is selected in draft', async () => {
      mockedListEvaluations.mockResolvedValue([
        { ...myDraft, recommendation: null },
      ])

      render(
        <MemoryRouter>
          <MyInterviewsPage />
        </MemoryRouter>,
      )

      await waitFor(() => {
        expect(screen.getByText('Bản nháp')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('button', { name: /Gửi đánh giá/i }))

      const dialog = screen.getByRole('dialog', { name: 'Xác nhận gửi đánh giá' })
      expect(within(dialog).getByText('Chưa có đề xuất')).toBeInTheDocument()
    })

    it('cancels confirmation via "Quay lại" without submitting and preserves draft inputs', async () => {
      const confirmSpy = vi.spyOn(window, 'confirm')
      mockedListEvaluations.mockResolvedValue([myDraft])

      render(
        <MemoryRouter>
          <MyInterviewsPage />
        </MemoryRouter>,
      )

      await waitFor(() => {
        expect(screen.getByText('Bản nháp')).toBeInTheDocument()
      })

      fireEvent.change(screen.getByLabelText('Ghi chú'), {
        target: { value: 'Updated note before cancel' },
      })

      fireEvent.click(screen.getByRole('button', { name: /Gửi đánh giá/i }))

      const dialog = screen.getByRole('dialog', { name: 'Xác nhận gửi đánh giá' })
      expect(dialog).toBeInTheDocument()

      const backButton = within(dialog).getByRole('button', { name: 'Quay lại' })
      fireEvent.click(backButton)

      expect(screen.queryByRole('dialog', { name: 'Xác nhận gửi đánh giá' })).not.toBeInTheDocument()
      expect(mockedSubmitEvaluation).not.toHaveBeenCalled()
      expect(confirmSpy).not.toHaveBeenCalled()
      expect(screen.getByLabelText('Ghi chú')).toHaveValue('Updated note before cancel')

      confirmSpy.mockRestore()
    })

    it('cancels confirmation via Escape key without submitting', async () => {
      const confirmSpy = vi.spyOn(window, 'confirm')
      mockedListEvaluations.mockResolvedValue([myDraft])

      render(
        <MemoryRouter>
          <MyInterviewsPage />
        </MemoryRouter>,
      )

      await waitFor(() => {
        expect(screen.getByText('Bản nháp')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('button', { name: /Gửi đánh giá/i }))

      expect(screen.getByRole('dialog', { name: 'Xác nhận gửi đánh giá' })).toBeInTheDocument()

      fireEvent.keyDown(document, { key: 'Escape' })

      expect(screen.queryByRole('dialog', { name: 'Xác nhận gửi đánh giá' })).not.toBeInTheDocument()
      expect(mockedSubmitEvaluation).not.toHaveBeenCalled()
      expect(confirmSpy).not.toHaveBeenCalled()

      confirmSpy.mockRestore()
    })

    it('submits evaluation via in-app dialog, closes modal, and enforces immutability', async () => {
      const confirmSpy = vi.spyOn(window, 'confirm')
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

      const submitFormButton = screen.getByRole('button', { name: /Gửi đánh giá/i })
      fireEvent.click(submitFormButton)

      const dialog = screen.getByRole('dialog', { name: 'Xác nhận gửi đánh giá' })
      expect(dialog).toBeInTheDocument()

      const confirmButton = within(dialog).getByRole('button', { name: /Gửi đánh giá/i })
      fireEvent.click(confirmButton)

      await waitFor(() => {
        expect(mockedUpdateEvaluation).toHaveBeenCalledWith('interview-1', 'eval-draft-1', {
          rating: 4,
          recommendation: 'hire',
          strengths: 'Strong algorithms',
          weaknesses: 'Needs async review',
          notes: 'Good candidate overall',
        })
        expect(mockedSubmitEvaluation).toHaveBeenCalledWith('interview-1', 'eval-draft-1')
      })

      await waitFor(() => {
        expect(screen.queryByRole('dialog', { name: 'Xác nhận gửi đánh giá' })).not.toBeInTheDocument()
        expect(screen.getByText('Đã gửi')).toBeInTheDocument()
      })
      expect(screen.queryByRole('button', { name: 'Lưu nháp' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Gửi đánh giá/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Xóa nháp/i })).not.toBeInTheDocument()
      expect(confirmSpy).not.toHaveBeenCalled()

      confirmSpy.mockRestore()
    })

    it('submits evaluation for brand new scorecard (creates then submits)', async () => {
      const confirmSpy = vi.spyOn(window, 'confirm')
      mockedListEvaluations
        .mockResolvedValueOnce([])
        .mockResolvedValue([mySubmitted])
      mockedCreateEvaluation.mockResolvedValue(myDraft)
      mockedSubmitEvaluation.mockResolvedValue(mySubmitted)

      render(
        <MemoryRouter>
          <MyInterviewsPage />
        </MemoryRouter>,
      )

      await waitFor(() => {
        expect(mockedListEvaluations).toHaveBeenCalledWith('interview-1')
      })

      fireEvent.change(await screen.findByLabelText('Điểm đánh giá'), {
        target: { value: '4' },
      })
      fireEvent.change(screen.getByLabelText('Đề xuất'), {
        target: { value: 'hire' },
      })

      fireEvent.click(screen.getByRole('button', { name: /Gửi đánh giá/i }))

      const dialog = screen.getByRole('dialog', { name: 'Xác nhận gửi đánh giá' })
      expect(dialog).toBeInTheDocument()

      fireEvent.click(within(dialog).getByRole('button', { name: /Gửi đánh giá/i }))

      await waitFor(() => {
        expect(mockedCreateEvaluation).toHaveBeenCalledWith('interview-1', {
          rating: 4,
          recommendation: 'hire',
          strengths: null,
          weaknesses: null,
          notes: null,
        })
        expect(mockedSubmitEvaluation).toHaveBeenCalledWith('interview-1', 'eval-draft-1')
      })

      await waitFor(() => {
        expect(screen.getByText('Đã gửi')).toBeInTheDocument()
      })
      expect(confirmSpy).not.toHaveBeenCalled()

      confirmSpy.mockRestore()
    })

    it('disables dialog actions while submission is pending', async () => {
      let resolveSubmit!: (val: InterviewEvaluation) => void
      const submitPromise = new Promise<InterviewEvaluation>((r) => {
        resolveSubmit = r
      })
      mockedListEvaluations.mockResolvedValue([myDraft])
      mockedUpdateEvaluation.mockResolvedValue(myDraft)
      mockedSubmitEvaluation.mockReturnValue(submitPromise)

      render(
        <MemoryRouter>
          <MyInterviewsPage />
        </MemoryRouter>,
      )

      await waitFor(() => {
        expect(screen.getByText('Bản nháp')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('button', { name: /Gửi đánh giá/i }))

      const dialog = screen.getByRole('dialog', { name: 'Xác nhận gửi đánh giá' })
      const confirmBtn = within(dialog).getByRole('button', { name: /Gửi đánh giá/i })
      const backBtn = within(dialog).getByRole('button', { name: 'Quay lại' })

      fireEvent.click(confirmBtn)

      await waitFor(() => {
        expect(confirmBtn).toBeDisabled()
        expect(backBtn).toBeDisabled()
      })

      // Try closing via Escape while pending - should not close
      fireEvent.keyDown(document, { key: 'Escape' })
      expect(dialog).toBeInTheDocument()

      await act(async () => {
        resolveSubmit(mySubmitted)
      })
    })

    it('displays accessible error and preserves draft on submission failure, allowing retry', async () => {
      const confirmSpy = vi.spyOn(window, 'confirm')
      mockedListEvaluations.mockResolvedValue([myDraft])
      const apiError = new Error('Submission network error')
      mockedUpdateEvaluation.mockResolvedValue(myDraft)
      mockedSubmitEvaluation
        .mockRejectedValueOnce(apiError)
        .mockResolvedValueOnce(mySubmitted)

      render(
        <MemoryRouter>
          <MyInterviewsPage />
        </MemoryRouter>,
      )

      await waitFor(() => {
        expect(screen.getByText('Bản nháp')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('button', { name: /Gửi đánh giá/i }))

      const dialog = screen.getByRole('dialog', { name: 'Xác nhận gửi đánh giá' })
      const confirmBtn = within(dialog).getByRole('button', { name: /Gửi đánh giá/i })
      fireEvent.click(confirmBtn)

      await waitFor(() => {
        expect(within(dialog).getByRole('alert')).toBeInTheDocument()
      })
      expect(dialog).toBeInTheDocument()
      expect(confirmBtn).toBeEnabled()

      // Retry submission
      fireEvent.click(confirmBtn)

      await waitFor(() => {
        expect(mockedSubmitEvaluation).toHaveBeenCalledTimes(2)
      })

      expect(confirmSpy).not.toHaveBeenCalled()
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
