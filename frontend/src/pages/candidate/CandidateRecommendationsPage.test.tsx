import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { CandidateRecommendationsPage } from './CandidateRecommendationsPage'
import * as aiApi from '@/api/ai'
import type { JobMatchRecommendation } from '@/types/ai'

const mockRecommendations: JobMatchRecommendation[] = [
  {
    job_id: 'job-1',
    parsed_job: {
      title: 'Senior Frontend Engineer',
      summary: 'Build modern web applications.',
      required_skills: ['React', 'TypeScript'],
      preferred_skills: [],
      minimum_years_experience: 4,
      education_level: null,
    },
    match_result: {
      overall_score: 82,
      cosine_similarity: 0.85,
      skill_coverage_score: 0.8,
      experience_match_score: 0.75,
      matching_skills: ['React', 'TypeScript'],
      skill_gap: ['GraphQL'],
      match_reasons: ['Strong skill overlap'],
    },
  },
  {
    job_id: 'job-2',
    parsed_job: {
      title: 'Backend Engineer',
      summary: 'Build scalable services.',
      required_skills: ['Python', 'FastAPI'],
      preferred_skills: [],
      minimum_years_experience: 3,
      education_level: null,
    },
    match_result: {
      overall_score: 91,
      cosine_similarity: 0.92,
      skill_coverage_score: 0.9,
      experience_match_score: 0.85,
      matching_skills: ['Python', 'FastAPI'],
      skill_gap: ['Docker'],
      match_reasons: ['Excellent overlap'],
    },
  },
]

vi.mock('@/api/ai', () => ({
  getJobRecommendations: vi.fn(),
  getCandidateRecommendations: vi.fn(),
  matchCandidateWithJob: vi.fn(),
  parseResume: vi.fn(),
}))

const mockedGetJobRecommendations = vi.mocked(aiApi.getJobRecommendations)

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/candidate/recommendations']}>
      <Routes>
        <Route
          path="/candidate/recommendations"
          element={<CandidateRecommendationsPage />}
        />
        <Route path="/candidate/cv-upload" element={<div>CV Upload</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('CandidateRecommendationsPage', () => {
  it('calls getJobRecommendations on mount', async () => {
    mockedGetJobRecommendations.mockResolvedValue(mockRecommendations)

    renderPage()

    await waitFor(() => {
      expect(mockedGetJobRecommendations).toHaveBeenCalledWith(10)
    })
  })

  it('shows the loading state while fetching', async () => {
    let resolve!: (value: JobMatchRecommendation[]) => void
    mockedGetJobRecommendations.mockReturnValue(
      new Promise((r) => {
        resolve = r
      }),
    )

    const { container } = renderPage()

    await waitFor(() => {
      expect(container.querySelector('.animate-pulse')).not.toBeNull()
    })

    resolve(mockRecommendations)
  })

  it('renders recommendation cards on success', async () => {
    mockedGetJobRecommendations.mockResolvedValue(mockRecommendations)

    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
      expect(screen.getByText('Backend Engineer')).toBeInTheDocument()
    })
  })

  it('sorts recommendations by score descending', async () => {
    mockedGetJobRecommendations.mockResolvedValue(mockRecommendations)

    renderPage()

    await waitFor(() => {
      const scoreBadges = screen
        .getAllByLabelText(/Điểm đối sánh \d+ phần trăm/i)
        .map((el) => Number(el.textContent?.replace('%', '')))
      expect(scoreBadges).toEqual([91, 82])
    })
  })

  it('shows the empty state with a CV upload CTA', async () => {
    mockedGetJobRecommendations.mockResolvedValue([])

    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText(
          /Chưa có gợi ý việc làm phù hợp/i,
        ),
      ).toBeInTheDocument()
    })

    const link = screen.getByRole('link', { name: /Tải lên CV/i })
    expect(link).toHaveAttribute('href', '/candidate/cv-upload')
  })

  it('shows a friendly error and retries', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Server error' } },
    })
    mockedGetJobRecommendations
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce(mockRecommendations)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
    })
  })
})