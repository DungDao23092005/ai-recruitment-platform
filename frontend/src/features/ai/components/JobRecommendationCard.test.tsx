import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { JobRecommendationCard } from './JobRecommendationCard'
import type { JobMatchRecommendation } from '@/types/ai'

const mockRecommendation: JobMatchRecommendation = {
  job_id: 'job-1',
  parsed_job: {
    title: 'Senior Frontend Engineer',
    summary: 'Build modern web applications with React.',
    required_skills: ['React', 'TypeScript'],
    preferred_skills: ['GraphQL'],
    minimum_years_experience: 4,
    education_level: 'Bachelor',
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
}

function renderCard() {
  return render(
    <MemoryRouter>
      <JobRecommendationCard recommendation={mockRecommendation} />
    </MemoryRouter>,
  )
}

describe('JobRecommendationCard', () => {
  it('renders the job title', () => {
    renderCard()
    expect(
      screen.getByText('Senior Frontend Engineer'),
    ).toBeInTheDocument()
  })

  it('renders the job summary', () => {
    renderCard()
    expect(
      screen.getByText('Build modern web applications with React.'),
    ).toBeInTheDocument()
  })

  it('renders the match score', () => {
    renderCard()
    expect(
      screen.getByLabelText('Match score 82 percent'),
    ).toBeInTheDocument()
  })

  it('renders matching skills', () => {
    renderCard()
    expect(screen.getAllByText('React').length).toBeGreaterThan(0)
    expect(screen.getAllByText('TypeScript').length).toBeGreaterThan(0)
  })

  it('renders skill gaps', () => {
    renderCard()
    expect(screen.getAllByText('GraphQL').length).toBeGreaterThan(0)
  })

  it('renders a CTA linking to the job detail route', () => {
    renderCard()
    const link = screen.getByRole('link', {
      name: /Xem chi tiết Job & Nộp đơn/i,
    })
    expect(link).toHaveAttribute('href', '/jobs/job-1')
  })

  it('falls back to an untitled role when parsed job is null', () => {
    render(
      <MemoryRouter>
        <JobRecommendationCard
          recommendation={{ ...mockRecommendation, parsed_job: null }}
        />
      </MemoryRouter>,
    )
    expect(screen.getByText('Untitled role')).toBeInTheDocument()
  })
})