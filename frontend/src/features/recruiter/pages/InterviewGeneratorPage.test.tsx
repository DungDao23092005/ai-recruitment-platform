import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { InterviewGeneratorPage } from './InterviewGeneratorPage'
import { getMyJobById } from '@/api/jobs'
import { getApplicationDetail } from '@/api/applications'
import { getApplicationMatch } from '@/api/applications'
import { generateInterviewQuestions } from '@/api/ai'
import type {
  GenerateInterviewQuestionsResponse,
  InterviewQuestion,
  MatchResult,
} from '@/types/ai'
import type { Job } from '@/types/job'
import type { ApplicationDetail } from '@/types/application'

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
  getMyJobById: vi.fn(),
}))

vi.mock('@/api/applications', () => ({
  getApplicationDetail: vi.fn(),
  getApplicationMatch: vi.fn(),
}))

vi.mock('@/api/ai', () => ({
  generateInterviewQuestions: vi.fn(),
  getCandidateRecommendations: vi.fn(),
}))

const mockedGetMyJobById = vi.mocked(getMyJobById)
const mockedGetApplicationDetail = vi.mocked(getApplicationDetail)
const mockedGetApplicationMatch = vi.mocked(getApplicationMatch)
const mockedGenerate = vi.mocked(generateInterviewQuestions)

