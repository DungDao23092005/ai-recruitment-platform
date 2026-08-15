import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { CandidateRecommendationCard } from './CandidateRecommendationCard'
import type { CandidateMatchRecommendation } from '@/types/ai'

const mockRecommendation: CandidateMatchRecommendation = {
  candidate_id: 'candidate-1',
  parsed_resume: {
    full_name: 'John Doe',
    email: 'john@example.com',
    phone: '+84123456789',
    title: 'Frontend Engineer',
    summary: 'React specialist.',
    total_years_experience: 5,
    skills: ['React', 'TypeScript', 'Node.js'],
    experiences: [],
    education: [],
    certifications: [],
    languages: ['English'],
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
}

describe('CandidateRecommendationCard', () => {
  it('renders the candidate full name', () => {
    render(<CandidateRecommendationCard recommendation={mockRecommendation} />)
    expect(screen.getByText('John Doe')).toBeInTheDocument()
  })

  it('renders the candidate title', () => {
    render(<CandidateRecommendationCard recommendation={mockRecommendation} />)
    expect(screen.getByText('Frontend Engineer')).toBeInTheDocument()
  })

  it('renders years of experience', () => {
    render(<CandidateRecommendationCard recommendation={mockRecommendation} />)
    expect(screen.getByText('Kinh nghiệm: 5 năm')).toBeInTheDocument()
  })

  it('renders the match score', () => {
    render(<CandidateRecommendationCard recommendation={mockRecommendation} />)
    expect(
      screen.getByLabelText('Điểm đối sánh 78 phần trăm'),
    ).toBeInTheDocument()
  })

  it('renders candidate skills', () => {
    render(<CandidateRecommendationCard recommendation={mockRecommendation} />)
    expect(screen.getAllByText('React').length).toBeGreaterThan(0)
    expect(screen.getByText('Node.js')).toBeInTheDocument()
  })

  it('renders skill gaps', () => {
    render(<CandidateRecommendationCard recommendation={mockRecommendation} />)
    expect(screen.getAllByText('GraphQL').length).toBeGreaterThan(0)
  })

  it('falls back gracefully when parsed resume is null', () => {
    render(
      <CandidateRecommendationCard
        recommendation={{ ...mockRecommendation, parsed_resume: null }}
      />,
    )
    expect(screen.getByText(/^Ứng viên /)).toBeInTheDocument()
  })

  it('omits experience when years are null', () => {
    render(
      <CandidateRecommendationCard
        recommendation={{
          ...mockRecommendation,
          parsed_resume: {
            ...mockRecommendation.parsed_resume!,
            total_years_experience: null,
          },
        }}
      />,
    )
    expect(screen.queryByText(/Kinh nghiệm:/)).not.toBeInTheDocument()
  })
})