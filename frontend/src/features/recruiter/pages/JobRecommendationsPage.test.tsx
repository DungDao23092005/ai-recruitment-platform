import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { JobRecommendationsPage } from './JobRecommendationsPage'
import * as jobsApi from '@/api/jobs'
import * as aiApi from '@/api/ai'
import type { CandidateMatchRecommendation } from '@/types/ai'
import type { Job } from '@/types/job'

const mockJob: Job = {
  id: 'job-1',
  company_id: 'company-1',
  company_name: null,
  title: 'Senior Frontend Engineer',
  description: 'Build modern web applications with React.',
  status: 'published',
  job_type: 'full_time',
  workplace_type: 'remote',
  location: 'Ho Chi Minh City',
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-01-15T00:00:00Z',
}

const mockRecommendations: CandidateMatchRecommendation[] = [
  {
    candidate_id: 'candidate-1',
    parsed_resume: {
      full_name: 'John Doe',
      email: 'john@example.com',
      phone: null,
      title: 'Frontend Engineer',
      summary: null,
      total_years_experience: 5,
      skills: ['React', 'TypeScript'],
      experiences: [],
      education: [],
      certifications: [],
      languages: [],
    },
    match_result: {
      overall_score: 78,
      cosine_similarity: 0.8,
      skill_coverage_score: 0.75,
      experience_match_score: 0.7,
      matching_skills: ['React', 'TypeScript'],
      skill_gap: ['GraphQL'],
      match_reasons: ['Strong skill overlap'],
    },
  },
  {
    candidate_id: 'candidate-2',
    parsed_resume: {
      full_name: 'Jane Smith',
      email: 'jane@example.com',
      phone: null,
      title: 'Senior Frontend Engineer',
      summary: null,
      total_years_experience: 8,
      skills: ['React', 'Vue'],
      experiences: [],
      education: [],
      certifications: [],
      languages: [],
    },
    match_result: {
      overall_score: 88,
      cosine_similarity: 0.9,
      skill_coverage_score: 0.85,
      experience_match_score: 0.9,
      matching_skills: ['React'],
      skill_gap: [],
      match_reasons: ['Excellent experience'],
    },
  },
]

vi.mock('@/api/jobs', () => ({
  getJobs: vi.fn(),
  getMyJobById: vi.fn(),
}))

vi.mock('@/api/ai', () => ({
  getJobRecommendations: vi.fn(),
  getCandidateRecommendations: vi.fn(),
  matchCandidateWithJob: vi.fn(),
  parseResume: vi.fn(),
}))

const mockedGetMyJobById = vi.mocked(jobsApi.getMyJobById)
const mockedGetCandidateRecommendations = vi.mocked(
  aiApi.getCandidateRecommendations,
)

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/recruiter/jobs/job-1/recommendations']}>
      <Routes>
        <Route
          path="/recruiter/jobs/:id/recommendations"
          element={<JobRecommendationsPage />}
        />
        <Route path="/recruiter/jobs" element={<div>Jobs Page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('JobRecommendationsPage', () => {
  it('fetches job and candidate recommendations with the job id', async () => {
    mockedGetMyJobById.mockResolvedValue(mockJob)
    mockedGetCandidateRecommendations.mockResolvedValue(mockRecommendations)

    renderPage()

    await waitFor(() => {
      expect(mockedGetMyJobById).toHaveBeenCalledWith('job-1')
      expect(mockedGetCandidateRecommendations).toHaveBeenCalledWith(
        'job-1',
        10,
      )
    })
  })

  it('shows the loading state while fetching', async () => {
    let resolveJob!: (value: Job) => void
    let resolveRecs!: (value: CandidateMatchRecommendation[]) => void
    mockedGetMyJobById.mockReturnValue(
      new Promise((r) => {
        resolveJob = r
      }),
    )
    mockedGetCandidateRecommendations.mockReturnValue(
      new Promise((r) => {
        resolveRecs = r
      }),
    )

    const { container } = renderPage()

    await waitFor(() => {
      expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
    })

    resolveJob(mockJob)
    resolveRecs(mockRecommendations)
  })

  it('renders candidate recommendation cards', async () => {
    mockedGetMyJobById.mockResolvedValue(mockJob)
    mockedGetCandidateRecommendations.mockResolvedValue(mockRecommendations)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('John Doe')).toBeInTheDocument()
      expect(screen.getByText('Jane Smith')).toBeInTheDocument()
    })
  })

  it('renders the job title in the description', async () => {
    mockedGetMyJobById.mockResolvedValue(mockJob)
    mockedGetCandidateRecommendations.mockResolvedValue(mockRecommendations)

    renderPage()

    await waitFor(() => {
      expect(
        screen.getAllByText(/Senior Frontend Engineer/).length,
      ).toBeGreaterThan(0)
    })
  })

  it('shows the empty state when there are no candidates', async () => {
    mockedGetMyJobById.mockResolvedValue(mockJob)
    mockedGetCandidateRecommendations.mockResolvedValue([])

    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText('Chưa có ứng viên gợi ý'),
      ).toBeInTheDocument()
    })
  })

  it('shows an error and retries', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Server error' } },
    })
    mockedGetMyJobById.mockResolvedValue(mockJob)
    mockedGetCandidateRecommendations
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce(mockRecommendations)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(screen.getByText('John Doe')).toBeInTheDocument()
    })
  })

it('shows 404 when job is not found', async () => {
    const error = new Error('Not Found')
    Object.assign(error, { response: { status: 404 } })
    mockedGetMyJobById.mockRejectedValue(error)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('404')).toBeInTheDocument()
      expect(screen.getByText('Không tìm thấy tin tuyển dụng')).toBeInTheDocument()
    })
  })

  it('renders own draft job', async () => {
    const draftJob: Job = { ...mockJob, status: 'draft' }
    mockedGetMyJobById.mockResolvedValue(draftJob)
    mockedGetCandidateRecommendations.mockResolvedValue(mockRecommendations)

    renderPage()

    await waitFor(() => {
      expect(mockedGetMyJobById).toHaveBeenCalledWith('job-1')
      expect(
        screen.getByText(/gợi ý cho tin tuyển dụng "Senior Frontend Engineer"/),
      ).toBeInTheDocument()
      expect(screen.getByText('John Doe')).toBeInTheDocument()
    })
  })
})
