import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { InterviewEvaluationList } from './InterviewEvaluationList'
import * as applicationsApi from '@/api/applications'
import { useAuth } from '@/contexts/AuthContext'
import type { Interview, InterviewEvaluation } from '@/types/application'

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

vi.mock('@/api/applications', () => ({
  listApplicationEvaluations: vi.fn(),
  createInterviewEvaluation: vi.fn(),
  updateInterviewEvaluation: vi.fn(),
  deleteInterviewEvaluation: vi.fn(),
}))

const mockedList = vi.mocked(applicationsApi.listApplicationEvaluations)
const mockedCreate = vi.mocked(applicationsApi.createInterviewEvaluation)
const mockedUseAuth = vi.mocked(useAuth)

function mockUser(id = 'user-1', role: 'recruiter' | 'admin' = 'recruiter') {
  mockedUseAuth.mockReturnValue({
    currentUser: {
      id,
      email: 'r@example.com',
      role,
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
}

const interview: Interview = {
  id: 'interview-1',
  application_id: 'app-1',
  scheduled_at: '2026-02-10T09:00:00Z',
  duration_minutes: 60,
  interview_type: 'technical',
  meeting_url: null,
  location: 'Online',
  notes: null,
  candidate_notes: null,
  status: 'scheduled',
  created_at: '2026-02-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
}

const myEvaluation: InterviewEvaluation = {
  id: 'eval-1',
  interview_id: 'interview-1',
  application_id: 'app-1',
  evaluator_id: 'user-1',
  rating: 4,
  strengths: 'Nắm chắc thuật toán',
  weaknesses: 'Thiếu kinh nghiệm hệ thống',
  recommendation: 'hire',
  notes: 'Nên mời vòng tiếp theo',
  created_at: '2026-02-11T00:00:00Z',
  updated_at: '2026-02-11T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUser()
})

describe('InterviewEvaluationList', () => {
  it('shows an empty state when there are no interviews', () => {
    render(<InterviewEvaluationList applicationId="app-1" interviews={[]} />)

    expect(screen.getByText('Chưa có buổi phỏng vấn')).toBeInTheDocument()
  })

  it('renders existing evaluations with rating and recommendation', async () => {
    mockedList.mockResolvedValue([myEvaluation])

    render(
      <InterviewEvaluationList applicationId="app-1" interviews={[interview]} />,
    )

    await waitFor(() => {
      expect(screen.getByText('Nắm chắc thuật toán')).toBeInTheDocument()
    })
    expect(screen.getByLabelText('Đánh giá 4/5')).toBeInTheDocument()
    expect(screen.getByText('Nên tuyển')).toBeInTheDocument()
    expect(screen.getByText('Bạn')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Thêm đánh giá' }),
    ).not.toBeInTheDocument()
  })

  it('submits a new scorecard', async () => {
    mockedList.mockResolvedValue([])
    mockedCreate.mockResolvedValue(myEvaluation)

    render(
      <InterviewEvaluationList applicationId="app-1" interviews={[interview]} />,
    )

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'Thêm đánh giá' }),
      ).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Thêm đánh giá' }))
    fireEvent.change(screen.getByLabelText('Điểm đánh giá'), {
      target: { value: '4' },
    })
    fireEvent.change(screen.getByLabelText('Đề xuất'), {
      target: { value: 'hire' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Gửi đánh giá' }))

    await waitFor(() => {
      expect(mockedCreate).toHaveBeenCalledWith('app-1', 'interview-1', {
        rating: 4,
        strengths: null,
        weaknesses: null,
        recommendation: 'hire',
        notes: null,
      })
    })
  })

  it('shows a conflict message when a scorecard already exists', async () => {
    mockedList.mockResolvedValue([])
    const error = new Error('Conflict')
    Object.assign(error, { response: { status: 409 } })
    mockedCreate.mockRejectedValue(error)

    render(
      <InterviewEvaluationList applicationId="app-1" interviews={[interview]} />,
    )

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'Thêm đánh giá' }),
      ).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Thêm đánh giá' }))
    fireEvent.click(screen.getByRole('button', { name: 'Gửi đánh giá' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Bạn đã đánh giá buổi phỏng vấn này',
      )
    })
  })
})
