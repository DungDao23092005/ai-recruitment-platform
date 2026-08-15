import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { InterviewGeneratorPage } from './InterviewGeneratorPage'
import { getJobById } from '@/api/jobs'
import { generateInterviewQuestions } from '@/api/ai'
import type {
  GenerateInterviewQuestionsResponse,
  InterviewQuestion,
} from '@/types/ai'
import type { Job } from '@/types/job'

const job: Job = {
  id: 'job-1',
  company_id: 'company-1',
  company_name: null,
  title: 'Senior Frontend Engineer',
  description: 'Build modern web applications with React.',
  status: 'published',
  job_type: 'full_time',
  workplace_type: 'remote',
  location: 'Hanoi',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const question: InterviewQuestion = {
  question: 'Explain how you handle React state.',
  category: 'technical',
  difficulty: 'medium',
  target_skill_or_topic: 'React',
  evaluation_criteria: 'Demonstrates understanding of state management.',
  sample_answer_points: ['Mentions hooks'],
}

const response: GenerateInterviewQuestionsResponse = {
  job_title: 'Senior Frontend Engineer',
  candidate_title: null,
  total_questions: 1,
  questions: [question],
}

vi.mock('@/api/jobs', () => ({
  getJobById: vi.fn(),
}))

vi.mock('@/api/ai', () => ({
  generateInterviewQuestions: vi.fn(),
  getCandidateRecommendations: vi.fn(),
}))

const mockedGetJobById = vi.mocked(getJobById)
const mockedGenerate = vi.mocked(generateInterviewQuestions)

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/recruiter/jobs/job-1/interview']}>
      <Routes>
        <Route
          path="/recruiter/jobs/:id/interview"
          element={<InterviewGeneratorPage />}
        />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.resetAllMocks()
  mockedGetJobById.mockResolvedValue(job)
  mockedGenerate.mockResolvedValue(response)
})

describe('InterviewGeneratorPage', () => {
  it('renders job context', async () => {
    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText(/Senior Frontend Engineer/),
      ).toBeInTheDocument()
    })
  })

  it('renders configuration form', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Số câu hỏi')).toBeInTheDocument()
    })
    expect(screen.getByText('Độ khó')).toBeInTheDocument()
    expect(screen.getByText('Chủ đề tập trung')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /Tạo bộ câu hỏi/i }),
    ).toBeInTheDocument()
  })

  it('calls API with default configuration on submit', async () => {
    renderPage()

    await waitFor(() => {
      expect(mockedGetJobById).toHaveBeenCalled()
    })

    fireEvent.click(screen.getByRole('button', { name: /Tạo bộ câu hỏi/i }))

    await waitFor(() => {
      expect(mockedGenerate).toHaveBeenCalled()
    })
    expect(mockedGenerate.mock.calls[0][0]).toEqual({
      job: {
        title: 'Senior Frontend Engineer',
        summary: 'Build modern web applications with React.',
        required_skills: [],
        preferred_skills: [],
        minimum_years_experience: null,
        education_level: null,
      },
      num_questions: 5,
      difficulty: 'medium',
      focus_areas: [],
    })
  })

  it('passes selected configuration values', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Số câu hỏi')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: '10' }))
    fireEvent.click(screen.getByRole('button', { name: 'Khó' }))

    fireEvent.change(screen.getByLabelText('Thêm trọng tâm'), {
      target: { value: 'Performance testing' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Thêm' }))

    fireEvent.click(screen.getByRole('button', { name: /Tạo bộ câu hỏi/i }))

    await waitFor(() => {
      expect(mockedGenerate).toHaveBeenCalled()
    })
    const request = mockedGenerate.mock.calls[0][0]
    expect(request.num_questions).toBe(10)
    expect(request.difficulty).toBe('hard')
    expect(request.focus_areas).toEqual(['Performance testing'])
  })

  it('shows loading state while generating', async () => {
    mockedGenerate.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(response), 50)),
    )

    renderPage()

    await waitFor(() => {
      expect(mockedGetJobById).toHaveBeenCalled()
    })

    fireEvent.click(screen.getByRole('button', { name: /Tạo bộ câu hỏi/i }))

    await waitFor(() => {
      expect(screen.getByText('Đang tạo...')).toBeInTheDocument()
    })
  })

  it('renders generated questions on success', async () => {
    renderPage()

    await waitFor(() => {
      expect(mockedGetJobById).toHaveBeenCalled()
    })

    fireEvent.click(screen.getByRole('button', { name: /Tạo bộ câu hỏi/i }))

    await waitFor(() => {
      expect(
        screen.getByText('Explain how you handle React state.'),
      ).toBeInTheDocument()
    })
    expect(screen.getByText('Kỹ thuật')).toBeInTheDocument()
    expect(screen.getByText('Mentions hooks')).toBeInTheDocument()
  })

  it('shows error and retries', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 502, data: { detail: 'Gemini API request failed' } },
    })
    mockedGenerate
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce(response)

    renderPage()

    await waitFor(() => {
      expect(mockedGetJobById).toHaveBeenCalled()
    })

    fireEvent.click(screen.getByRole('button', { name: /Tạo bộ câu hỏi/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(
        screen.getByText('Explain how you handle React state.'),
      ).toBeInTheDocument()
    })
    expect(mockedGenerate).toHaveBeenCalledTimes(2)
  })

  it('copies questions to clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })

    renderPage()

    await waitFor(() => {
      expect(mockedGetJobById).toHaveBeenCalled()
    })

    fireEvent.click(screen.getByRole('button', { name: /Tạo bộ câu hỏi/i }))

    await waitFor(() => {
      expect(screen.getByText('Explain how you handle React state.')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Sao chép câu hỏi/i }))

    await waitFor(() => {
      expect(writeText).toHaveBeenCalled()
    })
    const copied = writeText.mock.calls[0][0] as string
    expect(copied).toContain('Senior Frontend Engineer')
    expect(copied).toContain('Explain how you handle React state.')
  })

  it('renders job error state when job is missing', async () => {
    mockedGetJobById.mockRejectedValue({
      response: { status: 404, data: { detail: 'Not found' } },
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('404')).toBeInTheDocument()
    })
  })
})