function renderPage(searchParams?: string) {
  return render(
    <MemoryRouter initialEntries={[`/recruiter/jobs/job-1/interview${searchParams ? `?${searchParams}` : ''}`]}>
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
  mockedGetMyJobById.mockResolvedValue(job)
  mockedGetApplicationDetail.mockResolvedValue({
    id: 'app-1',
    candidate_id: 'cand-1',
    job_id: 'job-1',
    job_title: 'Senior Frontend Engineer',
    company_name: 'Test Company',
    status: 'applied',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    candidate: {
      id: 'cand-1',
      full_name: 'Test Candidate',
      title: 'Engineer',
    },
    resume: {
      id: 'res-1',
      candidate_id: 'cand-1',
      title: 'cv.pdf',
      is_primary: true,
      parsed_data: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    parsed_job: {
      title: 'Senior Frontend Engineer',
      summary: 'Build modern web applications with React.',
      required_skills: ['React', 'TypeScript'],
      preferred_skills: [],
      minimum_years_experience: 3,
      education_level: 'Bachelor',
    },
    interviews: [],
  })
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
      expect(mockedGetMyJobById).toHaveBeenCalled()
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
      candidate: null,
      match_result: null,
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
      expect(mockedGetMyJobById).toHaveBeenCalled()
    })

    fireEvent.click(screen.getByRole('button', { name: /Tạo bộ câu hỏi/i }))

    await waitFor(() => {
      expect(screen.getByText('Đang tạo...')).toBeInTheDocument()
    })
  })

  it('renders generated questions on success', async () => {
    renderPage()

    await waitFor(() => {
      expect(mockedGetMyJobById).toHaveBeenCalled()
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
      expect(mockedGetMyJobById).toHaveBeenCalled()
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
      expect(mockedGetMyJobById).toHaveBeenCalled()
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
    mockedGetMyJobById.mockRejectedValue({
      response: { status: 404, data: { detail: 'Not found' } },
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('404')).toBeInTheDocument()
    })
  })

  it('renders own draft job', async () => {
    const draftJob: Job = { ...job, status: 'draft' }
    mockedGetMyJobById.mockResolvedValue(draftJob)

    renderPage()

    await waitFor(() => {
      expect(mockedGetMyJobById).toHaveBeenCalledWith('job-1')
      expect(
        screen.getByText(/Tạo câu hỏi phỏng vấn cho tin tuyển dụng "Senior Frontend Engineer"/),
      ).toBeInTheDocument()
    })
  })

  it('retries the job request after a failure', async () => {
    mockedGetMyJobById
      .mockRejectedValueOnce({
        response: { status: 500, data: { detail: 'Server error' } },
      })
      .mockResolvedValueOnce(job)

    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Thử lại/i })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(mockedGetMyJobById).toHaveBeenCalledTimes(2)
      expect(
        screen.getByText(/Tạo câu hỏi phỏng vấn cho tin tuyển dụng "Senior Frontend Engineer"/),
      ).toBeInTheDocument()
    })
  })

  describe('Personalized mode (with applicationId)', () => {
    // Use void to suppress unused variable warning - the value is used in renderPageWithAppId
    const _applicationId = 'app-123'
    void _applicationId

    const mockApplication: ApplicationDetail = {
      id: 'app-123',
      candidate_id: 'cand-1',
      job_id: 'job-1',
      job_title: 'Senior Frontend Engineer',
      company_name: 'Test Company',
      status: 'applied',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      candidate: {
        id: 'cand-1',
        full_name: 'Nguyễn Văn A',
        title: 'Senior Engineer',
      },
      resume: {
        id: 'res-1',
        candidate_id: 'cand-1',
        title: 'cv.pdf',
        is_primary: true,
        parsed_data: {
          full_name: 'Nguyễn Văn A',
          email: 'test@example.com',
          phone: '0901234567',
          title: 'Senior Engineer',
          summary: 'Experienced engineer.',
          total_years_experience: 5,
          skills: ['React', 'TypeScript', 'Node.js'],
          experiences: [],
          education: [],
          certifications: [],
          languages: [],
        },
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      parsed_job: {
        title: 'Senior Frontend Engineer',
        summary: 'Build modern web applications with React.',
        required_skills: ['React', 'TypeScript'],
        preferred_skills: [],
        minimum_years_experience: 3,
        education_level: 'Bachelor',
      },
      interviews: [],
    }

    const mockMatch: MatchResult = {
      overall_score: 85,
      cosine_similarity: 0.9,
      skill_coverage_score: 0.8,
      experience_match_score: 0.95,
      matching_skills: ['React', 'TypeScript'],
      skill_gap: ['GraphQL'],
      match_reasons: ['Strong React skills'],
    }

    function renderPageWithAppId() {
      return renderPage(`applicationId=app-123`)
    }

    beforeEach(() => {
      vi.resetAllMocks()
      mockedGetMyJobById.mockResolvedValue(job)
      mockedGetApplicationDetail.mockResolvedValue(mockApplication)
      mockedGetApplicationMatch.mockResolvedValue(mockMatch)
      mockedGenerate.mockResolvedValue(response)
    })

    it('fetches application detail and match when applicationId provided', async () => {
      renderPageWithAppId()

      await waitFor(() => {
        expect(mockedGetApplicationDetail).toHaveBeenCalledWith('app-123')
        expect(mockedGetApplicationMatch).toHaveBeenCalledWith('app-123')
      })

      await waitFor(() => {
        expect(screen.getByText('Chế độ cá nhân hóa đang hoạt động')).toBeInTheDocument()
      })
    })

    it('displays candidate name in personalized banner', async () => {
      renderPageWithAppId()

      await waitFor(() => {
        expect(screen.getByText('Chế độ cá nhân hóa đang hoạt động')).toBeInTheDocument()
      })
      // Use getAllByText and check the one in the personalized banner card
      const names = screen.getAllByText('Nguyễn Văn A')
      expect(names.length).toBeGreaterThan(0)
      // The name should appear in the personalized banner card
      const bannerCard = screen.getByText('Chế độ cá nhân hóa đang hoạt động').closest('[class*="border-primary"]')
      expect(bannerCard).toBeInTheDocument()
      expect(bannerCard).toHaveTextContent('Nguyễn Văn A')
    })

    it('calls API with candidate and match_result in personalized mode', async () => {
      renderPageWithAppId()

      await waitFor(() => {
        expect(screen.getByText('Chế độ cá nhân hóa đang hoạt động')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('button', { name: /Tạo bộ câu hỏi/i }))

      await waitFor(() => {
        expect(mockedGenerate).toHaveBeenCalled()
      })

      const request = mockedGenerate.mock.calls[0][0]
      expect(request.candidate).toEqual({
        full_name: 'Nguyễn Văn A',
        email: 'test@example.com',
        phone: '0901234567',
        title: 'Senior Engineer',
        summary: 'Experienced engineer.',
        total_years_experience: 5,
        skills: ['React', 'TypeScript', 'Node.js'],
        experiences: [],
        education: [],
        certifications: [],
        languages: [],
      })
      expect(request.match_result).toEqual(mockMatch)
    })

    it('handles missing resume gracefully', async () => {
      mockedGetApplicationDetail.mockResolvedValue({
        ...mockApplication,
        resume: { ...mockApplication.resume!, parsed_data: null },
      })

      renderPageWithAppId()

      await waitFor(() => {
        expect(screen.getByText('Chưa có CV được phân tích')).toBeInTheDocument()
      })
    })

    it('handles match fetch failure gracefully', async () => {
      mockedGetApplicationMatch.mockRejectedValue(new Error('Match service unavailable'))

      renderPageWithAppId()

      await waitFor(() => {
        expect(screen.getByText('Chưa có điểm khớp AI')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('button', { name: /Tạo bộ câu hỏi/i }))

      await waitFor(() => {
        expect(mockedGenerate).toHaveBeenCalled()
      })

      const request = mockedGenerate.mock.calls[0][0]
      expect(request.match_result).toBeNull()
      expect(request.candidate).not.toBeNull()
    })

    it('falls back to generic mode when application fetch fails', async () => {
      mockedGetApplicationDetail.mockRejectedValue({
        response: { status: 404, data: { detail: 'Not found' } },
      })

      renderPageWithAppId()

      await waitFor(() => {
        expect(screen.getByText('Không thể tải hồ sơ ứng viên. Đang chuyển sang chế độ chung.')).toBeInTheDocument()
      })

      // Should not show personalized banner
      expect(screen.queryByText('Chế độ cá nhân hóa đang hoạt động')).not.toBeInTheDocument()
    })

    it('falls back to generic mode when application access is forbidden', async () => {
      mockedGetApplicationDetail.mockRejectedValue({
        response: { status: 403, data: { detail: 'Forbidden' } },
      })

      renderPageWithAppId()

      await waitFor(() => {
        expect(screen.getByText('Không thể tải hồ sơ ứng viên. Đang chuyển sang chế độ chung.')).toBeInTheDocument()
      })
    })

    it('continues without match when match fetch fails', async () => {
      mockedGetApplicationMatch.mockRejectedValue(new Error('Match service unavailable'))

      renderPageWithAppId()

      await waitFor(() => {
        expect(screen.getByText('Chưa có điểm khớp AI')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('button', { name: /Tạo bộ câu hỏi/i }))

      await waitFor(() => {
        expect(mockedGenerate).toHaveBeenCalled()
      })

      const request = mockedGenerate.mock.calls[0][0]
      expect(request.match_result).toBeNull()
      expect(request.candidate).not.toBeNull()
    })

    it('does not leak candidate data when unauthorized', async () => {
      mockedGetApplicationDetail.mockRejectedValue({
        response: { status: 403, data: { detail: 'Forbidden' } },
      })

      renderPageWithAppId()

      await waitFor(() => {
        expect(screen.getByText('Không thể tải hồ sơ ứng viên. Đang chuyển sang chế độ chung.')).toBeInTheDocument()
      })

      // Should not expose any candidate data
      expect(screen.queryByText('Nguyễn Văn A')).not.toBeInTheDocument()
      expect(screen.queryByText('test@example.com')).not.toBeInTheDocument()
    })
  })
})
